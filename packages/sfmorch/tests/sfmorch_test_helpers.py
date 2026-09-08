"""Shared test helpers, in a module with a collision-proof name.

These lived in conftest.py, and `from conftest import ...` breaks whenever this
directory's conftest and the repo-root tests/conftest.py are loaded in the same
pytest run -- both claim the module name "conftest", and whichever loads first
wins. The root tests/ directory solved the same collision with dataset_paths.py;
this is the same fix on this side.
"""

from pathlib import Path

FIXTURE_MODULES = Path(__file__).parent / "fixtures" / "modules"


def contract_metrics(*type_names):
    """The metric block a manifest needs to satisfy the types it produces.

    Generated from the type registry rather than hardcoded, so tests whose subject
    is something else -- orphan warnings, tool-surface size, capability queries --
    keep testing that when the contract changes.
    """
    from sfmkit.schema import registry as core_types

    return {
        name: {"direction": req.direction, "meaning": req.meaning}
        for tname in type_names
        for name, req in core_types().get(tname).metrics.items()
    }
