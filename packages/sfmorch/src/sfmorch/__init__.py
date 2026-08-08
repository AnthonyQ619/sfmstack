"""sfmorch -- the orchestrator.

Owns what neither the agent nor a module should: whether a pipeline is legal,
whether the work is already done, and what was attempted.

    ModuleSpec / ModuleRegistry   module.yaml, indexed by consumed/produced type
    Orchestrator                  type checking, caching, the run DAG, replay
    Runner / InProcessRunner      the seam containers slot into (step 5)
    Run / Step                    runs/<run_id>/run.md
    diverge / compare             lineage, because nothing is ever "stale"
"""

from .errors import (
    ExecutionError,
    ManifestError,
    ModuleNotFound,
    OrchestratorError,
    ParamError,
    WiringError,
)
from .lineage import Divergence, compare, diverge
from .modulespec import (
    DiagnosticSpec,
    MetricSpec,
    ModuleSpec,
    Resources,
    Slot,
)
from .orchestrator import Orchestrator, RunResult
from .params import ParamSet, ParamSpec
from .registry import ModuleRegistry, OrphanWarning
from .run_record import Run, Step
from .runner import InProcessRunner, Job, Runner

__version__ = "0.1.0"

__all__ = [
    "DiagnosticSpec",
    "Divergence",
    "ExecutionError",
    "InProcessRunner",
    "Job",
    "ManifestError",
    "MetricSpec",
    "ModuleNotFound",
    "ModuleRegistry",
    "ModuleSpec",
    "Orchestrator",
    "OrchestratorError",
    "OrphanWarning",
    "ParamError",
    "ParamSet",
    "ParamSpec",
    "Resources",
    "Run",
    "RunResult",
    "Runner",
    "Slot",
    "Step",
    "WiringError",
    "compare",
    "diverge",
]
