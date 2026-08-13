"""The module contract.

A module author writes one function. Everything else -- artifact resolution,
schema validation, provenance, metrics, timing -- is handled here.

    from sfmkit import module, Ctx

    @module
    def run(ctx: Ctx):
        obs   = ctx.inputs["pairs"].load("matches", "xy")
        scene = ctx.inputs["scene"]

        tracks = union_find(obs, min_len=ctx.params.min_track_len)

        out = ctx.output("tracks")
        out.save("observations", obs=tracks, track_count=np.int64(n))
        out.metric("avg_track_length", 4.21)
        out.note("Built %d tracks from %d pairs." % (n, len(obs)))

The function returns nothing. Outputs are sealed when it returns, so a module
that raises produces no artifact at all -- there is no half-written state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .artifact import Artifact, ArtifactWriter
from .errors import InputError
from .manifest import Provenance, artifact_id
from .store import ArtifactStore


class Params:
    """Attribute access over the parameter dict, with dict access as a fallback."""

    def __init__(self, values: dict[str, Any] | None = None):
        self._values = dict(values or {})

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(
                f"no parameter '{name}'. Given: {sorted(self._values)}. "
                f"Parameters and their defaults are declared in module.yaml; the "
                f"orchestrator fills defaults before invoking a module."
            ) from None

    def __getitem__(self, name: str) -> Any:
        return self._values[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)

    def __repr__(self) -> str:
        return f"Params({self._values!r})"


@dataclass
class Ctx:
    """Everything a module is given, and the only way it produces output."""

    store: ArtifactStore
    module: str
    module_version: str = "0.0.0"
    image: str = ""
    # The content-addressed id of the image actually running, set by the runner.
    # The tag above says which image was ASKED for; this says which one answered.
    image_digest: str = ""
    run: str = ""
    scene: str = ""
    device: str | None = None

    inputs: dict[str, Artifact] = field(default_factory=dict)
    params: Params = field(default_factory=Params)

    # output slot name -> payload type, from the module manifest's `produces`
    output_types: dict[str, str] = field(default_factory=dict)

    # Set by the runner. Progress is how a caller distinguishes "still working"
    # from "wedged" on a job that legitimately runs for twenty minutes.
    on_progress: Callable[[float | None, str], None] | None = None

    _writers: dict[str, ArtifactWriter] = field(default_factory=dict, repr=False)
    _started: float = field(default_factory=time.monotonic, repr=False)
    _started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"),
        repr=False,
    )

    # --------------------------------------------------------------- progress

    def progress(self, fraction: float | None = None, stage: str = "") -> None:
        """Report how far along this job is.

        Call it from any loop that runs for more than a few seconds -- per image,
        per pair, per bundle-adjustment iteration. Cheap, and it is the only
        thing that lets a caller tell a module that is working from one that is
        stuck. Modules that never call it simply report no progress.

            for i, path in enumerate(paths):
                ctx.progress(i / len(paths), f"detecting {i + 1}/{len(paths)}")
        """
        if self.on_progress is None:
            return
        if fraction is not None:
            fraction = max(0.0, min(1.0, float(fraction)))
        self.on_progress(fraction, stage)

    # ----------------------------------------------------------------- inputs

    def input(self, name: str, *, expect: str | None = None) -> Artifact:
        try:
            art = self.inputs[name]
        except KeyError:
            raise InputError(
                f"module '{self.module}' was not given input '{name}'. "
                f"Given: {sorted(self.inputs)}."
            ) from None
        if expect is not None and art.type != expect:
            raise InputError(
                f"input '{name}' is {art.type}, expected {expect}. The orchestrator "
                f"should have rejected this before spawning; treat it as a bug."
            )
        return art

    # ---------------------------------------------------------------- outputs

    def output(self, name: str) -> ArtifactWriter:
        """Get (or create) the writer for a declared output slot."""
        if name in self._writers:
            return self._writers[name]

        try:
            payload_type = self.output_types[name]
        except KeyError:
            raise InputError(
                f"module '{self.module}' has no declared output '{name}'. "
                f"Declared: {sorted(self.output_types)}. Outputs come from the "
                f"`produces` block in module.yaml."
            ) from None

        aid = artifact_id(
            type=payload_type,
            module=self.module,
            module_version=self.module_version,
            slot=name,
            params=self.params.as_dict(),
            inputs=[a.id for a in self.inputs.values()],
        )

        writer = self.store.writer(
            artifact_id=aid,
            type=payload_type,
            run=self.run,
            scene=self.scene or self._scene_from_inputs(),
            inputs=[a.id for a in self.inputs.values()],
            provenance=Provenance(
                module=self.module,
                module_version=self.module_version,
                image=self.image,
                image_digest=self.image_digest,
                params=self.params.as_dict(),
                started_at=self._started_at,
                device=self.device,
            ),
            enforce_metric_contract=True,
        )
        self._writers[name] = writer
        return writer

    def _scene_from_inputs(self) -> str:
        for art in self.inputs.values():
            if art.type.startswith("scene/"):
                return art.id
            if art.manifest.scene:
                return art.manifest.scene
        return ""

    def seal_all(self) -> dict[str, Artifact]:
        elapsed = time.monotonic() - self._started
        sealed = {}
        for name, writer in self._writers.items():
            if writer.manifest.produced_by is not None:
                writer.manifest.produced_by.duration_s = round(elapsed, 3)
            sealed[name] = writer.seal()
        return sealed


def module(fn: Callable[[Ctx], None]) -> Callable[[Ctx], None]:
    """Mark the module entry point.

    Thin by design: the harness looks for the marker, and `run_module` does the
    sealing. Keeping the decorator dumb means a module function stays an
    ordinary function that a test can call directly.
    """
    fn._is_sfm_module = True  # type: ignore[attr-defined]
    return fn


def run_module(fn: Callable[[Ctx], None], ctx: Ctx) -> dict[str, Artifact]:
    """Invoke a module function and seal whatever it produced.

    If `fn` raises, nothing is sealed and no artifact appears in the store. A
    failed job leaves no half-written output to confuse a later run.
    """
    fn(ctx)
    return ctx.seal_all()
