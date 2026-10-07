"""The context tree's own contract, and proof that each check can still fail.

Two halves, and the second is the point.

**The contract.** Diagnostics route to headings that exist, retired bands do not
orphan their readings, no prose claims a band that was removed, every `[Sn]` resolves,
every evidence campaign is registered both ways, and a row claiming a direct
measurement records what it was measured with.

**The negative controls.** Each check is also run against a copy of the tree with its
own kind of defect injected, and is REQUIRED to report it. This exists because four
of these checks, as one-off scripts, were each found unable to see the thing they were
written for -- a citation check that skipped the file the dead citation lived in, a
figure checker that could not read a Unicode minus, a parser that printed its own
failure as data, and a repeatability test whose every "identical" reading was a cache
hit compared against itself. All four had passed, and passing had been treated as
evidence. A green check is evidence only if red was reachable, so red is exercised
here on every run.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from context_checks import (
    ALL_CHECKS,
    campaign_registration,
    dead_anchor_links,
    dead_citations,
    dead_see_also,
    ghost_bands,
    orphaned_readings,
    provenance_without_config,
)

REPO = Path(__file__).resolve().parents[1]

# Rows that claim a direct measurement and record no configuration. Both are pilot
# runs predating this stack, and their settings are not recoverable from anything the
# repository retains -- so they are debt, listed rather than hidden.
#
# The assertion below is EQUALITY, not containment. A new bare row fails the suite, and
# so does fixing one of these without removing it from this list, which keeps the list
# from quietly outliving the debt.
PROVENANCE_DEBT = {
    "feature_sift S4",
    "scene_loader S1",
}


def _tree(tmp_path: Path) -> Path:
    """A copy of the parts of the repository the checks read.

    `docs/` is included even though no check reads it directly: an earlier harness
    copied only `skills/` and `modules/`, which left every `../../../docs/...` link
    dangling and produced a baseline that was already red, where an injected defect
    could not be distinguished from the staging.
    """
    root = tmp_path / "sfmstack"
    root.mkdir()
    for sub in ("skills", "modules", "docs"):
        src = REPO / sub
        if src.is_dir():
            shutil.copytree(src, root / sub,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root


# --------------------------------------------------------------- the contract

@pytest.mark.parametrize("name", sorted(set(ALL_CHECKS) - {"provenance_without_config"}))
def test_context_tree_satisfies_its_contract(name):
    findings = ALL_CHECKS[name](REPO)
    assert findings == [], f"{name}:\n  " + "\n  ".join(findings)


def test_every_measured_row_records_a_configuration():
    found = {f.split(":")[0] for f in provenance_without_config(REPO)}
    assert found == PROVENANCE_DEBT, (
        "rows claiming a direct measurement with no version or parameter recorded "
        f"changed.\n  now: {sorted(found)}\n  listed as debt: {sorted(PROVENANCE_DEBT)}\n"
        "A new entry means a measurement was recorded that cannot be reproduced; a "
        "missing one means the debt was paid and this list should shrink."
    )


# ------------------------------------------------------- the negative controls

def test_control_dead_see_also_is_detected(tmp_path):
    root = _tree(tmp_path)
    y = root / "modules/scene_triage/module.yaml"
    t = y.read_text()
    assert "see_also:" in t
    i = t.index("see_also:")
    j = t.index("\n", i)
    y.write_text(t[:i] + "see_also: tuning.md#no-such-heading" + t[j:])
    assert any("no-such-heading" in f for f in dead_see_also(root))


def test_control_dead_citation_is_detected(tmp_path):
    root = _tree(tmp_path)
    p = root / "modules/scene_motion/skills/tuning.md"
    assert "[S5]" in p.read_text()
    p.write_text(p.read_text().replace("[S5]", "[S99]", 1))
    assert any("S99" in f for f in dead_citations(root))


def test_control_dead_citation_inside_sources_is_detected(tmp_path):
    """The exact blind spot: the citation check used to skip sources.md itself."""
    root = _tree(tmp_path)
    p = root / "modules/scene_motion/skills/sources.md"
    assert "[S5]" in p.read_text()
    p.write_text(p.read_text().replace("[S5]", "[S98]", 1))
    assert any("S98" in f for f in dead_citations(root))


def test_control_ghost_band_is_detected(tmp_path):
    root = _tree(tmp_path)
    p = root / "modules/scene_triage/skills/tuning.md"
    p.write_text(p.read_text() + "\n\nThe `color_shift` band sits at 0.12.\n")
    assert any("color_shift" in f for f in ghost_bands(root))


def test_control_orphaned_reading_is_detected(tmp_path):
    root = _tree(tmp_path)
    y = root / "modules/scene_triage/module.yaml"
    y.write_text(y.read_text().replace(
        "metrics:", "metrics:\n  zz_orphan_probe:\n    meaning: nothing\n", 1))
    assert any("zz_orphan_probe" in f for f in orphaned_readings(root))


def test_control_unregistered_campaign_is_detected(tmp_path):
    root = _tree(tmp_path)
    (root / "skills/evidence/unregistered-2026-12.md").write_text("# probe\n")
    assert any("unregistered-2026-12" in f for f in campaign_registration(root))


def test_control_registration_without_a_file_is_detected(tmp_path):
    root = _tree(tmp_path)
    p = root / "skills/evidence/EVIDENCE.md"
    p.write_text(p.read_text() + "\n- [ghost-campaign-2026-12](ghost-campaign-2026-12.md)\n")
    assert any("ghost-campaign-2026-12" in f for f in campaign_registration(root))


def test_control_measurement_without_a_configuration_is_detected(tmp_path):
    """Strip the one parameter S5 records and the row must stop passing."""
    root = _tree(tmp_path)
    p = root / "modules/scene_motion/skills/sources.md"
    t = p.read_text()
    assert "stride 1" in t
    p.write_text(t.replace("ten scenes at 12 images each, stride 1",
                           "ten scenes, a dozen images each", 1)
                  .replace("`sampling: head`", "contiguous selection")
                  .replace("`SceneLoader.sampling`", "the subset mode")
                  .replace("sampling", "selection"))
    assert any(f.startswith("scene_motion S5") for f in provenance_without_config(root))


def test_control_dead_anchor_link_is_detected(tmp_path):
    """A cross-directory anchor link into a fragment that does not exist.

    This whole class was uncovered: the script-era check matched only same-directory
    targets and `context_integrity` stops at the file, so nineteen links into the
    evidence tier were read by nothing.
    """
    root = _tree(tmp_path)
    p = root / "skills/health/ladder.md"
    p.write_text(p.read_text()
                 + "\n\nSee [pose](../plan/pose.md#this-fragment-does-not-exist).\n")
    assert any("this-fragment-does-not-exist" in f for f in dead_anchor_links(root))


def test_control_a_link_to_an_explicit_anchor_is_not_flagged(tmp_path):
    """The complement, and the false positive that was actually there.

    The evidence tier pins per-capture sections with `<a id="cap-...">` rather than with
    headings. Reading only headings called all nineteen of those links dead.
    """
    root = _tree(tmp_path)
    p = root / "skills/health/ladder.md"
    p.write_text(p.read_text() + "\n\nSee [scan1]"
                 "(../evidence/agentic-campaign-2026-09.md#cap-dtu-scan1).\n")
    assert not any("cap-dtu-scan1" in f for f in dead_anchor_links(root))
