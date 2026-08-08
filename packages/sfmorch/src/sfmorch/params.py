"""Parameter schemas: defaults, coercion, and range checking.

A module's `params` block is the single source for four things -- the MCP tool
schema, the agent-facing documentation, the values a module actually receives,
and the recipe an artifact id is hashed from. Keeping one declaration is what
stops those four drifting apart, which is precisely what happened to the
previous system's hand-maintained tool catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import ManifestError, ParamError

_TYPES: dict[str, tuple[type, ...]] = {
    "integer": (int,),
    "number": (int, float),
    "string": (str,),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[Any, ...] = ()
    description: str = ""
    tuning: str = ""
    required: bool = False

    def __post_init__(self) -> None:
        if self.type not in _TYPES:
            raise ManifestError(
                f"parameter '{self.name}' has unknown type '{self.type}'. "
                f"Use one of {sorted(_TYPES)}."
            )

    def coerce(self, value: Any) -> Any:
        allowed = _TYPES[self.type]

        # bool is a subclass of int in Python; an integer param must not silently
        # accept True.
        if self.type in ("integer", "number") and isinstance(value, bool):
            raise ParamError(
                f"parameter '{self.name}' expects {self.type}, got boolean {value!r}"
            )

        if not isinstance(value, allowed):
            # Widening int -> float is safe and common in hand-written params.
            if self.type == "number" and isinstance(value, int):
                value = float(value)
            else:
                raise ParamError(
                    f"parameter '{self.name}' expects {self.type}, got "
                    f"{type(value).__name__} ({value!r})"
                )

        if self.type == "integer":
            value = int(value)
        elif self.type == "number":
            value = float(value)

        if self.enum and value not in self.enum:
            raise ParamError(
                f"parameter '{self.name}' must be one of {list(self.enum)}, got {value!r}"
            )

        if self.minimum is not None and value < self.minimum:
            raise ParamError(
                f"parameter '{self.name}' is {value}, below the minimum "
                f"{self.minimum}"
            )
        if self.maximum is not None and value > self.maximum:
            raise ParamError(
                f"parameter '{self.name}' is {value}, above the maximum "
                f"{self.maximum}"
            )

        return value

    def to_json_schema(self) -> dict[str, Any]:
        """JSON Schema fragment, for the MCP tool definition."""
        doc: dict[str, Any] = {"type": self.type}
        if self.description:
            doc["description"] = self.description
        if self.default is not None:
            doc["default"] = self.default
        if self.minimum is not None:
            doc["minimum"] = self.minimum
        if self.maximum is not None:
            doc["maximum"] = self.maximum
        if self.enum:
            doc["enum"] = list(self.enum)
        return doc


@dataclass(frozen=True)
class ParamSet:
    specs: dict[str, ParamSpec] = field(default_factory=dict)

    def resolve(self, given: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate what was given and fill in defaults.

        The result is what the module receives AND what the artifact id is hashed
        from, so defaults must be materialised here rather than inside the
        module. Otherwise the same effective run would hash differently depending
        on whether the caller spelled out a default.
        """
        given = dict(given or {})

        unknown = sorted(set(given) - set(self.specs))
        if unknown:
            raise ParamError(
                f"unknown parameter(s) {unknown}. Accepted: {sorted(self.specs)}."
            )

        resolved: dict[str, Any] = {}
        for name, spec in self.specs.items():
            if name in given:
                resolved[name] = spec.coerce(given[name])
            elif spec.default is not None:
                resolved[name] = spec.coerce(spec.default)
            elif spec.required:
                raise ParamError(f"parameter '{name}' is required and has no default")
            # A param with neither a value nor a default is simply absent.

        return resolved

    def to_json_schema(self) -> dict[str, Any]:
        required = [n for n, s in self.specs.items() if s.required and s.default is None]
        doc: dict[str, Any] = {
            "type": "object",
            "properties": {n: s.to_json_schema() for n, s in self.specs.items()},
            "additionalProperties": False,
        }
        if required:
            doc["required"] = required
        return doc

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None, *, origin: str = "") -> "ParamSet":
        specs = {}
        for name, pdoc in (doc or {}).items():
            pdoc = pdoc or {}
            if "type" not in pdoc:
                raise ManifestError(
                    f"{origin}: parameter '{name}' must declare a type"
                )
            specs[name] = ParamSpec(
                name=name,
                type=str(pdoc["type"]),
                default=pdoc.get("default"),
                minimum=pdoc.get("minimum"),
                maximum=pdoc.get("maximum"),
                enum=tuple(pdoc.get("enum") or ()),
                description=str(pdoc.get("description", "")),
                tuning=str(pdoc.get("tuning", "")),
                required=bool(pdoc.get("required", False)),
            )
        return cls(specs=specs)
