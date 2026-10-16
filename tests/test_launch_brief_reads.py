"""The launcher copies an agent's reads of the brief's Markdown into its context log.

Those files are read with the file reader, which no `sfmx` call sees, so without this the
context log under-counts exactly the pages the brief now delivers.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "harness"


def _launch():
    spec = importlib.util.spec_from_file_location("launch_mod", HARNESS / "launch.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["launch_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def _transcript(projects, scratch, sid, reads):
    launch = _launch()
    d = launch.transcript_dir(scratch, projects)
    d.mkdir(parents=True)
    with open(d / f"{sid}.jsonl", "w") as fh:
        for path, offset in reads:
            fh.write(json.dumps({"timestamp": "2026-10-15T21:38:48.136Z", "message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": str(path), "offset": offset, "limit": 400}}]}}) + "\n")


def test_brief_pages_are_logged_under_their_topics(tmp_path):
    cap = tmp_path / "runs" / "TT" / "Barn"
    (cap / "scratch").mkdir(parents=True)
    projects = tmp_path / "projects"
    _transcript(projects, cap / "scratch", "s1",
                [(cap / "brief_guide.md", 0), (cap / "brief_pose.md", 0), (cap / "brief_pose.md", 400)])
    n = _launch().record_brief_reads(cap, ["s1"], projects)
    rows = [json.loads(l) for l in (cap / "context_reads.jsonl").read_text().splitlines()]
    assert n == 3
    assert [r["topic"] for r in rows] == ["plan/scene_to_pipeline", "plan/pose", "plan/pose"]
    assert all(r["kind"] == "file_read" for r in rows)


def test_other_reads_are_not_logged(tmp_path):
    """The control: a contact sheet, brief.json itself, and a brief file of another capture."""
    cap = tmp_path / "runs" / "TT" / "Barn"
    (cap / "scratch").mkdir(parents=True)
    other = tmp_path / "runs" / "TT" / "Church"
    projects = tmp_path / "projects"
    _transcript(projects, cap / "scratch", "s1",
                [(cap / "scratch" / "contact_sheet.jpg", None), (cap / "brief.json", None),
                 (other / "brief_pose.md", 0)])
    assert _launch().record_brief_reads(cap, ["s1"], projects) == 0
    assert not (cap / "context_reads.jsonl").exists()
