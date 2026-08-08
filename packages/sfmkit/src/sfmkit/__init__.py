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
from .schema import TypeRegistry, TypeSchema, parse_schema, registry
from .store import ArtifactStore

__version__ = "0.2.0"

__all__ = [
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
