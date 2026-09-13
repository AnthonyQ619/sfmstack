"""`runs/<run_id>/run.md` -- the attempt DAG.

Not a linear history. Because artifacts are immutable and ids come from the
recipe, re-running a module with new parameters appends a step and keeps the
earlier one, so the record is a tree of attempts. That is the substrate the
driving agent compares over, and the raw material distillation reads.

Same one-file convention as an artifact: YAML frontmatter for machines, markdown
body for whoever is reading.
"""

from __future__ import annotations

import os

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
    # The service's second-solve decisions: which chain was solved again, at what
    # window, and which model it kept. Kept in the record rather than recomputed,
    # because the decision rests on verdicts the steps alone do not carry.
    second_solves: list[dict[str, Any]] = field(default_factory=list)

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

    def leaves(self, ignore_consumers: set[str] | frozenset[str] = frozenset()) -> list[str]:
        """Artifacts nothing else in this run consumed.

        `ignore_consumers` names modules whose reading an artifact does not stop it
        being a result. An analysis that reads a model -- the verification the
        service runs after every refinement -- does not supersede that model, and
        without this the run's final model would vanish from its own leaves the
        moment it was checked.
        """
        consumed = {
            a for s in self.steps if s.module not in ignore_consumers
            for a in s.inputs.values()
        }
        produced = [a for s in self.steps for a in s.outputs.values()]
        return [a for a in produced if a not in consumed]

    # -------------------------------------------------------------- file I/O

    @property
    def path(self) -> Path:
        return self.root / "run.md"

    def to_doc(self) -> dict[str, Any]:
        doc = {
            "run": self.id,
            "scene": self.scene,
            "dataset": self.dataset,
            "goal": self.goal,
            "steps": [s.to_doc() for s in self.steps],
        }
        if self.second_solves:
            doc["second_solves"] = self.second_solves
        return doc

    def save(self) -> None:
        """Write the record atomically: temp file in the same directory, then rename.

        A bare write_text here was a permanent-failure bug. A process killed
        mid-write -- or, as happened, a full filesystem -- left a truncated file
        whose frontmatter would not parse, so `open` raised and EVERY subsequent
        run under that id died before reaching the module. A transient container
        race became a dead run_id that had to be deleted by hand.

        os.replace is atomic within a filesystem, so a reader sees either the whole
        old record or the whole new one. Under ENOSPC the temp write fails and the
        previous record survives intact, which is the behaviour that matters: losing
        an update is recoverable, losing the file is not.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        front = yaml.safe_dump(
            self.to_doc(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=None,
            width=100,
        )
        body = "\n\n".join(
            part for part in [self._table(), self._second_solve_lines(), *self.notes]
            if part
        ).strip()
        text = f"---\n{front}---\n\n{body}\n"

        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

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

    def _second_solve_lines(self) -> str:
        if not self.second_solves:
            return ""
        lines = ["**Second solves**", ""]
        for d in self.second_solves:
            first = d.get("first") or {}
            lines.append(
                f"- `{first.get('model')}` (window {first.get('window')}): "
                f"{d.get('status')}, kept `{d.get('kept')}`. {d.get('reason', '')}"
            )
        return "\n".join(lines)

    @classmethod
    def open(cls, root: str | Path, *, quarantine_corrupt: bool = False) -> "Run":
        """Load a record. With `quarantine_corrupt`, an unreadable one is set aside.

        The caller that is about to RUN something passes the flag: a record it
        cannot parse must not be allowed to block the work, because the attempt
        history of a run that already crashed is worth less than the ability to
        retry it. The corrupt file is moved aside rather than deleted, and the fresh
        record says where it went, so nothing is silently lost. A caller that is
        merely READING a record leaves the flag off and gets the error, because
        there silence would be a wrong answer rather than an inconvenience.
        """
        root = Path(root)
        path = root / "run.md"
        if not path.exists():
            raise FileNotFoundError(f"no run record at {path}")
        text = path.read_text(encoding="utf-8")
        try:
            doc, body = split_frontmatter(text, origin=str(path))
        except Exception as exc:
            if not quarantine_corrupt:
                raise
            n = 0
            while (kept := path.with_name(f"run.md.corrupt.{n}")).exists():
                n += 1
            os.replace(path, kept)
            run = cls(id=root.name, root=root)
            run.notes.append(
                f"**The previous record at `run.md` could not be read** "
                f"({type(exc).__name__}: {exc}). It has been moved to "
                f"`{kept.name}` and this record started fresh. The usual cause is a "
                f"write interrupted by a kill or a full filesystem; the steps that "
                f"ran before it are in the quarantined file and their artifacts, "
                f"being content-addressed, are still in the store."
            )
            run.save()
            return run
        return cls(
            id=str(doc.get("run", root.name)),
            root=root,
            scene=str(doc.get("scene", "")),
            dataset=str(doc.get("dataset", "")),
            goal=str(doc.get("goal", "")),
            steps=[Step.from_doc(s) for s in (doc.get("steps") or [])],
            second_solves=list(doc.get("second_solves") or []),
        )
