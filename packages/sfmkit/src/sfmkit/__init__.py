"""sfmkit -- the contract layer every sfmstack module shares.

Deliberately small. It is installed into every module container, so anything it
depends on becomes a dependency of every module. See pyproject.toml.

    Artifact / ArtifactWriter   immutable, typed, self-describing directories
    ArtifactStore               where they live and how they are addressed
    Manifest                    artifact.md -- YAML frontmatter + narrative body
    TypeRegistry / TypeSchema   payload contracts between modules
    Ctx / @module               what a module author writes against
"""

from .artifact import Artifact, ArtifactWriter
from .errors import (
    ArtifactNotFound,
    InputError,
    ManifestError,
    SchemaError,
    SfmkitError,
    ValidationError,
)
from .manifest import Diagnostic, Manifest, Metric, Provenance, artifact_id
from .module import Ctx, Params, module, run_module
from .geometry import scene_intrinsics, trifocal_transfer
from .ply import read_ply_header, write_ply
from .tracks import SPLIT_TOLERANCE_PX, split_rate
from .cycles import MERGE_TOLERANCE_PX, cycle_rates
from .schema import TypeRegistry, TypeSchema, parse_schema, registry
from .store import ArtifactStore

__version__ = "0.2.0"

__all__ = [
    "write_ply",
    "trifocal_transfer",
    "scene_intrinsics",
    "split_rate",
    "cycle_rates",
    "MERGE_TOLERANCE_PX",
    "SPLIT_TOLERANCE_PX",
    "read_ply_header",
    "Artifact",
    "ArtifactNotFound",
    "ArtifactStore",
    "ArtifactWriter",
    "Ctx",
    "Diagnostic",
    "InputError",
    "Manifest",
    "ManifestError",
    "Metric",
    "Params",
    "Provenance",
    "SchemaError",
    "SfmkitError",
    "TypeRegistry",
    "TypeSchema",
    "ValidationError",
    "artifact_id",
    "module",
    "parse_schema",
    "registry",
    "run_module",
]
