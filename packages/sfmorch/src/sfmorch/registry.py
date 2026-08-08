"""The module registry.

Scans `modules/*/module.yaml`, validates each, registers any custom payload
types they declare, and indexes everything by consumed/produced type -- which is
what turns "what can follow a tracks/v1?" from tribal knowledge into a query, and
what lets a newly added module become reachable without editing a catalog
anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sfmkit import SchemaError, TypeRegistry, registry as core_types

from .errors import ManifestError, ModuleNotFound
from .modulespec import ModuleSpec


@dataclass(frozen=True)
class OrphanWarning:
    """A module produces a type nothing consumes.

    Legal -- final outputs are terminal by definition -- but surfaced at
    registration so the agent knows before spending a GPU hour, rather than
    after.
    """

    module: str
    type: str
    terminal_ok: bool

    def __str__(self) -> str:
        return (
            f"module '{self.module}' produces '{self.type}', which no registered "
            f"module consumes. If this is a final output that is expected; "
            f"otherwise the artifact is a dead end."
        )


class ModuleRegistry:
    def __init__(self, *, types: TypeRegistry | None = None):
        self.types = types or core_types()
        self._modules: dict[str, ModuleSpec] = {}
        self.warnings: list[OrphanWarning] = []

    # ------------------------------------------------------------- population

    def add(self, spec: ModuleSpec) -> ModuleSpec:
        if spec.name in self._modules:
            existing = self._modules[spec.name]
            raise ManifestError(
                f"duplicate module name '{spec.name}' "
                f"({existing.root} and {spec.root}). Names are the registry key "
                f"and appear in every artifact's provenance."
            )

        # A module may declare its own payload types; register them before the
        # slot check below so it can legitimately produce one.
        for tdoc in spec.custom_types:
            tname = tdoc.get("type", "<unnamed>")
            if tname in self.types:
                continue
            try:
                self.types.register_doc(tdoc, origin=f"{spec.name}:module.yaml")
            except SchemaError as e:
                raise ManifestError(
                    f"module '{spec.name}' declares an invalid type: {e}"
                ) from e

        for kind, slots in (("consumes", spec.consumes), ("produces", spec.produces)):
            for slot in slots.values():
                if slot.type not in self.types:
                    raise ManifestError(
                        f"module '{spec.name}' {kind} unknown payload type "
                        f"'{slot.type}'. Register it as a core type, or declare it "
                        f"in this manifest's `types:` block as "
                        f"'custom/<name>/v1'. Known: {self.types.names()}"
                    )

        self._modules[spec.name] = spec
        self._recompute_warnings()
        return spec

    def load_dir(self, directory: str | Path) -> list[ModuleSpec]:
        """Load every `<directory>/*/module.yaml`."""
        directory = Path(directory)
        loaded = []
        for child in sorted(directory.iterdir()) if directory.is_dir() else []:
            manifest = child / "module.yaml"
            if manifest.exists():
                loaded.append(self.add(ModuleSpec.read(manifest)))
        return loaded

    def _recompute_warnings(self) -> None:
        consumed = {t for m in self._modules.values() for t in m.consumed_types}
        self.warnings = [
            OrphanWarning(module=m.name, type=t, terminal_ok=True)
            for m in self._modules.values()
            for t in sorted(m.produced_types)
            if t not in consumed
        ]

    # ---------------------------------------------------------------- queries

    def get(self, name: str) -> ModuleSpec:
        try:
            return self._modules[name]
        except KeyError:
            raise ModuleNotFound(
                f"no module '{name}'. Registered: {sorted(self._modules)}"
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._modules

    def __len__(self) -> int:
        return len(self._modules)

    def names(self) -> list[str]:
        return sorted(self._modules)

    def find(
        self,
        *,
        kind: str | None = None,
        consumes: str | None = None,
        produces: str | None = None,
        not_consuming: str | None = None,
        excluding: str | None = None,
    ) -> list[ModuleSpec]:
        """Capability query.

        `not_consuming` is what makes a `limitations.md` escape expressible
        without naming a module: "something producing tracks/v1 that does NOT
        consume pairwise_matches/v1" is exactly the query for "stop building
        tracks from a matcher that isn't working, use a direct tracker".
        """
        out = []
        for spec in self._modules.values():
            if kind is not None and spec.kind != kind:
                continue
            if consumes is not None and consumes not in spec.consumed_types:
                continue
            if produces is not None and produces not in spec.produced_types:
                continue
            if not_consuming is not None and not_consuming in spec.consumed_types:
                continue
            if excluding is not None and spec.name == excluding:
                continue
            out.append(spec)
        return sorted(out, key=lambda s: s.name)

    def successors(self, spec_or_type: str | ModuleSpec) -> list[ModuleSpec]:
        """Modules that can consume something this one produces."""
        types = (
            {spec_or_type}
            if isinstance(spec_or_type, str)
            else spec_or_type.produced_types
        )
        return sorted(
            {
                m.name: m
                for t in types
                for m in self.find(consumes=t)
            }.values(),
            key=lambda s: s.name,
        )

    def summary(self) -> list[dict]:
        """Compact listing for `sfm_list_modules`."""
        return [
            {
                "name": s.name,
                "version": s.version,
                "kind": s.kind,
                "summary": s.summary,
                "consumes": {n: sl.type for n, sl in s.consumes.items()},
                "produces": {n: sl.type for n, sl in s.produces.items()},
                "gpu": s.resources.gpu,
                "terminal": any(
                    w.module == s.name for w in self.warnings
                ),
            }
            for s in sorted(self._modules.values(), key=lambda x: x.name)
        ]
