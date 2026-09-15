"""The second solve.

When the pose stage reports points that left the image during its in-loop window
solves, the service re-solves the chain behind the refined model at a wider window
and keeps the wider solve unless it failed, the verifier vetoed it, or it gave up
more cameras than the pose stage's registered-fraction band allows against a first
solve the verifier accepted. The wider last-resort window runs only when the
default one was not kept.

The verifier is stood in for here: which models it vetoes is what each test
stages, and the real one needs real geometry.
"""

from pathlib import Path

import pytest

from sfmorch import Orchestrator
from sfmorch.run_record import Run
from sfmorch.service import ServiceConfig, SfmService, second_solve_rungs

from sfmorch_test_helpers import FIXTURE_MODULES

SECOND_SOLVE_MODULES = Path(__file__).parent / "fixtures" / "second_solve"
VETO = "contradicted_by_held_out_evidence"


@pytest.fixture
def service(registry, store):
    registry.load_dir(SECOND_SOLVE_MODULES)
    svc = SfmService(
        config=ServiceConfig(modules_dir=FIXTURE_MODULES, store_root=store.root,
                             skills_dir=Path("skills").resolve(), inline_wait_s=60.0),
        orchestrator=Orchestrator(store=store, registry=registry),
        registry=registry,
    )
    yield svc
    svc.jobs.shutdown()


def veto_windows(svc, windows):
    """Veto every model whose poses were solved at one of `windows`."""

    def verify(model, run_id):
        pose = svc._ancestor_of_type(model, "poses/v1")
        window = pose.manifest.produced_by.params["local_ba_window"]
        return {"status": "ran", "model": model.id, "metrics": {},
                "diagnostics": [{"code": VETO}] if window in windows else []}

    svc._verify_model = verify


def chain(svc, *, n_images=45, window=8, escape_below=20, fail_at=0, drop_from=0, drop=0):
    def run(module, **kw):
        out = svc.run(module, run_id="r", wait_s=60.0, **kw)
        assert out["status"] == "ok", out
        return out

    scene = run("MakeScene", params={"n_images": n_images})["outputs"]["scene"]
    feats = run("FakeDetector", inputs={"scene": scene})["outputs"]["features"]
    pairs = run("FakeMatcher", inputs={"scene": scene, "features": feats})["outputs"]["pairs"]
    tracks = run("FakeTracker", inputs={"scene": scene, "pairs": pairs})["outputs"]["tracks"]
    pose = run("FakePose", inputs={"scene": scene, "tracks": tracks},
               params={"local_ba_window": window, "escape_below": escape_below,
                       "fail_at": fail_at, "drop_from": drop_from, "drop": drop})
    sparse = run("FakeTriangulator", inputs={
        "scene": scene, "tracks": tracks, "poses": pose["outputs"]["poses"]})
    refined = run("FakeRefiner", inputs={
        "scene": scene, "sparse": sparse["outputs"]["sparse"]})
    return pose, refined


def test_the_windows_are_the_default_then_the_last_resort_each_capped_at_the_capture():
    assert second_solve_rungs(8, 45) == [(28, "default"), (40, "last_resort")]
    assert second_solve_rungs(8, 32) == [(28, "default"), (32, "last_resort")]
    assert second_solve_rungs(8, 20) == [(20, "default")]
    assert second_solve_rungs(28, 45) == [(40, "last_resort")]
    assert second_solve_rungs(30, 45) == [(40, "last_resort")]
    assert second_solve_rungs(40, 45) == []
    assert second_solve_rungs(8, 8) == []


def test_escaped_points_start_a_second_solve_that_is_kept(service):
    veto_windows(service, set())
    pose, refined = chain(service)

    assert pose["second_solve"]["status"] == "pending"
    s = refined["second_solve"]
    assert s["status"] == "kept_second"
    assert s["kept_window"] == 28
    assert [a["window"] for a in s["attempts"]] == [28]
    assert s["attempts"][0]["escaped_points"] == 0
    assert s["kept"] == s["attempts"][0]["model"] != refined["outputs"]["sparse"]


def test_only_the_chain_behind_the_model_is_solved_again(service):
    veto_windows(service, set())
    chain(service)
    steps = service.run_summary("r")["steps"]
    replayed = [s["module"] for s in steps if s.get("replay_of") is not None]
    assert replayed == ["FakePose", "FakeTriangulator", "FakeRefiner"]
    assert next(s for s in steps if s.get("replay_of") is not None)["params"][
        "local_ba_window"] == 28


def test_the_run_summary_says_which_of_the_two_solves_was_kept(service, store):
    veto_windows(service, set())
    _, refined = chain(service)
    first, kept = refined["outputs"]["sparse"], refined["second_solve"]["kept"]

    summary = service.run_summary("r")
    assert first in summary["leaves"] and kept in summary["leaves"]
    assert summary["second_solves"][0]["kept"] == kept
    assert summary["verification"][kept]["second_solve"] == "kept"
    assert summary["verification"][first]["second_solve"].startswith("not kept")
    # And it survives the record being read back from disk.
    assert Run.open(store.runs_dir / "r").second_solves[0]["kept"] == kept


def test_nothing_escaped_means_no_second_solve(service):
    veto_windows(service, set())
    pose, refined = chain(service, escape_below=0)
    assert "second_solve" not in pose
    assert "second_solve" not in refined


def test_the_last_resort_runs_only_when_the_default_is_vetoed(service):
    veto_windows(service, {28})
    _, refined = chain(service)
    s = refined["second_solve"]
    assert [(a["window"], a["vetoed"]) for a in s["attempts"]] == [(28, True), (40, False)]
    assert s["status"] == "kept_second" and s["kept_window"] == 40


def test_a_re_solve_that_fails_moves_to_the_last_resort(service):
    veto_windows(service, set())
    _, refined = chain(service, fail_at=28)
    s = refined["second_solve"]
    assert [a["status"] for a in s["attempts"]] == ["failed", "ok"]
    assert s["kept_window"] == 40


def test_when_every_wider_solve_is_vetoed_the_first_is_kept(service):
    veto_windows(service, {28, 40})
    _, refined = chain(service)
    s = refined["second_solve"]
    assert s["status"] == "kept_first"
    assert s["kept"] == refined["outputs"]["sparse"]


def test_when_every_solve_is_vetoed_nothing_is_kept(service):
    veto_windows(service, {8, 28, 40})
    _, refined = chain(service)
    s = refined["second_solve"]
    assert s["status"] == "none_kept"
    assert s["kept"] is None
    assert len(s["attempts"]) == 2


def test_a_first_solve_at_the_default_escalates_only_on_a_veto(service):
    veto_windows(service, set())
    _, refined = chain(service, window=28, escape_below=40)
    assert refined["second_solve"]["status"] == "kept_first"
    assert refined["second_solve"]["attempts"] == []


def test_a_vetoed_first_solve_at_the_default_goes_to_the_last_resort(service):
    veto_windows(service, {28})
    _, refined = chain(service, window=28, escape_below=40)
    s = refined["second_solve"]
    assert [a["window"] for a in s["attempts"]] == [40]
    assert s["status"] == "kept_second"


def test_a_second_solve_that_loses_cameras_inside_the_band_is_kept_and_names_them(service):
    veto_windows(service, set())
    _, refined = chain(service, drop_from=28, drop=2)  # 43 of 45, inside 0.9
    s = refined["second_solve"]
    assert s["status"] == "kept_second" and s["kept_window"] == 28
    r = s["attempts"][0]["registration"]
    assert (r["first_registered"], r["registered"], r["within_band"]) == (45, 43, True)
    assert len(r["lost"]) == 2 and r["lost"][0] in s["reason"]
    t = s["attempts"][0]["trade_off"]
    assert t["cameras_lost"] == 2
    assert set(t["lost_structure_still_covered"]) == set(r["lost"])
    assert t["rotation_change_deg"]["shared_cameras"] == 43
    assert t["verdicts"] == {"first": "accepted", "second": "accepted"}


def test_losing_more_than_the_band_allows_against_an_accepted_first_is_not_kept(service):
    veto_windows(service, set())
    _, refined = chain(service, drop_from=28, drop=6)  # 39 of 45, below 0.9, at 28 and 40
    s = refined["second_solve"]
    assert [a["rejected_on_registration"] for a in s["attempts"]] == [True, True]
    assert s["status"] == "kept_first" and s["kept"] == refined["outputs"]["sparse"]
    assert "below the pose stage's registered_fraction band" in s["reason"]
    assert s["attempts"][0]["trade_off"]["cameras_lost"] == 6


def test_a_default_solve_below_the_band_moves_to_the_last_resort(service):
    veto_windows(service, set())
    _, refined = chain(service, drop_from=28, drop=6)
    first_rung = refined["second_solve"]["attempts"][0]
    assert first_rung["window"] == 28 and first_rung["rejected_on_registration"]
    assert [a["window"] for a in refined["second_solve"]["attempts"]] == [28, 40]


def test_against_a_vetoed_first_solve_fewer_cameras_do_not_disqualify(service):
    veto_windows(service, {8})
    _, refined = chain(service, drop_from=28, drop=6)
    s = refined["second_solve"]
    assert s["status"] == "kept_second" and s["kept_window"] == 28
    a = s["attempts"][0]
    assert a["registration"]["within_band"] is False
    assert a["rejected_on_registration"] is False
    assert a["trade_off"]["verdicts"]["first"] == "vetoed"
    assert "no alternative" in s["reason"]


def test_a_window_that_already_spans_the_capture_has_nothing_wider(service):
    veto_windows(service, set())
    pose, refined = chain(service, n_images=6, escape_below=20)
    assert "spans the capture" in pose["second_solve"]["note"]
    assert refined["second_solve"]["status"] == "no_wider_window"
    assert refined["second_solve"]["attempts"] == []


def test_the_health_profile_describes_the_model_the_service_kept(service):
    veto_windows(service, set())
    _, refined = chain(service)
    s = refined["second_solve"]
    assert s["status"] == "kept_second"
    # The model a caller delivers is the kept one, so that is what is profiled;
    # the first solve's profile moves into the decision beside it.
    assert refined["health_profile"]["model"] == s["kept"]
    assert s["first_solve_health_profile"]["model"] == refined["outputs"]["sparse"]


def test_without_a_second_solve_the_profile_is_the_step_s_own(service):
    veto_windows(service, set())
    _, refined = chain(service, escape_below=0)
    assert "second_solve" not in refined or refined["second_solve"]["status"] != "kept_second"
    assert refined["health_profile"]["model"] == refined["outputs"]["sparse"]


def test_the_composition_rung_is_labelled_as_what_it_measures():
    label = dict(SfmService._HEALTH_RUNGS)["composition"]
    assert label == "share of points seen in more than two views"


def test_compare_on_two_solves_of_one_chain_pairs_them_on_their_shared_tracks(service):
    veto_windows(service, set())
    _, refined = chain(service)
    first, kept = refined["outputs"]["sparse"], refined["second_solve"]["kept"]
    sm = service.compare([first, kept])["sparse_models"]
    assert set(sm["error_by_support"]) == {first, kept}
    pair = sm["pairs"][f"{first} vs {kept}"]
    assert pair["same_track_table"] is True
    assert "paired_error_by_support" in pair and "rotation_agreement" in pair
