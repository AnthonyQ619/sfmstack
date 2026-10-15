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
import sys
from pathlib import Path

import yaml

# The provenance sidecar's addressing (paragraphs, hashes, sections) is defined once,
# in tools/provenance.py, so this file, the drafting tool and the view builder cannot
# disagree about what a paragraph is.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import provenance as prov  # noqa: E402

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
    # The adapters emit see_also too, and those links are what a reader actually
    # receives at run time. Reading only the manifests left one dead for weeks:
    # SceneTriage's illumination alarm pointed at a heading named after a threshold
    # that had since moved, and this check stayed green. A link built at run time
    # (an f-string with a placeholder) cannot be resolved here and is skipped.
    for y in _modules(root):
        adapter = y.parent / "adapter.py"
        if not adapter.is_file():
            continue
        for m in re.finditer(r"""see_also\s*=\s*(f?)["']([^"']+)["']""", adapter.read_text()):
            if m.group(1) and "{" in m.group(2):
                continue
            fn, _, frag = m.group(2).partition("#")
            tgt = y.parent / "skills" / fn
            if not tgt.is_file():
                bad.append(f"{y.parent.name}:adapter -> missing file {fn}")
            elif frag and frag not in anchors(tgt):
                bad.append(f"{y.parent.name}:adapter -> #{frag} not in {fn}")
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


def stale_defaults(root: Path) -> list[str]:
    """Prose that states a parameter's default agrees with the manifest.

    Written because a measured default was moved and the pages that quote it were
    updated by hand: `max_epipolar_error` went from 1.0 to 2.0 and five passages now
    assert the new number. Nothing checked that they still matched the manifest, so a
    later change to the default would leave the guidance confidently wrong about the
    value a reader is about to accept -- the same staleness class as a retired band
    orphaning its reading, and the one defect kind this family did not yet cover.

    Only the explicit form is matched, "`param` is 2.0" or "its 2.0 default" or
    "`param` default 2.0", because that is prose committing to a number. A passage
    naming a value to tune TOWARD is not a claim about the default and is left alone.
    """
    bad = []
    for y in _modules(root):
        spec = yaml.safe_load(y.read_text()) or {}
        params = spec.get("params") or {}
        pages = list((y.parent / "skills").glob("*.md"))
        for name, meta in params.items():
            if not isinstance(meta, dict) or "default" not in meta:
                continue
            d = meta["default"]
            if not isinstance(d, (int, float)) or isinstance(d, bool):
                continue
            forms = [
                rf"`{re.escape(name)}`\s+is\s+(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\b",
                rf"`{re.escape(name)}`\s+default\s+(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\b",
                rf"its\s+(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+default\b[^\n]{{0,40}}`?{re.escape(name)}`?",
                rf"`{re.escape(name)}`[^\n]{{0,30}}?\bdefault\b[^\n]{{0,20}}?(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)",
            ]
            for page in pages:
                text = page.read_text()
                for pat in forms:
                    for hit in re.finditer(pat, text):
                        tok = hit.group(1)
                        # A number followed by an exponent marker was matched short
                        # -- "5" out of "5e-4" -- which is a false positive, and was
                        # one before this guard existed.
                        if text[hit.end(1):hit.end(1) + 1] in ("e", "E"):
                            continue
                        claimed = float(tok)
                        if abs(claimed - float(d)) > 1e-9:
                            bad.append(
                                f"{y.parent.name}/{page.name}: prose says "
                                f"{name} default {hit.group(1)}, manifest says {d} "
                                f"('{hit.group(0).strip()[:60]}')")
    return bad


def image_tag_drift(root: Path) -> list[str]:
    """Every module's image tag names the version its manifest declares.

    The tag is a separate field from `version`, so a bump that forgets it leaves the
    service running an image whose name says an older version -- harmless only by
    luck. Three dense modules carried a 1.0.0 tag past a version bump, unnoticed,
    because nothing compared the two; a reader matching a run's image against a module
    page had no way to know the code was current.
    """
    bad = []
    for y in _modules(root):
        spec = yaml.safe_load(y.read_text()) or {}
        image, version = str(spec.get("image") or ""), str(spec.get("version") or "")
        if image and version and image.rsplit(":", 1)[-1] != version:
            bad.append(f"{y.parent.name}: version {version}, image {image}")
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


# ----------------------------------------------------------- the provenance sidecar
#
# `skills/evidence/provenance.yaml` says what every measured paragraph in the guidance
# tiers rests on, and which captures each campaign section names. It is kept current
# by the three checks below, which is the whole reason a sidecar can be trusted:
# a label that lives outside the text it labels drifts silently unless something
# fails when it does.

def _sidecar(root: Path) -> dict:
    p = root / prov.SIDECAR
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def provenance_drift(root: Path) -> list[str]:
    """Every claim entry still addresses a paragraph that exists, unchanged.

    The hash is of the paragraph's own text, so rewording, moving or deleting a labelled
    claim fails here and names the file, anchor, hash and first words. That failure is
    the point: an edited claim must be re-labelled, and nothing else would make anyone
    notice."""
    side = _sidecar(root)
    if not side:
        return ["no provenance sidecar at " + str(prov.SIDECAR)]
    bad, cache = [], {}
    for c in side.get("claims", []):
        file, _, anchor = c["at"].partition("#")
        path = root / "skills" / file
        if not path.is_file():
            bad.append(f"{c['at']}: file missing")
            continue
        paras = cache.setdefault(path, prov.paragraphs(path))
        if not any(p.anchor == anchor and p.hash == c["hash"] for p in paras):
            bad.append(f"{c['at']} {c['hash']} ({c['starts']!r}): no paragraph matches -- "
                       "the claim was edited, moved or deleted; re-label it")
    return bad


def provenance_coverage(root: Path) -> list[str]:
    """Every measured paragraph in plan/, judge/ and health/ has an entry, sourced or
    declared unsourced, and no entry is left blank or carries both."""
    side = _sidecar(root)
    known = {}
    bad = []
    for c in side.get("claims", []):
        known[(c["at"], c["hash"])] = c
        has_src, has_un = bool(c.get("rests_on")), bool(c.get("unsourced"))
        if has_src == has_un:
            bad.append(f"{c['at']} {c['hash']}: needs exactly one of rests_on / unsourced, "
                       f"has {'both' if has_src else 'neither (blank)'}")
    for tier in prov.GUIDANCE:
        for path in sorted((root / "skills" / tier).glob("*.md")):
            rel = f"{tier}/{path.name}"
            for p in prov.paragraphs(path):
                if prov.MEASURED.search(p.text) and (f"{rel}#{p.anchor}", p.hash) not in known:
                    bad.append(f"{rel}#{p.anchor} {p.hash} ({p.starts!r}): measured, no provenance entry")
    return bad


def provenance_targets(root: Path) -> list[str]:
    """Every entry points at a campaign that exists and captures the corpus has; every
    campaign file has an entry; an in-text citation agrees with the sidecar."""
    side = _sidecar(root)
    ev = root / "skills" / "evidence"
    corpus = set(prov.corpus_keys(root / "skills"))
    files = {p.stem for p in ev.glob("*-20*.md")}
    camps = side.get("campaigns", {})
    bad = []
    for name, c in camps.items():
        if name not in files and not c.get("unfiled"):
            bad.append(f"campaigns.{name}: no such campaign file and not declared unfiled")
            continue
        bad += [f"campaigns.{name}: {k} not in CORPUS.txt" for k in c.get("captures", []) if k not in corpus]
        if name in files:
            have = prov.anchors(ev / f"{name}.md")
            bad += [f"campaigns.{name}.sections.{a}: no such anchor" for a in c.get("sections", {}) if a not in have]
            for a, caps in c.get("sections", {}).items():
                bad += [f"campaigns.{name}.sections.{a}: {k} not in CORPUS.txt" for k in caps if k not in corpus]
    bad += [f"campaign file with no sidecar entry: {f}" for f in sorted(files - set(camps))]
    bad += [f"aliases.{k}: target {v} not in CORPUS.txt" for k, v in side.get("aliases", {}).items() if v not in corpus]
    prof = side.get("profile", {})
    if prof:
        pf = ev / f"{prof.get('campaign', '')}.md"
        if not pf.is_file():
            bad.append(f"profile.campaign {prof.get('campaign')}: no such campaign file")
        elif prof.get("table") not in prov.anchors(pf):
            bad.append(f"profile.table {prof.get('table')}: no such anchor in {pf.name}")
    cache = {}
    for c in side.get("claims", []):
        if not c.get("rests_on"):
            continue
        camp, _, anchor = c["rests_on"].partition("#")
        if camp not in camps:
            bad.append(f"{c['at']}: rests_on {camp}, not a sidecar campaign")
            continue
        if anchor and camp in files and anchor not in prov.anchors(ev / f"{camp}.md"):
            bad.append(f"{c['at']}: rests_on {c['rests_on']}, anchor missing")
        file, _, _ = c["at"].partition("#")
        path = root / "skills" / file
        if path.is_file():
            for p in cache.setdefault(path, prov.paragraphs(path)):
                if p.hash == c["hash"]:
                    cited = {m[0] for m in prov.CAMPAIGN_LINK.findall(p.text)}
                    if cited and camp not in cited:
                        bad.append(f"{c['at']}: text cites {sorted(cited)}, sidecar says {camp}")
    return bad


def unreachable_links(root: Path) -> list[str]:
    """Every link from a context page to a file in `skills/` or `docs/` can be fetched.

    Existence is not reachability. An agent reads the context through one call,
    `workflow_skill`, and that call serves a bounded set of files; the link checks above
    test that a target exists on disk. `evidence/CORPUS.txt` existed, was linked from the
    skills index and the evidence index, and could not be fetched by any agent for as
    long as the bound served Markdown only -- three agents of one batch said so, and
    every check stayed green. So this asks the resolver itself, on this root, rather than
    restating its rules here, where they would drift from it.
    """
    from types import SimpleNamespace
    from sfmorch.service import SfmService as Service

    skills, docs = (root / "skills").resolve(), (root / "docs").resolve()
    resolver = SimpleNamespace(config=SimpleNamespace(skills_dir=root / "skills"),
                               _MOVED_TOPICS=Service._MOVED_TOPICS)
    pages = list((root / "skills").rglob("*.md")) + \
        list((root / "modules").glob("*/skills/*.md"))
    bad, seen = [], {}
    for page in sorted(pages):
        for target in re.findall(r"\]\(([^)\s#:]+)(?:#[^)\s]*)?\)", page.read_text()):
            tgt = (page.parent / target).resolve()
            if not tgt.is_file():
                continue
            if tgt.is_relative_to(skills):
                topic = tgt.relative_to(skills).as_posix()
            elif tgt.is_relative_to(docs):
                topic = "docs/" + tgt.relative_to(docs).as_posix()
            else:
                continue
            if topic not in seen:
                try:
                    got = Service.workflow_skill(resolver, topic)
                    seen[topic] = Path(got["path"]).resolve() == tgt
                except Exception:
                    seen[topic] = False
            if not seen[topic]:
                bad.append(f"{page.relative_to(root)} -> {target}")
    return bad


ALL_CHECKS = {
    "unreachable_links": unreachable_links,
    "provenance_drift": provenance_drift,
    "provenance_coverage": provenance_coverage,
    "provenance_targets": provenance_targets,
    "dead_see_also": dead_see_also,
    "dead_anchor_links": dead_anchor_links,
    "orphaned_readings": orphaned_readings,
    "ghost_bands": ghost_bands,
    "stale_defaults": stale_defaults,
    "image_tag_drift": image_tag_drift,
    "dead_citations": dead_citations,
    "campaign_registration": campaign_registration,
    "provenance_without_config": provenance_without_config,
}
