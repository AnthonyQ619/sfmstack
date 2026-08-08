"""`module.yaml` -- the keystone declaration.

One file feeds four things that were separately hand-maintained in the previous
system and had drifted badly apart by the time anyone checked:

    the MCP tool schema        (params -> JSON Schema)
    the agent's documentation  (summary, description, tuning notes)
    plan validation            (consumes / produces types)
    metric interpretation      (direction, healthy band, meaning)

Because they are generated from one source, they cannot disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestError
from .params import ParamSet

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Slot:
    """One input or output port."""

    name: str
    type: str
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class MetricSpec:
    name: str
    direction: str = "unknown"  # higher_better | lower_better | neutral | unknown
    healthy: tuple[float | None, float | None] | None = None
    meaning: str = ""

    _DIRECTIONS = ("higher_better", "lower_better", "neutral", "unknown")

    def __post_init__(self) -> None:
        if self.direction not in self._DIRECTIONS:
            raise ManifestError(
                f"metric '{self.name}' has direction '{self.direction}'; "
                f"expected one of {list(self._DIRECTIONS)}"
            )


@dataclass(frozen=True)
class DiagnosticSpec:
    code: str
    severity: str = "warn"
    message: str = ""
    suggested_actions: tuple[str, ...] = ()
    see_also: str = ""


@dataclass(frozen=True)
class Resources:
    gpu: bool = False
    min_ram_gb: float | None = None

    expected_duration_s: float | None = None
    """Roughly how long a typical job takes.

    Not a limit -- a hint, used to decide how long to wait inline before handing
    back a job id, and to suggest a polling interval. Modules vary from two
    seconds to forty minutes, so a single global wait either blocks pointlessly
    on the slow ones or round-trips pointlessly on the fast ones. The service
    refines this from observed durations as runs accumulate; the declared value
    is just the cold-start estimate.
    """

    timeout_s: float | None = None
    """Hard ceiling for one job. None means no limit."""


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    version: str
    kind: str = ""
    summary: str = ""
    description: str = ""

    image: str = ""
    entrypoint: str = "adapter:run"
    resources: Resources = field(default_factory=Resources)

    consumes: dict[str, Slot] = field(default_factory=dict)
    produces: dict[str, Slot] = field(default_factory=dict)
    params: ParamSet = field(default_factory=ParamSet)
    metrics: dict[str, MetricSpec] = field(default_factory=dict)
    diagnostics: dict[str, DiagnosticSpec] = field(default_factory=dict)

    custom_types: tuple[dict[str, Any], ...] = ()
    root: Path | None = None

    # ------------------------------------------------------------------ views

    @property
    def consumed_types(self) -> set[str]:
        return {s.type for s in self.consumes.values()}

    @property
    def produced_types(self) -> set[str]:
        return {s.type for s in self.produces.values()}

    @property
    def output_types(self) -> dict[str, str]:
        """Slot name -> payload type, as `sfmkit.Ctx` wants it."""
        return {name: slot.type for name, slot in self.produces.items()}

    @property
    def skills_dir(self) -> Path | None:
        if self.root is None:
            return None
        d = self.root / "skills"
        return d if d.is_dir() else None

    def skill(self, topic: str) -> str | None:
        """Read one curated skill document without spawning the container.

        `topic` is a stem: SKILL, tuning, limitations, artifact, sources.
        """
        d = self.skills_dir
        if d is None:
            return None
        path = d / f"{topic}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def describe(self) -> dict[str, Any]:
        """What `sfm_describe_module` returns: the machine contract plus the
        module's own SKILL.md, so one call gives the agent both."""
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "summary": self.summary,
            "description": self.description,
            "image": self.image,
            "resources": {"gpu": self.resources.gpu, "min_ram_gb": self.resources.min_ram_gb},
            "consumes": {
                n: {"type": s.type, "required": s.required, "description": s.description}
                for n, s in self.consumes.items()
            },
            "produces": {n: {"type": s.type} for n, s in self.produces.items()},
            "params": self.params.to_json_schema(),
            "param_tuning": {
                n: s.tuning for n, s in self.params.specs.items() if s.tuning
            },
            "metrics": {
                n: {
                    "direction": m.direction,
                    "healthy": list(m.healthy) if m.healthy else None,
                    "meaning": m.meaning,
                }
                for n, m in self.metrics.items()
            },
            "diagnostics": {
                c: {
                    "severity": d.severity,
                    "message": d.message,
                    "suggested_actions": list(d.suggested_actions),
                    "see_also": d.see_also,
                }
                for c, d in self.diagnostics.items()
            },
            "skill": self.skill("SKILL"),
            "available_skills": sorted(
                p.stem for p in (self.skills_dir.glob("*.md") if self.skills_dir else [])
            ),
        }

    # ----------------------------------------------------------------- parsing

    @classmethod
    def from_doc(
        cls, doc: dict[str, Any], *, root: Path | None = None, origin: str = "<memory>"
    ) -> "ModuleSpec":
        def need(key: str) -> Any:
            if key not in doc:
                raise ManifestError(f"{origin}: missing required field '{key}'")
            return doc[key]

        name = str(need("name"))
        if not NAME_RE.match(name):
            raise ManifestError(
                f"{origin}: module name '{name}' must be a bare identifier -- it "
                f"becomes an attribute in generated pipelines and a key in the "
                f"registry."
            )

        version = str(need("version"))
        if not VERSION_RE.match(version):
            raise ManifestError(
                f"{origin}: version '{version}' must be semver (e.g. 1.2.0). It is "
                f"part of every artifact id, so a bump must be unambiguous."
            )

        def slots(key: str, *, default_required: bool) -> dict[str, Slot]:
            out = {}
            for sname, sdoc in (doc.get(key) or {}).items():
                sdoc = sdoc or {}
                if "type" not in sdoc:
                    raise ManifestError(
                        f"{origin}: {key} slot '{sname}' must declare a payload type"
                    )
                out[sname] = Slot(
                    name=sname,
                    type=str(sdoc["type"]),
                    required=bool(sdoc.get("required", default_required)),
                    description=str(sdoc.get("description", "")),
                )
            return out

        produces = slots("produces", default_required=True)
        if not produces:
            raise ManifestError(
                f"{origin}: a module must declare at least one output in `produces`"
            )

        metrics = {}
        for mname, mdoc in (doc.get("metrics") or {}).items():
            mdoc = mdoc or {}
            healthy = mdoc.get("healthy")
            metrics[mname] = MetricSpec(
                name=mname,
                direction=str(mdoc.get("direction", "unknown")),
                healthy=tuple(healthy) if healthy is not None else None,
                meaning=str(mdoc.get("meaning", "")),
            )

        diagnostics = {}
        for ddoc in doc.get("diagnostics") or []:
            code = str(ddoc.get("code", "")).strip()
            if not code:
                raise ManifestError(f"{origin}: every diagnostic needs a `code`")
            diagnostics[code] = DiagnosticSpec(
                code=code,
                severity=str(ddoc.get("severity", "warn")),
                message=str(ddoc.get("message", "")),
                suggested_actions=tuple(ddoc.get("suggested_actions") or ()),
                see_also=str(ddoc.get("see_also", "")),
            )

        res_doc = doc.get("resources") or {}

        return cls(
            name=name,
            version=version,
            kind=str(doc.get("kind", "")),
            summary=str(doc.get("summary", "")),
            description=str(doc.get("description", "")),
            image=str(doc.get("image", "")),
            entrypoint=str(doc.get("entrypoint", "adapter:run")),
            resources=Resources(
                gpu=bool(res_doc.get("gpu", False)),
                min_ram_gb=res_doc.get("min_ram_gb"),
                expected_duration_s=res_doc.get("expected_duration_s"),
                timeout_s=res_doc.get("timeout_s"),
            ),
            consumes=slots("consumes", default_required=True),
            produces=produces,
            params=ParamSet.from_doc(doc.get("params"), origin=origin),
            metrics=metrics,
            diagnostics=diagnostics,
            custom_types=tuple(doc.get("types") or ()),
            root=root,
        )

    @classmethod
    def read(cls, path: str | Path) -> "ModuleSpec":
        path = Path(path)
        if path.is_dir():
            path = path / "module.yaml"
        if not path.exists():
            raise ManifestError(f"no module manifest at {path}")
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ManifestError(f"{path}: module.yaml must be a YAML mapping")
        return cls.from_doc(doc, root=path.parent, origin=str(path))
