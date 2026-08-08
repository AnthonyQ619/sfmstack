"""Payload type schemas and the validator that enforces them.

A *type* names a payload contract: which files an artifact of that type holds,
which arrays live in each, their shapes and dtypes, and invariants that must
hold. Modules declare `consumes`/`produces` in terms of these names, which is
what lets the orchestrator check a pipeline before spawning anything.

Two rules make the type set open without letting it fragment:

1.  **Extension is additive.** Arrays are `required` or optional; a payload may
    carry arrays the schema never mentions. A module that adds per-point
    uncertainty to a point cloud emits `sparse_model/v1` with an extra array --
    it does NOT invent a new type. Consumers ignore what they do not know.

2.  **A new version means a required field changed.** Anything else is additive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .errors import SchemaError, ValidationError
from .invariants import REGISTRY as INVARIANT_REGISTRY

TYPE_NAME_RE = re.compile(r"^(custom/)?[a-z][a-z0-9_]*/v[0-9]+$")

_CORE_TYPES_DIR = Path(__file__).parent / "types"


@dataclass(frozen=True)
class ArraySpec:
    name: str
    required: bool = True
    shape: tuple[int | None, ...] | None = None
    dtype: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    description: str = ""

    def problems(self, arr: np.ndarray) -> list[str]:
        out: list[str] = []

        if self.shape is not None:
            if arr.ndim != len(self.shape):
                out.append(
                    f"array '{self.name}' has rank {arr.ndim}, expected "
                    f"{len(self.shape)} (shape spec {list(self.shape)})"
                )
            else:
                for axis, (want, got) in enumerate(zip(self.shape, arr.shape)):
                    if want is not None and want != got:
                        out.append(
                            f"array '{self.name}' axis {axis} is {got}, expected {want}"
                        )

        if self.dtype and not self._dtype_ok(arr):
            out.append(
                f"array '{self.name}' has dtype {arr.dtype}, expected one of "
                f"{list(self.dtype)}"
            )

        if self.columns and arr.ndim >= 1 and arr.shape[-1] != len(self.columns):
            out.append(
                f"array '{self.name}' has {arr.shape[-1]} columns, expected "
                f"{len(self.columns)} {list(self.columns)}"
            )

        return out

    # Widths vary ('<U12' vs '<U73'), so string dtypes are matched by kind.
    _KINDS = {"str": "U", "bool": "b", "int": "iu", "float": "f"}

    def _dtype_ok(self, arr: np.ndarray) -> bool:
        actual = str(arr.dtype)
        for allowed in self.dtype:
            if allowed == actual:
                return True
            kind = self._KINDS.get(allowed)
            if kind and arr.dtype.kind in kind:
                return True
        return False


@dataclass(frozen=True)
class FileSpec:
    name: str
    required: bool = True
    description: str = ""
    arrays: dict[str, ArraySpec] = field(default_factory=dict)


@dataclass(frozen=True)
class TypeSchema:
    type: str
    summary: str = ""
    description: str = ""
    files: dict[str, FileSpec] = field(default_factory=dict)
    invariants: tuple[dict[str, Any], ...] = ()

    @property
    def is_custom(self) -> bool:
        return self.type.startswith("custom/")

    def validate(self, payload: dict[str, dict[str, np.ndarray]]) -> None:
        """Raise ValidationError unless `payload` conforms.

        `payload` maps file name -> array name -> ndarray.
        """
        problems: list[str] = []

        for fname, fspec in self.files.items():
            if fname not in payload:
                if fspec.required:
                    problems.append(f"missing required file '{fname}'")
                continue

            arrays = payload[fname]
            for aname, aspec in fspec.arrays.items():
                if aname not in arrays:
                    if aspec.required:
                        problems.append(
                            f"file '{fname}' is missing required array '{aname}'"
                        )
                    continue
                problems.extend(
                    f"file '{fname}': {p}" for p in aspec.problems(arrays[aname])
                )

        # Extra files and arrays are legal: this is additive extension.

        # Invariants only run once the structural contract holds. Checking
        # "column 0 implies N ids" against an array of the wrong rank produces a
        # crash or a confusing second error, when the actionable problem is the
        # shape. Report structure first; semantics once structure is sound.
        if not problems:
            problems.extend(self._invariant_problems(payload))

        if problems:
            raise ValidationError(self.type, problems)

    def _invariant_problems(
        self, payload: dict[str, dict[str, np.ndarray]]
    ) -> list[str]:
        def resolve(file: str, array: str) -> np.ndarray | None:
            return payload.get(file, {}).get(array)

        problems: list[str] = []
        for spec in self.invariants:
            check_name = spec.get("check")
            fn = INVARIANT_REGISTRY.get(check_name)
            if fn is None:
                raise SchemaError(
                    f"type '{self.type}' references unknown invariant "
                    f"'{check_name}'. Known: {sorted(INVARIANT_REGISTRY)}"
                )
            result = fn(resolve, **spec.get("args", {}))
            if result:
                problems.append(result)
        return problems

    def extras(
        self, payload: dict[str, dict[str, np.ndarray]]
    ) -> dict[str, list[str]]:
        """Arrays present in the payload but absent from the schema.

        Legal by the additive-extension rule, but worth recording in the manifest
        so a consumer can discover them.
        """
        out: dict[str, list[str]] = {}
        for fname, arrays in payload.items():
            known = set(self.files[fname].arrays) if fname in self.files else set()
            extra = sorted(set(arrays) - known)
            if extra:
                out[fname] = extra
        return out


# --------------------------------------------------------------------------- #
# Parsing and registry
# --------------------------------------------------------------------------- #


def _as_shape(raw: Any) -> tuple[int | None, ...] | None:
    if raw is None:
        return None
    return tuple(None if d in (None, "any", "*") else int(d) for d in raw)


def _as_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    return tuple(str(x) for x in raw)


def parse_schema(doc: dict[str, Any], origin: str = "<memory>") -> TypeSchema:
    name = doc.get("type")
    if not name or not TYPE_NAME_RE.match(str(name)):
        raise SchemaError(
            f"{origin}: type name {name!r} must look like 'tracks/v1' or "
            f"'custom/my_thing/v1'"
        )

    files: dict[str, FileSpec] = {}
    for fname, fdoc in (doc.get("files") or {}).items():
        fdoc = fdoc or {}
        arrays = {
            aname: ArraySpec(
                name=aname,
                required=bool((adoc or {}).get("required", True)),
                shape=_as_shape((adoc or {}).get("shape")),
                dtype=_as_tuple((adoc or {}).get("dtype")),
                columns=_as_tuple((adoc or {}).get("columns")),
                description=str((adoc or {}).get("description", "")),
            )
            for aname, adoc in (fdoc.get("arrays") or {}).items()
        }
        files[fname] = FileSpec(
            name=fname,
            required=bool(fdoc.get("required", True)),
            description=str(fdoc.get("description", "")),
            arrays=arrays,
        )

    return TypeSchema(
        type=str(name),
        summary=str(doc.get("summary", "")),
        description=str(doc.get("description", "")),
        files=files,
        invariants=tuple(doc.get("invariants") or ()),
    )


class TypeRegistry:
    """Known payload types. Core types ship with sfmkit; custom ones are
    registered from module manifests at load time."""

    def __init__(self) -> None:
        self._types: dict[str, TypeSchema] = {}

    def register(self, schema: TypeSchema, *, replace: bool = False) -> None:
        if schema.type in self._types and not replace:
            raise SchemaError(f"type '{schema.type}' is already registered")
        self._types[schema.type] = schema

    def register_doc(self, doc: dict[str, Any], origin: str = "<memory>") -> TypeSchema:
        schema = parse_schema(doc, origin=origin)
        self.register(schema)
        return schema

    def load_dir(self, directory: str | Path) -> None:
        for path in sorted(Path(directory).glob("*.yaml")):
            with open(path, encoding="utf-8") as fh:
                self.register_doc(yaml.safe_load(fh), origin=str(path))

    def get(self, name: str) -> TypeSchema:
        try:
            return self._types[name]
        except KeyError:
            raise SchemaError(
                f"unknown payload type '{name}'. Registered: {sorted(self._types)}. "
                f"Core types ship with sfmkit; a module-specific type must be "
                f"declared in that module's manifest as 'custom/<name>/v1'."
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._types

    def names(self) -> list[str]:
        return sorted(self._types)


_registry: TypeRegistry | None = None


def registry() -> TypeRegistry:
    """The process-wide registry, lazily populated with the core types."""
    global _registry
    if _registry is None:
        _registry = TypeRegistry()
        _registry.load_dir(_CORE_TYPES_DIR)
    return _registry
