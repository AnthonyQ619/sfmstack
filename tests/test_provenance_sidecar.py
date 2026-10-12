"""The provenance sidecar stays current, and each of its checks can still fail.

The contract half runs through `test_context_contract.py`'s parametrize over
`ALL_CHECKS`. This file holds the negative controls: each injects the one kind of
staleness its check exists for into a copy of the tree and requires it to be seen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

from context_checks import provenance_coverage, provenance_drift, provenance_targets
from test_context_contract import _tree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import provenance as prov  # noqa: E402

SIDECAR = prov.SIDECAR


def _side(root):
    return yaml.safe_load((root / SIDECAR).read_text())


def _write(root, side):
    (root / SIDECAR).write_text(yaml.safe_dump(side, sort_keys=False, allow_unicode=True))


def test_the_sidecar_addresses_every_paragraph_with_the_tree_s_own_slugs():
    """The sidecar's slug must be the one the repository's links already use."""
    from context_checks import slug
    for f in list((REPO / "skills").rglob("*.md")) + list(REPO.glob("modules/*/skills/*.md")):
        for m in re.finditer(r"^#{1,6}\s+(.*)$", f.read_text(), re.M):
            assert slug(m.group(1)) == prov.slug(m.group(1)), (f, m.group(1))


def test_control_an_edited_claim_is_detected(tmp_path):
    root = _tree(tmp_path)
    c = next(c for c in _side(root)["claims"] if c.get("rests_on"))
    file, _, _ = c["at"].partition("#")
    p = root / "skills" / file
    text = p.read_text()
    assert c["starts"][:20] in text
    p.write_text(text.replace(c["starts"][:20], c["starts"][:20] + " (reworded)", 1))
    assert any(c["hash"] in f for f in provenance_drift(root))


def test_control_a_deleted_claim_is_detected(tmp_path):
    root = _tree(tmp_path)
    c = next(c for c in _side(root)["claims"] if c.get("rests_on"))
    file, _, _ = c["at"].partition("#")
    p = root / "skills" / file
    paras = prov.paragraphs(p)
    victim = next(x for x in paras if x.hash == c["hash"])
    lines = p.read_text().splitlines(keepends=True)
    del lines[victim.first - 1:victim.last]
    p.write_text("".join(lines))
    assert any(c["hash"] in f for f in provenance_drift(root))


def test_control_a_new_measured_paragraph_without_an_entry_is_detected(tmp_path):
    root = _tree(tmp_path)
    p = root / "skills/plan/sparse.md"
    p.write_text(p.read_text() + "\n\nMeasured on 24 of 24 captures, the median margin was 0.297.\n")
    assert any("plan/sparse.md" in f and "no provenance entry" in f for f in provenance_coverage(root))


def test_control_a_blank_entry_is_detected(tmp_path):
    root = _tree(tmp_path)
    side = _side(root)
    c = next(c for c in side["claims"] if c.get("rests_on"))
    c["rests_on"] = ""
    _write(root, side)
    assert any(c["hash"] in f and "blank" in f for f in provenance_coverage(root))


def test_control_a_campaign_without_an_entry_is_detected(tmp_path):
    root = _tree(tmp_path)
    (root / "skills/evidence/new-campaign-2026-11.md").write_text("# new\n")
    assert any("new-campaign-2026-11" in f for f in provenance_targets(root))


def test_control_a_capture_outside_the_corpus_is_detected(tmp_path):
    root = _tree(tmp_path)
    side = _side(root)
    name = next(iter(side["campaigns"]))
    side["campaigns"][name]["captures"].append("DTU/scan999")
    _write(root, side)
    assert any("scan999" in f for f in provenance_targets(root))


def test_control_a_citation_disagreeing_with_the_sidecar_is_detected(tmp_path):
    """Pick a paragraph that links a campaign in its own text, then point its sidecar
    entry at a different campaign."""
    root = _tree(tmp_path)
    side = _side(root)
    chosen = None
    for c in side["claims"]:
        if not c.get("rests_on"):
            continue
        file, _, _ = c["at"].partition("#")
        for p in prov.paragraphs(root / "skills" / file):
            if p.hash == c["hash"] and prov.CAMPAIGN_LINK.search(p.text):
                chosen = c
                break
        if chosen:
            break
    assert chosen is not None, "no claim paragraph carries an in-text campaign link"
    other = next(n for n in side["campaigns"] if n != chosen["rests_on"].partition("#")[0])
    chosen["rests_on"] = other
    _write(root, side)
    assert any(chosen["at"] in f and "sidecar says" in f for f in provenance_targets(root))


def test_control_a_missing_sidecar_is_detected(tmp_path):
    root = _tree(tmp_path)
    (root / SIDECAR).unlink()
    assert provenance_drift(root)


@pytest.mark.parametrize("check", [provenance_drift, provenance_coverage, provenance_targets])
def test_the_real_tree_is_clean(check):
    assert check(REPO) == [], "\n".join(check(REPO))
