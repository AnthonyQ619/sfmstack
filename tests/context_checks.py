"""Checks on the context tree itself, as functions over a root.

These ran as one-off scripts in the experiments directory and found real defects --
a diagnostic pointing at a renamed heading, a retired band orphaning its reading, a
citation with no row behind it. Scripts only check what someone remembers to run, and
one of them reported clean for a whole session while a dead `[S6]` sat in
`scene_triage/sources.md`, because it skipped the file the citation was in.

Every check is a function of a ROOT rather than of the real repository, for one
reason: that is what lets `test_context_contract.py` inject each defect into a copy
and prove the check can still see it. A check nobody has watched fail is not evidence.

Each returns a list of human-readable findings. Empty means clean.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

# A direct measurement must say what it was measured WITH. These are the forms the
# repository uses: a semantic version, or a parameter written in backticks (`stride: 1`)
# or in prose (`f = 800`). Both forms count -- an earlier pattern accepted only the
# backticked one and flagged a row recording "f = 800, principal point at the image
# centre" as having no configuration at all.
#
# Note what deliberately does NOT count: "at module defaults". Defaults change, which is
# the whole lesson here, so a row that pins nothing but "defaults" pins nothing.
VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")
PARAM = re.compile(r"`[a-z_]+`\s*[:=]\s*\S"
                   r"|`[a-z_]+\s*[:=][^`]+`"
                   r"|\b[a-z_]{1,24}\s*=\s*-?\d"
                   r"|\b(stride|sampling|pairing)\b")

# Which rows OWE a configuration. Scope is decided by recognising the EXTERNAL sources
# -- papers, vendor documentation, the predecessor codebase, this repo's own prose --
# and treating everything else as a measurement taken here.
#
# It is written this way round on purpose. An earlier version recognised measurements
# positively, matching only "direct measurement" and "measured directly", and silently
# skipped the row sourced to "The seventeen-capture sweep, 35 runs at 1.1.0" -- a
# measurement taken here, exempted from the check meant to catch exactly it. Under-
# inclusion is the dangerous direction: it reproduces the failure this check exists for,
# and it is invisible. Over-inclusion produces a visible finding somebody can label.
#
# No year pattern: "CVPR 1997" is already caught by the venue, while a year would also
# exclude a row sourced to "Direct measurement, 2026-10 corpus run", which is ours.
EXTERNAL_SOURCE = re.compile(
    r"Predecessor source|documentation|Classical practice|own [a-z ]*files"
    r"|\*[^*]+\*|CVPR|ECCV|ICCV|IJCV|NeurIPS|arXiv|et al\.|OpenCV", re.I)

# Prose that explicitly says a metric has no band. A metric without a band is the
# common case here -- most readings carry none -- so this list is what keeps the ghost
# band check from firing on correct prose. "no ceiling" is in it because the check keys
# on the word `ceiling` as well as `band`.
BAND_NEGATION = re.compile(
    r"no band|NO BAND|unbanded|retired|carries no band|without a band"
    r"|lost its (healthy )?band|has no (healthy )?band|there is no band"
    r"|no healthy band|band (on `?[a-z_]+`? )?was removed|no ceiling"
    r"|is the healthy case"
    r"|deliberately has no|not banded", re.I)


def slug(heading: str) -> str:
    """A heading's anchor, by the convention the repository's own links already use.

    This follows GitHub's slugger: lower-case, drop everything that is not a word
    character, space or hyphen, then turn EACH space into a hyphen. The last part is
    load-bearing. An earlier version collapsed runs of whitespace to one hyphen, and
    disagreed with 32 of the repository's own anchor links -- a heading like
    "... rather than swap — and do not refine ..." loses its em-dash and keeps both
    surrounding spaces, so the anchor carries a DOUBLE hyphen, which is exactly how the
    links are written.

    Those links were right and this function was wrong. Trusting it would have meant
    rewriting 32 correct links to satisfy a broken reader of the format.
    """
    s = re.sub(r"[^\w\s-]", "", heading.strip().lower(), flags=re.UNICODE)
    return s.strip().replace(" ", "-")


EXPLICIT_ANCHOR = re.compile(r"""<a\s+(?:id|name)\s*=\s*["']([^"']+)["']""")


def anchors(path: Path) -> set[str]:
    """Every anchor a link can target in this file: headings AND explicit anchors.

    The evidence tier pins per-capture sections with `<a id="cap-dtu-scan1">` rather
    than with headings, and one module page does the same. Reading only headings
    reported all nineteen of those links as dead -- a checker that did not know the
    format it was checking.
    """
    text = path.read_text()
    out = {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*)$", text, re.M)}
    out |= set(EXPLICIT_ANCHOR.findall(text))
    return out


def _modules(root: Path):
    return sorted((root / "modules").glob("*/module.yaml"))


def _skills_blob(root: Path) -> str:
    return "\n".join(p.read_text(errors="replace")
                     for p in (root / "skills").rglob("*.md"))


def dead_see_also(root: Path) -> list[str]:
    """Every diagnostic's see_also resolves to a real file and heading.

    A diagnostic is what a reader sees at the moment something went wrong; sending
    them to a heading that was renamed out from under it is the worst moment to do it.
    """
    bad = []
    for y in _modules(root):
        spec = yaml.safe_load(y.read_text()) or {}
        for diag in spec.get("diagnostics") or []:
            sa = diag.get("see_also")
            if not sa:
                continue
            fn, _, frag = sa.partition("#")
            tgt = y.parent / "skills" / fn
            if not tgt.is_file():
                bad.append(f"{y.parent.name}:{diag.get('code')} -> missing file {fn}")
                continue
            if frag:
                if frag not in anchors(tgt):
                    bad.append(f"{y.parent.name}:{diag.get('code')} -> "
                               f"#{frag} not in {fn}")
    return bad


def orphaned_readings(root: Path) -> list[str]:
    """A metric that lost its band is still documented SOMEWHERE in the context.

    Anywhere counts, not just the module's own page. Demanding the module page
    reported 28 problems, every one a reading documented centrally in `plan/` or
    `health/` instead -- which is the repository's actual contract.
    """
    blob = _skills_blob(root)
    bad = []
    for y in _modules(root):
        spec = yaml.safe_load(y.read_text()) or {}
        pages = "\n".join(p.read_text() for p in (y.parent / "skills").glob("*.md"))
        for name, m in (spec.get("metrics") or {}).items():
            if not isinstance(m, dict) or m.get("healthy") is not None:
                continue
            if name not in pages and name not in (m.get("meaning") or "") \
                    and name not in blob:
                bad.append(f"{y.parent.name}.{name}: no band and never mentioned")
    return bad


def ghost_bands(root: Path) -> list[str]:
    """No prose claims a band for a metric that does not have one."""
    bad = []
    for y in _modules(root):
        spec = yaml.safe_load(y.read_text()) or {}
        for name, m in (spec.get("metrics") or {}).items():
            if not isinstance(m, dict) or m.get("healthy") is not None:
                continue
            for page in (y.parent / "skills").glob("*.md"):
                for hit in re.finditer(rf"`{re.escape(name)}`[^\n]{{0,90}}",
                                       page.read_text()):
                    s = hit.group(0)
                    if re.search(r"\bband\b|\bceiling\b|\bhealthy\b", s) and not \
                            BAND_NEGATION.search(s):
                        bad.append(f"{y.parent.name}/{page.name}: '{s.strip()[:72]}' "
                                   f"(if this prose is correct, the wording belongs in "
                                   f"BAND_NEGATION, not the other way round)")
    return bad


def dead_citations(root: Path) -> list[str]:
    """Every [Sn] in a module's skills resolves to a row in that module's sources.md.

    sources.md is NOT exempt. An earlier version skipped it to avoid matching the row
    labels, but a label is pipe-delimited (`| S4 |`) and a citation is bracketed
    (`[S4]`), so the regex never confused them -- the skip was pure blind spot, and it
    hid a citation of a row that had been renumbered away.
    """
    bad = []
    for sd in sorted((root / "modules").glob("*/skills")):
        src = sd / "sources.md"
        rows = set(re.findall(r"^\|\s*(S\d+)\s*\|", src.read_text(), re.M)) \
            if src.is_file() else set()
        for page in sorted(sd.glob("*.md")):
            for sn in sorted(set(re.findall(r"\[(S\d+)\]", page.read_text()))):
                if sn not in rows:
                    bad.append(f"{sd.parent.name}/{page.name}: [{sn}] has no row")
    return bad


def dead_anchor_links(root: Path) -> list[str]:
    """Every `(file.md#anchor)` link in the context resolves to a real anchor.

    Nothing covered this before. The script-era link check matched only same-directory
    targets, so a `../plan/pose.md#...` link was never read, and `context_integrity`
    checks that the FILE exists without looking at the fragment. Nineteen links into the
    evidence tier sat unexamined between the two.

    Only the fragment is judged here; a missing file is `context_integrity`'s finding and
    reporting it twice would make two checks fail for one defect.
    """
    bad = []
    pages = list((root / "skills").rglob("*.md")) + \
        list((root / "modules").glob("*/skills/*.md"))
    for page in sorted(pages):
        for fn, frag in re.findall(r"\(([A-Za-z0-9_\-./]+\.md)#([^)\s]+)\)",
                                   page.read_text()):
            tgt = (page.parent / fn).resolve()
            if not tgt.is_file():
                continue
            if frag not in anchors(tgt):
                bad.append(f"{page.relative_to(root)} -> {fn}#{frag}")
    return bad


def campaign_registration(root: Path) -> list[str]:
    """Evidence campaigns are registered, and every registration resolves."""
    ev = root / "skills" / "evidence"
    index = (ev / "EVIDENCE.md").read_text() if (ev / "EVIDENCE.md").is_file() else ""
    files = {p.stem for p in ev.glob("*-20*.md")}
    bad = [f"campaign file not registered: {f}" for f in sorted(files) if f not in index]
    named = set(re.findall(r"\[([a-z0-9\-]+-20\d\d-\d\d)\]", index))
    bad += [f"registration with no file: {n}" for n in sorted(named - files)]
    return bad


def provenance_rows(root: Path) -> list[dict]:
    """Every `| Sn |` row in every module's sources.md, with its scope classification.

    Exposed separately from the check so the test suite can pin the CLASSIFICATION
    against hand-read labels for all of them. That matters more than it looks: if a
    future row is mis-scoped, the fix belongs in the test's label table, never in the
    context. A check must not be able to force a change to the thing it is checking.
    """
    out = []
    for src in sorted((root / "modules").glob("*/skills/sources.md")):
        module = src.parent.parent.name
        for line in src.read_text().splitlines():
            if not line.startswith("| S"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            # The WHOLE row, Source cell included. A version is often recorded there
            # rather than in the claims -- "The seventeen-capture sweep, 35 runs at
            # 1.1.0" pins its configuration in the Source cell, and scanning only the
            # later cells reported that row as recording nothing.
            body = " ".join(cells[1:])
            out.append({
                "key": f"{module} {cells[0]}",
                "kind": cells[1],
                "where": cells[2],
                "measured_here": not bool(EXTERNAL_SOURCE.search(cells[1])),
                "records_config": bool(VERSION.search(body) or PARAM.search(body)),
            })
    return out


def provenance_without_config(root: Path) -> list[str]:
    """A row claiming a measurement taken here records what it was measured WITH.

    This is the check that would have prevented the S4/S5 episode. Both rows read
    "ten scenes at 12 images each", which is a description and not a configuration: an
    image count does not determine the image set, `SceneLoader.sampling` does, and the
    default changed underneath them. Three re-measurements aimed at the stated
    description therefore measured a different set of images than the rows describe,
    and a correct row was condemned as unreliable for a day.

    The bar is low on purpose -- any version or any parameter passes. It cannot tell
    whether a configuration is COMPLETE, only whether one was recorded at all. S5 named
    `stride 1`, cleared this bar, and was still unreproducible. It exists to stop the
    empty case, not to certify a row.
    """
    return [f"{r['key']}: measured here, no version or parameter recorded -- "
            f"{r['where'][:60]}"
            for r in provenance_rows(root)
            if r["measured_here"] and not r["records_config"]]


ALL_CHECKS = {
    "dead_see_also": dead_see_also,
    "dead_anchor_links": dead_anchor_links,
    "orphaned_readings": orphaned_readings,
    "ghost_bands": ghost_bands,
    "dead_citations": dead_citations,
    "campaign_registration": campaign_registration,
    "provenance_without_config": provenance_without_config,
}
