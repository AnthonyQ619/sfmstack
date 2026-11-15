"""The ablation arm A3's sampler (harness/mcmc.py): it reads a finished pipeline back from the refined model's
lineage, draws one proposal at a time as exact `sfmx` commands, and accepts or rejects each by Metropolis on a
fixed score. Here the commands are executed against the fixture modules, as an agent would run them."""

import json
import shlex
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "harness"))
import mcmc  # noqa: E402

from test_estimator_reading import service  # noqa: F401,E402  (the fixture)
from test_second_solve import chain  # noqa: E402


def execute(svc, commands, current):
    """Run a proposal's commands the way an agent runs them through sfmx: pins set the current artifact of a slot,
    a run wires every required slot it does not name from the current ones."""
    last = None
    for c in commands:
        parts = shlex.split(c)
        assert parts[0] == "sfmx", c
        if parts[1] == "pin":
            current[parts[2]] = parts[3]
            continue
        assert parts[1] == "run", c
        module, params = parts[2], json.loads(parts[3])
        named = dict(p.split("=", 1) for p in parts[4:])
        cons = svc.describe_module(module).get("consumes") or {}
        inputs = {s: named.get(s) or current.get(s) for s, spec in cons.items()
                  if named.get(s) or (not isinstance(spec, dict) or spec.get("required", True))}
        out = svc.run(module, run_id="r", wait_s=60.0, inputs=inputs, params=params)
        if out["status"] != "ok":
            return None
        current.update(out["outputs"])
        last = out["outputs"].get("sparse", last)
    return last


@pytest.fixture
def sampler(service, tmp_path):  # noqa: F811
    _, refined = chain(service, escape_below=0)
    s = mcmc.Sampler(service, tmp_path, "X/y", "r", n=4, temp=5.0, seed=0)
    # A deterministic score in place of the health profile, which fixture models cannot be ranked on.
    s.score_of = lambda aid: (float(len(aid) + sum(map(ord, aid)) % 50), {})
    return s, refined["outputs"]["sparse"]


def test_the_lineage_is_the_pipeline_in_order(sampler):
    s, refined = sampler
    kinds = [st["kind"] for st in s.lineage(refined)]
    assert kinds == ["source", "detection", "matching", "tracking", "pose", "sparse", "optimization"]


def test_a_chain_runs_n_iterations_and_keeps_the_best(sampler):
    s, refined = sampler
    s.init(refined)
    current = {}
    for _ in range(4):
        p = s.propose()
        assert p["commands"] and p["commands"][-1].startswith("sfmx run FakeRefiner")
        new = execute(s.svc, p["commands"], current)
        r = s.score(new or "failed")
        assert r["iteration"] == s.state["iterations"]
        if not r["accepted"]:
            assert r["pin_back"]
    st = s.status()
    assert st["done"] and st["iterations"] == 4
    assert st["best"]["score"] == max([e["score"] for e in s.state["log"]] + [s.state["log"][0]["current_score"]])
    assert s.propose()["done"]


def test_a_failed_proposal_counts_and_is_rejected(sampler):
    s, refined = sampler
    s.init(refined)
    s.propose()
    r = s.score("failed")
    assert r["accepted"] is False and r["remaining"] == 3 and s.state["current"]["refined"] == refined


def test_the_same_seed_draws_the_same_proposal(service, tmp_path):  # noqa: F811
    _, out = chain(service, escape_below=0)
    refined = out["outputs"]["sparse"]
    a = mcmc.Sampler(service, tmp_path / "a", "X/y", "r", n=2, temp=5.0, seed=7)
    b = mcmc.Sampler(service, tmp_path / "b", "X/y", "r", n=2, temp=5.0, seed=7)
    for x in (a, b):
        x.path.parent.mkdir(parents=True, exist_ok=True)
        x.score_of = lambda aid: (10.0, {})
        x.init(refined)
    assert a.propose()["commands"] == b.propose()["commands"]


def test_a_proposal_must_be_scored_before_the_next(sampler):
    s, refined = sampler
    s.init(refined)
    s.propose()
    assert "error" in s.propose()


def test_metropolis_accepts_a_worse_model_only_by_the_draw(sampler):
    s, refined = sampler
    s.init(refined)
    s.state["current"]["score"] = 1000.0                      # every new model is far worse
    s.save()
    s.propose()
    r = s.score(refined)
    assert r["accepted"] is False
