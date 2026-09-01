"""The orchestrator.

Decides what may run, records what did, and hands execution to a Runner. It owns
the three things neither the agent nor a module should:

    type checking      a pipeline is refused before anything spawns
    identity + cache   the same recipe never runs twice
    the run DAG        every attempt kept, nothing overwritten

Scheduling, GPU brokering, and container lifecycle land here too (step 5); the
Runner seam is already in place for them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sfmkit import Artifact, ArtifactStore, artifact_id

from .errors import ExecutionError, WiringError
from .lineage import compare as _compare
from .modulespec import ModuleSpec
from .registry import ModuleRegistry
from .run_record import Run, Step
from .runner import InProcessRunner, Job, Runner


@dataclass(frozen=True)
class RunResult:
    """What one `run()` produced."""

    step: Step
    outputs: dict[str, Artifact]
    cached: bool

    @property
    def primary(self) -> Artifact:
        """The single output, for the common one-output module."""
        if len(self.outputs) != 1:
            raise ValueError(
                f"module produced {len(self.outputs)} outputs "
                f"({sorted(self.outputs)}); ask for one by name"
            )
        return next(iter(self.outputs.values()))


class Orchestrator:
    def __init__(
        self,
        *,
        store: ArtifactStore,
        registry: ModuleRegistry,
        runner: Runner | None = None,
        runs_dir: str | Path | None = None,
    ):
        self.store = store
        self.registry = registry
        self.runner = runner or InProcessRunner()
        self.runs_dir = Path(runs_dir) if runs_dir else store.runs_dir
        self._runs: dict[str, Run] = {}

    # ------------------------------------------------------------------- runs

    def open_run(
        self, run_id: str, *, scene: str = "", dataset: str = "", goal: str = ""
    ) -> Run:
        if run_id not in self._runs:
            root = self.runs_dir / run_id
            if (root / "run.md").exists():
                # quarantine_corrupt: this path is on the way to running a module, so
                # an unparseable record must not be able to block the run. See
                # Run.open.
                self._runs[run_id] = Run.open(root, quarantine_corrupt=True)
            else:
                run = Run(id=run_id, root=root, scene=scene, dataset=dataset, goal=goal)
                run.save()
                self._runs[run_id] = run
        return self._runs[run_id]

    # ------------------------------------------------------- validate & plan

    def check(
        self,
        module: str,
        *,
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate a proposed step without running it.

        Returns the resolved parameters and the artifact ids the step *would*
        produce -- so a caller can see whether the work is already cached before
        committing to it.
        """
        spec = self.registry.get(module)
        inputs = dict(inputs or {})

        resolved_inputs = self._resolve_inputs(spec, inputs)
        resolved_params = spec.params.resolve(params)
        planned = self._planned_ids(spec, resolved_inputs, resolved_params)

        return {
            "module": spec.name,
            "version": spec.version,
            "params": resolved_params,
            "inputs": {slot: art.id for slot, art in resolved_inputs.items()},
            "outputs": planned,
            # Same test `run` applies, so the preview cannot promise a hit that
            # the run then rejects as stale. A plan that disagrees with the run it
            # previews is worse than no plan.
            "cached": {
                slot: (
                    self.store.exists(aid)
                    and self._built_by_current_image(
                        spec, {slot: self.store.open(aid)}
                    )
                )
                for slot, aid in planned.items()
            },
        }

    def _resolve_inputs(
        self, spec: ModuleSpec, inputs: dict[str, str]
    ) -> dict[str, Artifact]:
        """Turn ids into artifacts, checking the wiring. Nothing spawns until
        this passes."""
        unknown = sorted(set(inputs) - set(spec.consumes))
        if unknown:
            raise WiringError(
                f"module '{spec.name}' has no input slot(s) {unknown}. "
                f"Accepts: {sorted(spec.consumes)}."
            )

        resolved: dict[str, Artifact] = {}
        for slot_name, slot in spec.consumes.items():
            if slot_name not in inputs:
                if slot.required:
                    raise WiringError(
                        f"module '{spec.name}' requires input '{slot_name}' of type "
                        f"'{slot.type}'. Given: {sorted(inputs) or 'nothing'}."
                    )
                continue

            art = self.store.open(inputs[slot_name])
            if art.type != slot.type:
                producers = self.registry.find(produces=slot.type)
                hint = (
                    f" Modules producing '{slot.type}': "
                    f"{[m.name for m in producers]}."
                    if producers
                    else ""
                )
                raise WiringError(
                    f"module '{spec.name}' input '{slot_name}' expects "
                    f"'{slot.type}' but artifact {art.id} is '{art.type}'.{hint}"
                )
            resolved[slot_name] = art

        return resolved

    def _planned_ids(
        self,
        spec: ModuleSpec,
        inputs: dict[str, Artifact],
        params: dict[str, Any],
    ) -> dict[str, str]:
        """The ids this step will produce. Computed the same way `Ctx.output`
        does, so a cache hit here is authoritative."""
        input_ids = [a.id for a in inputs.values()]
        return {
            slot: artifact_id(
                type=payload_type,
                module=spec.name,
                module_version=spec.version,
                slot=slot,
                params=params,
                inputs=input_ids,
            )
            for slot, payload_type in spec.output_types.items()
        }

    def _built_by_current_image(
        self, spec: ModuleSpec, outputs: dict[str, Artifact]
    ) -> bool:
        """Is this cache entry the CURRENT software's answer, or an older one?

        An artifact id is derived from the recipe -- module, version, slot, params,
        inputs -- and none of those changes when a module's code does. The
        convention was that a human bumps `module_version` whenever a metric set or
        a published band changes, and a convention is not a mechanism: an
        uncommitted version that has already produced artifacts will serve them
        back after the code behind it is fixed. That is not hypothetical, it
        happened twice while fixing this stage, and both times the stale value was
        a metric reading `None` that the new code always populates -- which reads
        as a code defect and costs a debugging session to rule out.

        The digest is what makes this answerable: a tag is mutable, so
        `sfmstack/foo:1.1.0` is a different image before and after a rebuild while
        being the same string. `Provenance.image_digest` has recorded the artifact's
        side of that comparison since it was introduced; nothing had ever read it.

        Conservative in both directions. A missing digest on either side is not
        evidence of staleness -- in-process runs have no image at all -- so the
        entry is served. Only two digests that both exist AND differ are a miss.
        """
        live = self.runner.image_digest(spec)
        if not live:
            return True
        for art in outputs.values():
            made = art.manifest.produced_by
            built_with = made.image_digest if made else ""
            if built_with and built_with != live:
                return False
        return True

    # -------------------------------------------------------------- execution

    def run(
        self,
        module: str,
        *,
        run_id: str,
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        device: str | None = None,
        force: bool = False,
        on_progress=None,
    ) -> RunResult:
        spec = self.registry.get(module)
        run = self.open_run(run_id)

        resolved_inputs = self._resolve_inputs(spec, dict(inputs or {}))
        resolved_params = spec.params.resolve(params)
        planned = self._planned_ids(spec, resolved_inputs, resolved_params)

        scene = self._scene_of(resolved_inputs, run)

        if not force and all(self.store.exists(a) for a in planned.values()):
            outputs = {slot: self.store.open(a) for slot, a in planned.items()}
            if self._built_by_current_image(spec, outputs):
                self._bind_scene(run, outputs)
                step = run.add(
                    self._step(spec, resolved_inputs, resolved_params, outputs, cached=True)
                )
                return RunResult(step=step, outputs=outputs, cached=True)

        job = Job(
            spec=spec,
            inputs=resolved_inputs,
            params=resolved_params,
            run=run_id,
            scene=scene,
            device=device,
            on_progress=on_progress,
        )

        started = time.monotonic()
        try:
            outputs = self.runner.run(job, self.store)
        except ExecutionError as e:
            run.add(
                Step(
                    index=-1,
                    module=spec.name,
                    module_version=spec.version,
                    params=resolved_params,
                    inputs={s: a.id for s, a in resolved_inputs.items()},
                    status="failed",
                    duration_s=round(time.monotonic() - started, 3),
                    error=f"{type(e.cause).__name__}: {e.cause}",
                )
            )
            raise

        elapsed = round(time.monotonic() - started, 3)
        self._bind_scene(run, outputs)
        step = run.add(
            self._step(
                spec, resolved_inputs, resolved_params, outputs, duration_s=elapsed
            )
        )
        return RunResult(step=step, outputs=outputs, cached=False)

    @staticmethod
    def _bind_scene(run: Run, outputs: dict[str, Artifact]) -> None:
        """A source module produces the scene rather than consuming one."""
        if run.scene:
            return
        for art in outputs.values():
            if art.type.startswith("scene/"):
                run.scene = art.id
                run.save()
                return

    def _scene_of(self, inputs: dict[str, Artifact], run: Run) -> str:
        """Which scene this step belongs to, binding the run to it on first sight.

        The run's scene is what `runs/INDEX.md` is keyed on for trait-based
        retrieval, so it has to be recorded rather than left to be reconstructed
        by walking every step's inputs later.
        """
        scene = run.scene
        for art in inputs.values():
            if art.type.startswith("scene/"):
                scene = art.id
                break
            if art.manifest.scene:
                scene = art.manifest.scene
                break

        if scene and not run.scene:
            run.scene = scene
            run.save()
        return scene

    @staticmethod
    def _step(
        spec: ModuleSpec,
        inputs: dict[str, Artifact],
        params: dict[str, Any],
        outputs: dict[str, Artifact],
        *,
        cached: bool = False,
        duration_s: float | None = None,
    ) -> Step:
        metrics: dict[str, Any] = {}
        diagnostics: list[str] = []
        for art in outputs.values():
            metrics.update({n: m.value for n, m in art.manifest.metrics.items()})
            diagnostics.extend(d.code for d in art.manifest.diagnostics)

        return Step(
            index=-1,
            module=spec.name,
            module_version=spec.version,
            params=params,
            inputs={s: a.id for s, a in inputs.items()},
            outputs={s: a.id for s, a in outputs.items()},
            status="ok",
            cached=cached,
            duration_s=duration_s,
            metrics=metrics,
            diagnostics=sorted(set(diagnostics)),
        )

    # ----------------------------------------------------------------- replay

    def replay(
        self,
        *,
        run_id: str,
        from_artifact: str,
        overrides: dict[str, Any] | None = None,
        device: str | None = None,
    ) -> list[RunResult]:
        """Re-run the step that produced `from_artifact`, then every recorded
        step downstream of it, substituting the regenerated inputs.

        Going back upstream is common -- a tracker's numbers often say the
        matcher is at fault -- and without this it costs the agent one call per
        remaining stage plus the bookkeeping to rewire them. The DAG branches;
        the original chain is untouched and still comparable.
        """
        run = self.open_run(run_id)
        origin = run.producer_of(from_artifact)
        if origin is None:
            raise WiringError(
                f"run '{run_id}' has no step producing artifact '{from_artifact}'"
            )

        results: list[RunResult] = []
        remap: dict[str, str] = {}

        first = self.run(
            origin.module,
            run_id=run_id,
            inputs=dict(origin.inputs),
            params={**origin.params, **(overrides or {})},
            device=device,
        )
        first.step.replay_of = origin.index
        run.save()
        results.append(first)
        for slot, new_id in first.step.outputs.items():
            if (old_id := origin.outputs.get(slot)) is not None:
                remap[old_id] = new_id

        for step in run.downstream_of(set(origin.outputs.values())):
            if step.index >= first.step.index:
                continue  # already part of this replay
            rewired = {s: remap.get(a, a) for s, a in step.inputs.items()}
            result = self.run(
                step.module,
                run_id=run_id,
                inputs=rewired,
                params=step.params,
                device=device,
            )
            result.step.replay_of = step.index
            run.save()
            results.append(result)
            for slot, new_id in result.step.outputs.items():
                if (old_id := step.outputs.get(slot)) is not None:
                    remap[old_id] = new_id

        return results

    # ------------------------------------------------------------- inspection

    def compare(self, artifact_ids: list[str]) -> dict[str, Any]:
        return _compare(self.store, artifact_ids)

    def summary(self, run_id: str) -> dict[str, Any]:
        run = self.open_run(run_id)
        return {
            "run": run.id,
            "scene": run.scene,
            "goal": run.goal,
            "steps": [s.to_doc() for s in run.steps],
            "leaves": run.leaves(),
        }
