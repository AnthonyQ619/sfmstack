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
# repository uses: a semantic version, or a parameter written as `key: value` /
# `key = value` / a backticked parameter name next to a number.
VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")
# A parameter can be written in backticks (`stride: 1`) or in prose (`f = 800`), and
# both count -- an earlier pattern accepted only the backticked form and flagged a row
# that records its synthetic setup as "f = 800, principal point at the image centre" as
# having no configuration at all.
PARAM = re.compile(r"`[a-z_]+`\s*[:=]\s*\S"
                   r"|`[a-z_]+\s*[:=][^`]+`"
                   r"|\b[a-z_]{1,24}\s*=\s*-?\d"
                   r"|\b(stride|sampling|pairing)\b")
# "this repository" alone is too loose: it also matches a row whose source is "This
# repository's own limitations files", which cites documents rather than measuring
# anything. Only a row that claims a MEASUREMENT owes a configuration.
MEASURED_HERE = re.compile(r"direct measurement|measured directly", re.I)


def slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"`|\*|\[|\]|\(|\)|:|,|\.|\?|'|\"|/|—|–", "", s)
    s = re.sub(r"[^a-z0-9_\- ]", "", s)
    return re.sub(r"\s+", "-", s.strip())


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
                anchors = {slug(m.group(1)) for m in
                           re.finditer(r"^#{1,6}\s+(.*)$", tgt.read_text(), re.M)}
                if frag not in anchors:
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
                       re.search(r"no band|NO BAND|retired|carries no band|"
                                 r"lost its healthy band|is the healthy case", s):
                        bad.append(f"{y.parent.name}/{page.name}: '{s.strip()[:72]}'")
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


def campaign_registration(root: Path) -> list[str]:
    """Evidence campaigns are registered, and every registration resolves."""
    ev = root / "skills" / "evidence"
    index = (ev / "EVIDENCE.md").read_text() if (ev / "EVIDENCE.md").is_file() else ""
    files = {p.stem for p in ev.glob("*-20*.md")}
    bad = [f"campaign file not registered: {f}" for f in sorted(files) if f not in index]
    named = set(re.findall(r"\[([a-z0-9\-]+-20\d\d-\d\d)\]", index))
    bad += [f"registration with no file: {n}" for n in sorted(named - files)]
    return bad


def provenance_without_config(root: Path) -> list[str]:
    """A row claiming a direct measurement records what it was measured WITH.

    This is the check that would have prevented the S4/S5 episode. Both rows read
    "ten scenes at 12 images each", which is a description and not a configuration: an
    image count does not determine the image set, `SceneLoader.sampling` does, and the
    default changed underneath them. Three re-measurements pointed at the stated
    description therefore measured a different set of images than the rows describe,
    and a correct row was condemned as unreliable.

    A row passes by naming a module version or at least one parameter. That is a low
    bar on purpose -- it cannot tell whether the configuration recorded is COMPLETE,
    only whether any was recorded at all. S5 named `stride 1`, passed this bar, and was
    still unreproducible. The bar exists to stop the empty case, not to certify.
    """
    bad = []
    for src in sorted((root / "modules").glob("*/skills/sources.md")):
        module = src.parent.parent.name
        for line in src.read_text().splitlines():
            if not line.startswith("| S"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            tag, kind, where = cells[0], cells[1], cells[2]
            body = " ".join(cells[2:])
            if not MEASURED_HERE.search(kind):
                continue
            if not (VERSION.search(body) or PARAM.search(body)):
                bad.append(f"{module} {tag}: direct measurement with no version or "
                           f"parameter recorded -- {where[:60]}")
    return bad


ALL_CHECKS = {
    "dead_see_also": dead_see_also,
    "orphaned_readings": orphaned_readings,
    "ghost_bands": ghost_bands,
    "dead_citations": dead_citations,
    "campaign_registration": campaign_registration,
    "provenance_without_config": provenance_without_config,
}
