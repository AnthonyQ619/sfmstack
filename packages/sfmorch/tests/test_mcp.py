"""The MCP adapter.

Thin on purpose, so this suite is thin too: it checks that the tools register
with sane schemas and that a call round-trips into the service. The behaviour
itself is covered in test_service.py, which is the point of keeping the logic out
of the adapter.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None, reason="mcp SDK not installed"
)

FIXTURES = Path("packages/sfmorch/tests/fixtures/modules").resolve()

EXPECTED_TOOLS = {
    # discovery
    "sfm_list_modules", "sfm_describe_module",
    # execution
    "sfm_check", "sfm_run", "sfm_replay", "sfm_job", "sfm_list_jobs",
    # inspection
    "sfm_artifact", "sfm_run_summary", "sfm_compare",
    # knowledge
    "sfm_module_skill", "sfm_find_alternatives", "sfm_workflow_skill",
    # authoring
    "sfm_scaffold_module", "sfm_build_module", "sfm_reload_modules",
    "sfm_smoke_test",
}


@pytest.fixture
def server(tmp_path):
    from sfmorch.mcp_server import build_server, build_service

    service = build_service(
        modules_dir=FIXTURES,
        store_root=tmp_path / "store",
        skills_dir=Path("skills").resolve(),
    )
    yield build_server(service), service
    service.jobs.shutdown()


def call(mcp, tool: str, args: dict):
    result = asyncio.run(mcp.call_tool(tool, args))
    assert not result.is_error, result.content
    return result.structured_content


def test_the_expected_tools_register(server):
    mcp, _ = server
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == EXPECTED_TOOLS


def test_the_surface_does_not_grow_with_the_module_count(server):
    """Modules are discovered, never enumerated as tools. Fourteen-odd tools at
    two modules must still be fourteen-odd at two hundred."""
    mcp, service = server
    before = len(asyncio.run(mcp.list_tools()))

    from conftest import contract_metrics
    from sfmorch import ModuleSpec

    for i in range(20):
        service.registry.add(ModuleSpec.from_doc({
            "name": f"Extra{i}",
            "version": "1.0.0",
            "produces": {"out": {"type": "tracks/v1"}},
            "metrics": contract_metrics("tracks/v1"),
        }))

    assert len(asyncio.run(mcp.list_tools())) == before
    assert len(call(mcp, "sfm_list_modules", {})["modules"]) == 6 + 20


def test_every_tool_has_a_description(server):
    mcp, _ = server
    for tool in asyncio.run(mcp.list_tools()):
        assert tool.description and len(tool.description) > 40, tool.name


def test_run_round_trips_through_the_adapter(server):
    mcp, _ = server
    result = call(mcp, "sfm_run", {
        "module": "MakeScene", "run_id": "r", "params": {"n_images": 3}
    })

    assert result["status"] == "ok"
    assert result["metrics"]["n_images"] == 3
    assert result["outputs"]["scene"].startswith("art_")


def test_a_wiring_error_carries_the_fix_to_the_caller(server):
    """A wiring mistake raises, which the SDK turns into an error response at the
    transport boundary. What matters is that the message names the modules that
    would satisfy the slot, so the caller can correct without another lookup."""
    from mcp.server.mcpserver.exceptions import ToolError

    mcp, _ = server
    scene = call(mcp, "sfm_run", {
        "module": "MakeScene", "run_id": "r", "params": {"n_images": 3}
    })
    feats = call(mcp, "sfm_run", {
        "module": "FakeDetector", "run_id": "r",
        "inputs": {"scene": scene["outputs"]["scene"]},
    })

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(mcp.call_tool("sfm_run", {
            "module": "FakeTracker", "run_id": "r",
            "inputs": {"scene": scene["outputs"]["scene"],
                       "pairs": feats["outputs"]["features"]},
        }))

    message = str(excinfo.value)
    assert "expects 'pairwise_matches/v1'" in message
    assert "FakeMatcher" in message


def test_capability_query_round_trips(server):
    mcp, _ = server
    result = call(mcp, "sfm_find_alternatives", {
        "produces": "tracks/v1", "not_consuming": "pairwise_matches/v1"
    })
    assert result["matches"] == []
    assert result["query"]["not_consuming"] == "pairwise_matches/v1"


def test_instructions_describe_the_loop(server):
    mcp, _ = server
    assert "sfm_list_modules" in mcp.instructions
    assert "sfm_replay" in mcp.instructions
