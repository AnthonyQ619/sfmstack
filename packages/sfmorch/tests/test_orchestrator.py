import pytest

from sfmorch import ExecutionError, ParamError, Run, WiringError


def pipeline(orch, scene, *, max_keypoints=16, keep_ratio=1.0, min_track_len=2):
    """scene -> features -> pairs -> tracks -> sparse."""
    feats = orch.run(
        "FakeDetector",
        run_id="run_test",
        inputs={"scene": scene.id},
        params={"max_keypoints": max_keypoints},
    ).primary
    pairs = orch.run(
        "FakeMatcher",
        run_id="run_test",
        inputs={"scene": scene.id, "features": feats.id},
        params={"keep_ratio": keep_ratio},
    ).primary
    tracks = orch.run(
        "FakeTracker",
        run_id="run_test",
        inputs={"scene": scene.id, "pairs": pairs.id},
        params={"min_track_len": min_track_len},
    ).primary
    sparse = orch.run(
        "FakeReconstructor",
        run_id="run_test",
        inputs={"scene": scene.id, "tracks": tracks.id},
    ).primary
    return feats, pairs, tracks, sparse


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


def test_a_five_stage_pipeline_runs(orch, scene):
    feats, pairs, tracks, sparse = pipeline(orch, scene)

    assert feats.type == "features/v1"
    assert pairs.type == "pairwise_matches/v1"
    assert tracks.type == "tracks/v1"
    assert sparse.type == "sparse_model/v1"
    assert sparse.metric("num_points3d") > 0


def test_provenance_chains_across_the_whole_pipeline(orch, scene):
    _, _, tracks, sparse = pipeline(orch, scene)

    assert tracks.id in sparse.manifest.inputs
    assert sparse.manifest.scene == scene.id
    assert set(orch.store.ancestry(sparse.id)) >= {sparse.id, tracks.id, scene.id}


def test_the_run_record_captures_every_step(orch, scene):
    pipeline(orch, scene)
    summary = orch.summary("run_test")

    assert [s["module"] for s in summary["steps"]] == [
        "MakeScene",
        "FakeDetector",
        "FakeMatcher",
        "FakeTracker",
        "FakeReconstructor",
    ]
    assert all(s["status"] == "ok" for s in summary["steps"])


def test_run_md_is_written_and_reloadable(orch, scene):
    pipeline(orch, scene)
    path = orch.runs_dir / "run_test" / "run.md"
    text = path.read_text()

    assert text.startswith("---\n")
    assert "| # | Module | Params | Status | Key metrics |" in text
    assert "FakeTracker" in text

    reloaded = Run.open(path.parent)
    assert len(reloaded.steps) == 5


def test_the_run_is_bound_to_its_scene(orch, scene):
    """runs/INDEX.md retrieval keys on this, so it has to be recorded rather
    than reconstructed by walking every step later."""
    assert orch.open_run("run_test").scene == scene.id
    assert orch.summary("run_test")["scene"] == scene.id


def test_diagnostics_propagate_into_the_run_record(orch, scene):
    """A weak matcher should surface its diagnostic at the step level, which is
    what the driving agent reads without opening every artifact."""
    pipeline(orch, scene, max_keypoints=16, keep_ratio=0.1)
    steps = {s["module"]: s for s in orch.summary("run_test")["steps"]}
    assert "weak_matching" in steps["FakeMatcher"]["diagnostics"]


# --------------------------------------------------------------------------- #
# Type checking happens BEFORE anything runs
# --------------------------------------------------------------------------- #


def test_wrong_input_type_is_refused(orch, scene):
    feats = orch.run(
        "FakeDetector", run_id="run_test", inputs={"scene": scene.id}
    ).primary
    with pytest.raises(WiringError, match="expects 'pairwise_matches/v1'"):
        orch.run(
            "FakeTracker",
            run_id="run_test",
            inputs={"scene": scene.id, "pairs": feats.id},
        )


def test_the_refusal_names_modules_that_would_satisfy_the_slot(orch, scene):
    feats = orch.run(
        "FakeDetector", run_id="run_test", inputs={"scene": scene.id}
    ).primary
    with pytest.raises(WiringError, match="FakeMatcher"):
        orch.run(
            "FakeTracker",
            run_id="run_test",
            inputs={"scene": scene.id, "pairs": feats.id},
        )


def test_missing_required_input_is_refused(orch, scene):
    with pytest.raises(WiringError, match="requires input 'pairs'"):
        orch.run("FakeTracker", run_id="run_test", inputs={"scene": scene.id})


def test_unknown_input_slot_is_refused(orch, scene):
    with pytest.raises(WiringError, match="no input slot"):
        orch.run(
            "FakeDetector",
            run_id="run_test",
            inputs={"scene": scene.id, "nonsense": scene.id},
        )


def test_a_refused_run_is_not_recorded_as_a_step(orch, scene):
    before = len(orch.summary("run_test")["steps"])
    with pytest.raises(WiringError):
        orch.run("FakeTracker", run_id="run_test", inputs={"scene": scene.id})
    assert len(orch.summary("run_test")["steps"]) == before


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #


def test_defaults_are_materialised_into_the_recipe(orch, scene):
    """A run that omits a default must hash the same as one that spells it out,
    or the cache would miss on an identical pipeline."""
    a = orch.check("FakeDetector", inputs={"scene": scene.id})
    b = orch.check(
        "FakeDetector", inputs={"scene": scene.id}, params={"max_keypoints": 16}
    )
    assert a["params"] == b["params"] == {"max_keypoints": 16}
    assert a["outputs"] == b["outputs"]


def test_unknown_param_is_rejected(orch, scene):
    with pytest.raises(ParamError, match="unknown parameter"):
        orch.run(
            "FakeDetector",
            run_id="run_test",
            inputs={"scene": scene.id},
            params={"maxKeypoints": 32},
        )


def test_out_of_range_param_is_rejected(orch, scene):
    with pytest.raises(ParamError, match="above the maximum"):
        orch.run(
            "FakeDetector",
            run_id="run_test",
            inputs={"scene": scene.id},
            params={"max_keypoints": 99999},
        )


def test_wrong_param_type_is_rejected(orch, scene):
    with pytest.raises(ParamError, match="expects integer"):
        orch.run(
            "FakeDetector",
            run_id="run_test",
            inputs={"scene": scene.id},
            params={"max_keypoints": "lots"},
        )


def test_boolean_is_not_accepted_as_an_integer(orch, scene):
    with pytest.raises(ParamError, match="got boolean"):
        orch.run(
            "FakeDetector",
            run_id="run_test",
            inputs={"scene": scene.id},
            params={"max_keypoints": True},
        )


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #


def test_identical_work_is_not_repeated(orch, scene):
    first = orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})
    second = orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})

    assert first.cached is False
    assert second.cached is True
    assert first.primary.id == second.primary.id


def test_a_cache_hit_is_still_recorded_as_a_step(orch, scene):
    orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})
    orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})
    steps = orch.summary("run_test")["steps"]
    assert [s.get("cached", False) for s in steps if s["module"] == "FakeDetector"] == [
        False,
        True,
    ]


def test_check_reports_cache_state_without_running(orch, scene):
    plan = orch.check("FakeDetector", inputs={"scene": scene.id})
    assert plan["cached"] == {"features": False}

    orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})
    assert orch.check("FakeDetector", inputs={"scene": scene.id})["cached"] == {
        "features": True
    }


def test_force_reruns_a_cached_step(orch, scene):
    orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})
    again = orch.run(
        "FakeDetector", run_id="run_test", inputs={"scene": scene.id}, force=True
    )
    assert again.cached is False


def test_a_scene_is_shared_across_parallel_runs(orch):
    """Five pipelines on one scene must decode once, not five times."""
    a = orch.run("MakeScene", run_id="run_a", params={"n_images": 4}).primary
    b = orch.run("MakeScene", run_id="run_b", params={"n_images": 4}).primary
    assert a.id == b.id


def test_different_params_keep_both_attempts(orch, scene):
    """Re-running with new parameters must never overwrite the earlier result --
    comparing attempts is the point."""
    a = orch.run(
        "FakeDetector",
        run_id="run_test",
        inputs={"scene": scene.id},
        params={"max_keypoints": 16},
    ).primary
    b = orch.run(
        "FakeDetector",
        run_id="run_test",
        inputs={"scene": scene.id},
        params={"max_keypoints": 64},
    ).primary

    assert a.id != b.id
    assert orch.store.exists(a.id) and orch.store.exists(b.id)


# --------------------------------------------------------------------------- #
# Failure
# --------------------------------------------------------------------------- #


def test_a_failing_module_is_recorded_and_seals_nothing(orch, scene, monkeypatch):
    def boom(self, job, store):
        raise ExecutionError(job.spec.name, RuntimeError("upstream library blew up"))

    monkeypatch.setattr(type(orch.runner), "run", boom)

    with pytest.raises(ExecutionError, match="blew up"):
        orch.run("FakeDetector", run_id="run_test", inputs={"scene": scene.id})

    failed = [s for s in orch.summary("run_test")["steps"] if s["status"] == "failed"]
    assert len(failed) == 1
    assert "blew up" in failed[0]["error"]
    assert orch.store.list(type="features/v1") == []


def test_a_truncated_run_record_does_not_poison_the_run_id(orch, scene):
    """A crashed write used to make a run_id permanently unusable.

    `Run.save` wrote in place, so a kill or a full filesystem mid-write left a file
    whose frontmatter would not parse. Every later run under that id then died in
    `open_run`, before reaching the module -- turning a transient container race
    into a dead tag that had to be deleted by hand. Three separate sessions hit it.
    """
    orch.run("FakeDetector", run_id="crashy", inputs={"scene": scene.id},
             params={"max_keypoints": 8})
    record = orch.runs_dir / "crashy" / "run.md"
    assert record.exists()

    # Exactly what an interrupted write leaves behind: the opening delimiter and
    # part of the frontmatter, with no closing one.
    record.write_text("---\nrun: crashy\nste", encoding="utf-8")
    orch._runs.clear()  # a fresh process would not have it cached

    result = orch.run("FakeDetector", run_id="crashy", inputs={"scene": scene.id},
                      params={"max_keypoints": 16})
    assert result.primary.metric("keypoints_min") > 0

    # The unreadable file is set aside rather than deleted, and the new record says
    # where it went -- losing the attempt history silently would be its own bug.
    assert (orch.runs_dir / "crashy" / "run.md.corrupt.0").exists()
    body = record.read_text(encoding="utf-8")
    assert "could not be read" in body
    assert "run.md.corrupt.0" in body


def test_a_failed_save_leaves_the_previous_record_intact(orch, scene, monkeypatch):
    """The atomic-write half of the same fix.

    Under ENOSPC the temp write fails; what must NOT happen is the live record
    being truncated on the way out. Losing an update is recoverable, losing the
    file is not.
    """
    orch.run("FakeDetector", run_id="nospace", inputs={"scene": scene.id},
             params={"max_keypoints": 8})
    record = orch.runs_dir / "nospace" / "run.md"
    before = record.read_text(encoding="utf-8")

    import pathlib
    real = pathlib.Path.write_text

    def full_disk(self, *a, **kw):
        if self.name.startswith(".run.md"):
            raise OSError(28, "No space left on device")
        return real(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "write_text", full_disk)
    run = orch.open_run("nospace")
    with pytest.raises(OSError):
        run.save()
    monkeypatch.undo()

    assert record.read_text(encoding="utf-8") == before
    assert not list(record.parent.glob(".run.md.*.tmp"))
