"""`runs/<run_id>/run.md` -- the attempt DAG.

Not a linear history. Because artifacts are immutable and ids come from the
recipe, re-running a module with new parameters appends a step and keeps the
earlier one, so the record is a tree of attempts. That is the substrate the
driving agent compares over, and the raw material distillation reads.

Same one-file convention as an artifact: YAML frontmatter for machines, markdown
body for whoever is reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sfmkit.manifest import split_frontmatter


@dataclass
class Step:
    index: int
    module: str
    module_version: str
    params: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, str] = field(default_factory=dict)  # slot -> artifact id
    outputs: dict[str, str] = field(default_factory=dict)  # slot -> artifact id
    status: str = "ok"  # ok | failed | cached
    cached: bool = False
    duration_s: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    error: str = ""
    replay_of: int | None = None

    def to_doc(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "index": self.index,
            "module": self.module,
            "module_version": self.module_version,
            "params": self.params,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "status": self.status,
        }
        if self.cached:
            doc["cached"] = True
        if self.duration_s is not None:
            doc["duration_s"] = self.duration_s
        if self.metrics:
            doc["metrics"] = self.metrics
        if self.diagnostics:
            doc["diagnostics"] = self.diagnostics
        if self.error:
            doc["error"] = self.error
        if self.replay_of is not None:
            doc["replay_of"] = self.replay_of
        return doc

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "Step":
        return cls(
            index=int(doc["index"]),
            module=str(doc["module"]),
            module_version=str(doc.get("module_version", "")),
            params=doc.get("params") or {},
            inputs=doc.get("inputs") or {},
            outputs=doc.get("outputs") or {},
            status=str(doc.get("status", "ok")),
            cached=bool(doc.get("cached", False)),
            duration_s=doc.get("duration_s"),
            metrics=doc.get("metrics") or {},
            diagnostics=list(doc.get("diagnostics") or []),
            error=str(doc.get("error", "")),
            replay_of=doc.get("replay_of"),
        )


@dataclass
class Run:
    id: str
    root: Path
    scene: str = ""
    dataset: str = ""
    goal: str = ""
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # -------------------------------------------------------------- mutation

    def add(self, step: Step) -> Step:
        step.index = len(self.steps)
        self.steps.append(step)
        self.save()
        return step

    def note(self, text: str) -> None:
        self.notes.append(text.strip())
        self.save()

    # --------------------------------------------------------------- queries

    def producer_of(self, artifact_id: str) -> Step | None:
        """The step that produced an artifact. Latest wins if it was re-run."""
        for step in reversed(self.steps):
            if artifact_id in step.outputs.values():
                return step
        return None

    def downstream_of(self, artifact_ids: set[str]) -> list[Step]:
        """Steps that consumed any of these artifacts, transitively, in order.

        This is what `replay` walks: change something upstream and these are the
        steps that have to be re-executed to get a comparable leaf.
        """
        tainted = set(artifact_ids)
        out: list[Step] = []
        for step in self.steps:
            if step.status == "failed":
                continue
            if tainted & set(step.inputs.values()):
                out.append(step)
                tainted |= set(step.outputs.values())
        return out

    def leaves(self) -> list[str]:
        """Artifacts nothing else in this run consumed."""
        consumed = {a for s in self.steps for a in s.inputs.values()}
        produced = [a for s in self.steps for a in s.outputs.values()]
        return [a for a in produced if a not in consumed]

    # -------------------------------------------------------------- file I/O

    @property
    def path(self) -> Path:
        return self.root / "run.md"

    def to_doc(self) -> dict[str, Any]:
        return {
            "run": self.id,
            "scene": self.scene,
            "dataset": self.dataset,
            "goal": self.goal,
            "steps": [s.to_doc() for s in self.steps],
        }

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        front = yaml.safe_dump(
            self.to_doc(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=None,
            width=100,
        )
        body = "\n\n".join([self._table(), *self.notes]).strip()
        self.path.write_text(f"---\n{front}---\n\n{body}\n", encoding="utf-8")

    def _table(self) -> str:
        if not self.steps:
            return "*No steps yet.*"
        lines = [
            "| # | Module | Params | Status | Key metrics |",
            "| --- | --- | --- | --- | --- |",
        ]
        for s in self.steps:
            params = ", ".join(f"{k}={v}" for k, v in sorted(s.params.items())) or "—"
            metrics = (
                ", ".join(f"{k}={v}" for k, v in sorted(s.metrics.items())) or "—"
            )
            status = s.status + (" (cached)" if s.cached else "")
            lines.append(
                f"| {s.index} | {s.module} | {params} | {status} | {metrics} |"
            )
        return "\n".join(lines)

    @classmethod
    def open(cls, root: str | Path) -> "Run":
        root = Path(root)
        path = root / "run.md"
        if not path.exists():
            raise FileNotFoundError(f"no run record at {path}")
        doc, body = split_frontmatter(path.read_text(encoding="utf-8"), origin=str(path))
        return cls(
            id=str(doc.get("run", root.name)),
            root=root,
            scene=str(doc.get("scene", "")),
            dataset=str(doc.get("dataset", "")),
            goal=str(doc.get("goal", "")),
            steps=[Step.from_doc(s) for s in (doc.get("steps") or [])],
        )
