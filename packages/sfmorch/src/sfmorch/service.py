"""The tool surface, as plain Python.

Every MCP tool is a thin call into a method here. Keeping the logic
framework-independent means the surface is testable without MCP transport, and a
change in the SDK touches one adapter file rather than nineteen tools.

Return shapes are chosen for an agent reading them, not for completeness. A run
returns its metrics and diagnostics inline, because the alternative is a second
round trip on every single step and the metrics are the whole reason to look.
"""

from __future__ import annotations

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

# The guide that translates step 2's numbers into the adjectives the family files
# are written in. Named here rather than inlined so the prose can be revised
# without touching the orchestrator, which is the same arrangement every other
# curated document has.
PLANNING_GUIDE = "scene_to_pipeline"

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
        """Machine contract plus the module's SKILL.md, in one call.

        Deeper curation (tuning, limitations, sources) is fetched separately --
        progressive disclosure, so context cost scales with how stuck the caller
        is rather than with the module count.
        """
        return self.registry.get(name).describe()

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
            return self._run_payload(result)

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
                "replayed": [self._run_payload(r) for r in results],
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

    @staticmethod
    def _run_payload(result) -> dict[str, Any]:
        step = result.step
        notes = {
            slot: art.manifest.body.strip()
            for slot, art in result.outputs.items()
            if art.manifest.body.strip()
        }
        return {
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
        analysis modules produce, exactly two are named anywhere in
        `skills/families/`. The families speak in adjectives and step 2 speaks in
        numbers, and `skills/scene_to_pipeline.md` is the translation.
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
        analyses.sort(key=lambda a: (a["module"], a["module_version"]))

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
                        f"{live}; re-running at the same params will not "
                        f"reproduce those artifacts)")
                if line not in stale:
                    stale.append(line)
        built.sort(key=lambda a: (a["type"], a["module"], a["artifact"]))

        wanted = list(stages or PLANNING_STAGES)
        families, missing = {}, []
        for stage in wanted:
            try:
                families[stage] = self.workflow_skill(f"families/{stage}")["text"]
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
    _CORPUS_MARKER = "skills/runs/CORPUS.txt"

    def _corpus_membership(self, scene) -> dict[str, Any]:
        root = self.config.skills_dir
        marker = (root / "runs" / "CORPUS.txt") if root else None
        if marker is None or not marker.exists():
            return {"known": False, "note": "no corpus record available"}
        entries = [ln.strip() for ln in marker.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.startswith("#")]
        source = str(scene.manifest.produced_by.params.get("image_dir", ""))
        hit = next((e for e in entries if e and e in source), None)
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
        return summary

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

    def workflow_skill(self, topic: str) -> dict[str, Any]:
        """Read a cross-cutting guide or judgment document from the knowledge base."""
        root = self.config.skills_dir
        if root is None:
            raise OrchestratorError("no skills directory is configured")

        candidates = [root / topic, root / f"{topic}.md"]
        candidates += [root / d / f"{topic}.md" for d in ("workflow", "judgment")]
        for path in candidates:
            if path.is_file():
                return {"topic": topic, "path": str(path),
                        "text": path.read_text(encoding="utf-8")}

        available = sorted(
            str(p.relative_to(root)) for p in root.rglob("*.md")
        )
        raise OrchestratorError(f"no skill '{topic}'. Available: {available}")

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
            problems += self._diagnostic_problems(spec, outcome)

        return {
            "module": name,
            "run": outcome,
            "contract_problems": problems,
            "passed": outcome["status"] == "ok" and not problems,
        }

    @staticmethod
    def _diagnostic_problems(spec, outcome: dict[str, Any]) -> list[str]:
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
