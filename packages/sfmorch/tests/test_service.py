"""The tool surface.

Exercised through SfmService directly rather than over MCP transport, because the
logic lives there by design and the MCP layer is one-line registrations.
"""

import pytest
from sfmkit import ArtifactStore

from sfmorch import ModuleRegistry, Orchestrator, OrchestratorError, WiringError
from sfmorch.service import ServiceConfig, SfmService

FIXTURES = "packages/sfmorch/tests/fixtures/modules"


@pytest.fixture
def service(tmp_path, registry, store):
    from pathlib import Path

    svc = SfmService(
        config=ServiceConfig(
            modules_dir=Path(FIXTURES).resolve(),
            store_root=store.root,
            skills_dir=Path("skills").resolve(),
            inline_wait_s=60.0,
        ),
        orchestrator=Orchestrator(store=store, registry=registry),
        registry=registry,
    )
    yield svc
    svc.jobs.shutdown()


@pytest.fixture
def scene(service):
    return service.run("MakeScene", run_id="r", params={"n_images": 4})


def pipeline(service, scene_id, *, keep_ratio=1.0):
    feats = service.run("FakeDetector", run_id="r", inputs={"scene": scene_id})
    pairs = service.run(
        "FakeMatcher", run_id="r",
        inputs={"scene": scene_id, "features": feats["outputs"]["features"]},
        params={"keep_ratio": keep_ratio},
    )
    tracks = service.run(
        "FakeTracker", run_id="r",
        inputs={"scene": scene_id, "pairs": pairs["outputs"]["pairs"]},
    )
    return feats, pairs, tracks


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_list_modules_reports_wiring_and_terminality(service):
    listed = {m["name"]: m for m in service.list_modules()["modules"]}

    assert listed["FakeTracker"]["consumes"] == {
        "scene": "scene/v1", "pairs": "pairwise_matches/v1"
    }
    assert listed["FakeReconstructor"]["terminal"] is True
    assert "tracks/v1" in service.list_modules()["payload_types"]


def test_list_modules_filters_by_payload_type(service):
    found = service.list_modules(produces="tracks/v1")["modules"]
    assert [m["name"] for m in found] == ["FakeTracker"]


def test_describe_module_carries_schema_metrics_and_diagnostics(service):
    doc = service.describe_module("FakeTracker")

    assert doc["params"]["properties"]["min_track_len"]["default"] == 2
    assert doc["metrics"]["avg_track_length"]["direction"] == "higher_better"
    assert doc["diagnostics"]["too_few_tracks"]["see_also"].startswith("tuning.md#")


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


def test_a_run_returns_metrics_inline(scene):
    """No second round trip to find out how it went."""
    assert scene["status"] == "ok"
    assert scene["metrics"]["n_images"] == 4
    assert scene["outputs"]["scene"].startswith("art_")
    assert scene["notes"]


def test_diagnostics_come_back_with_their_skill_pointer(service, scene):
    _, _, tracks = pipeline(service, scene["outputs"]["scene"], keep_ratio=0.1)
    codes = {d["code"]: d for d in tracks["diagnostics"]}

    assert "too_few_tracks" in codes
    assert codes["too_few_tracks"]["see_also"] == "tuning.md#track_count-below-10"


def test_check_previews_the_plan_without_running(service, scene):
    plan = service.check("FakeDetector", inputs={"scene": scene["outputs"]["scene"]})

    assert plan["params"] == {"max_keypoints": 16}
    assert plan["cached"] == {"features": False}
    assert service.list_jobs(status="ok")["jobs"]  # only the scene ran


def test_bad_wiring_is_refused_in_band_not_as_a_failed_job(service, scene):
    """A wiring mistake should come back as an immediate error, not as a job that
    has to be polled to discover it never had a chance."""
    feats = service.run("FakeDetector", run_id="r",
                        inputs={"scene": scene["outputs"]["scene"]})
    with pytest.raises(WiringError, match="FakeMatcher"):
        service.run("FakeTracker", run_id="r", inputs={
            "scene": scene["outputs"]["scene"],
            "pairs": feats["outputs"]["features"],
        })


def test_a_failing_module_becomes_a_failed_job_with_a_traceback(service, scene, monkeypatch):
    from sfmorch import ExecutionError

    def boom(self, job, store):
        raise ExecutionError(job.spec.name, RuntimeError("library blew up"))

    monkeypatch.setattr(type(service.orch.runner), "run", boom)
    outcome = service.run("FakeDetector", run_id="r",
                          inputs={"scene": scene["outputs"]["scene"]})

    assert outcome["status"] == "failed"
    assert "blew up" in outcome["error"]
    assert outcome["traceback"]


def test_slow_work_degrades_into_polling(service, scene):
    outcome = service.run(
        "FakeDetector", run_id="r",
        inputs={"scene": scene["outputs"]["scene"]},
        wait_s=0.0,
    )
    assert outcome["status"] in ("queued", "running", "ok")

    finished = service.job(outcome["job_id"], wait_s=60)
    assert finished["status"] == "ok"
    assert finished["metrics"]["keypoints_per_image"] == 16.0


def test_unknown_job_is_an_error(service):
    with pytest.raises(OrchestratorError, match="no job"):
        service.job("job_nope")


def test_caching_is_reported(service, scene):
    again = service.run("MakeScene", run_id="r", params={"n_images": 4})
    assert again["cached"] is True
    assert again["outputs"] == scene["outputs"]


# --------------------------------------------------------------------------- #
# Inspection
# --------------------------------------------------------------------------- #


def test_artifact_returns_the_rendered_manifest(service, scene):
    doc = service.artifact(scene["outputs"]["scene"])

    assert doc["type"] == "scene/v1"
    assert "images" in doc["files"]
    assert doc["artifact_md"].startswith("---\n")
    assert "n_images" in doc["metrics"]


def test_run_summary_lists_every_attempt(service, scene):
    pipeline(service, scene["outputs"]["scene"])
    summary = service.run_summary("r")

    assert [s["module"] for s in summary["steps"]] == [
        "MakeScene", "FakeDetector", "FakeMatcher", "FakeTracker"
    ]
    assert summary["leaves"]


def test_compare_reports_where_lineages_diverge(service, scene):
    scene_id = scene["outputs"]["scene"]
    _, pairs_a, tracks_a = pipeline(service, scene_id, keep_ratio=0.2)

    replayed = service.replay(
        run_id="r", from_artifact=pairs_a["outputs"]["pairs"],
        overrides={"keep_ratio": 1.0},
    )
    assert replayed["status"] == "ok"
    tracks_b = replayed["replayed"][-1]["outputs"]["tracks"]

    report = service.compare([tracks_a["outputs"]["tracks"], tracks_b])
    lines = next(iter(report["lineage_divergence"].values()))
    assert any("keep_ratio" in line for line in lines)


def test_compare_needs_two(service, scene):
    with pytest.raises(OrchestratorError, match="at least two"):
        service.compare([scene["outputs"]["scene"]])


# --------------------------------------------------------------------------- #
# Knowledge
# --------------------------------------------------------------------------- #


def test_find_alternatives_resolves_a_capability_escape(service):
    """The query a limitations.md escape compiles to."""
    empty = service.find_alternatives(
        produces="tracks/v1", not_consuming="pairwise_matches/v1"
    )
    assert empty["matches"] == []

    from conftest import contract_metrics
    from sfmorch import ModuleSpec

    service.registry.add(ModuleSpec.from_doc({
        "name": "DirectTracker",
        "version": "1.0.0",
        "consumes": {"scene": {"type": "scene/v1"}},
        "produces": {"tracks": {"type": "tracks/v1"}},
        "metrics": contract_metrics("tracks/v1"),
    }))
    found = service.find_alternatives(
        produces="tracks/v1", not_consuming="pairwise_matches/v1"
    )
    assert [m["name"] for m in found["matches"]] == ["DirectTracker"]


def test_module_skill_error_names_what_is_available(service):
    with pytest.raises(OrchestratorError, match="Available"):
        service.module_skill("FakeTracker", "nonexistent")


def test_workflow_skill_reads_the_knowledge_base(service):
    doc = service.workflow_skill("SKILLS.md")
    assert "Knowledge Index" in doc["text"]


# --------------------------------------------------------------------------- #
# Authoring
# --------------------------------------------------------------------------- #


def test_scaffold_writes_a_complete_module(service, tmp_path):
    service.config.modules_dir = tmp_path / "modules"
    result = service.scaffold_module(
        "MyMatcher",
        kind="matching",
        consumes={"scene": "scene/v1", "features": "features/v1"},
        produces={"pairs": "pairwise_matches/v1"},
        pip=["kornia==0.7.1"],
        repo="https://github.com/example/matcher",
    )

    files = set(result["files"])
    assert {"module.yaml", "adapter.py", "Dockerfile"} <= files
    assert {f"skills/{t}.md" for t in
            ("SKILL", "tuning", "limitations", "artifact", "sources")} <= files
    assert result["image"] == "sfmstack/my-matcher:0.1.0"


def test_the_scaffolded_manifest_parses_and_registers(service, tmp_path):
    from pathlib import Path

    service.config.modules_dir = tmp_path / "modules"
    service.scaffold_module(
        "MyMatcher",
        consumes={"scene": "scene/v1", "features": "features/v1"},
        produces={"pairs": "pairwise_matches/v1"},
    )

    fresh = ModuleRegistry(types=service.registry.types)
    fresh.load_dir(Path(service.config.modules_dir))
    spec = fresh.get("MyMatcher")

    assert spec.consumed_types == {"scene/v1", "features/v1"}
    assert spec.produced_types == {"pairwise_matches/v1"}


def test_the_scaffolded_adapter_is_valid_python(service, tmp_path):
    """The templates are f-strings, so any brace in the generated code is an
    interpolation unless escaped. A commented-out example containing `{i + 1}`
    silently became a NameError at generation time until this caught it."""
    service.config.modules_dir = tmp_path / "modules"
    service.scaffold_module(
        "MyThing",
        consumes={"scene": "scene/v1"},
        produces={"tracks": "tracks/v1"},
        pip=["numpy==2.1.3"],
    )
    root = tmp_path / "modules" / "my_thing"

    compile((root / "adapter.py").read_text(), "adapter.py", "exec")

    import yaml

    manifest = yaml.safe_load((root / "module.yaml").read_text())
    assert manifest["resources"]["expected_duration_s"]
    assert "numpy==2.1.3" in (root / "Dockerfile").read_text()


def test_the_scaffolded_adapter_refuses_to_run(service, tmp_path):
    """A stub that silently produces an empty artifact is worse than one that
    refuses -- it looks like a successful reconstruction."""
    service.config.modules_dir = tmp_path / "modules"
    service.scaffold_module("MyThing", produces={"tracks": "tracks/v1"})

    source = (tmp_path / "modules" / "my_thing" / "adapter.py").read_text()
    assert "raise NotImplementedError" in source


def test_scaffold_rejects_a_module_that_produces_nothing(service, tmp_path):
    from sfmorch import ManifestError

    service.config.modules_dir = tmp_path / "modules"
    with pytest.raises(ManifestError, match="at least one output"):
        service.scaffold_module("Nothing", produces={})


def test_scaffold_will_not_silently_overwrite(service, tmp_path):
    from sfmorch import ManifestError

    service.config.modules_dir = tmp_path / "modules"
    service.scaffold_module("Thing", produces={"tracks": "tracks/v1"})
    with pytest.raises(ManifestError, match="already exists"):
        service.scaffold_module("Thing", produces={"tracks": "tracks/v1"})


def test_reload_picks_up_a_scaffolded_module(service, tmp_path):
    import shutil
    from pathlib import Path

    staging = tmp_path / "modules"
    shutil.copytree(Path(FIXTURES).resolve(), staging)
    service.config.modules_dir = staging

    service.scaffold_module(
        "BrandNew", consumes={"scene": "scene/v1"}, produces={"tracks": "tracks/v1"}
    )
    reloaded = service.reload_modules()

    assert "BrandNew" in reloaded["modules"]
    assert "BrandNew" in service.orch.registry


# --------------------------------------------------------------------------- #
# Smoke test -- the manifest's promises
# --------------------------------------------------------------------------- #


def test_smoke_test_passes_for_a_well_formed_module(service):
    result = service.smoke_test("MakeScene", params={"n_images": 3})
    assert result["passed"] is True
    assert result["contract_problems"] == []


def test_smoke_test_catches_a_metric_declared_but_never_emitted(service):
    """A tuning section keyed on a metric the module never emits is dead text --
    exactly the drift that made the predecessor's guidance untrustworthy."""
    from sfmorch import MetricSpec

    spec = service.registry.get("MakeScene")
    spec.metrics["phantom"] = MetricSpec(
        name="phantom", direction="higher_better", meaning="never emitted"
    )
    result = service.smoke_test("MakeScene", params={"n_images": 3})

    assert result["passed"] is False
    assert any("declared but not emitted" in p for p in result["contract_problems"])


def test_smoke_test_catches_a_dangling_skill_pointer(service):
    from sfmorch import DiagnosticSpec

    spec = service.registry.get("MakeScene")
    spec.diagnostics["broken"] = DiagnosticSpec(
        code="broken", see_also="nowhere.md#anchor"
    )
    result = service.smoke_test("MakeScene", params={"n_images": 3})

    assert result["passed"] is False
    assert any("does not exist" in p for p in result["contract_problems"])


# --------------------------------------------------------------------------- #
# Smoke test -- the manifest and the adapter each hold half of a diagnostic
#
# The manifest is the catalogue `sfm_describe_module` shows before anything runs.
# The adapter writes the instance, with the run's numbers in it, and that is what
# reaches the caller. Nothing kept the two in step until these checks existed.
# --------------------------------------------------------------------------- #


def weak_match(service, scene, keep_ratio):
    feats = service.run("FakeDetector", run_id="r", inputs={"scene": scene})
    return service.smoke_test(
        "FakeMatcher",
        inputs={"scene": scene, "features": feats["outputs"]["features"]},
        params={"keep_ratio": keep_ratio},
    )


def test_a_band_alarm_that_agrees_with_its_own_metric_passes(service, scene):
    """`weak_matching` declares `metric: inlier_yield`, fires below 0.15, and the
    metric's healthy band starts at 0.15. Fired and outside: consistent."""
    result = weak_match(service, scene["outputs"]["scene"], 0.1)

    assert "weak_matching" in [d["code"] for d in result["run"]["diagnostics"]]
    assert result["contract_problems"] == []
    assert result["passed"] is True


def test_smoke_test_catches_an_alarm_that_fires_inside_its_own_healthy_band(
    service, scene
):
    """The drift this exists for: the adapter's firing threshold and the
    manifest's band are two numbers that have to agree, in two files."""
    from sfmorch import MetricSpec

    spec = service.registry.get("FakeMatcher")
    spec.metrics["inlier_yield"] = MetricSpec(
        name="inlier_yield", direction="higher_better",
        healthy=(0.0, None),  # now nothing can be unhealthy, but the alarm still fires
        meaning="Retained correspondences over candidates.",
    )
    result = weak_match(service, scene["outputs"]["scene"], 0.1)

    assert result["passed"] is False
    assert any("inside the healthy band" in p for p in result["contract_problems"])


def test_smoke_test_catches_a_severity_that_drifted_from_the_manifest(service, scene):
    from sfmorch import DiagnosticSpec

    spec = service.registry.get("FakeMatcher")
    spec.diagnostics["weak_matching"] = DiagnosticSpec(
        code="weak_matching", severity="error", metric="inlier_yield",
        see_also="tuning.md#inlier_yield-below-015",
    )
    result = weak_match(service, scene["outputs"]["scene"], 0.1)

    assert result["passed"] is False
    assert any("severity" in p for p in result["contract_problems"])


def test_smoke_test_catches_a_see_also_that_drifted_from_the_manifest(service, scene):
    """The manifest's pointer is the one the agent read BEFORE running, so a
    divergent one in the artifact sends it somewhere it was not promised."""
    from sfmorch import DiagnosticSpec

    spec = service.registry.get("FakeMatcher")
    spec.diagnostics["weak_matching"] = DiagnosticSpec(
        code="weak_matching", severity="warn", metric="inlier_yield",
        see_also="tuning.md#somewhere-else",
    )
    result = weak_match(service, scene["outputs"]["scene"], 0.1)

    assert result["passed"] is False
    assert any("pointing at" in p for p in result["contract_problems"])


def test_smoke_test_catches_a_diagnostic_raised_but_never_declared(service, scene):
    spec = service.registry.get("FakeMatcher")
    del spec.diagnostics["weak_matching"]
    result = weak_match(service, scene["outputs"]["scene"], 0.1)

    assert result["passed"] is False
    assert any("not declared in module.yaml" in p for p in result["contract_problems"])


def test_smoke_test_catches_a_metric_link_that_names_nothing(service):
    """Catches a renamed metric, which leaves the alarm pointing at nothing. This
    one is static -- it does not need the diagnostic to fire."""
    from sfmorch import DiagnosticSpec

    spec = service.registry.get("MakeScene")
    spec.diagnostics["orphan"] = DiagnosticSpec(
        code="orphan", metric="renamed_away", see_also="tuning.md#anything",
    )
    result = service.smoke_test("MakeScene", params={"n_images": 3})

    assert result["passed"] is False
    assert any("does not declare" in p for p in result["contract_problems"])


def test_a_declared_diagnostic_that_did_not_fire_is_not_a_problem(service, scene):
    """One smoke input cannot trip every condition, and demanding it would push
    modules toward diagnostics that always fire -- the opposite of the point."""
    result = weak_match(service, scene["outputs"]["scene"], 1.0)

    assert result["run"]["diagnostics"] == []
    assert "weak_matching" in service.registry.get("FakeMatcher").diagnostics
    assert result["passed"] is True
