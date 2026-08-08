"""Integration tests for real modules against real datasets.

Skipped wholesale when the datasets or a module's dependencies are absent, so the
unit suites under packages/ stay hermetic and fast.
"""

import pytest
from sfmkit import ArtifactStore

from dataset_paths import MODULES
from sfmorch import ModuleRegistry, Orchestrator


@pytest.fixture(scope="session")
def registry():
    reg = ModuleRegistry()
    reg.load_dir(MODULES)
    return reg


@pytest.fixture
def orch(tmp_path, registry):
    return Orchestrator(store=ArtifactStore(tmp_path / "store"), registry=registry)
