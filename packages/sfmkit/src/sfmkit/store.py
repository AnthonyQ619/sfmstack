"""The artifact store.

Local filesystem today. This is an *interface* rather than bare path handling so
a remote backend stays possible without touching module code -- modules only ever
see `Artifact` objects and paths handed to them.

    <root>/
      artifacts/<artifact_id>/     artifact.md, data/
      runs/<run_id>/run.md

Artifacts live in one flat, global namespace rather than under a run, because ids
are derived from the recipe: five parallel pipelines on the same scene resolve to
the same `scene/v1` id and share one decode. Runs reference artifacts by id.
"""

from __future__ import annotations

from pathlib import Path

from .artifact import Artifact, ArtifactWriter
from .errors import ArtifactNotFound
from .manifest import Provenance
from .schema import TypeRegistry


class ArtifactStore:
    def __init__(self, root: str | Path, *, type_registry: TypeRegistry | None = None):
        self.root = Path(root)
        self.registry = type_registry
        self.artifacts_dir = self.root / "artifacts"
        self.runs_dir = self.root / "runs"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def path_for(self, artifact_id: str) -> Path:
        return self.artifacts_dir / artifact_id

    def exists(self, artifact_id: str) -> bool:
        return (self.path_for(artifact_id) / "artifact.md").exists()

    # ------------------------------------------------------------------- read

    def open(self, artifact_id: str) -> Artifact:
        if not self.exists(artifact_id):
            raise ArtifactNotFound(
                f"no artifact '{artifact_id}' in {self.artifacts_dir}"
            )
        return Artifact.open(self.path_for(artifact_id))

    def list(self, *, type: str | None = None) -> list[str]:
        out = []
        for child in sorted(self.artifacts_dir.iterdir()):
            if not (child / "artifact.md").exists():
                continue
            if type is None:
                out.append(child.name)
            else:
                try:
                    if Artifact.open(child).type == type:
                        out.append(child.name)
                except Exception:
                    continue
        return out

    # ------------------------------------------------------------------ write

    def writer(
        self,
        *,
        artifact_id: str,
        type: str,
        run: str = "",
        scene: str = "",
        inputs: list[str] | None = None,
        provenance: Provenance | None = None,
    ) -> ArtifactWriter:
        return ArtifactWriter(
            root=self.path_for(artifact_id),
            artifact_id=artifact_id,
            type=type,
            run=run,
            scene=scene,
            inputs=inputs,
            provenance=provenance,
            type_registry=self.registry,
        )

    # ---------------------------------------------------------------- lineage

    def ancestry(self, artifact_id: str) -> dict[str, list[str]]:
        """artifact id -> its input ids, transitively.

        The orchestrator uses this to report where two artifacts' lineage
        diverges. Nothing is ever marked stale: re-running an upstream module
        branches the DAG, and a newer branch does not supersede an older one --
        it may well be worse. Divergence is a fact; supersession is a judgment.
        """
        seen: dict[str, list[str]] = {}
        stack = [artifact_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            try:
                inputs = self.open(current).manifest.inputs
            except ArtifactNotFound:
                inputs = []
            seen[current] = list(inputs)
            stack.extend(inputs)
        return seen
