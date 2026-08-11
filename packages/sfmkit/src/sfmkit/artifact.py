"""Artifacts: immutable, typed, self-describing directories.

    <store>/artifacts/<artifact_id>/
        artifact.md          manifest (frontmatter) + narrative (body)
        data/<file>.npz      payload, one npz per declared file

Artifacts are write-once. Re-running a module with different parameters produces
a NEW artifact and keeps the old one, which is what lets the driving agent
compare attempts instead of overwriting them.

Data never crosses a process or container boundary as bytes -- a module receives
a path, mounts the store, and reads numpy directly.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ArtifactNotFound, ManifestError
from .manifest import Diagnostic, Manifest, Metric, Provenance
from .schema import TypeRegistry, registry

MANIFEST_NAME = "artifact.md"
DATA_DIR = "data"


@dataclass(frozen=True)
class Artifact:
    """A sealed artifact on disk. Read-only."""

    root: Path
    manifest: Manifest

    # -------------------------------------------------------------- accessors

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def type(self) -> str:
        return self.manifest.type

    @property
    def data_dir(self) -> Path:
        return self.root / DATA_DIR

    def path(self, *parts: str) -> Path:
        """Path to something inside the artifact, for native sidecars.

        e.g. `art.path("data", "sparse")` for a COLMAP model directory that a
        pycolmap-backed module opens natively.
        """
        return self.root.joinpath(*parts)

    def has(self, file: str) -> bool:
        return (self.data_dir / f"{file}.npz").exists()

    def resolve(self, path: str) -> Path:
        """Resolve a filesystem path recorded inside this artifact.

        Relative paths are relative to the artifact root; absolute paths are
        returned unchanged. Producers that copy files INTO the artifact record
        them relatively, so the artifact stays self-contained and survives the
        store being mounted at a different point inside a container. Producers
        that merely reference external files (an unresized dataset) record
        absolute paths, and those files must then be mounted downstream too.
        """
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    def sidecar(self, name: str) -> Path | None:
        """Path to a native-format sidecar, or None if absent.

        The canonical payload is always npz. A sidecar is an ADDITIONAL native
        rendering of the same data -- most importantly COLMAP's
        `cameras/images/points3D.bin`, so a pycolmap-backed consumer can open a
        reconstruction directly instead of rebuilding it from arrays. A consumer
        that does not understand the sidecar reads the npz and loses nothing.
        """
        declared = self.manifest.files.get("__sidecars__", {})
        if name not in declared:
            return None
        path = self.root / declared[name]["path"]
        return path if path.exists() else None

    def sidecars(self) -> list[str]:
        return sorted(self.manifest.files.get("__sidecars__", {}))

    def load(self, file: str, array: str | None = None) -> Any:
        """Load one npz file, or a single array out of it."""
        path = self.data_dir / f"{file}.npz"
        if not path.exists():
            raise ArtifactNotFound(
                f"artifact {self.id} ({self.type}) has no file '{file}'. "
                f"Present: {sorted(p.stem for p in self.data_dir.glob('*.npz'))}"
            )
        with np.load(path, allow_pickle=False) as npz:
            if array is None:
                return {k: npz[k] for k in npz.files}
            if array not in npz.files:
                raise ArtifactNotFound(
                    f"artifact {self.id} file '{file}' has no array '{array}'. "
                    f"Present: {sorted(npz.files)}"
                )
            return npz[array]

    def payload(self) -> dict[str, dict[str, np.ndarray]]:
        return {p.stem: self.load(p.stem) for p in sorted(self.data_dir.glob("*.npz"))}

    def metric(self, name: str) -> float | int | None:
        m = self.manifest.metrics.get(name)
        return None if m is None else m.value

    @classmethod
    def open(cls, root: str | Path) -> "Artifact":
        root = Path(root)
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.exists():
            raise ArtifactNotFound(f"no artifact at {root} (expected {MANIFEST_NAME})")
        return cls(root=root, manifest=Manifest.read(manifest_path))


class ArtifactWriter:
    """Builds one artifact, validates it, and seals it.

    Validation happens at seal time in the PRODUCING process. A module that
    declares `tracks/v1` and writes something else fails here, not in a consumer
    three stages later.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        artifact_id: str,
        type: str,
        run: str = "",
        scene: str = "",
        inputs: list[str] | None = None,
        provenance: Provenance | None = None,
        type_registry: TypeRegistry | None = None,
        enforce_metric_contract: bool = False,
    ):
        self.root = Path(root)
        # The metric contract binds MODULES, not the payload format. An artifact
        # assembled by hand -- a repair script, a fixture, an import from another
        # tool -- is still a valid tracks/v1 even with no metrics on it. Only the
        # Ctx.output path sets this, because only there is there a module that
        # promised the numbers.
        self.enforce_metric_contract = enforce_metric_contract
        self.registry = type_registry or registry()
        self.schema = self.registry.get(type)  # fails fast on an unknown type

        self._payload: dict[str, dict[str, np.ndarray]] = {}
        self._sidecars: dict[str, str] = {}
        self._staged_sidecars = self.root / ".staging"
        self._notes: list[str] = []
        self._sealed = False

        self.manifest = Manifest(
            id=artifact_id,
            type=type,
            run=run,
            scene=scene,
            inputs=list(inputs or []),
            produced_by=provenance,
        )

    # ------------------------------------------------------------------ write

    def save(self, file: str, **arrays: Any) -> "ArtifactWriter":
        """Stage one payload file. Arrays are coerced to ndarray, not validated
        yet -- validation runs once at seal so it can report every problem."""
        if self._sealed:
            raise ManifestError("artifact is already sealed; artifacts are write-once")
        bucket = self._payload.setdefault(file, {})
        for name, value in arrays.items():
            bucket[name] = np.asarray(value)
        return self

    def sidecar_dir(self, name: str) -> Path:
        """A directory to write a native-format rendering into.

        Use for formats a downstream consumer opens with its own library --
        canonically a COLMAP model, so a pycolmap module can load a
        reconstruction directly. The npz payload remains authoritative and must
        still be written; a sidecar is never the only copy, because a consumer
        without that library has to be able to read the artifact.
        """
        if self._sealed:
            raise ManifestError("artifact is already sealed; artifacts are write-once")
        path = self._staged_sidecars / name
        path.mkdir(parents=True, exist_ok=True)
        self._sidecars[name] = f"{DATA_DIR}/{name}"
        return path

    def metric(
        self,
        name: str,
        value: float | int | None,
        *,
        direction: str = "unknown",
        healthy: tuple[float | None, float | None] | None = None,
        meaning: str = "",
    ) -> "ArtifactWriter":
        self.manifest.metrics[name] = Metric(
            value=None if value is None else _py(value),
            direction=direction,
            healthy=healthy,
            meaning=meaning,
        )
        return self

    def diagnostic(
        self,
        code: str,
        *,
        severity: str = "warn",
        message: str = "",
        suggested_actions: list[str] | None = None,
        see_also: str = "",
    ) -> "ArtifactWriter":
        self.manifest.diagnostics.append(
            Diagnostic(
                code=code,
                severity=severity,
                message=message,
                suggested_actions=list(suggested_actions or []),
                see_also=see_also,
            )
        )
        return self

    def note(self, text: str) -> "ArtifactWriter":
        """Append to the narrative body -- what the driving agent reads."""
        self._notes.append(text.strip())
        return self

    # ------------------------------------------------------------------- seal

    def seal(self) -> Artifact:
        if self._sealed:
            raise ManifestError("artifact is already sealed")

        self.schema.validate(self._payload)  # raises ValidationError
        if self.enforce_metric_contract:
            self.schema.validate_metrics(self.manifest.metrics)

        data_dir = self.root / DATA_DIR
        staged = self._staged_sidecars
        keep = staged.exists()
        if keep:
            holding = staged.parent.with_name(staged.parent.name + ".sidecars")
            if holding.exists():
                shutil.rmtree(holding)
            shutil.move(str(staged), str(holding))
        if self.root.exists():
            shutil.rmtree(self.root)
        data_dir.mkdir(parents=True)
        if keep:
            for child in sorted(holding.iterdir()):
                shutil.move(str(child), str(data_dir / child.name))
            shutil.rmtree(holding)

        files_doc: dict[str, Any] = {}
        for fname, arrays in sorted(self._payload.items()):
            path = data_dir / f"{fname}.npz"
            np.savez_compressed(path, **arrays)
            fspec = self.schema.files.get(fname)
            files_doc[fname] = {
                "path": f"{DATA_DIR}/{fname}.npz",
                "arrays": {
                    aname: _describe(arr, fspec.arrays.get(aname) if fspec else None)
                    for aname, arr in sorted(arrays.items())
                },
            }

        if self._sidecars:
            files_doc["__sidecars__"] = {
                name: {"path": path, "format": "native"}
                for name, path in sorted(self._sidecars.items())
            }

        self.manifest.files = files_doc
        self.manifest.extras = self.schema.extras(self._payload)
        self.manifest.body = "\n\n".join(self._notes)
        self.manifest.write(self.root / MANIFEST_NAME)

        self._sealed = True
        return Artifact(root=self.root, manifest=self.manifest)


def _describe(arr: np.ndarray, spec: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"shape": list(arr.shape), "dtype": str(arr.dtype)}
    if spec is not None and getattr(spec, "columns", ()):
        doc["columns"] = list(spec.columns)
    if spec is None:
        doc["schema"] = "extra"  # additive extension, not in the declared schema
    return doc


def _py(value: Any) -> Any:
    """numpy scalar -> python scalar, so YAML stays readable."""
    if isinstance(value, np.generic):
        return value.item()
    return value
