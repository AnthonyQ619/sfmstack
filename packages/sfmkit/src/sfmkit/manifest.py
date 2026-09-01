"""The `artifact.md` manifest: YAML frontmatter plus a markdown body.

One file, two audiences. The frontmatter is what the orchestrator validates and
routes on; the body is what the driving agent reads. Keeping them in one file is
deliberate -- two files drift, and a manifest that disagrees with its own
narrative is worse than either alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestError

FRONTMATTER_DELIM = "---"


@dataclass
class Metric:
    value: float | int | None
    direction: str = "unknown"  # higher_better | lower_better | neutral | unknown
    healthy: tuple[float | None, float | None] | None = None
    meaning: str = ""

    def to_doc(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"value": self.value, "direction": self.direction}
        if self.healthy is not None:
            doc["healthy"] = list(self.healthy)
        if self.meaning:
            doc["meaning"] = self.meaning
        return doc


@dataclass
class Diagnostic:
    code: str
    severity: str = "warn"  # info | warn | error
    message: str = ""
    suggested_actions: list[str] = field(default_factory=list)
    see_also: str = ""

    def to_doc(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"code": self.code, "severity": self.severity}
        if self.message:
            doc["message"] = self.message
        if self.suggested_actions:
            doc["suggested_actions"] = list(self.suggested_actions)
        if self.see_also:
            doc["see_also"] = self.see_also
        return doc


@dataclass
class Provenance:
    """Who made this artifact, and with what.

    `image` is a TAG and a tag is mutable: two builds of
    `sfmstack/foo:1.0.0` are the same string and different software. Artifact ids
    are recipe-derived and do not cover the image either, so without
    `image_digest` nothing in the record distinguishes a result produced before a
    rebuild from one produced after. Empty when the module ran in-process, which
    is honest -- there was no image.

    That paragraph described a hazard for as long as this field existed, and
    nothing read the field. The orchestrator now does: before serving a cache
    entry it compares this digest against the digest of the image that would run
    now, and a mismatch is a miss. So this is load-bearing rather than
    provenance detail -- a producer that stops recording it does not lose a nice
    -to-have, it silently restores the stale-cache bug.
    """

    module: str
    module_version: str = "0.0.0"
    image: str = ""
    image_digest: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    duration_s: float | None = None
    device: str | None = None


@dataclass
class Manifest:
    id: str
    type: str
    run: str = ""
    scene: str = ""
    inputs: list[str] = field(default_factory=list)
    produced_by: Provenance | None = None
    files: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    status: str = "ok"  # ok | failed
    diagnostics: list[Diagnostic] = field(default_factory=list)
    extras: dict[str, list[str]] = field(default_factory=dict)
    body: str = ""

    # ---------------------------------------------------------------- doc I/O

    def to_doc(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "run": self.run,
            "scene": self.scene,
            "inputs": list(self.inputs),
        }
        if self.produced_by is not None:
            doc["produced_by"] = {
                k: v for k, v in asdict(self.produced_by).items() if v not in (None, "", {})
            }
        doc["files"] = self.files
        doc["metrics"] = {k: v.to_doc() for k, v in self.metrics.items()}
        doc["status"] = self.status
        doc["diagnostics"] = [d.to_doc() for d in self.diagnostics]
        if self.extras:
            doc["extras"] = self.extras
        return doc

    @classmethod
    def from_doc(cls, doc: dict[str, Any], body: str = "") -> "Manifest":
        for required in ("id", "type"):
            if required not in doc:
                raise ManifestError(f"manifest is missing required field '{required}'")

        prov_doc = doc.get("produced_by")
        provenance = None
        if prov_doc:
            known = {f for f in Provenance.__dataclass_fields__}
            provenance = Provenance(**{k: v for k, v in prov_doc.items() if k in known})

        metrics = {}
        for name, m in (doc.get("metrics") or {}).items():
            if isinstance(m, dict):
                healthy = m.get("healthy")
                metrics[name] = Metric(
                    value=m.get("value"),
                    direction=m.get("direction", "unknown"),
                    healthy=tuple(healthy) if healthy is not None else None,
                    meaning=m.get("meaning", ""),
                )
            else:  # tolerate a bare scalar
                metrics[name] = Metric(value=m)

        diagnostics = [
            Diagnostic(
                code=d.get("code", "unknown"),
                severity=d.get("severity", "warn"),
                message=d.get("message", ""),
                suggested_actions=list(d.get("suggested_actions") or []),
                see_also=d.get("see_also", ""),
            )
            for d in (doc.get("diagnostics") or [])
        ]

        return cls(
            id=str(doc["id"]),
            type=str(doc["type"]),
            run=str(doc.get("run", "")),
            scene=str(doc.get("scene", "")),
            inputs=list(doc.get("inputs") or []),
            produced_by=provenance,
            files=doc.get("files") or {},
            metrics=metrics,
            status=str(doc.get("status", "ok")),
            diagnostics=diagnostics,
            extras=doc.get("extras") or {},
            body=body,
        )

    # ------------------------------------------------------------- file I/O

    def render(self) -> str:
        # default_flow_style=None keeps leaf sequences inline -- `shape: [4, 4]`
        # rather than four lines. The manifest is read by a human and by an agent
        # paying for tokens; both benefit.
        front = yaml.safe_dump(
            self.to_doc(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=None,
            width=100,
        )
        body = self.body.strip()
        return f"{FRONTMATTER_DELIM}\n{front}{FRONTMATTER_DELIM}\n\n{body}\n"

    def write(self, path: str | Path) -> None:
        Path(path).write_text(self.render(), encoding="utf-8")

    @classmethod
    def read(cls, path: str | Path) -> "Manifest":
        path = Path(path)
        if not path.exists():
            raise ManifestError(f"no manifest at {path}")
        return cls.parse(path.read_text(encoding="utf-8"), origin=str(path))

    @classmethod
    def parse(cls, text: str, origin: str = "<string>") -> "Manifest":
        front, body = split_frontmatter(text, origin=origin)
        return cls.from_doc(front, body=body)


def split_frontmatter(text: str, origin: str = "<string>") -> tuple[dict[str, Any], str]:
    stripped = text.lstrip("﻿")
    if not stripped.startswith(FRONTMATTER_DELIM):
        raise ManifestError(
            f"{origin}: expected YAML frontmatter opening with '{FRONTMATTER_DELIM}'"
        )

    rest = stripped[len(FRONTMATTER_DELIM) :].lstrip("\n")
    marker = f"\n{FRONTMATTER_DELIM}"
    end = rest.find(marker)
    if end == -1:
        raise ManifestError(f"{origin}: frontmatter is not closed")

    front_text = rest[:end]
    body = rest[end + len(marker) :].lstrip("\n")

    doc = yaml.safe_load(front_text)
    if not isinstance(doc, dict):
        raise ManifestError(f"{origin}: frontmatter must be a YAML mapping")
    return doc, body


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


def _canonical(value: Any) -> Any:
    """JSON-stable form, so identical recipes hash identically across runs."""
    if isinstance(value, dict):
        return {k: _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def artifact_id(
    *,
    type: str,
    module: str,
    module_version: str,
    slot: str = "",
    params: dict[str, Any] | None = None,
    inputs: list[str] | None = None,
    salt: str = "",
) -> str:
    """Deterministic id derived from the *recipe*, not the output bytes.

    Two identical recipes therefore land on the same id, which is what makes a
    `scene/v1` shared across five parallel pipelines cost one decode instead of
    five.

    `slot` is the output name from the module's `produces` block. It is part of
    the recipe because a module with two outputs of the SAME type would otherwise
    give both the same id and the second seal would overwrite the first.

    `salt` exists for the rare module that is genuinely non-deterministic and
    must not be deduplicated.
    """
    recipe = _canonical(
        {
            "type": type,
            "module": module,
            "module_version": module_version,
            "slot": slot,
            "params": params or {},
            "inputs": sorted(inputs or []),
            "salt": salt,
        }
    )
    blob = json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()
    return "art_" + hashlib.sha256(blob).hexdigest()[:12]
