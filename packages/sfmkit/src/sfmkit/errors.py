"""Exception hierarchy for sfmkit.

Every error a module can hit at the artifact boundary is one of these, so the
orchestrator can classify a failed job without parsing text.
"""

from __future__ import annotations


class SfmkitError(Exception):
    """Base for everything raised by sfmkit."""


class SchemaError(SfmkitError):
    """A type schema is itself malformed or unregistered."""


class ValidationError(SfmkitError):
    """An artifact payload does not conform to its declared type.

    Raised at seal time in the PRODUCING job. This is the guard that stops a
    module declaring `tracks/v1` and writing something else, which would
    otherwise surface as a crash in a consumer several stages later.
    """

    def __init__(self, artifact_type: str, problems: list[str]):
        self.artifact_type = artifact_type
        self.problems = problems
        detail = "\n".join(f"  - {p}" for p in problems)
        super().__init__(
            f"Artifact does not conform to type '{artifact_type}':\n{detail}\n\n"
            f"The schema is the contract between modules. Either fix the payload "
            f"or, if the type genuinely needs a new field, add it as an OPTIONAL "
            f"array to the schema rather than declaring a new type."
        )


class ManifestError(SfmkitError):
    """An artifact.md manifest is missing, malformed, or internally inconsistent."""


class ArtifactNotFound(SfmkitError):
    """No artifact with the requested id exists in the store."""


class InputError(SfmkitError):
    """A module asked for an input it was not given, or of the wrong type."""
