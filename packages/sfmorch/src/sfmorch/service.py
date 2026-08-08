"""The tool surface, as plain Python.

Every MCP tool is a thin call into a method here. Keeping the logic
framework-independent means the surface is testable without MCP transport, and a
change in the SDK touches one adapter file rather than fourteen tools.

Return shapes are chosen for an agent reading them, not for completeness. A run
returns its metrics and diagnostics inline, because the alternative is a second
round trip on every single step and the metrics are the whole reason to look.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sfmkit import ArtifactStore

from .errors import ModuleNotFound, OrchestratorError
from .jobs import JobHandle, JobManager
from .lineage import compare as _compare
from .orchestrator import Orchestrator
from .registry import ModuleRegistry
from .scaffold import ScaffoldRequest, scaffold_module, to_slug

DEFAULT_INLINE_WAIT = 20.0


@dataclass
class ServiceConfig:
    modules_dir: Path
    store_root: Path
    skills_dir: Path | None = None
    inline_wait_s: float = DEFAULT_INLINE_WAIT
    docker: str = "docker"


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
        self.orch.check(module, inputs=inputs, params=params)  # refuse early, in-band

        def work() -> dict[str, Any]:
            result = self.orch.run(
                module, run_id=run_id, inputs=inputs, params=params, force=force
            )
            return self._run_payload(result)

        handle = self.jobs.submit_and_wait(
            work,
            kind="run",
            label=module,
            run_id=run_id,
            wait_s=self.config.inline_wait_s if wait_s is None else wait_s,
        )
        return handle.to_doc()

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
        }
        if full:
            doc["artifact_md"] = (art.root / "artifact.md").read_text(encoding="utf-8")
        return doc

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
        is emitted, and that every diagnostic points at a skill file that exists.
        A tuning section keyed on a metric the module never emits is dead text,
        and that is precisely the drift that made the previous system's guidance
        untrustworthy.
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

        return {
            "module": name,
            "run": outcome,
            "contract_problems": problems,
            "passed": outcome["status"] == "ok" and not problems,
        }
