"""The two-estimator reading, attached by the service after refinement.

plan/pose.md asks for the reading before any model is delivered; agents skipped it
in 5 of 113 sessions. The service now takes it as a fixed step, like the verifier:
on the model it keeps, against two correspondence-free estimators run once per
scene, in both forms, with the fire level stated. The estimators are stood in for
here by modules that place cameras on a circle.
"""

from pathlib import Path

import numpy as np
import pytest

from sfmorch import Orchestrator
from sfmorch.health import FIRE_LEVEL, two_estimator_reading
from sfmorch.service import ServiceConfig, SfmService

from sfmorch_test_helpers import FIXTURE_MODULES
from test_second_solve import SECOND_SOLVE_MODULES, chain, veto_windows

ESTIMATOR_MODULES = Path(__file__).parent / "fixtures" / "estimators"


@pytest.fixture
def service(registry, store):
    registry.load_dir(SECOND_SOLVE_MODULES)
    registry.load_dir(ESTIMATOR_MODULES)
    svc = SfmService(
        config=ServiceConfig(modules_dir=FIXTURE_MODULES, store_root=store.root,
                             skills_dir=Path("skills").resolve(), inline_wait_s=60.0),
        orchestrator=Orchestrator(store=store, registry=registry),
        registry=registry,
    )
    svc.ESTIMATORS = ("FakeEstimatorA", "FakeEstimatorB")
    veto_windows(svc, set())
    yield svc
    svc.jobs.shutdown()


def estimator_steps(svc, name, run_id="r"):
    return [s for s in svc.run_summary(run_id)["steps"]
            if s.get("module") == name and not s.get("cached")]


# ------------------------------------------------------------------ the reading


class Posed:
    """Just enough of an artifact for the agreement functions."""

    def __init__(self, cam_from_world):
        n = len(cam_from_world)
        self.p = {"cam_from_world": np.asarray(cam_from_world),
                  "valid": np.ones(n, dtype=bool), "image_index": np.arange(n)}

    def load(self, group, name):
        return self.p[name]


def circle(n=24, shift=0.0, turn_deg=0.0):
    cams = []
    for i in range(n):
        t = 2 * np.pi * i / n
        r = 1.0 + (shift if i % 2 else -shift)
        c = np.array([r * np.cos(t), r * np.sin(t), 0.1 * np.sin(3 * t)])
        R = np.array([[np.cos(t), np.sin(t), 0.0], [0.0, 0.0, -1.0],
                      [-np.sin(t), np.cos(t), 0.0]])
        if turn_deg and i % 2:
            a = np.radians(turn_deg)
            R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0],
                          [0, 0, 1]]) @ R
        cams.append(np.hstack([R, (-R @ c)[:, None]]))
    return Posed(np.stack(cams))


def test_negative_control_a_model_equal_to_one_estimator_reads_half_and_is_quiet():
    a, b = circle(shift=0.0, turn_deg=0.5), circle(shift=0.01, turn_deg=0.0)
    r = two_estimator_reading(a, {"A": a, "B": b})
    for form in ("rotation", "centre"):
        assert r[form]["ratio"] == pytest.approx(0.5, abs=0.01)
        assert r[form]["fires"] is False
    assert r["fired_forms"] == []


def test_a_model_far_from_two_agreeing_estimators_fires_in_the_form_it_is_off_in():
    a, b = circle(shift=0.0), circle(shift=0.01)
    misplaced = circle(shift=0.2)
    r = two_estimator_reading(misplaced, {"A": a, "B": b})
    assert r["centre"]["fires"] is True and r["centre"]["ratio"] >= FIRE_LEVEL
    assert "centre" in r["fired_forms"]

    a, b = circle(turn_deg=0.0), circle(turn_deg=0.5)
    turned = circle(turn_deg=20.0)
    r = two_estimator_reading(turned, {"A": a, "B": b})
    assert r["rotation"]["fires"] is True


def test_estimators_far_from_each_other_carry_no_signal_on_the_same_model():
    model = circle(shift=0.2)
    agree = two_estimator_reading(model, {"A": circle(shift=0.0), "B": circle(shift=0.01)})
    spread = two_estimator_reading(model, {"A": circle(shift=0.0), "B": circle(shift=0.4)})
    assert agree["centre"]["fires"] and not spread["centre"]["fires"]


def test_the_fire_level_is_two_and_reached_exactly_fires():
    assert FIRE_LEVEL == 2.0
    r = two_estimator_reading(circle(), {"A": circle(), "B": circle()})
    # Three identical tables: no spread to read against, so no verdict either way.
    assert r["centre"]["ratio"] is None and r["centre"]["fires"] is None


def test_it_takes_exactly_two_estimators():
    with pytest.raises(ValueError):
        two_estimator_reading(circle(), {"A": circle()})


# ------------------------------------------------------------- the fixed step


def test_the_reading_is_attached_after_refinement_and_not_before(service):
    pose, refined = chain(service, escape_below=0)
    assert "estimator_reading" not in pose
    r = refined["estimator_reading"]
    assert r["status"] == "ran"
    assert r["model"] == refined["outputs"]["sparse"]
    assert set(r["estimators"]) == {"FakeEstimatorA", "FakeEstimatorB"}
    for form in ("rotation", "centre"):
        assert set(r[form]) >= {"ratio", "fires", "model_vs", "estimators_vs_each_other"}
    assert r["fire_level"] == FIRE_LEVEL


def test_the_estimators_run_once_per_scene(service):
    _, refined = chain(service, escape_below=0)
    again = service.run("FakeRefiner", run_id="r", wait_s=60.0, inputs={
        "scene": service.store.open(refined["outputs"]["sparse"]).manifest.scene,
        "sparse": refined["outputs"]["sparse"]})
    assert again["estimator_reading"]["status"] == "ran"
    assert len(estimator_steps(service, "FakeEstimatorA")) == 1
    assert len(estimator_steps(service, "FakeEstimatorB")) == 1


def test_an_estimator_the_agent_already_ran_is_reused_whatever_its_parameters(service):
    scene = service.run("MakeScene", run_id="r", wait_s=60.0,
                        params={"n_images": 45})["outputs"]["scene"]
    own = service.run("FakeEstimatorA", run_id="r", wait_s=60.0,
                      inputs={"scene": scene}, params={"shift": 3})["outputs"]["poses"]
    _, refined = chain(service, escape_below=0)
    assert refined["estimator_reading"]["estimators"]["FakeEstimatorA"] == own
    assert len(estimator_steps(service, "FakeEstimatorA")) == 1


def test_an_estimator_that_fails_makes_the_reading_unavailable_once_not_every_step(service):
    service.ESTIMATORS = ("FakeEstimatorA", "FakeEstimatorBroken")
    _, refined = chain(service, escape_below=0)
    r = refined["estimator_reading"]
    assert r["status"] == "unavailable"
    assert "FakeEstimatorBroken" in r["reason"] and "out of memory" in r["reason"]
    again = service.run("FakeRefiner", run_id="r", wait_s=60.0, inputs={
        "scene": service.store.open(refined["outputs"]["sparse"]).manifest.scene,
        "sparse": refined["outputs"]["sparse"]})
    assert again["estimator_reading"]["status"] == "unavailable"
    failed = [s for s in service.run_summary("r")["steps"]
              if s.get("module") == "FakeEstimatorBroken"]
    assert len(failed) == 1


def test_the_reading_is_taken_on_the_model_the_second_solve_kept(service):
    _, refined = chain(service)
    assert refined["second_solve"]["status"] == "kept_second"
    assert refined["estimator_reading"]["model"] == refined["second_solve"]["kept"]


def test_the_run_summary_reads_every_final_model_without_running_anything(service):
    _, refined = chain(service, escape_below=0)
    before = len(service.run_summary("r")["steps"])
    summary = service.run_summary("r")
    leaf = refined["outputs"]["sparse"]
    assert summary["estimator_reading"][leaf]["status"] == "ran"
    assert set(summary["estimator_reading"][leaf]) >= {"rotation", "centre", "fired_forms"}
    assert len(summary["steps"]) == before


def test_a_failure_is_remembered_by_the_next_service_on_the_same_store(service, registry, store):
    service.ESTIMATORS = ("FakeEstimatorA", "FakeEstimatorBroken")
    _, refined = chain(service, escape_below=0)
    assert refined["estimator_reading"]["status"] == "unavailable"
    # A launcher that builds a service per call must not retry it on every refinement.
    fresh = SfmService(
        config=ServiceConfig(modules_dir=FIXTURE_MODULES, store_root=store.root,
                             skills_dir=Path("skills").resolve(), inline_wait_s=60.0),
        orchestrator=Orchestrator(store=store, registry=registry),
        registry=registry,
    )
    fresh.ESTIMATORS = service.ESTIMATORS
    veto_windows(fresh, set())
    try:
        again = fresh.run("FakeRefiner", run_id="r", wait_s=60.0, inputs={
            "scene": store.open(refined["outputs"]["sparse"]).manifest.scene,
            "sparse": refined["outputs"]["sparse"]})
    finally:
        fresh.jobs.shutdown()
    assert again["estimator_reading"]["status"] == "unavailable"
    assert len([s for s in fresh.run_summary("r")["steps"]
                if s.get("module") == "FakeEstimatorBroken"]) == 1


def test_the_gate_is_held_only_while_an_estimator_runs(service):
    from contextlib import contextmanager
    held = []

    @contextmanager
    def gate(name):
        held.append(name)
        yield

    service.estimator_gate = gate
    _, refined = chain(service, escape_below=0)
    assert sorted(held) == ["FakeEstimatorA", "FakeEstimatorB"]
    service.run("FakeRefiner", run_id="r", wait_s=60.0, inputs={
        "scene": service.store.open(refined["outputs"]["sparse"]).manifest.scene,
        "sparse": refined["outputs"]["sparse"]})
    assert len(held) == 2  # reused, so nothing ran and nothing was held
