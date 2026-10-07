"""The checks must stay SILENT across every legitimate shape the context already uses.

`test_context_contract.py` proves each check can fail. That is recall, and on its own it
is the more dangerous half to have alone. A check that fires wrongly does not merely add
noise: it pressures whoever reads it into editing the CONTEXT to satisfy the CHECKER,
which inverts the authority. The format is the authority; a check is a reader of it.

Both halves of that inversion had already happened once. The provenance recogniser
flagged a row citing this repository's own prose as though it were an unrecorded
measurement, and another that records its setup as "f = 800, principal point (320, 240)"
-- a configuration, written in prose rather than backticks. Separately it SKIPPED a row
sourced to "The seventeen-capture sweep, 35 runs at 1.1.0", a measurement taken here,
exempting from the check the exact shape the check exists for.

So the tests here pin precision from four directions:

  * the scope classification of every provenance row, against hand-read labels;
  * every `see_also` target and every intra-repo anchor link resolving under `slug`,
    across all the heading styles the tree actually contains;
  * prose that correctly says a metric has no band, which must not read as a ghost band;
  * the findings being invariant under re-wrapping, since reflowing a paragraph is the
    most common legitimate edit these files get.

**Where to fix a disagreement.** If a future row, heading or phrasing trips one of
these, the fix belongs in the label table or the recogniser HERE. It does not belong in
the context. A check must never be able to force a change to the thing it checks.
"""
from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path

import pytest
import yaml

from context_checks import (
    ALL_CHECKS,
    BAND_NEGATION,
    anchors,
    ghost_bands,
    provenance_rows,
    slug,
)

REPO = Path(__file__).resolve().parents[1]

# Every `| Sn |` row, read by hand: is it a measurement taken HERE, and does the row
# record a version or a parameter? This table is ground truth. The recogniser is
# required to reproduce it, so a mis-scoped row shows up as a disagreement with a label
# rather than as pressure to reword a source.
PROVENANCE_LABELS = {
    # key:                        (measured_here, records_config)
    "feature_sift S1":            (False, True),   # Lowe, IJCV -- cites r=10
    "feature_sift S2":            (False, False),  # Arandjelović & Zisserman, CVPR
    "feature_sift S3":            (False, False),  # OpenCV docs
    "feature_sift S4":            (True,  False),  # pilot run, settings unrecorded
    "feature_sift S5":            (True,  True),   # the sweep, pinned at 1.1.0
    "scene_description S1":       (False, False),  # this repo's own limitations prose
    "scene_loader S1":            (True,  False),  # pilot run, settings unrecorded
    "scene_loader S2":            (False, False),  # predecessor source
    "scene_motion S1":            (False, True),   # predecessor source, quotes its cut
    "scene_motion S2":            (False, True),   # RAFT, names the weights
    "scene_motion S3":            (False, True),   # Torr, CVPR
    "scene_motion S4":            (True,  True),   # synthetic, f = 800
    "scene_motion S5":            (True,  True),   # ten scenes, stride 1
    "scene_triage S1":            (False, False),  # predecessor source
    "scene_triage S2":            (False, False),  # OpenCV docs
    "scene_triage S3":            (False, False),  # classical practice
    "scene_triage S4":            (True,  True),   # ten scenes, subset mode recorded
    "scene_triage S5":            (True,  True),   # stored readings, split by pairing
}

# Prose that correctly states a metric carries no band. None of it is a ghost band, and
# all of it sits near the words the check keys on.
LEGITIMATE_NO_BAND_PROSE = [
    "`texture_density` has no band, and that is the finding rather than an omission.",
    "There is no ceiling on `texture_density`; read it against the detector's counts.",
    "`high_motion_tail` carries no band because the cut it would need is unmeasured.",
    "`fastest_pair` lost its healthy band when the fraction it fed was retired.",
    "`pair_p90_across` is unbanded by design -- the consumer picks its own cut.",
    "A reading of zero on `planar_dominance` is the healthy case, so no band applies.",
    "`sharpness_median` has no healthy band; the ratio is the one to read.",
    "The band on `high_motion_tail` was removed, and the series replaced it.",
    "`n_pairs` is not banded: it describes the capture, not its condition.",
    "`ordered` deliberately has no band -- it is a fact about the filenames.",
]

SKIP_LINE = re.compile(r"^\s*(\||#|>|[-*+]\s|\d+\.\s|```|---|\s*$)")


def _tree(tmp_path: Path, name: str = "sfmstack") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    for sub in ("skills", "modules", "docs"):
        src = REPO / sub
        if src.is_dir():
            shutil.copytree(src, root / sub,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root


def _reflow(text: str, width: int) -> str:
    """Re-wrap prose paragraphs, leaving every structural line untouched.

    Tables are left alone because a table row IS one line in this format -- reflowing
    one would not be a legitimate edit, it would be a broken table.
    """
    out: list[str] = []
    para: list[str] = []
    fence = False

    def flush() -> None:
        if para:
            out.extend(textwrap.wrap(" ".join(x.strip() for x in para), width=width,
                                     break_long_words=False, break_on_hyphens=False))
            para.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            flush()
            fence = not fence
            out.append(line)
            continue
        if fence or SKIP_LINE.match(line) or line.startswith("    "):
            flush()
            out.append(line)
            continue
        para.append(line)
    flush()
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ scope

def test_provenance_scope_matches_hand_read_labels():
    got = {r["key"]: (r["measured_here"], r["records_config"])
           for r in provenance_rows(REPO)}
    assert set(got) == set(PROVENANCE_LABELS), (
        "the set of provenance rows changed; label the new ones here\n"
        f"  unlabelled: {sorted(set(got) - set(PROVENANCE_LABELS))}\n"
        f"  gone:       {sorted(set(PROVENANCE_LABELS) - set(got))}"
    )
    wrong = {k: {"labelled": PROVENANCE_LABELS[k], "recognised": got[k]}
             for k in got if got[k] != PROVENANCE_LABELS[k]}
    assert not wrong, (
        "the recogniser disagrees with the hand-read labels. Fix the recogniser or the "
        f"label -- not the sources.md row:\n  {wrong}"
    )


# ------------------------------------------------------- anchors and slugs

def _targets(path: Path) -> set[str]:
    """Headings AND explicit <a id> anchors -- both are live link targets here."""
    return anchors(path)


def test_every_diagnostic_see_also_resolves_under_slug():
    """136 live targets; if slug were wrong, every one of them would look broken."""
    checked, bad = 0, []
    for y in sorted((REPO / "modules").glob("*/module.yaml")):
        spec = yaml.safe_load(y.read_text()) or {}
        for diag in spec.get("diagnostics") or []:
            sa = diag.get("see_also")
            if not sa:
                continue
            fn, _, frag = sa.partition("#")
            tgt = y.parent / "skills" / fn
            checked += 1
            if not tgt.is_file() or (frag and frag not in _targets(tgt)):
                bad.append(f"{y.parent.name}:{diag.get('code')} -> {sa}")
    assert checked >= 100, f"expected the full set of see_also targets, saw {checked}"
    assert bad == [], f"slug() does not agree with these live targets: {bad}"


def test_every_intra_repo_anchor_link_resolves_under_slug():
    """The prose's own `(file.md#anchor)` links are an independent witness to slug()."""
    checked, bad = 0, []
    pages = list((REPO / "skills").rglob("*.md")) + \
        list((REPO / "modules").glob("*/skills/*.md"))
    for p in pages:
        for fn, frag in re.findall(r"\(([A-Za-z0-9_\-./]+\.md)#([^)\s]+)\)", p.read_text()):
            tgt = (p.parent / fn).resolve()
            if not tgt.is_file():
                continue          # file-level dead links are context_integrity's job
            checked += 1
            if frag not in _targets(tgt):
                bad.append(f"{p.relative_to(REPO)} -> {fn}#{frag}")
    assert checked >= 80, f"expected the full set of anchor links, saw {checked}"
    assert bad == [], f"slug() does not agree with these live links: {bad}"


def test_slug_is_stable_across_every_heading_style_present():
    """Whatever slug does, it must be deterministic and produce a usable anchor."""
    pages = list((REPO / "skills").rglob("*.md")) + \
        list((REPO / "modules").glob("*/skills/*.md"))
    seen = 0
    for p in pages:
        for m in re.finditer(r"^#{1,6}\s+(.*)$", p.read_text(), re.M):
            h = m.group(1)
            s = slug(h)
            seen += 1
            assert s == slug(h), f"slug is not deterministic for {h!r}"
            assert not re.search(r"[\s#?&/\\]", s), \
                f"slug({h!r}) = {s!r} contains a character no anchor can carry"
    assert seen >= 500, f"expected the tree's headings, saw {seen}"


# ------------------------------------------------------------- ghost bands

@pytest.mark.parametrize("prose", LEGITIMATE_NO_BAND_PROSE)
def test_correct_no_band_prose_is_not_read_as_a_ghost_band(prose):
    assert BAND_NEGATION.search(prose), (
        "this is correct prose saying a metric has no band, and the recogniser does not "
        "accept it. Add the wording to BAND_NEGATION -- do not reword the context."
    )


def test_a_real_ghost_band_is_still_caught_among_that_prose(tmp_path):
    """The permissive list must not have swallowed the defect it guards."""
    root = _tree(tmp_path)
    p = root / "modules/scene_triage/skills/tuning.md"
    p.write_text(p.read_text() + "\n\n" + "\n".join(LEGITIMATE_NO_BAND_PROSE)
                 + "\n\nThe `color_shift` band sits at 0.12.\n")
    found = ghost_bands(root)
    assert any("color_shift" in f for f in found), found
    assert not any("texture_density" in f or "high_motion_tail" in f for f in found), \
        f"legitimate prose was flagged: {found}"


# --------------------------------------------------------- layout stability

def test_findings_are_invariant_under_rewrapping(tmp_path):
    """Reflowing a paragraph must not change a single finding.

    Re-wrapping is the most common legitimate edit these files get -- every context edit
    in this area needed one. A check that noticed would push the next person into
    reformatting the context to keep it quiet.
    """
    base = _tree(tmp_path, "before")
    after = _tree(tmp_path, "after")
    touched = 0
    for p in list((after / "modules").glob("*/skills/*.md")) + \
            list((after / "skills").rglob("*.md")):
        t = p.read_text()
        r = _reflow(t, 64)        # deliberately not the house width
        if r != t:
            p.write_text(r)
            touched += 1
    assert touched >= 100, f"the reflow did not take effect ({touched} files)"
    for name, check in ALL_CHECKS.items():
        assert check(base) == check(after), (
            f"{name} is layout-sensitive: its findings changed when prose was "
            f"re-wrapped, which makes it a formatting rule rather than a check"
        )


# ------------------------------------------------- structural robustness

def test_checks_tolerate_a_module_with_no_sources_or_diagnostics(tmp_path):
    """A new module should not break the checks before it has any provenance."""
    root = _tree(tmp_path)
    mod = root / "modules" / "zz_probe_module"
    (mod / "skills").mkdir(parents=True)
    (mod / "module.yaml").write_text(
        "name: ZzProbe\nversion: 0.1.0\nmetrics: {}\ndiagnostics: []\n")
    (mod / "skills" / "SKILL.md").write_text("# ZzProbe\n\nNothing measured yet.\n")
    for name, check in ALL_CHECKS.items():
        findings = check(root)
        assert not any("zz_probe_module" in f for f in findings), \
            f"{name} flagged a module that has made no claims: {findings}"
