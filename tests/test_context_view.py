"""The context-view builder: faithful at full size, honest when reduced.

Two promises, each with the check that would catch its breach:

  - built with no reduction, the view is byte-for-byte the repository's `skills/`,
    so the default context is untouched and the builder copies faithfully;
  - built reduced, every surviving mention of a dropped capture is reported and the
    view is marked unclean, so the harness refuses it. The negative control plants
    a dropped capture's name in a guidance page and requires it to be found.

Nothing in the stack calls the builder; these tests are the only routine caller.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "build_context_view.py"
sys.path.insert(0, str(TOOL.parent))
import build_context_view as bcv  # noqa: E402


def build(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture(scope="module")
def small_repo(tmp_path_factory):
    """skills/ copied from the repository; docs/ reduced to one file so the fixture
    is cheap. The builder never cuts docs/, so the reduction changes nothing tested."""
    root = tmp_path_factory.mktemp("repo")
    shutil.copytree(REPO / "skills", root / "skills")
    (root / "docs").mkdir()
    (root / "docs" / "import_lessons.md").write_text("# lessons\n")
    return root


def test_no_reduction_is_the_identity(small_repo, tmp_path):
    code, out = build("--repo", str(small_repo), "--out", str(tmp_path / "v"), "--all")
    assert code == 0, out
    report = json.loads((tmp_path / "v" / "VIEW.json").read_text())
    assert report["identical_to_source"] is True and report["clean"] is True
    assert report["dropped"] == [] and report["rows_cut"] == {}
    assert bcv.identical(small_repo / "skills", tmp_path / "v" / "skills")


def test_a_reduced_view_cuts_rows_and_reports_what_survives(small_repo, tmp_path):
    corpus = bcv.corpus_keys(small_repo / "skills")
    keep = tmp_path / "keep.txt"
    keep.write_text("\n".join(corpus[:5]) + "\n")
    code, out = build("--repo", str(small_repo), "--out", str(tmp_path / "v"),
                      "--keep", str(keep))
    report = json.loads((tmp_path / "v" / "VIEW.json").read_text())
    assert sorted(report["kept"]) == sorted(corpus[:5])
    assert len(report["dropped"]) == len(corpus) - 5
    view_corpus = bcv.corpus_keys(tmp_path / "v" / "skills")
    assert sorted(view_corpus) == sorted(corpus[:5])
    # INDEX rows and campaign rows for dropped captures are gone.
    index = (tmp_path / "v" / "skills" / "evidence" / "INDEX.md").read_text()
    for row_key in (bcv.first_cell_key(ln, corpus) for ln in index.splitlines()):
        assert row_key is None or row_key in report["kept"]
    assert report["rows_cut"].get("evidence/INDEX.md", 0) > 0
    # The exit code says whether the view is clean, and the report says why not.
    assert (code == 0) == report["clean"]
    if not report["clean"]:
        assert report["residuals"], out


def test_a_dropped_name_planted_in_guidance_is_found(small_repo, tmp_path):
    corpus = bcv.corpus_keys(small_repo / "skills")
    planted = tmp_path / "planted"
    shutil.copytree(small_repo, planted)
    victim = corpus[-1]
    page = planted / "skills" / "plan" / "sparse.md"
    page.write_text(page.read_text() + f"\n\nMeasured on {victim}, which transfers.\n")
    keep = tmp_path / "keep.txt"
    keep.write_text("\n".join(corpus[:-1]) + "\n")
    code, out = build("--repo", str(planted), "--out", str(tmp_path / "v"),
                      "--keep", str(keep))
    report = json.loads((tmp_path / "v" / "VIEW.json").read_text())
    assert code == 1 and report["clean"] is False
    assert any(r["capture"] == victim and r["where"].startswith("plan/sparse.md")
               and r["kind"] == "exact" for r in report["residuals"]), report["residuals"]


def test_the_harness_refuses_an_unclean_view(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "harness"))
    from roots import context_roots
    view = tmp_path / "v"
    (view / "skills" / "evidence").mkdir(parents=True)
    (view / "skills" / "evidence" / "CORPUS.txt").write_text("/DTU/scan1\n")
    (view / "VIEW.json").write_text(json.dumps({"clean": False}))
    with pytest.raises(SystemExit):
        context_roots(REPO, {"SFM_SKILLS": str(view / "skills")})
    (view / "VIEW.json").write_text(json.dumps({"clean": True}))
    skills, modules = context_roots(REPO, {"SFM_SKILLS": str(view / "skills")})
    assert skills == (view / "skills").resolve() and modules == REPO / "modules"


def test_the_default_is_the_repository_and_nothing_else(tmp_path):
    sys.path.insert(0, str(REPO / "harness"))
    from roots import context_roots
    assert context_roots(REPO, {}) == (REPO / "skills", REPO / "modules")
    with pytest.raises(SystemExit):
        context_roots(REPO, {"SFM_SKILLS": str(tmp_path)})       # not a context tree
    with pytest.raises(SystemExit):
        context_roots(REPO, {"SFM_MODULES": str(tmp_path)})      # not a modules tree


def test_the_launcher_drops_an_inherited_override(monkeypatch):
    sys.path.insert(0, str(REPO / "harness"))
    import launch
    monkeypatch.setenv("SFM_SKILLS", "/somewhere/inherited")
    monkeypatch.setattr(launch, "SKILLS", None)
    monkeypatch.setattr(launch, "MODULES", None)
    env = launch.environment("DTU/scan1", 0, Path("/tmp"), None)
    assert "SFM_SKILLS" not in env and "SFM_MODULES" not in env
    monkeypatch.setattr(launch, "SKILLS", Path("/view/skills"))
    assert launch.environment("DTU/scan1", 0, Path("/tmp"), None)["SFM_SKILLS"] == "/view/skills"
