"""Orchestrator errors.

Everything the orchestrator refuses to do is one of these, so a failed MCP call
can be classified without parsing prose.
"""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base for everything raised by sfmorch."""


class ManifestError(OrchestratorError):
    """A module.yaml is malformed, or claims something the registry can't honour."""


class ModuleNotFound(OrchestratorError):
    """No module by that name is registered."""


class WiringError(OrchestratorError):
    """A run was requested with inputs that do not satisfy the module's contract.

    Raised BEFORE anything is spawned. This is the guard that makes a
    type-incompatible pipeline unbuildable rather than a runtime crash.
    """


class ParamError(OrchestratorError):
    """A parameter is unknown, of the wrong type, or out of range."""


class ExecutionError(OrchestratorError):
    """The module itself failed. `cause` carries what it raised."""

    def __init__(self, module: str, cause: BaseException):
        self.module = module
        self.cause = cause
        super().__init__(f"module '{module}' failed: {type(cause).__name__}: {cause}")
