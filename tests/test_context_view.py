"""The context-view builder: faithful at full size, honest when reduced.

Promises, each with the check that would catch its breach:

  - built with no reduction, the view is byte-for-byte the repository's `skills/`,
    so the default context is untouched and the builder copies faithfully;
  - built reduced, the sidecar drives every cut: rows, sections, whole campaigns, the
    reference profile and measured guidance paragraphs, each by the one support rule;
  - every surviving mention of a dropped capture is reported and the view is marked
    unclean, so the harness refuses it. The negative control plants a dropped name
    in a guidance page and requires it to be found;
  - a view is never written inside the repository.

Nothing in the stack calls the builder; these tests are the only routine caller.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "build_context_view.py"
sys.path.insert(0, str(TOOL.parent))
import build_context_view as bcv  # noqa: E402
import provenance as prov  # noqa: E402


def build(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def report(out: Path) -> dict:
    return json.loads((out / "VIEW.json").read_text())


@pytest.fixture(scope="module")
def small_repo(tmp_path_factory):
    """skills/ and docs/ copied from the repository, modules/ linked: a view links into
    both, and a clean view has no dangling link."""
    root = tmp_path_factory.mktemp("repo")
    shutil.copytree(REPO / "skills", root / "skills")
    shutil.copytree(REPO / "docs", root / "docs")
    # The module tier is held fixed; a view links into it, so the fixture needs it.
    (root / "modules").symlink_to(REPO / "modules", target_is_directory=True)
    return root


def test_no_reduction_is_the_identity(small_repo, tmp_path):
    code, out = build("--repo", str(small_repo), "--out", str(tmp_path / "v"), "--all")
    assert code == 0, out
    r = report(tmp_path / "v")
    assert r["identical_to_source"] is True and r["clean"] is True
    assert r["dropped"] == [] and r["rows_cut"] == {} and r["claims_pruned"] == []
    assert r["dangling_links"] == []
    assert bcv.identical(small_repo / "skills", tmp_path / "v" / "skills")
    # modules/ beside the view is the repository's, by symlink, so links into it hold.
    assert (tmp_path / "v" / "modules").is_symlink()
    assert (tmp_path / "v" / "modules" / "feature_sift" / "module.yaml").is_file()


def test_a_view_is_never_written_inside_the_repository(tmp_path):
    code, out = build("--out", str(REPO / "ctxview_should_not_exist"), "--all")
    assert code != 0 and "inside the repository" in out
    assert not (REPO / "ctxview_should_not_exist").exists()


def test_reducing_without_a_support_rule_is_refused(small_repo, tmp_path):
    keep = tmp_path / "keep.txt"
    keep.write_text(prov.corpus_keys(small_repo / "skills")[0] + "\n")
    code, out = build("--repo", str(small_repo), "--out", str(tmp_path / "v"), "--keep", str(keep))
    assert code != 0 and "min-support" in out


def test_a_reduced_view_cuts_by_the_sidecar(small_repo, tmp_path):
    corpus = prov.corpus_keys(small_repo / "skills")
    side = yaml.safe_load((small_repo / prov.SIDECAR).read_text())
    keep = tmp_path / "keep.txt"
    kept = corpus[:5]
    keep.write_text("\n".join(kept) + "\n")
    code, out = build("--repo", str(small_repo), "--out", str(tmp_path / "v"),
                      "--keep", str(keep), "--min-support", "0.5")
    r = report(tmp_path / "v")
    view = tmp_path / "v" / "skills"
    assert sorted(r["kept"]) == sorted(kept) and len(r["dropped"]) == len(corpus) - 5
    assert sorted(prov.corpus_keys(view)) == sorted(kept)
    # INDEX rows for dropped captures are gone, aliases included.
    for ln in (view / "evidence" / "INDEX.md").read_text().splitlines():
        k = prov.first_cell_key(ln, corpus, side["aliases"])
        assert k is None or k in kept
    # A campaign whose support fell below the rule is gone, and nothing in the evidence
    # tier still points at it: not its EVIDENCE.md row, not a prose link, not a row.
    for name in r["campaigns_removed"]:
        assert not (view / "evidence" / f"{name}.md").exists()
        for f in (view / "evidence").glob("*.md"):
            assert f"{name}.md" not in f.read_text() and f"[{name}]" not in f.read_text(), (name, f.name)
    # No guidance paragraph still cites a removed campaign.
    for tier in prov.GUIDANCE:
        for f in (view / tier).glob("*.md"):
            for name in r["campaigns_removed"]:
                assert f"{name}.md" not in f.read_text(), (tier, f.name, name)
    # Every pruned claim is a paragraph that no longer exists in the view.
    for c in r["claims_pruned"]:
        file, _, anchor = c["at"].partition("#")
        assert not any(p.anchor == anchor and p.hash == c["hash"]
                       for p in prov.paragraphs(view / file)), c
    # Every sourced claim with enough support, whose campaign survived, still exists.
    for c in side["claims"]:
        if not c.get("rests_on") or c["rests_on"].partition("#")[0] in r["campaigns_removed"]:
            continue
        orig = prov.support(c, side) or set()
        if bcv._enough(set(kept), orig, 0.5):
            file, _, anchor = c["at"].partition("#")
            assert any(p.anchor == anchor and p.hash == c["hash"]
                       for p in prov.paragraphs(view / file)), c
    # The profile was rebuilt from kept rows or removed, never left as the full one.
    yml = view / "evidence" / "reference_profile.yaml"
    if r["profile"]["rebuilt"]:
        assert yaml.safe_load(yml.read_text())["captures"] == r["profile"]["captures"] <= 5
        assert "REBUILT" in yml.read_text()
    else:
        assert not yml.exists()
    assert (code == 0) == r["clean"]


def test_a_stricter_support_rule_prunes_at_least_as_much(small_repo, tmp_path):
    corpus = prov.corpus_keys(small_repo / "skills")
    keep = tmp_path / "keep.txt"
    keep.write_text("\n".join(corpus[:8]) + "\n")
    build("--repo", str(small_repo), "--out", str(tmp_path / "loose"), "--keep", str(keep), "--min-support", "0.25")
    build("--repo", str(small_repo), "--out", str(tmp_path / "strict"), "--keep", str(keep), "--min-support", "1.0")
    loose, strict = report(tmp_path / "loose"), report(tmp_path / "strict")
    assert len(strict["claims_pruned"]) >= len(loose["claims_pruned"])
    assert len(strict["campaigns_removed"]) >= len(loose["campaigns_removed"])


def test_always_kept_captures_are_kept_at_every_level(small_repo, tmp_path):
    corpus = prov.corpus_keys(small_repo / "skills")
    dense_only = [k for k in corpus if k.startswith("tanks_and_temples/")]
    assert dense_only    # however many the corpus holds; promotion changes the count
    always = tmp_path / "always.txt"
    always.write_text("\n".join(dense_only) + "\n")
    order = tmp_path / "order.txt"
    order.write_text("\n".join(k for k in corpus if k not in dense_only) + "\n")
    for n in (0, 3):
        build("--repo", str(small_repo), "--out", str(tmp_path / f"v{n}"), "--n", str(n),
              "--order", str(order), "--always", str(always), "--min-support", "0.5", "--force")
        r = report(tmp_path / f"v{n}")
        assert set(dense_only) <= set(r["kept"]) and len(r["kept"]) == n + len(dense_only)
        assert set(dense_only) <= set(prov.corpus_keys(tmp_path / f"v{n}" / "skills"))


def test_an_empty_keep_leaves_the_skeleton(small_repo, tmp_path):
    keep = tmp_path / "keep.txt"
    keep.write_text("")
    build("--repo", str(small_repo), "--out", str(tmp_path / "v"), "--keep", str(keep), "--min-support", "0.5")
    r = report(tmp_path / "v")
    view = tmp_path / "v" / "skills"
    assert prov.corpus_keys(view) == []
    side = yaml.safe_load((small_repo / prov.SIDECAR).read_text())
    filed = [n for n in side["campaigns"] if (small_repo / "skills" / "evidence" / f"{n}.md").is_file()]
    assert sorted(r["campaigns_removed"]) == sorted(filed)
    assert not (view / "evidence" / "reference_profile.yaml").exists()
    # The structure survives: every guidance file still exists with its headings.
    for tier in prov.GUIDANCE:
        for f in (small_repo / "skills" / tier).glob("*.md"):
            assert (view / tier / f.name).is_file()
            assert prov.anchors(view / tier / f.name) == prov.anchors(f)


def test_a_dropped_name_planted_in_guidance_is_found(small_repo, tmp_path):
    corpus = prov.corpus_keys(small_repo / "skills")
    planted = tmp_path / "planted"
    shutil.copytree(small_repo, planted)
    victim = corpus[-1]
    page = planted / "skills" / "plan" / "sparse.md"
    page.write_text(page.read_text() + f"\n\nA sentence with no number naming {victim}.\n")
    keep = tmp_path / "keep.txt"
    keep.write_text("\n".join(corpus[:-1]) + "\n")
    code, out = build("--repo", str(planted), "--out", str(tmp_path / "v"),
                      "--keep", str(keep), "--min-support", "0.5")
    r = report(tmp_path / "v")
    assert code == 1 and r["clean"] is False
    assert any(h["capture"] == victim and h["where"].startswith("plan/sparse.md")
               and h["kind"] == "exact" for h in r["residuals"]), r["residuals"]


def test_the_harness_refuses_an_unclean_view(tmp_path):
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
        context_roots(REPO, {"SFM_SKILLS": str(tmp_path)})
    with pytest.raises(SystemExit):
        context_roots(REPO, {"SFM_MODULES": str(tmp_path)})


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


def test_a_capture_list_may_annotate_each_key(small_repo, tmp_path):
    """A pre-registered order annotates each key with its kind after a `#`; the
    builder reads the key and ignores the rest, whole-line comments included."""
    corpus = prov.corpus_keys(small_repo / "skills")
    order = tmp_path / "order.txt"
    order.write_text("# the first two, annotated\n"
                     f"/{corpus[0]}    # rig_orbit\n{corpus[1]}  # site_walk\n\n{corpus[2]}\n")
    out = tmp_path / "view"
    code, log = build("--repo", str(small_repo), "--out", str(out), "--n", "2",
                      "--order", str(order), "--min-support", "0.5")
    assert code == 0, log
    assert report(out)["kept"] == sorted(corpus[:2])
