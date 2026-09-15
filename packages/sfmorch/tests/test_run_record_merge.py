"""Two processes on one run record keep each other's steps.

Each opened the record, ran a step and saved, and the later write used to
replace the earlier one whole -- so one step, and with it the verification a
model needed to read as verified, was lost.
"""
from sfmorch.run_record import Run, Step


def _step(i, module, out):
    return Step(index=i, module=module, module_version="1.0.0", outputs={"x": out})


def test_two_writers_on_one_record_keep_both_steps(tmp_path):
    root = tmp_path / "r"
    Run(id="r", root=root).save()
    a, b = Run.open(root), Run.open(root)
    a.steps.append(_step(0, "A", "art_a"))
    a.save()
    b.steps.append(_step(0, "B", "art_b"))
    b.save()
    got = Run.open(root)
    assert sorted(s.module for s in got.steps) == ["A", "B"]
    assert len({s.index for s in got.steps}) == 2


def test_two_writers_keep_each_other_s_second_solve_decisions(tmp_path):
    root = tmp_path / "r"
    Run(id="r", root=root).save()
    a, b = Run.open(root), Run.open(root)
    a.second_solves = [{"first": {"model": "m1"}, "status": "kept_first"}]
    a.save()
    b.second_solves = [{"first": {"model": "m2"}, "status": "kept_second"}]
    b.save()
    got = Run.open(root)
    assert sorted(d["first"]["model"] for d in got.second_solves) == ["m1", "m2"]


def test_saving_twice_does_not_duplicate_anything(tmp_path):
    root = tmp_path / "r"
    run = Run(id="r", root=root)
    run.steps.append(_step(0, "A", "art_a"))
    run.second_solves = [{"first": {"model": "m1"}, "status": "kept_first"}]
    run.save()
    run.save()
    got = Run.open(root)
    assert len(got.steps) == 1 and len(got.second_solves) == 1


def test_a_repeated_identical_step_is_two_steps(tmp_path):
    """A cache hit records the same module, inputs and outputs as the run before it."""
    run = Run(id="r", root=tmp_path / "r")
    run.add(_step(0, "A", "art_a"))
    run.add(_step(0, "A", "art_a"))
    assert [s.index for s in Run.open(tmp_path / "r").steps] == [0, 1]


def test_a_step_updated_after_it_was_saved_stays_one_step(tmp_path):
    """A replay sets replay_of on a step after add() has already saved it."""
    run = Run(id="r", root=tmp_path / "r")
    run.add(_step(0, "A", "art_a"))
    step = run.add(_step(0, "A", "art_b"))
    step.replay_of = 0
    run.save()
    got = Run.open(tmp_path / "r").steps
    assert len(got) == 2 and got[1].replay_of == 0
