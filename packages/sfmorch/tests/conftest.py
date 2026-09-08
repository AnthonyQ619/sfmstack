from pathlib import Path

import pytest
from sfmkit import ArtifactStore, TypeRegistry
from sfmkit.schema import _CORE_TYPES_DIR

from sfmorch import ModuleRegistry, Orchestrator

from sfmorch_test_helpers import FIXTURE_MODULES, contract_metrics  # noqa: F401


@pytest.fixture
def types():
    """A fresh type registry per test, so custom types declared by one test's
    module manifest cannot leak into another."""
    reg = TypeRegistry()
    reg.load_dir(_CORE_TYPES_DIR)
    return reg


@pytest.fixture
def registry(types):
    reg = ModuleRegistry(types=types)
    reg.load_dir(FIXTURE_MODULES)
    return reg


@pytest.fixture
def store(tmp_path, types):
    return ArtifactStore(tmp_path / "store", type_registry=types)


@pytest.fixture
def orch(store, registry):
    return Orchestrator(store=store, registry=registry)


@pytest.fixture
def scene(orch):
    """A synthetic scene, ready to hang a pipeline off."""
    return orch.run("MakeScene", run_id="run_test", params={"n_images": 4}).primary
