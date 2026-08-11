import pytest
import yaml

from sfmorch import ManifestError, ModuleNotFound, ModuleRegistry, ModuleSpec


def write_module(tmp_path, name, doc):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "module.yaml").write_text(yaml.safe_dump(doc))
    return d


# tracks/v1 fixes a required metric set, and these tests are about manifest
# parsing rather than about that contract -- so MINIMAL produces a module-declared
# custom type, which has no required metrics. The contract itself is tested by
# test_a_module_must_report_the_metrics_its_output_type_requires.
MINIMAL = {
    "name": "Thing",
    "version": "1.0.0",
    "produces": {"out": {"type": "custom/thing/v1"}},
    "types": [
        {
            "type": "custom/thing/v1",
            "summary": "Test-only payload.",
            "files": {"blob": {"required": True, "arrays": {"x": {"shape": [None]}}}},
        }
    ],
}


from conftest import contract_metrics  # noqa: E402

# --------------------------------------------------------------------------- #
# Manifest parsing
# --------------------------------------------------------------------------- #


def test_fixture_modules_all_load(registry):
    assert registry.names() == [
        "FakeDetector",
        "FakeMatcher",
        "FakeReconstructor",
        "FakeTracker",
        "MakeScene",
        "SlowModule",
    ]


def test_version_must_be_semver_because_it_is_part_of_every_artifact_id():
    with pytest.raises(ManifestError, match="semver"):
        ModuleSpec.from_doc({**MINIMAL, "version": "v1"})


def test_module_name_must_be_a_bare_identifier():
    with pytest.raises(ManifestError, match="bare identifier"):
        ModuleSpec.from_doc({**MINIMAL, "name": "my-module"})


def test_a_module_must_produce_something():
    with pytest.raises(ManifestError, match="at least one output"):
        ModuleSpec.from_doc({"name": "Thing", "version": "1.0.0"})


def test_slot_without_a_type_is_rejected():
    with pytest.raises(ManifestError, match="must declare a payload type"):
        ModuleSpec.from_doc({**MINIMAL, "consumes": {"a": {}}})


def test_unknown_metric_direction_is_rejected():
    with pytest.raises(ManifestError, match="direction"):
        ModuleSpec.from_doc({**MINIMAL, "metrics": {"m": {"direction": "bigger"}}})


def test_diagnostic_needs_a_code():
    with pytest.raises(ManifestError, match="needs a `code`"):
        ModuleSpec.from_doc({**MINIMAL, "diagnostics": [{"message": "hi"}]})


# --------------------------------------------------------------------------- #
# Type wiring
# --------------------------------------------------------------------------- #


def test_unknown_payload_type_is_caught_at_registration(types):
    reg = ModuleRegistry(types=types)
    spec = ModuleSpec.from_doc({**MINIMAL, "produces": {"out": {"type": "bogus/v1"}}})
    with pytest.raises(ManifestError, match="unknown payload type"):
        reg.add(spec)


def test_a_module_may_declare_its_own_custom_type(types):
    reg = ModuleRegistry(types=types)
    reg.add(
        ModuleSpec.from_doc(
            {
                **MINIMAL,
                "produces": {"out": {"type": "custom/gaussians/v1"}},
                "types": [
                    {
                        "type": "custom/gaussians/v1",
                        "files": {
                            "splats": {
                                "arrays": {"mu": {"shape": [None, 3], "dtype": ["float32"]}}
                            }
                        },
                    }
                ],
            }
        )
    )
    assert "custom/gaussians/v1" in types


def test_duplicate_module_names_are_rejected(types):
    reg = ModuleRegistry(types=types)
    reg.add(ModuleSpec.from_doc(MINIMAL))
    with pytest.raises(ManifestError, match="duplicate module name"):
        reg.add(ModuleSpec.from_doc(MINIMAL))


def test_unknown_module_lookup_lists_what_exists(registry):
    with pytest.raises(ModuleNotFound, match="FakeDetector"):
        registry.get("Nope")


# --------------------------------------------------------------------------- #
# Orphan types -- surfaced at registration, not discovered at runtime
# --------------------------------------------------------------------------- #


def test_terminal_output_is_flagged_as_an_orphan(registry):
    """sparse_model/v1 is a final output here: nothing consumes it. Legal, but
    the agent should learn it before spending a GPU hour, not after."""
    orphans = {(w.module, w.type) for w in registry.warnings}
    assert ("FakeReconstructor", "sparse_model/v1") in orphans


def test_consumed_types_are_not_flagged(registry):
    orphans = {w.type for w in registry.warnings}
    assert "tracks/v1" not in orphans
    assert "features/v1" not in orphans


def test_adding_a_consumer_clears_the_orphan_warning(registry, types):
    assert any(w.type == "sparse_model/v1" for w in registry.warnings)
    registry.add(
        ModuleSpec.from_doc(
            {
                "name": "Optimizer",
                "version": "1.0.0",
                "consumes": {"sparse": {"type": "sparse_model/v1"}},
                "produces": {"out": {"type": "sparse_model/v1"}},
                "metrics": contract_metrics("sparse_model/v1"),
            }
        )
    )
    assert not any(w.type == "sparse_model/v1" for w in registry.warnings)



def test_a_module_must_report_the_metrics_its_output_type_requires(tmp_path):
    """The floor that makes two implementations of a stage comparable.

    Payload shape alone does not: SIFT and SuperPoint both emit features/v1, and if
    one reports `keypoints_per_image` while the other reports `n_features` there is
    no way to ask which covered the scene better without knowing both modules. The
    error has to name every missing metric at once -- a module author fixing them
    one registry-load at a time is the failure mode this replaces."""
    with pytest.raises(ManifestError, match="metric contract") as e:
        ModuleRegistry().add(ModuleSpec.from_doc({
            "name": "Thing",
            "version": "1.0.0",
            "produces": {"out": {"type": "features/v1"}},
        }))
    for name in ("keypoints_per_image", "keypoints_min", "spatial_coverage"):
        assert name in str(e.value)


def test_a_metric_may_not_point_the_opposite_way_from_its_type(tmp_path):
    """Direction is fixed by the type and the band is not. `healthy` is
    method-specific -- 200 keypoints is thin for SIFT and ordinary for a learned
    detector -- but a metric that means 'higher is better' in one module and the
    reverse in its sibling is not one metric, and nothing comparing them can tell."""
    doc = {
        "name": "Thing",
        "version": "1.0.0",
        "produces": {"out": {"type": "features/v1"}},
        "metrics": contract_metrics("features/v1"),
    }
    doc["metrics"]["keypoints_min"]["direction"] = "lower_better"

    with pytest.raises(ManifestError, match="fixes it at 'higher_better'"):
        ModuleRegistry().add(ModuleSpec.from_doc(doc))


# --------------------------------------------------------------------------- #
# Capability queries -- what makes a limitations.md escape expressible
# --------------------------------------------------------------------------- #


def test_find_by_produced_type(registry):
    assert [m.name for m in registry.find(produces="tracks/v1")] == ["FakeTracker"]


def test_find_by_consumed_type(registry):
    names = [m.name for m in registry.find(consumes="scene/v1")]
    assert names == ["FakeDetector", "FakeMatcher", "FakeReconstructor", "FakeTracker"]


def test_not_consuming_expresses_switch_to_a_direct_tracker(registry, types):
    """The canonical escape: 'something producing tracks/v1 that does NOT consume
    pairwise_matches/v1' -- i.e. stop feeding a matcher that isn't working."""
    assert registry.find(produces="tracks/v1", not_consuming="pairwise_matches/v1") == []

    registry.add(
        ModuleSpec.from_doc(
            {
                "name": "DirectTracker",
                "version": "1.0.0",
                "consumes": {"scene": {"type": "scene/v1"}},
                "produces": {"tracks": {"type": "tracks/v1"}},
                "metrics": contract_metrics("tracks/v1"),
            }
        )
    )
    found = registry.find(produces="tracks/v1", not_consuming="pairwise_matches/v1")
    assert [m.name for m in found] == ["DirectTracker"]


def test_excluding_drops_the_module_you_gave_up_on(registry):
    found = registry.find(produces="tracks/v1", excluding="FakeTracker")
    assert found == []


def test_successors_answers_what_can_follow_this(registry):
    detector = registry.get("FakeDetector")
    assert [m.name for m in registry.successors(detector)] == ["FakeMatcher"]


# --------------------------------------------------------------------------- #
# describe() -- one call gives the machine contract and the curated guidance
# --------------------------------------------------------------------------- #


def test_describe_carries_the_param_schema_as_json_schema(registry):
    doc = registry.get("FakeTracker").describe()
    props = doc["params"]["properties"]
    assert props["min_track_len"] == {
        "type": "integer",
        "description": "Minimum observations for a track to be kept.",
        "default": 2,
        "minimum": 2,
        "maximum": 10,
    }
    assert doc["params"]["additionalProperties"] is False


def test_describe_carries_metric_interpretation(registry):
    doc = registry.get("FakeTracker").describe()
    assert doc["metrics"]["avg_track_length"]["direction"] == "higher_better"
    assert doc["metrics"]["avg_track_length"]["healthy"] == [3.0, None]


def test_describe_carries_diagnostics_with_a_pointer_into_the_skills(registry):
    doc = registry.get("FakeTracker").describe()
    diag = doc["diagnostics"]["too_few_tracks"]
    assert diag["see_also"] == "tuning.md#track_count-below-10"
    assert diag["suggested_actions"]


def test_describe_carries_per_param_tuning_notes(registry):
    doc = registry.get("FakeTracker").describe()
    assert "MEAN" in doc["param_tuning"]["min_track_len"]


def test_summary_marks_terminal_modules(registry):
    rows = {r["name"]: r for r in registry.summary()}
    assert rows["FakeReconstructor"]["terminal"] is True
    assert rows["FakeTracker"]["terminal"] is False
