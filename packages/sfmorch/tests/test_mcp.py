"""The MCP adapter.

Thin on purpose, so this suite is thin too: it checks that the tools register
with sane schemas and that a call round-trips into the service. The behaviour
itself is covered in test_service.py, which is the point of keeping the logic out
of the adapter.
"""

import asyncio
import base64
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
    "sfm_artifact", "sfm_artifact_image", "sfm_run_summary", "sfm_compare",
    "sfm_plan_brief",
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
    """Modules are discovered, never enumerated as tools. Nineteen tools at two
    modules must still be nineteen at two hundred.

    The count moves on two other axes, neither of them the module count.
    `sfm_artifact_image` was added because artifacts could always hold pictures
    and there was no way to hand one back -- a payload KIND. `sfm_plan_brief` was
    added because choosing the first pipeline was a step of the loop with no tool
    behind it at all.
    """
    mcp, service = server
    before = len(asyncio.run(mcp.list_tools()))

    from sfmorch_test_helpers import contract_metrics
    from sfmorch import ModuleSpec

    for i in range(20):
        service.registry.add(ModuleSpec.from_doc({
            "name": f"Extra{i}",
            "version": "1.0.0",
            "produces": {"out": {"type": "tracks/v1"}},
            "metrics": contract_metrics("tracks/v1"),
        }))

    assert len(asyncio.run(mcp.list_tools())) == before
    assert len(call(mcp, "sfm_list_modules", {})["modules"]) == 7 + 20


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


def test_an_artifact_image_comes_back_as_a_picture_not_a_path(server):
    """The whole point of the tool. A path is useless to a caller that cannot
    reach this filesystem, and that was the one precondition SceneDescription had
    which no other module does.
    """
    mcp, service = server
    scene = call(mcp, "sfm_run", {
        "module": "MakeScene", "run_id": "r", "params": {"n_images": 3}
    })["outputs"]["scene"]

    sheet = service.store.open(scene).data_dir / "browse" / "contact_sheet.jpg"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_bytes(b"\xff\xd8\xff fake jpeg")

    result = asyncio.run(mcp.call_tool("sfm_artifact_image", {"artifact_id": scene}))

    assert not result.is_error, result.content
    kinds = [block.type for block in result.content]
    assert "image" in kinds, kinds

    image = next(b for b in result.content if b.type == "image")
    assert image.mime_type == "image/jpeg"
    assert base64.b64decode(image.data) == b"\xff\xd8\xff fake jpeg"

    # Provenance travels beside the picture; an image with no record of which
    # artifact it came out of is not evidence of anything.
    assert any(scene in getattr(b, "text", "") for b in result.content)


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
    # Step 3 has a tool now, and the loop text is where an agent finds that out.
    assert "sfm_plan_brief" in mcp.instructions


def test_plan_brief_round_trips_the_guide_and_the_families(server):
    """The adapter has to carry prose, not just numbers -- the guide and the six
    family files are most of what makes the brief worth one call."""
    mcp, _ = server
    scene = call(mcp, "sfm_run", {"module": "MakeScene", "run_id": "r",
                                  "params": {"n_images": 4}})
    call(mcp, "sfm_run", {"module": "FakeAnalyser", "run_id": "r",
                          "inputs": {"scene": scene["outputs"]["scene"]}})

    brief = call(mcp, "sfm_plan_brief", {"scene_id": scene["outputs"]["scene"]})

    assert [a["module"] for a in brief["analysis"]] == ["FakeAnalyser"]
    assert "texture_density" in brief["how_to_read"]["text"]
    assert len(brief["families"]) == 6
    assert brief["report_shape"]["sections"]
