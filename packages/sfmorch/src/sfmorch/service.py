"""The tool surface, as plain Python.

Every MCP tool is a thin call into a method here. Keeping the logic
framework-independent means the surface is testable without MCP transport, and a
change in the SDK touches one adapter file rather than nineteen tools.

Return shapes are chosen for an agent reading them, not for completeness. A run
returns its metrics and diagnostics inline, because the alternative is a second
round trip on every single step and the metrics are the whole reason to look.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sfmkit import ArtifactStore

from .errors import ModuleNotFound, OrchestratorError
from .jobs import JobHandle, JobManager
from .lineage import compare as _compare
from .orchestrator import Orchestrator
from .registry import ModuleRegistry
from .scaffold import ScaffoldRequest, scaffold_module, to_slug

DEFAULT_INLINE_WAIT = 20.0

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
IMAGE_SUFFIXES = frozenset(MIME_TYPES)

# A ceiling on what one call will hand back. Generous for a contact sheet, which
# is the case this exists for, and small enough that a full-resolution frame is a
# deliberate choice rather than an accident.
MAX_IMAGE_BYTES = 8 * 2**20

SCENE_TYPE = "scene/v1"
ANALYSIS_TYPE = "scene_analysis/v1"

# The guide that translates step 2's numbers into the adjectives the stage files
# are written in. Named here rather than inlined so the prose can be revised
# without touching the orchestrator, which is the same arrangement every other
# curated document has.
PLANNING_GUIDE = "plan/scene_to_pipeline"

# `dense` is deliberately absent. A first plan reaches a sparse model; dense
# reconstruction is a separate decision made after one exists, and carrying its
# family file into every planning call costs context for nothing. Pass `stages`
# explicitly to include it.
PLANNING_STAGES = (
    "detection", "matching", "tracking", "pose", "sparse", "optimization",
)

# How many elements of a per-frame or per-pair series `plan_brief` will hand over
# whole. Every metric an analysis module reports is a median or a p75 over the
# set, and a median cannot answer "which frame" or "which pair" -- which is what
# the advice attached to those metrics needs. Above the cap the series is
# summarised rather than dropped, because a 400-image scene is exactly the one
# where the extremes matter and exactly the one that must not blow up the reply.
SERIES_MAX = 200

# How many extremes survive the summary at each end.
SERIES_EXTREMES = 8

PLAN_SHAPE = {
    "sections": [
        "SCENE - one line: what it is, from the description's `overall`",
        "WHAT IS HARD - the two or three things that will actually cost you",
        "DETECTION - module + why, or 'skipped' + why",
        "MATCHING - module + pairing + why",
        "TRACKING - provisional; name what the matcher's output will decide",
        "POSE - module + why, naming any degeneracy reading",
        "SPARSE - provisional, but COMMIT to a module anyway. The metrics that "
        "settle this stage (long_track_fraction, track_survival_5) are produced "
        "two stages later, so the choice cannot be derived here - and the "
        "conventional answer is right most of the time, which makes 'undecidable' "
        "the less useful reply. Name the module, then name the reading that would "
        "overturn it, so the line fills itself in once tracking has run",
        "OPTIMIZATION - module + why",
        "WATCH - the metric to judge this scene on, often not the obvious one",
        "ESCAPE - what to try if it fails, and the observation that would trigger it",
        "UNSUPPORTED - what matters here that nothing in the brief backs, and "
        "what would settle it. This section exists because two of the first five "
        "plans needed a second WATCH for hazards no metric reaches; that is this, "
        "and it should be prompted rather than improvised.",
    ],
    "rules": [
        "This is an INITIAL plan, not a commitment - and not a lock. Every stage "
        "may be revised by what the stage before it measures; the point of "
        "writing it down is to know WHICH observation would change your mind, "
        "not to bind the pipeline.",
        "A provisional stage still gets a module. TRACKING cannot be settled "
        "until the matcher has run, because detector-based and detector-free "
        "matchers build tracks differently, and SPARSE cannot be settled until "
        "tracking reports. Neither is a reason to leave the line blank: name the "
        "default and name what would overturn it.",
        "Every stage gets a line, including when the answer is the cheap default. "
        "'SIFT, because nothing here is hard' is a real answer.",
        "Name the number. 'texture_density 475, seven times below the next lowest "
        "scene' beats 'low texture'.",
        "Where nothing supports a choice, say so rather than inventing a reason - "
        "in the stage line if it changes the choice, in UNSUPPORTED if it does not.",
        "Do not restate the metrics as prose - the reader has them. Say what they "
        "mean together.",
    ],
}


# The second solve's windows, and what triggers it. The default width is where
# the benefit of widening had levelled off on the captures measured. The last
# resort bought a little more on a few and costs more, so it runs only when the
# solve at the default was not kept.
WINDOW_PARAM = "local_ba_window"
ESCAPE_METRIC = "escaped_points"
SECOND_SOLVE_WINDOW = 28
LAST_RESORT_WINDOW = 40
# The tolerance for a second solve that registers fewer cameras is the pose
# stage's own healthy band on this metric, read off the artifact: no number of
# the service's own, and it moves if the module revises its band.
REGISTRATION_METRIC = "registered_fraction"


def second_solve_rungs(first_window: int, n_images: int) -> list[tuple[int, str]]:
    """The windows a second solve may use, narrowest first, each capped at the
    capture.

    A rung no wider than what already ran is dropped -- it would re-solve the same
    window -- so a first solve at or above the default leaves only the last
    resort, and a window already spanning the capture leaves nothing.
    """
    rungs: list[tuple[int, str]] = []
    floor = first_window
    for width, role in ((SECOND_SOLVE_WINDOW, "default"),
                        (LAST_RESORT_WINDOW, "last_resort")):
        width = min(width, n_images)
        if width > floor:
            rungs.append((width, role))
            floor = width
    return rungs


def _percentile(value: float, reference: list, *, lower_better: bool):
    """Where a reading sits within the reference corpus, in [0, 100].

    Coarse by construction -- with a corpus this size a percentile moves in
    steps of several points -- so it is an ORDERING over observed readings, not
    a score. A value past either extreme is outside what has been seen, which
    the caller reports as such: an extreme is the largest or smallest of N
    draws, never a limit.
    """
    ref = sorted(float(r) for r in reference
                 if isinstance(r, (int, float)) and r == r)
    if not ref or value is None or value != value:
        return None
    below = sum(1 for r in ref if r < value)
    equal = sum(1 for r in ref if r == value)
    pct = 100.0 * (below + 0.5 * equal) / len(ref)
    return round(100.0 - pct if lower_better else pct, 1)


def _cell(value):
    """One array element, as something JSON can carry."""
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.str_):
        return str(value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        # Six significant figures. These are measurements, not identifiers, and a
        # full float64 repr costs a third of the payload to carry noise.
        return float(f"{float(value):.6g}")
    return value.tolist() if isinstance(value, np.ndarray) else value


def _series(array) -> Any:
    """Render one stored array for the wire.

    Scalars pass through. A short series passes through whole -- that is the
    point of the field, because "which frame is the soft one" is not answerable
    from a median. A long one is summarised at both extremes rather than
    truncated to a prefix, since a prefix of a per-frame array is the first
    frames rather than the interesting ones.
    """
    if array.ndim == 0:
        return _cell(array[()])
    if len(array) <= SERIES_MAX:
        return [_cell(v) for v in array]

    doc: dict[str, Any] = {"n": len(array), "truncated": True}
    if array.ndim == 1 and np.issubdtype(array.dtype, np.number):
        order = np.argsort(array)
        doc |= {
            "min": _cell(array.min()),
            "median": _cell(np.median(array)),
            "max": _cell(array.max()),
            "lowest": [[int(i), _cell(array[i])] for i in order[:SERIES_EXTREMES]],
            "highest": [[int(i), _cell(array[i])]
                        for i in order[-SERIES_EXTREMES:][::-1]],
        }
    else:
        doc["hint"] = (
            f"{len(array)} entries, over the {SERIES_MAX} this call inlines. "
            f"Read it from the artifact directly."
        )
    return doc


_PARAM_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _named_params(actions, vocab: set[str]) -> set[str]:
    """Which tunable knobs a set of suggested_actions actually names.

    Words that are not parameters anywhere are prose and carry no obligation;
    what the reader acts on is the knob.
    """
    found: set[str] = set()
    for action in actions or ():
        found |= {t for t in _PARAM_TOKEN.findall(str(action)) if t in vocab}
    return found


def _sink(holder: dict):
    """Route a module's progress onto its job handle.

    Indirected through a holder because the handle only exists once the work has
    been submitted, and the work needs the sink to build the call.
    """

    def sink(fraction, stage: str) -> None:
        handle = holder.get("handle")
        if handle is None:
            return
        if fraction is not None:
            handle.progress = fraction
        if stage:
            handle.stage = stage

    return sink


@dataclass
class ServiceConfig:
    modules_dir: Path
    store_root: Path
    skills_dir: Path | None = None
    docker: str = "docker"

    inline_wait_s: float = DEFAULT_INLINE_WAIT
    """How long a call may block waiting for a module it expects to be quick."""

    probe_wait_s: float = 2.0
    """Minimum wait even for a module known to be slow.

    Long enough to catch the case that matters: an already-cached result returns
    almost instantly regardless of how expensive the module normally is, and
    handing back a job id for work that was never going to run is pure latency.
    """

    max_poll_interval_s: float = 30.0


class DurationEstimator:
    """Rolling estimate of how long each module takes.

    A single global inline wait cannot serve both a two-second union-find and a
    forty-minute dense reconstruction: it either blocks pointlessly on the slow
    ones or round-trips pointlessly on the fast ones. So the wait is derived
    per-module -- seeded from the manifest's declared `expected_duration_s` and
    refined from what actually happened.

    Deliberately biased upward (a slow observation moves the estimate faster than
    a fast one). Under-estimating costs a wasted round trip on every subsequent
    call; over-estimating costs one bounded block. The asymmetry is real, so the
    estimator leans that way.
    """

    def __init__(self, alpha_up: float = 0.6, alpha_down: float = 0.2):
        self.alpha_up = alpha_up
        self.alpha_down = alpha_down
        self._observed: dict[str, float] = {}

    def observe(self, module: str, duration_s: float) -> None:
        current = self._observed.get(module)
        if current is None:
            self._observed[module] = duration_s
            return
        alpha = self.alpha_up if duration_s > current else self.alpha_down
        self._observed[module] = (1 - alpha) * current + alpha * duration_s

    def estimate(self, module: str, declared: float | None) -> float | None:
        observed = self._observed.get(module)
        if observed is not None:
            return observed
        return declared

    def has_observed(self, module: str) -> bool:
        return module in self._observed


class SfmService:
    def __init__(
        self,
        *,
        config: ServiceConfig,
        orchestrator: Orchestrator,
        registry: ModuleRegistry,
        jobs: JobManager | None = None,
    ):
        self.config = config
        self.orch = orchestrator
        self.registry = registry
        self.jobs = jobs or JobManager()
        self.durations = DurationEstimator()

    @property
    def store(self) -> ArtifactStore:
        return self.orch.store

    # ===================================================================== #
    # Discovery
    # ===================================================================== #

    def list_modules(
        self,
        *,
        kind: str | None = None,
        consumes: str | None = None,
        produces: str | None = None,
    ) -> dict[str, Any]:
        specs = self.registry.find(kind=kind, consumes=consumes, produces=produces)
        terminal = {w.module for w in self.registry.warnings}
        return {
            "modules": [
                {
                    "name": s.name,
                    "version": s.version,
                    "kind": s.kind,
                    "summary": s.summary.strip(),
                    "consumes": {n: sl.type for n, sl in s.consumes.items()},
                    "produces": {n: sl.type for n, sl in s.produces.items()},
                    "gpu": s.resources.gpu,
                    "terminal": s.name in terminal,
                }
                for s in specs
            ],
            "payload_types": self.registry.types.names(),
        }

    def describe_module(self, name: str) -> dict[str, Any]:
        """Machine contract, the module's SKILL.md, and the CONTRACTS OF THE
        TYPES it touches, in one call.

        Deeper curation (tuning, limitations, sources) is fetched separately --
        progressive disclosure, so context cost scales with how stuck the caller
        is rather than with the module count.

        Type contracts are inlined here because nothing else serves them. They
        are the right home for a claim that binds every producer of a type --
        that observations are undistorted, that a published mean is per-point --
        and a claim with one owner cannot drift. But there is no
        `sfm_describe_type` and deliberately so, which previously left those
        claims reachable by nobody: they were duplicated into seven per-module
        files instead, and a seventeen-capture sweep measured all seven at zero
        reads while this call was made 204 times. Putting them where the reader
        already is costs one lookup and removes the reason to copy them.
        """
        spec = self.registry.get(name)
        doc = spec.describe()

        contracts: dict[str, Any] = {}
        for slot in list(spec.consumes.values()) + list(spec.produces.values()):
            tname = slot.type
            if tname in contracts or tname not in self.registry.types:
                continue
            t = self.registry.types.get(tname)
            if t.summary or t.description:
                contracts[tname] = {"summary": t.summary, "contract": t.description}
        if contracts:
            doc["type_contracts"] = contracts
        return doc

    # ===================================================================== #
    # Execution
    # ===================================================================== #

    def check(
        self,
        module: str,
        *,
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.orch.check(module, inputs=inputs, params=params)

    def _inline_wait_for(self, module: str, *, cached: bool) -> float:
        """How long to block before handing back a job id.

        A cached result is effectively instant, so wait for it whatever the
        module normally costs. Otherwise wait only if the module is expected to
        finish inside the budget; if it is not, take a short probe (it may still
        be quick on a small scene) and hand back a job id.
        """
        if cached:
            return self.config.inline_wait_s

        spec = self.registry.get(module)
        estimate = self.durations.estimate(module, spec.resources.expected_duration_s)

        if estimate is None:
            # Nothing declared and nothing observed: probe with the full budget
            # once, and the estimator will know better next time.
            return self.config.inline_wait_s
        if estimate <= self.config.inline_wait_s:
            return min(estimate * 1.5 + 2.0, self.config.inline_wait_s)
        return self.config.probe_wait_s

    def _poll_after_s(self, module: str, elapsed: float) -> float:
        """Suggested delay before the next `sfm_job` call.

        Returned on every unfinished run so the caller does not have to guess a
        cadence -- guessing costs either wasted round trips or idle time, and the
        right answer is module-dependent.
        """
        spec = self.registry.get(module)
        estimate = self.durations.estimate(module, spec.resources.expected_duration_s)
        if estimate is None:
            return 5.0
        remaining = max(estimate - elapsed, 0.0)
        return round(min(max(remaining * 0.5, 2.0), self.config.max_poll_interval_s), 1)

    def run(
        self,
        module: str,
        *,
        run_id: str,
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        force: bool = False,
        wait_s: float | None = None,
    ) -> dict[str, Any]:
        plan = self.orch.check(module, inputs=inputs, params=params)  # refuse early
        cached = not force and all(plan["cached"].values())

        holder: dict[str, JobHandle] = {}

        def work() -> dict[str, Any]:
            result = self.orch.run(
                module, run_id=run_id, inputs=inputs, params=params, force=force,
                on_progress=_sink(holder),
            )
            if not result.cached and result.step.duration_s:
                self.durations.observe(module, result.step.duration_s)
            return self._run_payload(result, run_id)

        handle = self.jobs.submit_and_wait(
            work,
            kind="run",
            label=module,
            run_id=run_id,
            wait_s=(
                self._inline_wait_for(module, cached=cached)
                if wait_s is None
                else wait_s
            ),
        )
        holder["handle"] = handle
        return self._with_polling_hint(handle, module)

    def _with_polling_hint(self, handle: JobHandle, module: str) -> dict[str, Any]:
        doc = handle.to_doc()
        if not handle.done:
            doc["poll_after_s"] = self._poll_after_s(module, handle.duration_s or 0.0)
            spec = self.registry.get(module)
            estimate = self.durations.estimate(
                module, spec.resources.expected_duration_s
            )
            if estimate is not None:
                doc["expected_duration_s"] = round(estimate, 1)
            doc["hint"] = (
                f"still running; call sfm_job('{handle.id}') again in about "
                f"{doc['poll_after_s']:.0f}s, or with wait_s to block for it"
            )
        return doc

    def replay(
        self,
        *,
        run_id: str,
        from_artifact: str,
        overrides: dict[str, Any] | None = None,
        wait_s: float | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            results = self.orch.replay(
                run_id=run_id, from_artifact=from_artifact, overrides=overrides
            )
            return {
                "replayed": [self._run_payload(r, run_id) for r in results],
                "leaf": results[-1].step.outputs if results else {},
            }

        handle = self.jobs.submit_and_wait(
            work,
            kind="replay",
            label=f"from {from_artifact}",
            run_id=run_id,
            wait_s=self.config.inline_wait_s if wait_s is None else wait_s,
        )
        return handle.to_doc()

    def job(self, job_id: str, *, wait_s: float = 0.0) -> dict[str, Any]:
        handle = (
            self.jobs.wait(job_id, timeout=wait_s)
            if wait_s > 0
            else self.jobs.get(job_id)
        )
        if handle is None:
            raise OrchestratorError(f"no job '{job_id}'")
        if handle.kind == "run" and handle.label and not handle.done:
            return self._with_polling_hint(handle, handle.label)
        return handle.to_doc()

    def list_jobs(
        self, *, run_id: str | None = None, status: str | None = None, limit: int = 25
    ) -> dict[str, Any]:
        return {
            "jobs": [j.to_doc() for j in self.jobs.list(
                run_id=run_id, status=status, limit=limit
            )]
        }

    def _run_payload(self, result, run_id: str | None = None) -> dict[str, Any]:
        step = result.step
        notes = {
            slot: art.manifest.body.strip()
            for slot, art in result.outputs.items()
            if art.manifest.body.strip()
        }
        payload = {
            "module": step.module,
            "outputs": step.outputs,
            "params": step.params,
            "cached": result.cached,
            "metrics": step.metrics,
            "diagnostics": [
                d.to_doc()
                for art in result.outputs.values()
                for d in art.manifest.diagnostics
            ],
            "notes": notes,
        }
        digest = self._health_digest(result.outputs)
        if digest is not None:
            payload["health_profile"] = digest
        verification = self._verify(result, run_id)
        if verification is not None:
            payload["verification"] = verification
        try:
            second = (self._second_solve(result, run_id, verification)
                      if verification is not None else self._second_solve_notice(result))
        except Exception as e:  # like the verifier: never take the step down with it
            second = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        if second is not None:
            payload["second_solve"] = second
        return payload

    # The fixed end step, and a VETO: SparseVerification rejects a refined model
    # that contradicts the matcher's correspondences it never used -- the one
    # reading a wrong but self-consistent model cannot pass by construction. It
    # does not rank models it accepts; choosing the lower of two passing readings
    # kept the worse model more often than keeping the pipeline's preferred solve. It runs HERE rather than
    # being left to the agent, because the agent's only other grounds for deciding
    # to run it are the self-reported readings a self-consistent wrong model
    # satisfies: one capture's wrong models were measured satisfying them better
    # than its correct model did. The same compelled delivery the health digest
    # gets, at the same moment.
    VERIFIER = "SparseVerification"
    VETO_CODE = "contradicted_by_held_out_evidence"

    def _verify(self, result, run_id: str | None) -> dict[str, Any] | None:
        step = result.step
        try:
            kind = self.registry.get(step.module).kind
        except Exception:
            return None
        models = [a for a in result.outputs.values() if a.type == self.SPARSE_MODEL_TYPE]
        # After refinement only. Before the final adjustment every model reads
        # badly on held-out evidence, correct or not, so a reading there would be
        # an alarm on every capture.
        if kind != "optimization" or not models:
            return None
        return self._verify_model(models[0], run_id)

    def _verify_model(self, model, run_id: str | None) -> dict[str, Any]:
        """The verifier's verdict on one refined model, against its lineage's
        matches."""
        if self.VERIFIER not in self.registry.names():
            return {"status": "unavailable", "model": model.id,
                    "note": f"{self.VERIFIER} is not registered; this model is "
                            f"unverified, not verified."}
        matches = self._ancestor_of_type(model, self.MATCHES_TYPE)
        if matches is None or not model.manifest.scene:
            return {"status": "unverified", "model": model.id,
                    "note": ("No pairwise_matches/v1 in this model's lineage: it came "
                             "from a pipeline that never matched pairs. Run "
                             f"{self.VERIFIER} yourself with any matcher's output for "
                             "this scene as `matches`.")}
        try:
            res = self.orch.run(
                self.VERIFIER, run_id=run_id or model.manifest.run,
                inputs={"scene": model.manifest.scene, "sparse": model.id,
                        "matches": matches.id},
            )
        except Exception as e:  # the check must never take the step down with it
            return {"status": "failed", "model": model.id, "error": str(e)}
        art = res.primary
        return {
            "status": "ran",
            "module": self.VERIFIER,
            "model": model.id,
            "evidence": matches.id,
            "artifact": art.id,
            "cached": res.cached,
            "metrics": {n: m.value for n, m in art.manifest.metrics.items()},
            "diagnostics": [d.to_doc() for d in art.manifest.diagnostics],
            "note": art.manifest.body.strip(),
        }

    # The second solve. When the pose stage reports points that left the image
    # during its in-loop window solves, one solve is not enough: on the captures
    # where that happened, a wider window gave a better finished model far more
    # often than a worse one, and where nothing escaped, widening changed nothing
    # on most. So once a model built on those poses is refined, the chain from the
    # pose step to that model is solved again at a wider window, and the wider
    # solve is kept unless it failed, the verifier vetoed it, or it gave up too
    # many cameras (below).
    #
    # Never chosen on reprojection error: keeping whichever solve reported the
    # lower error gave back most of the benefit. And the width is fixed rather
    # than searched: widening until nothing escaped chose worse models, because the
    # count does not fall as the window grows. Argued in PoseEssentialToPnP's
    # limitations, "Escaped points start a second solve".
    #
    # Registration is part of the decision, but only against a first solve the
    # verifier accepted -- a vetoed one is no alternative. A wider solve that
    # registers fewer cameras than an accepted first solve is kept while its
    # registered fraction stays inside the pose stage's healthy band, and counts
    # as failed below it. Every loss is recorded by name with what it cost
    # (`trade_off`), because where the correction stops outweighing the lost
    # cameras was never measured.

    def _second_solve(self, result, run_id: str | None,
                      verification: dict[str, Any]) -> dict[str, Any] | None:
        model = next((a for a in result.outputs.values()
                      if a.type == self.SPARSE_MODEL_TYPE), None)
        if model is None:
            return None
        pose = self._ancestor_of_type(model, self.POSES_TYPE)
        spec = self._windowed_spec(pose)
        escaped = pose.metric(ESCAPE_METRIC) if spec else None
        if not escaped:
            return None

        run_id = run_id or model.manifest.run
        run = self.orch.open_run(run_id)
        first_window = int(pose.manifest.produced_by.params[WINDOW_PARAM])
        n_images = self._capture_size(model.manifest.scene)
        first = {"window": first_window, "pose": pose.id, "model": model.id,
                 "status": "ok", "vetoed": self._vetoed(verification)}
        doc: dict[str, Any] = {
            "trigger": {"pose": pose.id, "module": spec.name, "escaped_points": escaped,
                        "window": first_window, "capture_images": n_images},
            "first": first,
            "attempts": [],
            "read": (f"sfm_module_skill('{spec.name}', 'limitations') -- "
                     f"'Escaped points start a second solve'"),
        }
        kept_first = model.id if self._acceptable(first) else None

        rungs = second_solve_rungs(first_window, n_images)
        if not rungs:
            return self._decide(
                run, doc, "no_wider_window", kept_first, first_window,
                f"The first solve's window ({first_window}) already spans the "
                f"capture's {n_images} images, so there is no wider solve to run; "
                f"the escapes are reported only.")
        if run.producer_of(pose.id) is None or run.producer_of(model.id) is None:
            return self._decide(
                run, doc, "unavailable", kept_first, first_window,
                f"The steps that built this model are not all recorded in run "
                f"'{run_id}', so its chain cannot be re-solved here. By hand: "
                f"sfm_replay from {pose.id} with {WINDOW_PARAM}={rungs[0][0]}, "
                f"carried through the same refinement.")

        floor = self._band_floor(pose)
        for width, role in rungs:
            below = doc["attempts"][-1] if doc["attempts"] else first
            if role == "last_resort" and self._acceptable(below):
                break
            attempt = self._solve_again(run_id, pose, model, width, role)
            if attempt["status"] == "ok":
                self._weigh_registration(attempt, model, n_images, floor,
                                         first_accepted=kept_first is not None)
            doc["attempts"].append(attempt)
            if self._acceptable(attempt):
                break

        kept = next((a for a in doc["attempts"] if self._acceptable(a)), None)
        if kept is not None:
            detour = ""
            if kept["role"] == "last_resort" and len(doc["attempts"]) > 1:
                d = doc["attempts"][0]
                detour = (f"; the solve at {d['window']} {self._outcome(d)}, "
                          f"so the last resort ran")
            return self._decide(
                run, doc, "kept_second", kept["model"], kept["window"],
                f"Points escaped the first solve at {WINDOW_PARAM}={first_window}. "
                f"Kept the re-solve at {kept['window']}{detour}: it completed and "
                f"the verifier did not veto it. Continue from it. The choice was "
                f"not made on reprojection error."
                + self._loss_sentence(kept, first))
        if kept_first is not None:
            reason = (
                "No wider solve was kept: "
                + "; ".join(f"the one at {a['window']} {self._outcome(a)}"
                            for a in doc["attempts"])
                + ". So the first model -- which the verifier did not veto -- is "
                  "kept."
                if doc["attempts"] else
                f"The first solve already ran at {first_window}, at or above the "
                f"default second-solve width, and the verifier did not veto it. The "
                f"last resort ({rungs[0][0]}) runs only when that model is vetoed.")
            return self._decide(run, doc, "kept_first", kept_first, first_window, reason)
        return self._decide(
            run, doc, "none_kept", None, None,
            f"Every solve of this chain failed or was vetoed, the first included. "
            f"None of them is a model to keep. If each was vetoed, the evidence may "
            f"be inconsistent with any single geometry: "
            f"sfm_module_skill('{self.VERIFIER}', 'limitations') -- 'What a "
            f"contradiction means'.")

    def _second_solve_notice(self, result) -> dict[str, Any] | None:
        """On the pose step itself: say that a second solve is coming, and when."""
        pose = next((a for a in result.outputs.values()
                     if a.type == self.POSES_TYPE), None)
        spec = self._windowed_spec(pose)
        escaped = pose.metric(ESCAPE_METRIC) if spec else None
        if not escaped:
            return None
        first_window = int(pose.manifest.produced_by.params[WINDOW_PARAM])
        rungs = second_solve_rungs(first_window, self._capture_size(pose.manifest.scene))
        if not rungs:
            note = ("The window already spans the capture, so there is no wider "
                    "solve; the escapes are reported only.")
        elif rungs[0][1] == "default":
            note = (f"Once a bundle adjustment refines a model built on these poses, "
                    f"the service re-solves that chain at {WINDOW_PARAM}={rungs[0][0]} "
                    f"and keeps it unless it fails, the verifier vetoes it, or it "
                    f"gives up more cameras than this stage's {REGISTRATION_METRIC} "
                    f"band allows against an accepted first solve"
                    + (f"; only then does it try {rungs[1][0]} as a last resort"
                       if len(rungs) > 1 else "")
                    + ". Continue the pipeline as planned -- do not re-solve by hand.")
        else:
            note = (f"This solve already ran at or above the default second-solve "
                    f"width. The service re-solves at {WINDOW_PARAM}={rungs[0][0]} "
                    f"only if the refined model fails or is vetoed.")
        return {"status": "pending", "escaped_points": escaped,
                "window": first_window, "note": note}

    def _solve_again(self, run_id: str, pose, model, width: int,
                     role: str) -> dict[str, Any]:
        """Re-solve the chain from `pose` to `model` at one window, and verify it."""
        entry: dict[str, Any] = {"window": width, "role": role}
        try:
            results = self.orch.replay(
                run_id=run_id, from_artifact=pose.id,
                overrides={WINDOW_PARAM: width}, toward=model.id,
            )
        except Exception as e:  # a re-solve that cannot finish is an outcome
            return entry | {"status": "failed", "error": f"{type(e).__name__}: {e}"[:500]}
        new_pose = next((a for a in results[0].outputs.values()
                         if a.type == self.POSES_TYPE), None)
        new_model = next((a for a in results[-1].outputs.values()
                          if a.type == self.SPARSE_MODEL_TYPE), None)
        if new_model is None:
            return entry | {"status": "failed",
                            "error": "the re-solved chain ended without a sparse model"}
        verdict = self._verify_model(new_model, run_id)
        return entry | {
            "status": "ok",
            "pose": new_pose.id if new_pose is not None else None,
            "model": new_model.id,
            "escaped_points": new_pose.metric(ESCAPE_METRIC) if new_pose is not None else None,
            "cached": all(r.cached for r in results),
            "verification": {
                "status": verdict.get("status"),
                "artifact": verdict.get("artifact"),
                "metrics": verdict.get("metrics") or {},
                "diagnostics": [d.get("code") for d in verdict.get("diagnostics") or []],
            },
            "vetoed": self._vetoed(verdict),
        }

    def _decide(self, run, doc: dict[str, Any], status: str, kept: str | None,
                kept_window: int | None, reason: str) -> dict[str, Any]:
        """Record a second-solve decision in the run, replacing any earlier one
        about the same first model, and return it."""
        doc |= {"status": status, "kept": kept, "kept_window": kept_window,
                "reason": reason}
        first = doc["first"]["model"]
        run.second_solves = [d for d in run.second_solves
                             if (d.get("first") or {}).get("model") != first] + [doc]
        run.save()
        return doc

    def _windowed_spec(self, pose):
        """The pose artifact's module, if it is one a wider window can re-solve."""
        if pose is None:
            return None
        made = pose.manifest.produced_by
        try:
            spec = self.registry.get(made.module)
        except Exception:
            return None
        if WINDOW_PARAM not in spec.params.specs or WINDOW_PARAM not in made.params:
            return None
        return spec

    def _capture_size(self, scene_id: str) -> int:
        scene = self.store.open(scene_id)
        n = scene.metric("n_images")
        if isinstance(n, (int, float)) and n > 0:
            return int(n)
        return len(scene.load("images", "names"))

    def _vetoed(self, verdict: dict[str, Any] | None) -> bool:
        return bool(verdict) and any(
            d.get("code") == self.VETO_CODE for d in verdict.get("diagnostics") or [])

    @staticmethod
    def _acceptable(entry: dict[str, Any]) -> bool:
        return (entry.get("status") == "ok" and not entry.get("vetoed")
                and not entry.get("rejected_on_registration"))

    @staticmethod
    def _outcome(entry: dict[str, Any]) -> str:
        """Why a solve was not kept, as a clause."""
        if entry.get("status") != "ok":
            return "failed"
        if entry.get("vetoed"):
            return "was vetoed"
        if entry.get("rejected_on_registration"):
            r = entry.get("registration") or {}
            return (f"registered {len(r.get('lost') or [])} fewer camera(s) than the "
                    f"accepted first solve, leaving {r.get('fraction')} of the "
                    f"capture, below the pose stage's {REGISTRATION_METRIC} band")
        return "was kept"

    @staticmethod
    def _loss_sentence(kept: dict[str, Any], first: dict[str, Any]) -> str:
        lost = (kept.get("registration") or {}).get("lost") or []
        if not lost:
            return ""
        why = ("the first solve was vetoed, so it is no alternative"
               if first.get("vetoed") else
               f"its {REGISTRATION_METRIC} stays inside the pose stage's band")
        return (f" It does not register {len(lost)} camera(s) the first solve had "
                f"({', '.join(lost)}); kept because {why}. What those cameras saw "
                f"and how far the geometry moved are in this attempt's `trade_off`: "
                f"weigh them if those cameras matter.")

    def _band_floor(self, pose) -> float | None:
        """The lower edge of the pose artifact's own registered-fraction band."""
        m = pose.manifest.metrics.get(REGISTRATION_METRIC)
        band = getattr(m, "healthy", None)
        return float(band[0]) if band and band[0] is not None else None

    def _weigh_registration(self, attempt: dict[str, Any], first_model, n_images: int,
                            floor: float | None, *, first_accepted: bool) -> None:
        """Compare a re-solve's cameras with the first model's; record any loss,
        and what it cost."""
        try:
            new_model = self.store.open(attempt["model"])
            before, after = self._rotations(first_model), self._rotations(new_model)
            names = [str(n) for n in
                     self.store.open(first_model.manifest.scene).load("images", "names")]
        except Exception as e:  # a reading, never a reason to fail the step
            attempt["registration"] = {"status": "unavailable",
                                       "error": f"{type(e).__name__}: {e}"[:300]}
            return
        name = lambda i: names[i] if i < len(names) else str(i)  # noqa: E731
        lost = sorted(set(before) - set(after))
        gained = sorted(set(after) - set(before))
        fraction = len(after) / n_images if n_images else 0.0
        # A pose artifact that publishes no band tolerates no loss.
        within = fraction >= floor if floor is not None else not lost
        attempt["registration"] = {
            "registered": len(after), "first_registered": len(before),
            "capture_images": n_images, "fraction": round(fraction, 3),
            "band_floor": floor, "within_band": within,
            "lost": [name(i) for i in lost], "gained": [name(i) for i in gained],
        }
        attempt["rejected_on_registration"] = bool(lost) and first_accepted and not within
        if not lost:
            return
        covered = self._still_covered(new_model, set(after), n_images)
        typical = None
        if covered is not None:
            kept_shares = covered[sorted(after)]
            kept_shares = kept_shares[np.isfinite(kept_shares)]
            typical = round(float(np.median(kept_shares)), 3) if len(kept_shares) else None
        attempt["trade_off"] = {
            "cameras_lost": len(lost),
            "share_of_capture_lost": round(len(lost) / n_images, 3) if n_images else None,
            # Per lost camera: the share of the tracks it observes that at least two
            # OTHER cameras of this solve still see. Low beside the typical share
            # means part of the scene lost support, not just a redundant viewpoint.
            "lost_structure_still_covered": (
                {name(i): (round(float(covered[i]), 3) if np.isfinite(covered[i]) else None)
                 for i in lost} if covered is not None else None),
            "typical_for_registered": typical,
            # On the cameras both solves registered: how far the relative rotations
            # between them moved. Large means the second solve corrected something;
            # near zero means the wider window bought little.
            "rotation_change_deg": self._rotation_change(before, after),
            "verdicts": {"first": "accepted" if first_accepted else "vetoed",
                         "second": "vetoed" if attempt.get("vetoed") else "accepted"},
        }

    @staticmethod
    def _rotations(model) -> dict[int, np.ndarray]:
        """Scene image index -> world-to-camera rotation, registered cameras only."""
        cams = np.asarray(model.load("poses", "cam_from_world"))
        valid = np.asarray(model.load("poses", "valid"), dtype=bool)
        idx = np.asarray(model.load("poses", "image_index")).astype(np.int64)
        return {int(i): cams[r][:, :3] for r, (i, v) in enumerate(zip(idx, valid)) if v}

    def _still_covered(self, model, registered: set[int], n_images: int):
        """Per scene image, the share of the tracks it observes that at least two
        other registered cameras see; NaN where it observes none. None without a
        tracks artifact in the lineage."""
        tracks = self._ancestor_of_type(model, self.TRACKS_TYPE)
        if tracks is None:
            return None
        obs = np.asarray(tracks.load("observations", "obs"))
        if not len(obs):
            return None
        t, f = obs[:, 0].astype(np.int64), obs[:, 1].astype(np.int64)
        size = max(n_images, int(f.max()) + 1)
        reg = np.zeros(size, dtype=np.int64)
        reg[sorted(registered)] = 1
        views = np.bincount(t, weights=reg[f])        # registered views per track
        covered = (views[t] - reg[f]) >= 2            # excluding the image itself
        seen = np.bincount(f, minlength=size)
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.bincount(f, weights=covered, minlength=size) / seen
        return share

    @staticmethod
    def _rotation_change(a: dict[int, np.ndarray], b: dict[int, np.ndarray],
                         cap: int = 400) -> dict[str, Any] | None:
        """Median and p90 change, in degrees, of the relative rotation between
        every pair of cameras both solves registered. Relative rotations need no
        alignment: each solve's own world frame cancels."""
        shared = sorted(set(a) & set(b))
        if len(shared) < 2:
            return None
        n_shared = len(shared)
        if n_shared > cap:  # pairs grow with the square; an even subset suffices
            shared = [shared[i] for i in np.linspace(0, n_shared - 1, cap).round().astype(int)]
        A = np.stack([a[i] for i in shared])
        B = np.stack([b[i] for i in shared])
        i, j = np.triu_indices(len(shared), k=1)
        rel_a = A[j] @ np.swapaxes(A[i], 1, 2)
        rel_b = B[j] @ np.swapaxes(B[i], 1, 2)
        d = rel_a @ np.swapaxes(rel_b, 1, 2)
        ang = np.degrees(np.arccos(np.clip((np.trace(d, axis1=1, axis2=2) - 1) / 2, -1, 1)))
        return {"median": round(float(np.median(ang)), 3),
                "p90": round(float(np.percentile(ang, 90)), 3),
                "shared_cameras": n_shared}

    # The rungs of the reconstruction health profile, in ladder order. Defined
    # and argued in skills/health/ladder.md -- the run payload carries the
    # digest because a file nothing delivers is a file nothing reads: the health
    # tier gets the same compelled delivery a diagnostic's see_also gives
    # tuning.md, at the exact moment a sparse model exists.
    #
    # `yield` is two entries because the corpus has not decided between the two
    # forms; recording both is cheaper than freezing the wrong one.
    _HEALTH_RUNGS = (
        ("registration", "registered frames / capture frames"),
        ("conditioning", "median widest triangulation angle over points"),
        ("composition", "median observations per surviving point"),
        ("coverage", "median per-frame fraction of image grid cells holding "
                     "an observation"),
        ("error", "median reprojection error among well-supported points only"),
        ("yield_obs", "model observations / track observations"),
        ("yield_track", "model points / input tracks"),
        ("pose_agreement", "median angular discrepancy between final relative "
                           "poses and the pairwise two-view estimates"),
    )

    SPARSE_MODEL_TYPE = "sparse_model/v1"
    TRACKS_TYPE = "tracks/v1"
    MATCHES_TYPE = "pairwise_matches/v1"
    POSES_TYPE = "poses/v1"

    def _ancestor_of_type(self, art, wanted: str, *, depth: int = 8):
        """The nearest artifact of `wanted` upstream of `art`, or None.

        A sparse model does not consume every artifact its rungs need -- a
        triangulator takes tracks and poses, never the matches the pose
        agreement rung is measured against -- so the digest walks the lineage
        the manifests already record rather than demanding a wider contract.
        """
        seen, frontier = set(), [(art, 0)]
        while frontier:
            node, d = frontier.pop(0)
            if d > depth:
                continue
            # `Manifest.inputs` is a list of artifact ids, not a slot mapping:
            # the slot names belong to the producing step, and the artifact only
            # records what it was built from.
            for aid in list(node.manifest.inputs):
                if aid in seen:
                    continue
                seen.add(aid)
                try:
                    up = self.store.open(aid)
                except Exception:
                    continue
                if up.type == wanted:
                    return up
                frontier.append((up, d + 1))
        return None

    def _health_digest(self, outputs) -> dict[str, Any] | None:
        """The health profile for a run that just produced a sparse model.

        Every rung is a percentile against the reference corpus -- the reference
        pipeline's reconstruction of every corpus capture, recorded as a campaign
        under skills/evidence/ with a machine-readable reference_profile.yaml
        beside it. Until that campaign has run there is nothing to normalise
        against, and the honest report is "cannot evaluate", not a guess: a
        rung's raw value without the corpus distribution behind it invites
        exactly the threshold-reading the ladder file warns against.
        """
        model = next((a for a in outputs.values()
                      if a.type == self.SPARSE_MODEL_TYPE), None)
        if model is None:
            return None

        root = self.config.skills_dir
        ref_path = (root / "evidence" / "reference_profile.yaml") if root else None
        reference = None
        if ref_path is not None and ref_path.is_file():
            try:
                import yaml
                reference = yaml.safe_load(ref_path.read_text())
            except Exception:
                reference = None

        read_note = (
            "sfm_workflow_skill('health/ladder') defines each rung and the "
            "weakest-rung scalar; 'health/bounce' says what a persistently weak "
            "rung means. Read these only AFTER the sparse step -- they describe "
            "a finished model and say nothing about an upstream stage."
        )
        if reference is None:
            return {
                "status": "cannot evaluate: no reference corpus yet",
                "reference": (
                    "skills/evidence/reference_profile.yaml -- absent; it is "
                    "written by the reference campaign (see evidence/EVIDENCE)"
                ),
                "rungs": {name: {"component": component,
                                 "value": "cannot evaluate: no reference yet"}
                          for name, component in self._HEALTH_RUNGS},
                "read": read_note,
            }

        try:
            measured = self._health_components(model)
        except Exception as exc:
            return {
                "status": f"cannot evaluate: {type(exc).__name__}: {exc}",
                "reference": str(ref_path),
                "read": read_note,
            }

        rungs, weakest = {}, None
        for name, component in self._HEALTH_RUNGS:
            spec = (reference.get("rungs") or {}).get(name) or {}
            value = measured.get(name)
            entry: dict[str, Any] = {"component": component, "value": value}
            values = spec.get("values") or []
            if value is None or not values:
                entry["percentile"] = None
                entry["note"] = "no reference values for this rung"
                rungs[name] = entry
                continue
            lower_better = spec.get("direction") == "lower_better"
            entry["percentile"] = _percentile(value, values,
                                              lower_better=lower_better)
            lo, hi = min(values), max(values)
            entry["corpus_range"] = [lo, hi]
            if value < lo or value > hi:
                # An extreme is the largest or smallest of N draws, so a reading
                # past it is outside what has been seen -- which is not a verdict.
                entry["note"] = ("outside the observed range of the reference "
                                 "corpus; that is not the same as wrong")
            if entry["percentile"] is not None and (
                    weakest is None or entry["percentile"] < weakest[1]):
                weakest = (name, entry["percentile"])
            rungs[name] = entry

        return {
            "status": "evaluated",
            "reference": {
                "campaign": reference.get("campaign"),
                "captures": reference.get("captures"),
                "path": str(ref_path),
            },
            "rungs": rungs,
            # The scalar is the MINIMUM percentile, never a mean: a model is only
            # as healthy as its worst constraint, and an average hides exactly
            # the rung the ladder would have disqualified it on.
            "weakest_rung": (
                {"rung": weakest[0], "percentile": round(weakest[1], 1)}
                if weakest else None),
            "how_to_read": (
                "Percentiles locate this model in the reference corpus; they are "
                "an ordering over observed readings, not a score and not a pass "
                "mark. With this many reference draws they move in coarse steps."
            ),
            "read": read_note,
        }

    def _health_components(self, model) -> dict[str, Any]:
        """Raw rung components for a sparse model, from it and its lineage."""
        from .health import components

        scene = self.store.open(model.manifest.scene) if model.manifest.scene else None
        tracks = self._ancestor_of_type(model, self.TRACKS_TYPE)
        matches = self._ancestor_of_type(model, self.MATCHES_TYPE)
        return components(model, scene=scene, tracks=tracks, matches=matches)

    # ===================================================================== #
    # Inspection
    # ===================================================================== #

    def artifact(self, artifact_id: str, *, full: bool = True) -> dict[str, Any]:
        art = self.store.open(artifact_id)
        doc: dict[str, Any] = {
            "id": art.id,
            "type": art.type,
            "run": art.manifest.run,
            "scene": art.manifest.scene,
            "inputs": art.manifest.inputs,
            "metrics": {n: m.value for n, m in art.manifest.metrics.items()},
            "diagnostics": [d.to_doc() for d in art.manifest.diagnostics],
            "files": {
                name: list(spec.get("arrays", {}))
                for name, spec in art.manifest.files.items()
                if name != "__sidecars__"
            },
            "sidecars": art.sidecars(),
            "path": str(art.root),
            # N': whose execution this describes. An artifact id is derived from
            # the recipe, so asking for the same module, params and inputs returns
            # the artifact SOMEONE ELSE'S run already produced -- and its
            # provenance still records that run's device, wall-clock and duration.
            # Read as the requesting run's, those fields are simply wrong: a
            # reader here concluded from `device` that its own job had been placed
            # on a device it was told not to use, and reported the violation in
            # writing. It had run nothing at all. Nothing in the artifact said so.
            "produced_by_run": art.manifest.run,
            "provenance_describes": (
                f"the run '{art.manifest.run}' that FIRST produced this recipe, "
                f"including its device, start time and duration. If you asked for "
                f"this artifact and got it back instantly, those fields are that "
                f"run's and not yours -- check `cached` on your own run result."
            ),
        }
        if full:
            doc["artifact_md"] = (art.root / "artifact.md").read_text(encoding="utf-8")
        return doc

    def artifact_image(
        self, artifact_id: str, *, name: str = "", max_bytes: int = MAX_IMAGE_BYTES
    ) -> dict[str, Any]:
        """Locate an image inside an artifact, for a caller that can look at it.

        Returns a path and its media type; it does not read or decode the file.
        Encoding it for the wire belongs to the transport, and decoding it belongs
        to nobody here -- the orchestrator has no image library and should not
        acquire one. Pixels are a container concern; serving bytes a container
        already wrote is inspection, which is what this is.

        With no `name`, returns the artifact's images so the caller can choose --
        unless there is exactly one, which is the `SceneDescription` case and the
        one worth making frictionless.
        """
        art = self.store.open(artifact_id)
        data_dir = art.data_dir.resolve()

        available = sorted(
            str(p.relative_to(data_dir))
            for p in data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
        )

        if not name:
            if len(available) != 1:
                return {
                    "artifact": art.id,
                    "type": art.type,
                    "images": available,
                    "hint": (
                        f"{len(available)} images; pass one as `name`."
                        if available
                        else "this artifact carries no images."
                    ),
                }
            name = available[0]

        path = (data_dir / name).resolve()

        # An artifact id plus a caller-supplied path is the shape that leaks a
        # filesystem if nobody checks it. `..` must not walk out of the artifact.
        if not path.is_relative_to(data_dir):
            raise OrchestratorError(
                f"'{name}' resolves outside artifact {art.id}. Names are relative "
                f"to the artifact's data directory."
            )
        if not path.is_file():
            raise OrchestratorError(
                f"artifact {art.id} has no image '{name}'. Available: {available}"
            )
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise OrchestratorError(
                f"'{name}' is not an image ({sorted(IMAGE_SUFFIXES)}). This tool "
                f"serves pictures; use sfm_artifact for the manifest and the "
                f"array inventory."
            )

        size = path.stat().st_size
        if size > max_bytes:
            raise OrchestratorError(
                f"'{name}' is {size / 2**20:.1f} MiB, over the {max_bytes / 2**20:.0f} "
                f"MiB limit. A contact sheet is meant to be one modest image; if "
                f"this is a full-resolution frame, look at a thumbnail instead. "
                f"Available: {available}"
            )

        return {
            "artifact": art.id,
            "type": art.type,
            "name": name,
            "path": str(path),
            "mime_type": MIME_TYPES[path.suffix.lower()],
            "bytes": size,
        }

    def plan_brief(
        self, scene_id: str, *, stages: list[str] | None = None
    ) -> dict[str, Any]:
        """Assemble everything needed to turn a scene analysis into a first plan.

        This is step 3 of the loop and it is the same shape as
        `SceneDescription`: it PREPARES and it does not decide. There is no model
        in the orchestrator, so nothing here converts a metric into a module. What
        it does is put the four things that argument needs into one response --
        the measurements, the guide that says how to read them, the family files
        that say which member of a stage to reach for, and the live menu -- so the
        reasoning happens once, against a complete picture, rather than across six
        calls with the early ones already out of context.

        The gap being closed is real and was measured: of the 29 metrics the three
        analysis modules produce, exactly two are named anywhere in the stage
        files of `skills/plan/`. Those speak in adjectives and step 2 speaks in
        numbers, and `skills/plan/scene_to_pipeline.md` is the translation.
        """
        scene = self.store.open(scene_id)
        if scene.type != SCENE_TYPE:
            raise OrchestratorError(
                f"artifact {scene_id} is '{scene.type}', not '{SCENE_TYPE}'. "
                f"Pass the scene this analysis was run against."
            )

        analyses, pending = [], []
        for aid in self.store.list(type=ANALYSIS_TYPE):
            art = self.store.open(aid)
            if art.manifest.scene != scene_id:
                continue
            groups = [n for n in art.manifest.files if n != "__sidecars__"]
            if not groups:
                # A `scene_analysis/v1` carrying no group is a placeholder, not
                # an analysis -- `SceneDescription`'s first call renders a contact
                # sheet and writes nothing. Counting it as an analysis would let
                # a scene that was looked at but never described read as complete,
                # which is the one mistake this field exists to prevent.
                pending.append({"artifact": art.id,
                                "module": art.manifest.produced_by.module})
                continue
            analyses.append({
                "artifact": art.id,
                "module": art.manifest.produced_by.module,
                # A scene re-analysed after a module version bump carries BOTH
                # results, because the recipe changed and the id follows it. Two
                # entries reading `SceneTriage` with different contents are
                # indistinguishable without this, and the newer one is not
                # reliably the one to trust -- the version is the fact, so report
                # it rather than making the reader infer it.
                "module_version": art.manifest.produced_by.module_version,
                "groups": groups,
                "metrics": {n: m.value for n, m in art.manifest.metrics.items()},
                # Every metric above is a median, a p75 or a fraction over the
                # set, and the advice attached to those metrics is per-frame and
                # per-pair: open the soft frame before dropping it, keep the
                # planar pair out of the seed. That advice was unfollowable from
                # this call until the series came with it.
                "series": {
                    group: {name: _series(arr)
                            for name, arr in art.load(group).items()}
                    for group in groups
                },
                "diagnostics": [d.to_doc() for d in art.manifest.diagnostics],
                "notes": art.manifest.body.strip(),
            })
        # Several analyses of one scene by one module are the SAME module run at
        # different parameters -- `SceneMotion` at several `stride` values is the
        # case the guide itself asks for. Listed unordered and unlabelled, the
        # brief then carries three answers to "what is `overall_magnitude`" while
        # `plan/scene_to_pipeline.md` forbids locating a raised-stride reading in
        # the corpus band at all. Sort so the reading the ranges are denominated
        # in comes first, and say which one that is.
        def _analysis_key(a: dict[str, Any]) -> tuple:
            stride = a.get("metrics", {}).get("stride")
            return (a["module"], a["module_version"],
                    stride if isinstance(stride, (int, float)) else 0)

        analyses.sort(key=_analysis_key)
        seen: set[str] = set()
        for a in analyses:
            stride = a.get("metrics", {}).get("stride")
            if not isinstance(stride, (int, float)):
                continue
            if a["module"] not in seen:
                seen.add(a["module"])
                a["comparable_to_published_ranges"] = (stride == 1)
                if stride != 1:
                    a["stride_note"] = (
                        "No stride-1 analysis of this scene exists, so NO entry "
                        "here is on the denominator the guide's ranges use.")
            else:
                a["comparable_to_published_ranges"] = False
                a["stride_note"] = (
                    f"Read at stride {stride}. This is a different quantity on a "
                    f"different denominator from the stride-1 entry above -- the "
                    f"guide's ranges do not apply to it. Read the DIRECTION of "
                    f"the change against stride 1, never the level.")

        # H: say when an artifact is behind the module that would produce it now.
        # The brief holds both numbers and used to print neither against the other,
        # so a reader could be told to consult a metric the guide describes and the
        # artifact in front of them does not carry -- which happened, on prose
        # written against a newer version than the stored analyses. A version bump
        # is not automatically meaningful, so this states the fact rather than
        # advising a re-run.
        stale = []
        for entry in analyses:
            try:
                live = self.registry.get(entry["module"]).version
            except OrchestratorError:
                continue
            if live != entry["module_version"]:
                entry["module_is_behind"] = live
                stale.append(f"{entry['module']} {entry['module_version']} "
                             f"(module is now {live})")

        # Everything ELSE already built on this scene. A brief that lists only the
        # analyses is complete for planning stage one and wrong for every stage
        # after it: a reader arriving at matching inherits a features/v1 chosen and
        # tuned by someone else and could not see the module, the parameters or the
        # metrics behind it. Whether to trust an inherited choice is a real question
        # at every stage past the first, and it cannot be asked from an artifact id.
        built = []
        for aid in self.store.list():
            art = self.store.open(aid)
            if art.manifest.scene != scene_id or art.type in (SCENE_TYPE, ANALYSIS_TYPE):
                continue
            prov = art.manifest.produced_by
            built.append({
                "artifact": art.id,
                "type": art.type,
                "module": prov.module,
                "module_version": prov.module_version,
                # The parameters are the point. "Which detector" is half the
                # question; "at what cap, and was that cap binding" is the other
                # half, and only the params plus the metrics answer it together.
                "params": dict(prov.params),
                "metrics": {n: m.value for n, m in art.manifest.metrics.items()},
                "diagnostics": [d.to_doc() for d in art.manifest.diagnostics],
                "notes": art.manifest.body.strip(),
            })
            # H': the same staleness question the analyses get, asked of the
            # artifacts a later stage actually INHERITS. It was only asked of the
            # three analysis modules, so a reader could be handed a detector
            # artifact a minor version behind the live module with the brief
            # reporting nothing behind at all -- which happened on two captures.
            # It matters most at exactly the moment it is least visible: a reader
            # that decides to backtrack and re-runs detection at the inherited
            # parameters does NOT reproduce the inherited artifact, because the id
            # is derived from the module version too. Without this the divergence
            # surfaces as a mysterious second artifact.
            try:
                live = self.registry.get(prov.module).version
            except OrchestratorError:
                continue
            if live != prov.module_version:
                built[-1]["module_is_behind"] = live
                # One line per module and version, not per artifact: a capture
                # with eight runs of one bumped matcher was reporting the same
                # sentence eight times, which buries the one line that matters
                # -- the inherited detector sitting a version back.
                line = (f"{prov.module} {prov.module_version} (module is now "
                        f"{live}; a re-run is a DIFFERENT recipe and lands on a "
                        f"new artifact id, but whether the NUMBERS move depends on "
                        f"what changed -- a bump that only moved bands or prose "
                        f"reproduces them exactly, which has been measured twice)")
                if line not in stale:
                    stale.append(line)
        built.sort(key=lambda a: (a["type"], a["module"], a["artifact"]))

        wanted = list(stages or PLANNING_STAGES)
        families, missing = {}, []
        for stage in wanted:
            try:
                families[stage] = self.workflow_skill(f"plan/{stage}")["text"]
            except OrchestratorError:
                missing.append(stage)

        return {
            "scene": {
                "artifact": scene.id,
                "run": scene.manifest.run,
                "metrics": {n: m.value for n, m in scene.manifest.metrics.items()},
                # The index every per-frame series below is in. A series saying
                # element 11 is the soft one is not actionable until 11 has a
                # name, and per-PAIR series carry a pair of these same indices.
                "images": _series(scene.load("images", "names")),
                "diagnostics": [d.to_doc() for d in scene.manifest.diagnostics],
                "notes": scene.manifest.body.strip(),
            },
            # Empty is a legitimate state and worth surfacing rather than
            # returning a brief that silently plans from nothing.
            "analysis": analyses,
            "analysis_pending": sorted(pending, key=lambda a: a["module"]),
            "analysis_missing": sorted(
                {"SceneTriage", "SceneMotion", "SceneDescription"}
                - {a["module"] for a in analyses}
            ),
            # The analysis modules' own skills ARE fetchable -- module_skill resolves
            # every one of them -- but nothing here said so, and the menu below lists
            # only what consumes a scene. So every `see_also` an analysis diagnostic
            # emits (tuning.md#..., limitations.md#...) read as a dangling citation,
            # and readers reported the advice they most needed as unreachable when it
            # was one call away.
            "skills_available": {
                "note": (
                    "Fetch any of these with module_skill(<name>, <topic>), topics "
                    "tuning / limitations / artifact / SKILL / sources. This is how "
                    "a `see_also` on an analysis diagnostic resolves -- those "
                    "modules are not in `menu`, which lists only what consumes a "
                    "scene, but their skills are here."
                ),
                "modules": sorted(
                    {"SceneLoader", "SceneTriage", "SceneMotion", "SceneDescription"}
                    | {m["name"] for m in self.list_modules(consumes=SCENE_TYPE)["modules"]}
                ),
            },
            # A flat statement, not a warning: whether the difference matters
            # depends on what changed, which the module's own version history says
            # and this call does not.
            # Renamed with H': it no longer covers only the analyses, and a name
            # that says "analysis" while carrying an inherited detector is the
            # kind of thing a reader trusts and should not.
            "behind_live_module": stale,
            # H, second half: whether the bands in the planning guide were fitted
            # ON this capture. When they were, locating a reading in them is recall
            # rather than confirmation, and the guide asks a planner to say so --
            # which until now they could only discover by recognising their own
            # number in a printed extreme, i.e. by performing the leak the guide
            # warns about. Sourced from the corpus record so it cannot drift from
            # the evidence it describes.
            "in_planning_corpus": self._corpus_membership(scene),
            "already_built": built,
            "how_to_read": self.workflow_skill(PLANNING_GUIDE),
            "families": families,
            "families_missing": missing,
            "menu": self.list_modules(consumes=SCENE_TYPE),
            # The menu above is "what consumes this scene", which structurally
            # EXCLUDES whatever produced it -- and the scene producer is exactly the
            # module a heavy_downscale diagnostic and the planning guide both tell
            # you to go and change. Nine readers in a row concluded no such module
            # existed, then reasoned around a working-resolution decision they were
            # never offered. Listed separately rather than merged, because reaching
            # for one is a different kind of act: it builds a NEW scene and every
            # artifact downstream of it gets a new id.
            "rebuild_scene": {
                "modules": self.list_modules(produces=SCENE_TYPE)["modules"],
                "note": (
                    "These produce a scene rather than consuming one, so they are "
                    "not in `menu`. Running one does not adjust this scene -- it "
                    "builds another, and every analysis and every downstream "
                    "artifact must be recomputed against the new id. That cost is "
                    "why it is a separate list. It is still the right move when the "
                    "working resolution, and not a detector parameter, is what is "
                    "limiting the pipeline: the guide's advice to raise the working "
                    "resolution and the loader's own heavy_downscale action both "
                    "land here. Note the resize mode -- `max_edge` applies under "
                    "`resize: auto`, `target_resolution` under `resize: fixed` or "
                    "`square`; they are two parameters for two modes, not two names "
                    "for one knob."
                ),
            },
            "report_shape": PLAN_SHAPE,
        }

    # The captures the planning guide's ranges were fitted on, by the source path
    # their scene was built from. A path rather than an artifact id because the id
    # changes with every loader parameter while the capture does not.
    _CORPUS_MARKER = "skills/evidence/CORPUS.txt"

    def _corpus_membership(self, scene) -> dict[str, Any]:
        root = self.config.skills_dir
        marker = (root / "evidence" / "CORPUS.txt") if root else None
        if marker is None or not marker.exists():
            return {"known": False, "note": "no corpus record available"}
        entries = [ln.strip() for ln in marker.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.startswith("#")]
        # Whole path segments only: as a bare substring, a capture named like a
        # prefix of another (a scan numbered 1 and one numbered 11, a subject and
        # its second session) would claim captures it was never fitted on.
        source = str(scene.manifest.produced_by.params.get("image_dir", "")).rstrip("/") + "/"
        hit = next((e for e in entries if e and e.rstrip("/") + "/" in source), None)
        return {
            "known": True,
            "is_member": hit is not None,
            "note": (
                "This capture is one the planning guide's ranges were fitted on. "
                "Locating its readings in those ranges is RECALL, not independent "
                "confirmation -- say so in the plan rather than presenting a band "
                "match as evidence, and prefer the capture-kind labels over the "
                "numbers." if hit else
                "This capture is not in the set the planning guide's ranges were "
                "fitted on, so locating a reading in them is out-of-sample."
            ),
        }

    def run_summary(self, run_id: str) -> dict[str, Any]:
        summary = self.orch.summary(run_id)
        summary["run_md"] = str(self.orch.runs_dir / run_id / "run.md")
        summary["verification"] = self._leaf_verification(summary)
        return summary

    def _leaf_verification(self, summary: dict[str, Any]) -> dict[str, Any]:
        """The fixed step's verdict for every final sparse model in the run.

        A final model that no SparseVerification step read is reported as
        unverified rather than left out, so its absence is visible the way
        `analysis_missing` makes a skipped triage visible in the plan brief.
        """
        verdicts: dict[str, Any] = {}
        steps = summary.get("steps") or []
        for leaf in summary.get("leaves") or []:
            try:
                art = self.store.open(leaf)
            except Exception:
                continue
            if art.type != self.SPARSE_MODEL_TYPE:
                continue
            reads = [
                s for s in steps
                if s.get("module") == self.VERIFIER
                and (s.get("inputs") or {}).get("sparse") == leaf
            ]
            if not reads:
                verdicts[leaf] = {
                    "status": "unverified",
                    "note": f"No {self.VERIFIER} step read this model in this run.",
                }
                continue
            out_id = next(iter((reads[-1].get("outputs") or {}).values()), None)
            try:
                v = self.store.open(out_id) if out_id else None
            except Exception:
                v = None
            verdicts[leaf] = {
                "status": "ran",
                "artifact": out_id,
                "metrics": {n: m.value for n, m in v.manifest.metrics.items()} if v else {},
                "diagnostics": [d.code for d in v.manifest.diagnostics] if v else [],
            }
        # Two solves of one chain are both leaves. Say which one the service kept,
        # so they do not read as two answers.
        for decision in summary.get("second_solves") or []:
            kept = decision.get("kept")
            solved = [(decision.get("first") or {}).get("model")] + [
                a.get("model") for a in decision.get("attempts") or []]
            for m in solved:
                if m in verdicts:
                    verdicts[m]["second_solve"] = (
                        "kept" if m == kept else
                        f"not kept: {kept} was kept instead" if kept else
                        "not kept: every solve of this chain failed or was vetoed")
        return verdicts

    def compare(self, artifact_ids: list[str]) -> dict[str, Any]:
        if len(artifact_ids) < 2:
            raise OrchestratorError("compare needs at least two artifact ids")
        return _compare(self.store, artifact_ids)

    # ===================================================================== #
    # Knowledge
    # ===================================================================== #

    def module_skill(self, name: str, topic: str = "tuning") -> dict[str, Any]:
        spec = self.registry.get(name)
        text = spec.skill(topic)
        if text is None:
            available = spec.describe()["available_skills"]
            raise OrchestratorError(
                f"module '{name}' has no skill '{topic}'. Available: {available}"
            )
        return {"module": name, "topic": topic, "text": text}

    def find_alternatives(
        self,
        *,
        produces: str | None = None,
        consumes: str | None = None,
        not_consuming: str | None = None,
        excluding: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a capability query.

        This is what a `limitations.md` escape compiles to. Escapes are written as
        queries rather than module names precisely so they keep working as the
        module set changes.
        """
        specs = self.registry.find(
            kind=kind,
            produces=produces,
            consumes=consumes,
            not_consuming=not_consuming,
            excluding=excluding,
        )
        return {
            "query": {
                "produces": produces,
                "consumes": consumes,
                "not_consuming": not_consuming,
                "excluding": excluding,
                "kind": kind,
            },
            "matches": [
                {
                    "name": s.name,
                    "version": s.version,
                    "kind": s.kind,
                    "summary": s.summary.strip(),
                    "consumes": {n: sl.type for n, sl in s.consumes.items()},
                    "produces": {n: sl.type for n, sl in s.produces.items()},
                    "gpu": s.resources.gpu,
                }
                for s in specs
            ],
        }

    # The tree was reorganised from knowledge-kind tiers (families/, judgment/,
    # runs/) into moment tiers (plan/, judge/, health/, evidence/). Old topics
    # resolve silently to the file's new home -- a miss costs more than a
    # redirect (when `workflow/` raised on every request, one sweep's readers
    # concluded the whole knowledge base was gone), and the response carries no
    # mention of the old name: the returned `topic` and `path` are simply the
    # current ones, so nothing keeps advertising names that no longer exist.
    _MOVED_TOPICS = {
        "scene_to_pipeline": "plan/scene_to_pipeline",
        "judgment/swap_or_build": "judge/swap_or_build",
        "judgment/tradeoffs": "judge/tradeoffs",
        "judgment/stopping": "health/ladder",
        "judgment/smells": "health/smells",
        "judgment/priors": "evidence/EVIDENCE",
        "runs/EVIDENCE": "evidence/EVIDENCE",
        "runs/INDEX": "evidence/INDEX",
        **{f"families/{s}": f"plan/{s}"
           for s in ("detection", "matching", "tracking", "pose", "sparse",
                     "optimization", "dense")},
    }

    def workflow_skill(self, topic: str) -> dict[str, Any]:
        """Read a cross-cutting guide from the knowledge base."""
        root = self.config.skills_dir
        if root is None:
            raise OrchestratorError("no skills directory is configured")

        clean = topic.removesuffix(".md")
        if clean in self._MOVED_TOPICS:
            topic = self._MOVED_TOPICS[clean]

        candidates = [root / topic, root / f"{topic}.md"]
        # The moment tiers are bare-topic searchable: `ladder` finds
        # `health/ladder.md`. There was a `workflow/` search path here once and
        # it is deliberately gone: it was requested 24 times across a
        # seventeen-capture sweep and raised an error every time, because the six
        # guides it was to hold were never written. A search path for a directory
        # that does not exist is an invitation to a miss; do not add one back
        # without the files.
        candidates += [root / d / f"{topic}.md"
                       for d in ("plan", "judge", "health", "evidence")]
        # docs/ sits beside skills/, not inside it, and the family files and module
        # skills cite `docs/import_lessons.md` and `docs/design/DECISIONS.md`
        # repeatedly as where the per-capture numbers and the full experiments live.
        # Until now neither was reachable through any call, so every magnitude in
        # the stack arrived with no way to check its scope -- and readers said so.
        # A citation a reader cannot follow is worse than no citation: it implies
        # evidence that cannot be examined.
        parent = root.parent
        candidates += [parent / topic, parent / f"{topic}.md",
                       parent / "docs" / f"{topic}.md",
                       parent / "docs" / "design" / f"{topic}.md"]
        for path in candidates:
            if path.is_file():
                return {"topic": topic, "path": str(path),
                        "text": path.read_text(encoding="utf-8")}

        # Enumerate from the SAME places the lookup above searches. Listing only
        # `skills/` was a half-fix: `docs/import_lessons.md` and
        # `docs/design/DECISIONS.md` became fetchable and stayed invisible, so a
        # reader who hit any miss saw an authoritative-looking list without the
        # two documents the family files cite most, and concluded they did not
        # exist. One said so in writing.
        #
        # Topics are reported as they must be TYPED, not as filesystem paths --
        # `judgment/swap_or_build`, not `judgment/swap_or_build.md` -- because the
        # previous list invited a reader to paste back a string the getter does
        # accept only by accident of the `.md` candidate.
        seen, available = set(), []
        for base, prefix in ((root, ""), (parent / "docs", "")):
            if not base.is_dir():
                continue
            for f in sorted(base.rglob("*.md")):
                name = str(f.relative_to(base).with_suffix(""))
                if name not in seen:
                    seen.add(name)
                    available.append(prefix + name)
        raise OrchestratorError(
            f"no skill '{topic}'. Available: {sorted(available)}"
        )

    # ===================================================================== #
    # Authoring
    # ===================================================================== #

    def scaffold_module(
        self,
        name: str,
        *,
        produces: dict[str, str],
        consumes: dict[str, str] | None = None,
        kind: str = "",
        summary: str = "",
        gpu: bool = False,
        pip: list[str] | None = None,
        repo: str = "",
        paper: str = "",
        version: str = "0.1.0",
        force: bool = False,
    ) -> dict[str, Any]:
        result = scaffold_module(
            ScaffoldRequest(
                name=name,
                kind=kind,
                summary=summary,
                consumes=dict(consumes or {}),
                produces=dict(produces),
                gpu=gpu,
                pip=list(pip or []),
                repo=repo,
                paper=paper,
                version=version,
            ),
            self.config.modules_dir,
            force=force,
        )
        return result

    def build_module(self, name: str, *, wait_s: float | None = None) -> dict[str, Any]:
        try:
            spec = self.registry.get(name)
            root, image = spec.root, spec.image
        except ModuleNotFound:
            # Freshly scaffolded and not yet registered -- build it anyway, since
            # registration is exactly what the build is meant to enable.
            slug = to_slug(name)
            root = self.config.modules_dir / slug
            if not (root / "Dockerfile").exists():
                raise
            image = f"sfmstack/{slug.replace('_', '-')}:0.1.0"

        dockerfile = root / "Dockerfile"
        context = self.config.modules_dir.parent

        def work() -> dict[str, Any]:
            result = subprocess.run(
                [self.config.docker, "build", "-t", image,
                 "-f", str(dockerfile), str(context)],
                capture_output=True, text=True,
            )
            tail = (result.stdout + result.stderr).strip().splitlines()[-30:]
            if result.returncode != 0:
                raise OrchestratorError(
                    f"docker build failed for '{name}':\n" + "\n".join(tail)
                )
            return {"image": image, "log_tail": tail}

        handle = self.jobs.submit_and_wait(
            work, kind="build", label=name,
            wait_s=120.0 if wait_s is None else wait_s,
        )
        return handle.to_doc()

    def reload_modules(self) -> dict[str, Any]:
        """Re-scan the modules directory. Call after scaffolding or editing."""
        fresh = ModuleRegistry(types=self.registry.types)
        fresh.load_dir(self.config.modules_dir)
        self.registry = fresh
        self.orch.registry = fresh
        return {
            "modules": fresh.names(),
            "warnings": [str(w) for w in fresh.warnings],
        }

    def _param_vocabulary(self) -> set[str]:
        """Every tunable knob name in the registry.

        The vocabulary is deliberately every module's, not just the one being
        checked: an action legitimately names another stage's knob ("raise the
        matcher's `window`"), and that cross-module pointer is the most common
        shape a real action takes.
        """
        vocab: set[str] = set()
        for name in self.registry.names():
            vocab |= set(self.registry.get(name).params.specs)
        return vocab

    def smoke_test(
        self,
        name: str,
        *,
        run_id: str = "smoke",
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        wait_s: float = 300.0,
    ) -> dict[str, Any]:
        """Run a module once and check what it produced actually validates.

        Also verifies the manifest's own promises: that every metric it declares
        is emitted, that every diagnostic points at a skill file that exists, and
        that the diagnostic the adapter ACTUALLY raised agrees with the one the
        manifest advertises. A tuning section keyed on a metric the module never
        emits is dead text, and that is precisely the drift that made the previous
        system's guidance untrustworthy.

        The manifest and the adapter each hold half of a diagnostic. The manifest
        is the catalogue -- what `sfm_describe_module` shows before anything runs.
        The adapter writes the instance, with the run's numbers in its message,
        and THAT is what reaches the caller. Nothing kept the two in step until
        this ran.
        """
        spec = self.registry.get(name)

        problems: list[str] = []
        for code, diag in spec.diagnostics.items():
            doc = diag.see_also.partition("#")[0]
            if not diag.see_also:
                problems.append(f"diagnostic '{code}' has no see_also")
            elif spec.root and not (spec.root / "skills" / doc).exists():
                problems.append(
                    f"diagnostic '{code}' points at skills/{doc}, which does not exist"
                )
            if diag.metric and diag.metric not in spec.metrics:
                problems.append(
                    f"diagnostic '{code}' names metric '{diag.metric}', which this "
                    f"module does not declare. A renamed metric leaves the alarm "
                    f"pointing at nothing."
                )
        for metric, m in spec.metrics.items():
            if not m.meaning:
                problems.append(f"metric '{metric}' declares no meaning")

        outcome = self.run(
            name, run_id=run_id, inputs=inputs, params=params, wait_s=wait_s
        )

        if outcome["status"] == "ok":
            declared = set(spec.metrics)
            emitted = set(outcome.get("metrics") or {})
            missing = sorted(declared - emitted)
            if missing:
                problems.append(
                    f"declared but not emitted: {missing}. A tuning section keyed "
                    f"on one of these would be dead text."
                )
            undeclared = sorted(emitted - declared)
            if undeclared:
                problems.append(
                    f"emitted but not declared in module.yaml: {undeclared}. The "
                    f"agent has no interpretation for these."
                )
            problems += self._diagnostic_problems(
                spec, outcome, self._param_vocabulary()
            )

        return {
            "module": name,
            "run": outcome,
            "contract_problems": problems,
            "passed": outcome["status"] == "ok" and not problems,
        }

    @staticmethod
    def _diagnostic_problems(
        spec, outcome: dict[str, Any], param_vocab: set[str]
    ) -> list[str]:
        """Check what the adapter raised against what the manifest advertises.

        Only what the run actually exercised. A declared diagnostic that did not
        fire is NOT a problem: one smoke input cannot trip every condition, and
        demanding it would push modules toward diagnostics that always fire --
        which is the opposite of what a diagnostic is for.
        """
        problems: list[str] = []
        metrics = outcome.get("metrics") or {}

        for raised in outcome.get("diagnostics") or []:
            code = raised.get("code", "")
            declared = spec.diagnostics.get(code)

            if declared is None:
                problems.append(
                    f"diagnostic '{code}' was raised but is not declared in "
                    f"module.yaml, so `sfm_describe_module` cannot warn that this "
                    f"module can say it."
                )
                continue

            if raised.get("severity") != declared.severity:
                problems.append(
                    f"diagnostic '{code}' was raised at severity "
                    f"'{raised.get('severity')}'; the manifest declares "
                    f"'{declared.severity}'."
                )
            if raised.get("see_also") != declared.see_also:
                problems.append(
                    f"diagnostic '{code}' was raised pointing at "
                    f"'{raised.get('see_also')}'; the manifest declares "
                    f"'{declared.see_also}'. The manifest's is what the agent read "
                    f"before running."
                )
            if not raised.get("message", "").strip():
                problems.append(
                    f"diagnostic '{code}' was raised with an empty message. The "
                    f"manifest's static text does not travel with the artifact; "
                    f"only this does."
                )
            if not raised.get("suggested_actions"):
                problems.append(
                    f"diagnostic '{code}' was raised with no suggested_actions."
                )
            else:
                # The drift the severity and see_also checks did not reach. A
                # diagnostic can keep its code, severity and pointer while its
                # ACTIONS say something else -- which is what happened to
                # `high_conflict_rate`: the adapter learned to branch on matcher
                # family and name `filter_threshold`, the manifest went on telling
                # readers to lower a `ratio_test` the matcher in use does not have.
                # Three readers in a row were handed it, because
                # `sfm_describe_module` serves the manifest and the procedure
                # requires reading it before the run.
                #
                # Compared as the SET OF PARAMETERS NAMED, not as text. An adapter
                # that fills a measured value into the manifest's advice ("lower
                # detection_threshold from 5e-4") is giving the reader a better
                # version of the same instruction, and 28 of them do. Naming a
                # DIFFERENT knob is the drift, because the knob is the part the
                # reader acts on. Measured across the module set: text equality
                # flagged 85 divergences, almost all of them rewording; this rule
                # flags 12, and every one is a real disagreement about what to do.
                declared_knobs = _named_params(
                    declared.suggested_actions, param_vocab
                )
                raised_knobs = _named_params(
                    raised["suggested_actions"], param_vocab
                )
                if declared_knobs != raised_knobs:
                    problems.append(
                        f"diagnostic '{code}' names parameters "
                        f"{sorted(raised_knobs)} but the manifest declares "
                        f"{sorted(declared_knobs)}. The manifest's is what the "
                        f"agent read before running, so the two must point at the "
                        f"same knobs."
                    )

            # The threshold/band check. One direction only, deliberately: a
            # diagnostic that fires while its own metric reads healthy is
            # unambiguous drift, but the reverse -- outside the band with no
            # diagnostic -- is legitimate hysteresis. A band says "outside the
            # comfortable range"; a warn says "loud enough to interrupt", and
            # those are allowed to sit apart.
            spec_metric = spec.metrics.get(declared.metric) if declared.metric else None
            value = metrics.get(declared.metric) if declared.metric else None
            if spec_metric is not None and spec_metric.healthy and value is not None:
                low, high = spec_metric.healthy
                inside = (low is None or value >= low) and (high is None or value <= high)
                if inside:
                    problems.append(
                        f"diagnostic '{code}' fired while its metric "
                        f"'{declared.metric}' read {value}, inside the healthy band "
                        f"{list(spec_metric.healthy)}. The adapter's threshold and "
                        f"the declared band disagree."
                    )

        return problems
