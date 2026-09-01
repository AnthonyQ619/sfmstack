"""Execution backends.

This is the seam containers slot into. The orchestrator decides *what* to run and
whether it is allowed; a Runner decides *where*. `InProcessRunner` imports the
adapter and calls it -- fast, debuggable, no isolation. `ContainerRunner` (step 5)
will POST to a module server over a mounted store, with the same signature.

Nothing above this line knows which one it is using.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from sfmkit import Artifact, ArtifactStore, Ctx, Params, run_module

from .errors import ExecutionError, ManifestError
from .modulespec import ModuleSpec


@dataclass(frozen=True)
class Job:
    """A fully resolved request to execute a module once.

    By the time a Job exists the orchestrator has already type-checked the
    inputs and materialised parameter defaults, so a Runner never has to
    validate anything -- it only has to execute.
    """

    spec: ModuleSpec
    inputs: dict[str, Artifact]
    params: dict[str, Any] = field(default_factory=dict)
    run: str = ""
    scene: str = ""
    device: str | None = None

    # Honoured by both runners, so a long job reports the same way whether it is
    # running in a container or in this process.
    on_progress: Callable[[float | None, str], None] | None = None


class Runner(Protocol):
    def run(self, job: Job, store: ArtifactStore) -> dict[str, Artifact]: ...

    def image_digest(self, spec: ModuleSpec) -> str:
        """The digest of the image this runner would use for `spec`, right now.

        The cache asks this before serving a stored artifact. "" means the
        question does not apply -- an in-process run has no image -- and never
        invalidates anything.
        """
        return ""


class InProcessRunner:
    """Import the module's adapter and call it in this process.

    Used for development and for the pure-numpy modules where a container buys
    nothing but latency. It offers NO dependency isolation -- that is the whole
    point of the container runner -- so a module with heavy or conflicting
    dependencies will fail to import here, which is correct and informative.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def image_digest(self, spec: ModuleSpec) -> str:
        """No image, so nothing to go stale behind. Never invalidates a cache entry."""
        return ""

    def run(self, job: Job, store: ArtifactStore) -> dict[str, Artifact]:
        fn = self._load(job.spec)

        ctx = Ctx(
            store=store,
            module=job.spec.name,
            module_version=job.spec.version,
            image=job.spec.image,
            run=job.run,
            scene=job.scene,
            device=job.device,
            inputs=dict(job.inputs),
            params=Params(job.params),
            output_types=job.spec.output_types,
            on_progress=job.on_progress,
        )

        try:
            return run_module(fn, ctx)
        except Exception as e:  # noqa: BLE001 -- deliberately broad; re-raised typed
            raise ExecutionError(job.spec.name, e) from e

    # ------------------------------------------------------------------ import

    def _load(self, spec: ModuleSpec):
        key = f"{spec.name}@{spec.version}"
        if key in self._cache:
            return self._cache[key]

        if spec.root is None:
            raise ManifestError(
                f"module '{spec.name}' has no directory; InProcessRunner needs one "
                f"to import its adapter"
            )

        mod_path, _, func_name = spec.entrypoint.partition(":")
        func_name = func_name or "run"
        source = spec.root / f"{mod_path}.py"
        if not source.exists():
            raise ManifestError(
                f"module '{spec.name}' declares entrypoint '{spec.entrypoint}' but "
                f"{source} does not exist"
            )

        # Imported under a unique name so two modules may both ship `adapter.py`
        # without colliding in sys.modules.
        unique = f"_sfm_module_{spec.name}_{spec.version.replace('.', '_')}"
        importer = importlib.util.spec_from_file_location(unique, source)
        if importer is None or importer.loader is None:
            raise ManifestError(f"cannot import {source}")
        module = importlib.util.module_from_spec(importer)
        sys.modules[unique] = module
        importer.loader.exec_module(module)

        fn = getattr(module, func_name, None)
        if fn is None:
            raise ManifestError(
                f"module '{spec.name}': {source} has no function '{func_name}'"
            )
        if not getattr(fn, "_is_sfm_module", False):
            raise ManifestError(
                f"module '{spec.name}': {func_name} in {source} is not decorated "
                f"with @module"
            )

        self._cache[key] = fn
        return fn
