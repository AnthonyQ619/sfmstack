"""MCP adapter.

Deliberately thin: every tool is a one-line call into `SfmService`. All the logic
lives there so it is testable without MCP transport, and an SDK change touches
this file alone rather than nineteen tools.

Nineteen tools in five stable categories -- discovery, execution, inspection,
knowledge, authoring -- and the count does not grow with the module count.
Modules are *discovered* through `sfm_list_modules` / `sfm_describe_module`,
never enumerated as tools, so this surface is the same at 2 modules and at 200.

It grows, rarely, and on two axes that are not the module count.

The number of PAYLOAD KINDS the surface can carry: `sfm_artifact_image` was the
eighteenth, because artifacts could always hold pictures and there was no way to
hand one to the caller, so anything that needed looking at required filesystem
access outside this protocol.

And a STEP OF THE LOOP that had no tool at all: `sfm_plan_brief` is the
nineteenth. Choosing the first pipeline was the one step with nothing behind it
-- the type system says what CAN follow, the family files say what SHOULD, and
nothing joined either to the numbers step 2 produces.

Which files each tool reads: docs/mcp-tools.md.

    python -m sfmorch.mcp_server --modules ./modules --store ./store [--docker]
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sfmkit import ArtifactStore

from .backends import DockerBackend
from .container import ContainerRunner
from .gpu import GpuBroker
from .jobs import JobManager
from .orchestrator import Orchestrator
from .registry import ModuleRegistry
from .runner import InProcessRunner
from .service import ServiceConfig, SfmService

INSTRUCTIONS = """\
Structure-from-Motion pipelines built from containerized modules.

Modules are discovered, not listed as tools. Start with `sfm_list_modules` and
`sfm_describe_module`; both are cheap.

The loop:
  1. Build a scene with `SceneLoader`, then characterise it. Run `SceneTriage`
     and `SceneMotion` BEFORE `SceneDescription`, not alongside it: the describer
     opens three frames at full resolution and one of them is a free choice, and
     the per-image series those two modules produce are what make that choice by
     evidence rather than by eye. Every call reports its metrics and diagnostics
     inline -- you do not need a second call to see how it went.
  2. `sfm_run` returns metric VALUES. Their `direction` and `healthy` band live
     in `sfm_describe_module(name)` and in the artifact's own frontmatter, not in
     the run response -- so a bare number is a measurement, and the DIAGNOSTIC is
     what tells you it is out of band.
  3. A diagnostic's `see_also` names the exact curated section that addresses it.
     Fetch it with `sfm_module_skill`.
  4. `sfm_artifact_image` hands back a picture an artifact carries, so questions
     a number cannot answer -- what is actually in this scene -- do not need
     filesystem access outside this protocol.
  5. Before choosing any module, `sfm_plan_brief(scene_id)`. It gathers the
     analysis, the guide that says how to read those numbers, the family file for
     each stage and the live menu, so the first pipeline is argued once against a
     complete picture. It prepares; the argument is yours.
  6. Re-running with different parameters keeps BOTH results. Use `sfm_compare`
     to put them side by side -- it also reports where two lineages diverge, so a
     difference inherited from three stages upstream is not credited to the knob
     you just turned.
  7. When metrics suggest the real problem is upstream, `sfm_replay` re-runs that
     step and everything downstream in one call.
  8. When tuning has bottomed out, `sfm_module_skill(name, "limitations")` gives
     the failure signature and a capability query; `sfm_find_alternatives` runs
     that query against the live registry.
  9. If nothing fits, `sfm_scaffold_module` -> implement the adapter ->
     `sfm_build_module` -> `sfm_smoke_test`.

Type checking happens before anything is spawned, so a wiring mistake is a fast
refusal that names the modules which would satisfy the slot -- not a crash
several minutes in.
"""


def build_service(
    *,
    modules_dir: Path,
    store_root: Path,
    skills_dir: Path | None = None,
    use_docker: bool = False,
    mounts: list[str] | None = None,
    gpus: list[int] | None = None,
) -> SfmService:
    registry = ModuleRegistry()
    registry.load_dir(modules_dir)

    runner = (
        ContainerRunner(
            DockerBackend(mounts=mounts or []), gpus=GpuBroker(devices=gpus)
        )
        if use_docker
        else InProcessRunner()
    )

    store = ArtifactStore(store_root)
    return SfmService(
        config=ServiceConfig(
            modules_dir=modules_dir, store_root=store_root, skills_dir=skills_dir
        ),
        orchestrator=Orchestrator(store=store, registry=registry, runner=runner),
        registry=registry,
        jobs=JobManager(),
    )


def build_server(service: SfmService):
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer(name="sfmstack", instructions=INSTRUCTIONS, version="0.1.0")

    # ------------------------------------------------------------ discovery

    @mcp.tool()
    def sfm_list_modules(
        kind: str | None = None,
        consumes: str | None = None,
        produces: str | None = None,
    ) -> dict[str, Any]:
        """List available modules, optionally filtered by payload type.

        `consumes`/`produces` take a payload type such as 'tracks/v1'. Use them to
        answer "what can follow this?" without guessing at names.
        """
        return service.list_modules(kind=kind, consumes=consumes, produces=produces)

    @mcp.tool()
    def sfm_describe_module(name: str) -> dict[str, Any]:
        """Full contract for one module: parameter schema with defaults and
        ranges, what each metric means and which direction is good, the
        diagnostics it can raise, and its SKILL.md."""
        return service.describe_module(name)

    # ------------------------------------------------------------ execution

    @mcp.tool()
    def sfm_check(
        module: str,
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate a step without running it, and report whether the result is
        already cached. Cheap way to plan a pipeline before committing GPU time."""
        return service.check(module, inputs=inputs, params=params)

    @mcp.tool()
    def sfm_run(
        module: str,
        run_id: str,
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        force: bool = False,
        wait_s: float | None = None,
    ) -> dict[str, Any]:
        """Run one module. Returns metrics and diagnostics inline.

        Fast modules complete within this call; slow ones return status 'running'
        with a job_id to poll via `sfm_job`. Identical work is not repeated --
        pass force=True to override. Different parameters always produce a new
        artifact and keep the old one.
        """
        return service.run(
            module, run_id=run_id, inputs=inputs, params=params,
            force=force, wait_s=wait_s,
        )

    @mcp.tool()
    def sfm_replay(
        run_id: str,
        from_artifact: str,
        overrides: dict[str, Any] | None = None,
        wait_s: float | None = None,
    ) -> dict[str, Any]:
        """Re-run the step that produced an artifact, plus everything downstream,
        with the given parameter overrides.

        For when metrics indicate the real problem is upstream. The original
        branch is left intact and remains comparable.
        """
        return service.replay(
            run_id=run_id, from_artifact=from_artifact,
            overrides=overrides, wait_s=wait_s,
        )

    @mcp.tool()
    def sfm_job(job_id: str, wait_s: float = 0.0) -> dict[str, Any]:
        """Poll a job. `wait_s` blocks up to that long for it to finish."""
        return service.job(job_id, wait_s=wait_s)

    @mcp.tool()
    def sfm_list_jobs(
        run_id: str | None = None, status: str | None = None, limit: int = 25
    ) -> dict[str, Any]:
        """Recent jobs, newest first, with their status and metrics.

        Use it to pick up work left running from an earlier turn, or to see what
        is still in flight when several runs were launched in parallel. Filter by
        `run_id` for one pipeline, or by `status` ('running', 'failed') to find
        what needs attention.
        """
        return service.list_jobs(run_id=run_id, status=status, limit=limit)

    # ----------------------------------------------------------- inspection

    @mcp.tool()
    def sfm_artifact(artifact_id: str, full: bool = True) -> dict[str, Any]:
        """Read an artifact: metrics, diagnostics, provenance, array inventory,
        and the narrative its producer wrote."""
        return service.artifact(artifact_id, full=full)

    @mcp.tool()
    def sfm_artifact_image(artifact_id: str, name: str = "") -> Any:
        """Return an image an artifact carries, as a picture you can look at.

        For the cases a number cannot answer -- what is actually in this scene,
        what does this reconstruction look like. `SceneDescription` renders a
        contact sheet for exactly this; `name` is relative to the artifact's data
        directory, e.g. 'browse/contact_sheet.jpg'. Omit it to list what is there,
        or when the artifact carries only one image.

        A scene's own working images are reachable the same way, so a single frame
        can be inspected at full resolution without any module in between.
        """
        doc = service.artifact_image(artifact_id, name=name)
        if "path" not in doc:
            return doc  # a listing, not a picture

        from mcp.server.mcpserver.utilities.types import Image

        # Picture plus provenance: without the second block the caller has an
        # image and no record of which artifact it came out of.
        return [Image(path=doc["path"]), {k: v for k, v in doc.items() if k != "path"}]

    @mcp.tool()
    def sfm_plan_brief(
        scene_id: str, stages: list[str] | None = None
    ) -> dict[str, Any]:
        """Everything needed to turn a scene analysis into a first pipeline plan.

        Call this after `SceneTriage`, `SceneMotion` and `SceneDescription` have
        run, and before choosing any module. It gathers, in one response:

          - the scene's own bookkeeping and its image names, and every
            `scene_analysis/v1` artifact produced against it -- metrics,
            diagnostics, narrative, and the per-frame and per-pair SERIES those
            metrics are summaries of. Every analysis metric is a median, a p75 or
            a fraction, and the advice attached to them is per-frame: open the
            soft frame before dropping it, keep the planar pair out of the seed.
            `series` is what makes that followable; indices are positions in
            `scene.images`, and each series carries the index it was written
            against, which is not always the same one
          - `skills/scene_to_pipeline.md`, which is how those numbers are read:
            the ranges measured across every scene so far, what each metric can
            and cannot tell you, and the traps that have already caught someone
          - the family file for each pipeline stage, which is what says which
            member of that stage to reach for
          - the live menu of modules consuming `scene/v1`
          - the shape the plan should take

        It does NOT decide. There is no model here; the argument is yours to
        make. What this closes is a measured gap -- of the 29 metrics the analysis
        modules produce, two are named anywhere in the family files, so the
        families speak in adjectives while step 2 speaks in numbers.

        `stages` defaults to detection, matching, tracking, pose, sparse and
        optimization. Pass it to narrow the call, or to add 'dense'.
        """
        return service.plan_brief(scene_id, stages=stages)

    @mcp.tool()
    def sfm_run_summary(run_id: str) -> dict[str, Any]:
        """Every step attempted in a run, with parameters and metrics, plus the
        leaf artifacts nothing consumed."""
        return service.run_summary(run_id)

    @mcp.tool()
    def sfm_compare(artifact_ids: list[str]) -> dict[str, Any]:
        """Compare artifacts side by side, and report where their lineages
        diverge.

        The divergence report matters: without it, two results differing because
        of a change three stages upstream look like evidence about the parameter
        under test.
        """
        return service.compare(artifact_ids)

    # ------------------------------------------------------------ knowledge

    @mcp.tool()
    def sfm_module_skill(name: str, topic: str = "tuning") -> dict[str, Any]:
        """Curated guidance for a module.

        'tuning' is indexed by observed metric state and gives the gradient for
        moving it. 'limitations' gives failure signatures and when to switch
        capability instead of tuning. Also 'artifact' and 'sources'.
        """
        return service.module_skill(name, topic)

    @mcp.tool()
    def sfm_find_alternatives(
        produces: str | None = None,
        consumes: str | None = None,
        not_consuming: str | None = None,
        excluding: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a capability query against the live registry.

        This is what a limitations.md escape compiles to. `not_consuming` is the
        important one: "produces tracks/v1 but does NOT consume
        pairwise_matches/v1" means "a direct tracker, because the matcher is the
        problem".
        """
        return service.find_alternatives(
            produces=produces, consumes=consumes,
            not_consuming=not_consuming, excluding=excluding, kind=kind,
        )

    @mcp.tool()
    def sfm_workflow_skill(topic: str) -> dict[str, Any]:
        """Read a cross-cutting workflow guide or judgment document."""
        return service.workflow_skill(topic)

    # ------------------------------------------------------------ authoring

    @mcp.tool()
    def sfm_scaffold_module(
        name: str,
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
        """Generate a new module: manifest, adapter stub, Dockerfile, skill stubs.

        `produces`/`consumes` map slot names to payload types. The adapter stub
        raises until implemented -- a scaffolded module that silently produces an
        empty artifact is worse than one that refuses to start.
        """
        return service.scaffold_module(
            name, produces=produces, consumes=consumes, kind=kind, summary=summary,
            gpu=gpu, pip=pip, repo=repo, paper=paper, version=version, force=force,
        )

    @mcp.tool()
    def sfm_build_module(name: str, wait_s: float | None = None) -> dict[str, Any]:
        """Build a module's container image from its Dockerfile.

        Required after scaffolding, and after any change to the module's code or
        dependencies -- the image bakes in both, and the server refuses a job
        whose requested version does not match what the image actually serves.
        """
        return service.build_module(name, wait_s=wait_s)

    @mcp.tool()
    def sfm_reload_modules() -> dict[str, Any]:
        """Re-scan the modules directory. Call after scaffolding or editing a
        manifest to make the change visible."""
        return service.reload_modules()

    @mcp.tool()
    def sfm_smoke_test(
        name: str,
        run_id: str = "smoke",
        inputs: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a module once and check its output validates, plus that its
        manifest keeps its own promises: every declared metric is actually
        emitted, and every diagnostic points at a skill file that exists."""
        return service.smoke_test(name, run_id=run_id, inputs=inputs, params=params)

    return mcp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sfmorch.mcp_server")
    ap.add_argument("--modules", default="modules", type=Path)
    ap.add_argument("--store", default="store", type=Path)
    ap.add_argument("--skills", default=None, type=Path)
    ap.add_argument("--docker", action="store_true",
                    help="run modules in containers rather than in-process")
    ap.add_argument("--mount", action="append", default=[],
                    help="host path to mount read-only into module containers "
                         "(repeatable); dataset directories go here")
    ap.add_argument("--gpu", action="append", type=int, default=None,
                    help="device index available for leasing (repeatable)")
    args = ap.parse_args(argv)

    service = build_service(
        modules_dir=args.modules.resolve(),
        store_root=args.store.resolve(),
        skills_dir=args.skills.resolve() if args.skills else None,
        use_docker=args.docker,
        mounts=args.mount,
        gpus=args.gpu,
    )
    build_server(service).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
