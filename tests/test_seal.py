"""The P11 seal: each scene signal can be withheld alone or in any combination, and nothing of it
reaches the agent through any `sfmx` answer, file the agent may read, or image it is served.

Unit tests run anywhere. The integration tests drive the real `sfmx` against the scene-analysis
stores built on three staged captures (~/sfm_experiments/P11/seal_test, `run_analysis.sh`) and are
skipped where those do not exist. Every check has a negative control: the same check run where the
signal is NOT withheld must find it, so a pass cannot be vacuous.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness"))
import withhold  # noqa: E402
import audit_seal  # noqa: E402
import views  # noqa: E402
import stage_anon  # noqa: E402

SIGNALS = ("visual", "illumination", "motion")
CONDITIONS = [set(c) for n in (1, 2, 3) for c in itertools.combinations(SIGNALS, n)]
TEST = Path("/home/anthonyq/sfm_experiments/P11/seal_test")
SFMX = REPO / "harness" / "bin" / "sfmx"
needs_store = pytest.mark.skipif(not (TEST / "exp" / "scenes").is_dir(), reason="no seal_test stores")

# ---------------------------------------------------------------------------------------- unit

NOTE = ("Triage over 100 images (99 pairs, consecutive). Photometric: combined 0.017 (illumination "
        "0.013, colour 0.032, exposure 0.003). Texture: 5438 corners/MP, 33% textureless, repetitiveness "
        "0.40. Sharpness ratio 0.65 against a median of 303. Clipping: 0.00% highlight, 0.00% shadow in "
        "the median frame. Ordered capture.")


def old_prose_scrub(text):
    """Wave 3's filter, kept here as the negative control: it stops at the decimal point."""
    return re.sub(r"\s*(Photometric|Clipping):[^.]*(\([^)]*\))?[^.]*\.", "", text)


def test_three_switches_and_the_wave3_alias():
    assert withhold.parse("visual") == {"visual"}
    assert withhold.parse("illumination,motion") == {"illumination", "motion"}
    assert withhold.parse("motion_illumination") == {"illumination", "motion"}
    assert withhold.parse(None) == set()
    with pytest.raises(SystemExit):
        withhold.parse("lighting")


def test_refusals_name_no_experiment():
    for s in CONDITIONS:
        for m in withhold.modules(s):
            r = withhold.refusal(m, s)
            assert r and not re.search(r"withh|experiment|ablat", r, re.I)
    assert not re.search(r"withh|experiment", views.REFUSE_FRAMES + views.REFUSE_NAMES, re.I)


def test_the_note_loses_exactly_the_withheld_sentences():
    ill = withhold.rebuild_note(NOTE, {"illumination"})
    assert "0.013" not in ill and "0.017" not in ill and "highlight" not in ill and "Photometric" not in ill
    assert "Texture: 5438" in ill and "Sharpness ratio 0.65" in ill and "Ordered capture." in ill
    mot = withhold.rebuild_note(NOTE, {"motion"})
    assert "Ordered capture" not in mot and "illumination 0.013" in mot
    assert withhold.rebuild_note(NOTE, {"visual"}) == NOTE


def test_negative_control_the_wave3_filter_leaked_the_numbers():
    leaked = old_prose_scrub(NOTE)
    assert "illumination 0.013" in leaked            # what every Wave 3 motion session received
    readings = {"values": {"illumination 0.013": "x"}, "keys": []}
    assert audit_seal.find_leaks(leaked, readings, {"illumination"})["values"]


CANARY = {
    "metrics": {"illumination_change": "CANARY_ILL_1", "highlight_clipped_fraction": "CANARY_ILL_2",
                "ordered": "CANARY_MOT_1", "texture_density": "KEEP_TEX"},
    "diagnostics": [{"code": "illumination_unstable", "message": "CANARY_ILL_3"},
                    {"code": "unordered_capture", "message": "CANARY_MOT_2"},
                    {"code": "textureless", "message": "KEEP_DIAG"}],
    "series": {"photometric": {"pair_combined": "CANARY_ILL_4"},
               "metadata": {"capture_interval_s": "CANARY_MOT_3", "n_images": "KEEP_N"},
               "points": {"rgb": "CANARY_COL_1", "xyz": "KEEP_XYZ"}},
    "analysis": [{"module": "SceneMotion", "metrics": {"overall_magnitude": "CANARY_MOT_4"}},
                 {"module": "SceneDescription", "series": {"overall": "CANARY_VIS_1"}},
                 {"module": "SceneTriage", "metrics": {"sharpness_ratio": "KEEP_SHARP"}}],
    "list": [{"name": "SceneMotion", "summary": "CANARY_MOT_5"}, {"name": "SceneDescription", "summary": "CANARY_VIS_2"}],
    "history": [{"action": "run", "module": "SceneMotion", "metrics": {"x": "CANARY_MOT_6"}}],
    "notes": NOTE.replace("0.013", "CANARY_ILL_5") + " KEEP_NOTE",
}
OWNER = {"ILL": "illumination", "MOT": "motion", "VIS": "visual", "COL": "colour"}


@pytest.mark.parametrize("signals", CONDITIONS, ids=lambda s: "+".join(sorted(s)))
def test_canaries_in_withheld_fields_vanish_and_kept_fields_survive(signals):
    out = json.dumps(withhold.scrub(json.loads(json.dumps(CANARY)), signals))
    for tok in re.findall(r"CANARY_[A-Z]+_\d", json.dumps(CANARY)):
        owner = OWNER[tok.split("_")[1]]
        gone = (owner in signals) or (owner == "colour" and {"visual", "illumination"} & signals)
        assert (tok not in out) == bool(gone), (tok, signals)
    for keep in ("KEEP_TEX", "KEEP_DIAG", "KEEP_N", "KEEP_XYZ", "KEEP_SHARP", "KEEP_NOTE"):
        assert keep in out, keep


def test_negative_control_nothing_withheld_keeps_every_canary():
    out = json.dumps(withhold.scrub(json.loads(json.dumps(CANARY)), set()))
    assert all(t in out for t in re.findall(r"CANARY_[A-Z]+_\d", json.dumps(CANARY)))


def test_normalised_frames_lose_their_brightness_differences():
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (120, 160, 3)).astype(np.float64)
    frames = [Image.fromarray(np.clip(base * g + o, 0, 255).astype(np.uint8))
              for g, o in ((0.3, 0), (0.6, 20), (1.0, 0), (0.8, 50))]
    tinted = Image.fromarray(np.clip(base * [1.0, 0.7, 0.4], 0, 255).astype(np.uint8))
    before = [np.asarray(f).mean() for f in frames]
    after = [np.asarray(views.Views.normalise(f)).mean() for f in frames]
    assert np.std(after) < 0.2 * np.std(before)
    ch = np.asarray(views.Views.normalise(tinted)).reshape(-1, 3).mean(0)
    assert np.ptp(ch) < 0.1 * np.ptp(np.asarray(tinted).reshape(-1, 3).mean(0))


def test_the_geometry_render_is_uncoloured_and_not_blank():
    pts = Path("/home/anthonyq/sfm_experiments/P10/paper_fig/office_replay/store/artifacts/art_942e36f81270/data/points.npz")
    xyz = np.load(pts)["xyz"] if pts.exists() else np.random.default_rng(1).normal(size=(20000, 3)) * [3, 1, 0.2]
    a = np.asarray(views.Views.uncoloured(xyz))
    assert (a[..., 0] == a[..., 1]).all() and (a[..., 1] == a[..., 2]).all()
    assert (a[..., 0] < 250).mean() > 0.02


def test_staging_strips_metadata_without_touching_pixels(tmp_path):
    src = next(Path("/home/anthonyq/datasets/Fuji_SfM/east/scene_001/images").glob("*.jpg"), None)
    if src is None:
        pytest.skip("no Fuji frames")
    clean = tmp_path / "x.jpg"
    clean.write_bytes(stage_anon.strip_jpeg(src.read_bytes()))
    assert len(Image.open(src).getexif()) and not len(Image.open(clean).getexif())
    assert "xmp" not in Image.open(clean).info
    assert np.array_equal(np.asarray(Image.open(src)), np.asarray(Image.open(clean)))


def test_staging_refuses_a_corpus_window_under_a_different_layout():
    with pytest.raises(SystemExit, match="planning corpus"):
        stage_anon.stage_one({"capture": "Fuji/west_scene_000",
                              "image_dir": "/home/anthonyq/datasets/Fuji_SfM/west/scene_000/images",
                              "calibration_path": "/dev/null"}, set())


def test_sealed_settings_deny_the_store_and_unfiltered_records():
    import launch
    launch.SEALED = True
    try:
        s = launch.settings(Path("/x/cap"), Path("/x/PROCEDURE.md"))["permissions"]
    finally:
        launch.SEALED = False
    allow, deny = " ".join(s["allow"]), " ".join(s["deny"])
    assert "Read(///x/cap/**)" not in allow and "Read(//x/cap/**)" not in allow
    for d in ("store/**", "chain.json", "context_roots.json", ".views_key.json", ".views_log.jsonl",
              "datasets/**", "Grep", "Glob", "Bash(cat:*)", "Bash(ls:*)"):
        assert d in deny, d


def test_sealed_sessions_get_four_tools_and_no_peers_or_connectors():
    import launch
    launch.SEALED = True
    try:
        cmd = launch.command("p", Path("/x/cap"), Path("/x/PROCEDURE.md"))
        env = launch.environment("c", 0, Path("/x/cap/scratch"), None)
    finally:
        launch.SEALED = False
    assert cmd[cmd.index("--tools") + 1] == "Bash,Read,Edit,Write"
    assert "--strict-mcp-config" in cmd and "--disable-slash-commands" in cmd
    off = cmd[cmd.index("--disallowedTools") + 1:]
    for t in ("SendMessage", "ListAgents", "ToolSearch", "mcp__*"):
        assert t in off, t
    assert env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"
    # negative control: an ordinary run is unchanged
    plain = launch.command("p", Path("/x/cap"), Path("/x/PROCEDURE.md"))
    assert "--tools" not in plain and "--strict-mcp-config" not in plain


def test_the_audit_fails_a_session_that_messaged_a_peer(tmp_path, monkeypatch):
    cap = tmp_path / "cap"
    (cap / "store" / "artifacts").mkdir(parents=True)
    (cap / "context_roots.json").write_text(json.dumps({"withheld": ["visual"], "sealed": True}))
    tr = tmp_path / "t"
    tr.mkdir()

    def write(lines):
        (tr / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    monkeypatch.setattr(audit_seal, "transcripts", lambda d: sorted(tr.glob("*.jsonl")))
    use = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "sfmx state"}}]}}
    write([use])
    assert audit_seal.audit(cap)["pass"]                   # negative control: clean session passes
    write([use, {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "b", "name": "SendMessage", "input": {"to": "peer", "message": "what do you see"}}]}}])
    assert not audit_seal.audit(cap)["pass"]
    write([use, {"type": "user", "message": {"content": "Another Claude session sent a message:\n"
                                                        "<cross-session-message from=\"x\">hi</cross-session-message>"}}])
    assert not audit_seal.audit(cap)["pass"]


def test_the_audit_reads_results_saved_outside_the_transcript(tmp_path, monkeypatch):
    cap = tmp_path / "cap"
    a = cap / "store" / "artifacts" / "art_1"
    a.mkdir(parents=True)
    a.joinpath("artifact.md").write_text("---\nproduced_by: {module: SceneMotion}\nmetrics:\n"
                                         "  overall_magnitude: {value: 0.2041}\n---\nnotes\n")
    (cap / "context_roots.json").write_text(json.dumps({"withheld": ["motion"], "sealed": True}))
    tr = tmp_path / "t"
    (tr / "s" / "tool-results").mkdir(parents=True)
    (tr / "s.jsonl").write_text("")
    monkeypatch.setattr(audit_seal, "transcripts", lambda d: sorted(tr.glob("*.jsonl")))
    assert audit_seal.audit(cap)["pass"]
    (tr / "s" / "tool-results" / "big.txt").write_text('{"overall_magnitude": 0.2041}')
    r = audit_seal.audit(cap)
    assert not r["pass"] and any("tool-results/big.txt" in v for v in r["values"])


def test_a_sealed_sfmx_error_prints_no_source():
    cap = captures()[0]
    env = {**os.environ, "SFM_BATCH": str(TEST / "anon_batch.json"), "SFM_EXP": str(TEST / "exp"),
           "SFM_SEALED": "1", "SFM_CAPTURE": cap, "SFM_WITHHOLD": "visual"}
    r = subprocess.run([str(SFMX), "skill"], env=env, capture_output=True, text=True)
    plain = subprocess.run([str(SFMX), "skill"], env={**env, "SFM_SEALED": ""}, capture_output=True, text=True)
    restore(cap)
    assert "Traceback" in plain.stderr                    # negative control: the same call does trace
    assert "Traceback" not in r.stderr and "withhold" not in r.stderr and "sfmx.py" not in r.stderr
    assert "failed" in r.stderr

# --------------------------------------------------------------------------------- integration


def captures():
    return sorted(p.parent.relative_to(TEST / "exp").as_posix()
                  for p in (TEST / "exp").glob("scenes/*/chain.json"))


def restore(cap):
    """`sfmx run` under a withheld signal saves the chain filtered; every probe starts from the full one."""
    home = TEST / "exp" / cap
    (home / "chain.json").write_text((home / "chain.pristine.json").read_text())


def ids(cap):
    restore(cap)
    ch = json.loads((TEST / "exp" / cap / "chain.json").read_text())
    by = {}
    for h in ch["history"]:
        if h.get("status") == "ok":
            by.setdefault(h["module"], []).append(list(h["outputs"].values())[0])
    return ch["current"]["scene"], by


def sfmx(cap, signals, *args):
    env = {**os.environ, "SFM_BATCH": str(TEST / "anon_batch.json"), "SFM_EXP": str(TEST / "exp"),
           "SFM_SEALED": "1", "SFM_SCOPE": "dense", "SFM_CAPTURE": cap, "SFM_GPU": "3", "SFMX_FOLLOW_S": "600"}
    env.pop("SFM_WITHHOLD", None)
    if signals:
        env["SFM_WITHHOLD"] = ",".join(sorted(signals))
    p = subprocess.run([str(SFMX), *args], env=env, capture_output=True, text=True, timeout=900)
    restore(cap)
    return p.stdout + "\n" + p.stderr


def everything(cap, signals):
    """What an agent could see: every answer, and every file it may read afterwards."""
    home = TEST / "exp" / cap
    scene, by = ids(cap)
    tri, mot, desc = by["SceneTriage"][-1], by["SceneMotion"][-1], by["SceneDescription"][-1]
    for f in (home / "scratch").glob("last_*"):
        f.unlink()
    out = [sfmx(cap, signals, *a) for a in (
        ("state",), ("brief",), ("summary",), ("list",),
        ("artifact", scene), ("artifact", tri), ("artifact", mot), ("artifact", desc),
        ("series", tri, "photometric"), ("series", tri, "metadata"), ("series", tri, "texture"),
        ("series", desc, "description"),
        ("run", "SceneTriage", "{}"), ("run", "SceneMotion", "{}"), ("run", "SceneDescription", "{}"),
        ("describe", "SceneMotion"), ("image", scene), ("image", desc))]
    listing = out[-2]
    names = re.findall(r'"((?:images/|frame_)[^"]+\.(?:png|jpe?g))"', listing)
    for n in names[:3]:
        out.append(sfmx(cap, signals, "image", scene, n))
    out.append(sfmx(cap, signals, "image", scene, "images/000000.png"))
    out.append(sfmx(cap, signals, "image", scene, "images/000000.jpg"))
    files = list((home / "scratch").glob("last_*")) + list(home.glob("brief*"))
    return "\n".join(out + [f.read_text(errors="ignore") for f in files]), names


@needs_store
@pytest.mark.parametrize("signals", CONDITIONS, ids=lambda s: "+".join(sorted(s)))
def test_no_withheld_reading_reaches_the_agent(signals):
    for cap in captures():
        text, names = everything(cap, signals)
        readings = audit_seal.withheld_readings(TEST / "exp" / cap / "store", signals)
        if {"illumination", "motion"} & signals:
            assert readings["values"], "negative control: the store holds readings to look for"
        leaks = audit_seal.find_leaks(text, readings, signals)
        assert not any(leaks.values()), (cap, leaks)
        assert not re.search(r"withh|experiment", "\n".join(
            ln for ln in text.splitlines() if "available on this run" in ln or "this run" in ln), re.I)
        if "visual" in signals:
            assert not any(n.startswith(("images/", "frame_")) for n in names), (cap, names)
        if "motion" in signals and "visual" not in signals:
            assert names and all(n.startswith("frame_") for n in names), names
            assert "frame names" not in text
            assert not re.search(r"images/\d{6}\.(png|jpe?g)", "\n".join(
                ln for ln in text.splitlines() if "SceneDescription" in ln or "sfm_artifact_image" in ln)), cap
        if "illumination" not in signals:
            assert "texture_density" in text           # triage itself still answers


@needs_store
def test_negative_control_unsealed_answers_carry_every_reading():
    for cap in captures():
        text, names = everything(cap, set())
        readings = audit_seal.withheld_readings(TEST / "exp" / cap / "store", set(SIGNALS))
        leaks = audit_seal.find_leaks(text, readings, set(SIGNALS))
        assert leaks["values"] and leaks["keys"], cap
        assert any(n.startswith("images/") for n in names)


@needs_store
def test_served_images_follow_the_signals():
    cap = captures()[0]
    home = TEST / "exp" / cap
    scene, by = ids(cap)
    log = home / ".views_log.jsonl"
    for signals in CONDITIONS:
        log.unlink(missing_ok=True)
        listing = sfmx(cap, signals, "image", scene)
        names = re.findall(r'"((?:images/|frame_)[^"]+)"', listing)
        for n in names[:4]:
            sfmx(cap, signals, "image", scene, n)
        sfmx(cap, signals, "image", by["SceneDescription"][-1])
        served = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        if "visual" in signals:
            assert not [v for v in served if v["kind"] in ("frame", "sheet")], (signals, served)
        else:
            assert [v for v in served if v["kind"] == "frame"], signals
        if "illumination" in signals:
            assert all("normalised" in v["transform"] for v in served if v["kind"] in ("frame", "sheet"))
        if "motion" in signals and "visual" not in signals:
            assert any(v["kind"] == "sheet" and "shuffled" in v["transform"] for v in served), served
    # and a served normalised frame really is one
    sig = {"illumination"}
    names = re.findall(r'"(images/[^"]+)"', sfmx(cap, sig, "image", scene))
    path = re.search(r'"path": "([^"]+)"', sfmx(cap, sig, "image", scene, names[0])).group(1)
    assert "/scratch/views/" in path
    src = next((home / "store" / "artifacts" / scene / "data").glob(names[0]))
    assert not np.array_equal(np.asarray(Image.open(path)), np.asarray(Image.open(src)))
