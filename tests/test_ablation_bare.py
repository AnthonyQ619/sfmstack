"""Bare service mode (harness/bare.py) and the arm options of launch.py: the ablation arms keep the tools'
measurements and lose their advice, and read nothing in their capture directory but scratch files and images."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "harness"))
import bare  # noqa: E402
import launch  # noqa: E402


def test_scrub_keeps_measurements_and_drops_advice():
    run = {"metrics": {"point_count": 9835, "mean_reprojection_error": 0.25},
           "diagnostics": [{"code": "did_not_converge", "severity": "warn", "message": "Ceres stopped",
                            "suggested_actions": ["Raise max_iterations"], "see_also": "tuning.md#x"}],
           "notes": {"sparse": "Global bundle adjustment ..."},
           "health_profile": {"rungs": {"error": {"value": 0.07, "percentile": 92.3, "corpus_range": [0, 1],
                                                  "component": "reprojection error"}}},
           "estimator_reading": {"rotation": {"ratio": 0.65, "fires": False}, "fire_level": 2.0,
                                 "how_to_read": "plan/pose.md ..."},
           "second_solve": {"status": "kept_second"}}
    out = bare.scrub(run)
    assert out["metrics"] == run["metrics"]
    assert out["diagnostics"] == [{"code": "did_not_converge", "severity": "warn"}]
    assert "notes" not in out and "second_solve" not in out
    assert out["health_profile"]["rungs"]["error"]["percentile"] == 92.3
    assert "corpus_range" not in out["health_profile"]["rungs"]["error"]
    assert out["estimator_reading"] == {"rotation": {"ratio": 0.65}}


def test_describe_keeps_the_schema_and_drops_the_prose():
    desc = {"name": "M", "kind": "pose", "summary": "s", "description": "d", "skill": "---",
            "params": {"type": "object", "properties": {"k": {"type": "integer", "default": 6, "minimum": 4,
                                                              "description": "why"}}},
            "metrics": {"m": {"direction": "higher_better", "healthy": [1, None], "meaning": "x"}},
            "consumes": {"scene": "scene/v1"}, "produces": {"poses": "poses/v1"}}
    out = bare.scrub(desc)
    assert out["params"]["properties"]["k"] == {"type": "integer", "default": 6, "minimum": 4}
    assert out["metrics"] == {"m": {"direction": "higher_better"}}
    assert set(out) == {"name", "kind", "params", "metrics", "consumes", "produces"}


def test_control_without_bare_mode_scrub_is_never_applied_by_sfmx():
    env = {k: v for k, v in os.environ.items() if not k.startswith("SFM_")}
    env.update(SFM_CAPTURE="DTU/scan1", SFM_CONTROL="1", SFM_EXP=str(Path("/tmp") / "sfmx_bare_test"))
    plain = subprocess.run([sys.executable, str(REPO / "harness" / "sfmx.py"), "skills"], env=env,
                           capture_output=True, text=True)
    env["SFM_BARE"] = "1"
    refused = subprocess.run([sys.executable, str(REPO / "harness" / "sfmx.py"), "skills"], env=env,
                             capture_output=True, text=True)
    assert plain.returncode == 0 and plain.stdout
    assert refused.returncode != 0 and "not available in this experiment" in refused.stderr


def test_bare_arms_read_only_scratch_and_images(tmp_path):
    launch.BARE = True
    try:
        allow = launch.settings(tmp_path / "X" / "y", tmp_path / "P.md")["permissions"]["allow"]
    finally:
        launch.BARE = False
    here = f"//{str(tmp_path / 'X' / 'y').lstrip('/')}"
    assert f"Read({here}/scratch/**)" in allow and f"Read({here}/**/*.png)" in allow
    assert f"Read({here}/**/*.jpg)" in allow          # the contact sheet is a JPEG
    assert f"Edit({here}/agent_report.json)" in allow  # file writes are checked against Edit rules
    assert f"Read({here}/**)" not in allow
    plain = launch.settings(tmp_path / "X" / "y", tmp_path / "P.md")["permissions"]["allow"]
    assert f"Read({here}/**)" in plain


def test_extra_reads_are_allowed_by_path(tmp_path):
    launch.EXTRA_READS = [tmp_path / "MECHANICS.md"]
    try:
        allow = launch.settings(tmp_path / "X" / "y", tmp_path / "P.md")["permissions"]["allow"]
    finally:
        launch.EXTRA_READS = []
    assert f"Read(//{str(tmp_path / 'MECHANICS.md').lstrip('/')})" in allow


def test_the_arm_environment_is_set_only_when_asked(tmp_path):
    env = launch.environment("DTU/scan1", 0, tmp_path, None)
    assert not {"SFM_BARE", "SFM_MCMC_N"} & set(env)
    launch.BARE, launch.MCMC = True, {"n": "14", "t": "5", "seed": "0"}
    try:
        env = launch.environment("DTU/scan1", 0, tmp_path, None)
    finally:
        launch.BARE, launch.MCMC = False, {}
    assert env["SFM_BARE"] == "1" and env["SFM_MCMC_N"] == "14"
