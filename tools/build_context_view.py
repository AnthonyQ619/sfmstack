#!/usr/bin/env python3
"""Build a reduced VIEW of the context for an ablation batch. Never run otherwise.

    tools/build_context_view.py --out DIR --all
    tools/build_context_view.py --out DIR --keep captures.txt --min-support 0.5
    tools/build_context_view.py --out DIR --n 5 --order ladder.txt --min-support 0.5
    tools/build_context_view.py --out DIR --n 5 --seed 7 --min-support 0.5

The repository's `skills/` is the context, and every ordinary run reads all of it.
This tool copies `skills/` and `docs/` to DIR, outside the repository, and cuts the
copy down to the captures you name, guided by `skills/evidence/provenance.yaml`:

  CORPUS.txt            entries for dropped captures removed
  INDEX.md              rows for dropped captures removed (aliases resolved)
  campaign files        rows for dropped captures removed; a section whose kept
                        support falls below --min-support removed whole; a campaign
                        whose kept support falls below it removed as a file, with
                        its EVIDENCE.md row
  reference_profile     rebuilt from the kept rows of the reference campaign's own
                        table, at the table's precision; absent if none are kept
  plan/ judge/ health/  a measured paragraph whose kept support falls below
                        --min-support removed; unsourced and unmeasured text stays

Which captures, how many, and the support rule are arguments to the call. There is
no ladder in this file, nothing in the stack calls it, and the harness reads a view
only when SFM_SKILLS points at one and its VIEW.json says `clean: true`.

Two checks decide whether the result is a view at all, both written to VIEW.json:

  identical   with --all, the copy is byte-for-byte the repository's tree. This is
              what proves the builder faithful and the default untouched.
  residuals   every surviving mention of a dropped capture under the reduced
              skills/. A view with residuals is not clean and the harness refuses it.

--min-support is a fraction of a claim's (or section's, or campaign's) ORIGINAL
support that must still be kept: 1.0 keeps a claim only when every capture behind
it is kept; a small value keeps it on one. It has no default on purpose, because it
decides what a reduced context is allowed to still say, and that belongs in the
experiment's pre-registration, not here.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import math
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provenance as prov  # noqa: E402

DEFAULT_REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ small helpers

def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("".join(lines), encoding="utf-8")


def _delete(lines: list[str], first: int, last: int) -> None:
    """Delete 1-based inclusive [first, last], plus one blank line before it if any."""
    lo = first - 1
    if lo > 0 and not lines[lo - 1].strip():
        lo -= 1
    del lines[lo:last]


def _enough(kept: set[str], original: set[str], min_support: float) -> bool:
    if not original:
        return True
    return len(kept & original) >= max(1, math.ceil(min_support * len(original)))


# ------------------------------------------------------------------------- cutting

def cut_corpus(path: Path, keep: set[str], dropped_keys: list[str], aliases: dict) -> int:
    """Entries for dropped captures go, and so does any comment line that names one:
    the file's own notes explain promotions by name."""
    out, dropped = [], 0
    for line in _lines(path):
        s = line.strip()
        if s and not s.startswith("#") and s.lstrip("/") not in keep:
            dropped += 1
            continue
        if s.startswith("#") and prov.mentions(s, dropped_keys, aliases, bare=True):
            dropped += 1
            continue
        out.append(line)
    _write(path, out)
    return dropped


def cut_prose(path: Path, dropped_keys: list[str], aliases: dict) -> int:
    """In an evidence file, a prose paragraph that names a dropped capture is removed:
    at this corpus size the capture was never seen, so the paragraph could not have
    been written. Tables are left to the row cut; a heading is not a paragraph."""
    doomed = [p for p in prov.paragraphs(path)
              if not p.text.startswith("|") and not p.text.startswith("```")
              and prov.mentions(p.text, dropped_keys, aliases, bare=True)]
    lines = _lines(path)
    for p in sorted(doomed, key=lambda p: p.first, reverse=True):
        _delete(lines, p.first, p.last)
    if doomed:
        _write(path, lines)
    return len(doomed)


_LIST_CELL = re.compile(r"^\s*[A-Za-z_]+/[\w\-]+(\s*,\s*[A-Za-z_]+/[\w\-]+)*\s*$")


def cut_rows(path: Path, keep: set[str], corpus: list[str], aliases: dict) -> int:
    """A row whose first cell names a dropped capture goes. A cell that is a list of
    capture keys (a campaign's "which captures ran this" column) is filtered to the
    kept ones, and the row goes if that leaves it empty."""
    out, dropped = [], 0
    for line in _lines(path):
        key = prov.first_cell_key(line, corpus, aliases)
        if key is not None and key not in keep:
            dropped += 1
            continue
        if line.startswith("|"):
            cells = line.rstrip("\n").split("|")
            changed, emptied = False, False
            for i, cell in enumerate(cells):
                if _LIST_CELL.match(cell) and any(prov.canonical(t, corpus, aliases) for t in cell.split(",")):
                    kept_keys = [t.strip() for t in cell.split(",")
                                 if (k := prov.canonical(t, corpus, aliases)) is None or k in keep]
                    if not kept_keys:
                        emptied = True
                    elif len(kept_keys) != len(cell.split(",")):
                        cells[i] = " " + ", ".join(kept_keys) + " "
                        changed = True
            if emptied:
                dropped += 1
                continue
            if changed:
                line = "|".join(cells) + "\n"
        out.append(line)
    _write(path, out)
    return dropped


def cut_sections(path: Path, section_caps: dict[str, list[str]], keep: set[str],
                 min_support: float) -> list[str]:
    """Remove every labelled section whose kept support is below the rule."""
    secs = {s.anchor: s for s in prov.sections(path)}
    doomed = [secs[a] for a, caps in section_caps.items()
              if a in secs and not _enough(keep, set(caps), min_support)]
    lines = _lines(path)
    for s in sorted(doomed, key=lambda s: s.first, reverse=True):
        _delete(lines, s.first, s.last)
    if doomed:
        _write(path, lines)
    return [s.anchor for s in doomed]


def unlink_campaign(skills: Path, name: str) -> int:
    """Once a campaign file is gone, nothing may still point at it: its EVIDENCE.md
    row, any INDEX row whose precedent it was, any table row or prose paragraph in
    any tier that links it. A paragraph may not outlive its evidence, whether or not
    it states a number. Returns the number of removals."""
    return unlink(skills, re.compile(r"\[%s\]|%s\.md" % (re.escape(name), re.escape(name))))


def unlink(skills: Path, pat: re.Pattern) -> int:
    """Remove every table row and every prose paragraph under skills/ that matches."""
    n = 0
    for f in sorted(skills.rglob("*.md")):
        lines = _lines(f)
        kept = [ln for ln in lines if not (ln.startswith("|") and pat.search(ln))]
        n += len(lines) - len(kept)
        doomed = [p for p in prov.paragraphs(f) if not p.text.startswith("|") and pat.search(p.text)]
        # Re-read after the row cut so paragraph line numbers are right.
        _write(f, kept)
        if doomed:
            lines = _lines(f)
            for p in sorted((q for q in prov.paragraphs(f) if not q.text.startswith("|") and pat.search(q.text)),
                            key=lambda p: p.first, reverse=True):
                _delete(lines, p.first, p.last)
                n += 1
            _write(f, lines)
    return n


def prune_claims(skills: Path, side: dict, keep: set[str], min_support: float,
                 removed: set[str] = frozenset()) -> list[dict]:
    """A measured paragraph goes when its kept support is below the rule, or when the
    campaign it rests on was removed as a file: a claim may not outlive its evidence."""
    pruned = []
    by_file: dict[str, list[dict]] = {}
    for c in side.get("claims", []):
        if c.get("rests_on"):
            by_file.setdefault(c["at"].partition("#")[0], []).append(c)
    for rel, claims in by_file.items():
        path = skills / rel
        if not path.is_file():
            continue
        paras = {(p.anchor, p.hash): p for p in prov.paragraphs(path)}
        doomed = []
        for c in claims:
            original = prov.support(c, side) or set()
            p = paras.get((c["at"].partition("#")[2], c["hash"]))
            gone = c["rests_on"].partition("#")[0] in removed
            if p is not None and (gone or not _enough(keep, original, min_support)):
                doomed.append((p, c))
        lines = _lines(path)
        for p, c in sorted(doomed, key=lambda t: t[0].first, reverse=True):
            _delete(lines, p.first, p.last)
            pruned.append({"at": c["at"], "hash": c["hash"], "starts": c["starts"],
                           "rests_on": c["rests_on"]})
        if doomed:
            _write(path, lines)
    return pruned


def rebuild_profile(skills: Path, side: dict, keep: set[str], corpus: list[str]) -> dict:
    """The health digest's reference distribution, from the kept rows of the campaign
    table the sidecar names, at the table's precision. Removed if nothing is kept."""
    prof = side.get("profile") or {}
    yml = skills / "evidence" / "reference_profile.yaml"
    if not prof or not yml.is_file():
        return {"rebuilt": False, "reason": "no profile section or no reference_profile.yaml"}
    table_file = skills / "evidence" / f"{prof['campaign']}.md"
    if not table_file.is_file():
        yml.unlink()
        return {"rebuilt": False, "reason": f"{table_file.name} absent; profile removed", "captures": 0}
    sec = next((s for s in prov.sections(table_file) if s.anchor == prof["table"]), None)
    if sec is None:
        return {"rebuilt": False, "reason": f"anchor {prof['table']} not found"}
    body = _lines(table_file)[sec.first - 1:sec.last]
    header = next((ln for ln in body if ln.startswith("|") and "capture" in ln.split("|")[1].lower()), None)
    if header is None:
        return {"rebuilt": False, "reason": "no capture-keyed table under the anchor"}
    cols = [c.strip() for c in header.strip().strip("|").split("|")]
    rows: dict[str, list[float | None]] = {rung: [] for rung in prof["columns"]}
    kept_rows = 0
    for ln in body:
        key = prov.first_cell_key(ln, corpus, side.get("aliases"))
        if key is None or key not in keep:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        kept_rows += 1
        for rung, col in prof["columns"].items():
            try:
                rows[rung].append(float(cells[cols.index(col)]))
            except (ValueError, IndexError):
                pass
    if kept_rows == 0:
        yml.unlink()
        return {"rebuilt": False, "reason": "no kept capture in the reference table; profile removed",
                "captures": 0}
    old = yaml.safe_load(yml.read_text(encoding="utf-8"))
    out = {"campaign": old.get("campaign"), "captures": kept_rows,
           "pipeline": old.get("pipeline"), "rungs": {}}
    for rung, vals in rows.items():
        meta = (old.get("rungs") or {}).get(rung, {})
        vals = sorted(vals)
        out["rungs"][rung] = {
            "direction": meta.get("direction"), "meaning": meta.get("meaning"),
            "n": len(vals),
            "min": vals[0] if vals else None,
            "median": statistics.median(vals) if vals else None,
            "max": vals[-1] if vals else None,
            "values": vals,
        }
    for k, v in old.items():
        if k not in out:
            out[k] = v
    head = ("# REBUILT by tools/build_context_view.py for a reduced context view, from the\n"
            f"# kept rows of {prof['campaign']}.md#{prof['table']}, at the table's precision.\n"
            "# The repository's own file is generated from the campaign results by\n"
            "# tools/phase_a_report.py and is not this one.\n\n")
    yml.write_text(head + yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
    return {"rebuilt": True, "captures": kept_rows}


# ------------------------------------------------------------------------- checking

def residuals(skills: Path, dropped: list[str], aliases: dict) -> list[dict]:
    hits = []
    for f in sorted(skills.rglob("*")):
        if not f.is_file() or f.suffix not in (".md", ".txt"):
            continue
        in_evidence = "evidence" in f.relative_to(skills).parts
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            exact = prov.mentions(line, dropped, aliases, bare=False)
            bare = (prov.mentions(line, dropped, None, bare=True) - exact) if in_evidence else set()
            hits += [{"capture": k, "kind": "exact", "where": f"{f.relative_to(skills)}:{n}"} for k in sorted(exact)]
            hits += [{"capture": k, "kind": "bare", "where": f"{f.relative_to(skills)}:{n}"} for k in sorted(bare)]
    return hits


def dangling_links(skills: Path) -> list[str]:
    """Relative links under skills/ that no longer resolve. A view with one is not
    clean: a reader following it would be told the context is defective."""
    bad = []
    for f in sorted(skills.rglob("*.md")):
        for m in re.finditer(r"\]\(([^)\s]+)\)", f.read_text(encoding="utf-8", errors="replace")):
            t = m.group(1)
            if t.startswith(("http", "mailto", "#")):
                continue
            p = t.partition("#")[0]
            if p and not (f.parent / p).exists():
                bad.append(f"{f.relative_to(skills)}: {t}")
    return bad


def identical(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(identical(a / d, b / d) for d in cmp.common_dirs)


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


# ----------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO,
                    help="the tree holding skills/ and docs/ (default: this repository)")
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--all", action="store_true", help="no reduction: the identity check")
    how.add_argument("--keep", type=Path, help="file of canonical capture keys, one per line")
    how.add_argument("--n", type=int, help="keep the first N of --order, or N drawn with --seed")
    ap.add_argument("--order", type=Path, help="pre-registered capture order for --n")
    ap.add_argument("--seed", type=int, help="draw N captures at random from CORPUS.txt")
    ap.add_argument("--always", type=Path,
                    help="file of captures kept at every level and not counted in N (for a "
                         "sparse ablation, the dense-only captures)")
    ap.add_argument("--min-support", type=float,
                    help="fraction of a claim's original support that must be kept (0, 1]; "
                         "required when reducing")
    ap.add_argument("--force", action="store_true", help="replace an existing --out")
    a = ap.parse_args(argv)

    repo, out = a.repo.resolve(), a.out.resolve()
    if out == repo or repo in out.parents:
        sys.exit(f"--out {out} is inside the repository; a view is written to the experiment "
                 "record, never beside the context it reduces")
    src_skills, src_docs = repo / "skills", repo / "docs"
    if not (src_skills / "evidence" / "CORPUS.txt").is_file():
        sys.exit(f"{src_skills}: no evidence/CORPUS.txt, so not a context tree")
    corpus = prov.corpus_keys(src_skills)
    side = yaml.safe_load((src_skills / "evidence" / "provenance.yaml").read_text(encoding="utf-8")) \
        if (src_skills / "evidence" / "provenance.yaml").is_file() else {}
    aliases = side.get("aliases", {})

    if a.all:
        keep, mode = list(corpus), "all"
    else:
        if a.min_support is None or not (0 < a.min_support <= 1):
            sys.exit("--min-support in (0, 1] is required when reducing; it is a pre-registered choice")
        if a.keep:
            keep = [ln.strip().lstrip("/") for ln in a.keep.read_text().splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")]
            mode = f"keep:{a.keep}"
        elif a.n is None or a.n < 0:
            sys.exit("--n needs a non-negative count")
        elif a.order:
            order = [ln.strip().lstrip("/") for ln in a.order.read_text().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
            keep, mode = order[:a.n], f"n={a.n} order:{a.order}"
        elif a.seed is not None:
            keep = random.Random(a.seed).sample(corpus, min(a.n, len(corpus)))
            mode = f"n={a.n} seed:{a.seed}"
        else:
            sys.exit("--n needs --order or --seed")
        if a.always:
            always = [ln.strip().lstrip("/") for ln in a.always.read_text().splitlines()
                      if ln.strip() and not ln.lstrip().startswith("#")]
            keep = list(dict.fromkeys(keep + always))
            mode += f" always:{a.always}"
    unknown = sorted(set(keep) - set(corpus))
    if unknown:
        sys.exit(f"not in CORPUS.txt, so not a capture this context has: {unknown}")
    keep_set = set(keep)
    dropped = [k for k in corpus if k not in keep_set]

    if out.exists():
        if not a.force:
            sys.exit(f"{out} exists; pass --force to replace it")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    skills = out / "skills"
    shutil.copytree(src_skills, skills)
    if src_docs.is_dir():
        shutil.copytree(src_docs, out / "docs")
    # The module tier is held fixed and read from the repository, but the context's
    # own links into modules/*/skills and the resolver's `modules/...` topics are
    # relative to whatever sits beside skills/. A symlink keeps both working and
    # makes "held fixed" literal: there is one modules/ and this is it.
    if (repo / "modules").is_dir():
        (out / "modules").symlink_to(repo / "modules", target_is_directory=True)

    report = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(repo), "source_commit": git_head(repo), "mode": mode,
        "min_support": a.min_support,
        "kept": sorted(keep_set), "dropped": dropped,
        "rows_cut": {}, "paragraphs_cut": {}, "campaigns_removed": [], "unlinked": {},
        "sections_cut": {}, "claims_pruned": [],
        "profile": {"rebuilt": False, "reason": "no reduction"},
        "uncut": ["docs/: copied whole, held fixed",
                  "modules/: a symlink to the repository's, held fixed"],
    }

    if dropped:
        ev = skills / "evidence"
        report["rows_cut"]["evidence/CORPUS.txt"] = cut_corpus(ev / "CORPUS.txt", keep_set, dropped, aliases)
        # The profile first, from the still-whole reference table: the campaign file it
        # reads may itself fall below the support rule and be removed just below.
        report["profile"] = rebuild_profile(skills, side, keep_set, corpus)
        if not (skills / "evidence" / "reference_profile.yaml").exists():
            report["unlinked"]["reference_profile.yaml"] = unlink(skills, re.compile(r"reference_profile\.yaml"))
        for name, c in sorted(side.get("campaigns", {}).items()):
            f = ev / f"{name}.md"
            if not f.is_file():
                continue
            if not _enough(keep_set, set(c.get("captures", [])), a.min_support):
                f.unlink()
                report["campaigns_removed"].append(name)
                continue
            gone = cut_sections(f, c.get("sections", {}), keep_set, a.min_support)
            if gone:
                report["sections_cut"][name] = gone
        for name in report["campaigns_removed"]:
            report["unlinked"][name] = unlink_campaign(skills, name)
        for f in sorted(ev.glob("*.md")):
            n = cut_rows(f, keep_set, corpus, aliases)
            if n:
                report["rows_cut"][f"evidence/{f.name}"] = n
            n = cut_prose(f, dropped, aliases)
            if n:
                report["paragraphs_cut"][f"evidence/{f.name}"] = n
        report["claims_pruned"] = prune_claims(skills, side, keep_set, a.min_support,
                                               set(report["campaigns_removed"]))

    same = identical(src_skills, skills) if a.all else None
    left = residuals(skills, dropped, aliases) if dropped else []
    dangling = dangling_links(skills)
    report.update({
        "identical_to_source": same,
        "residuals": left,
        "dangling_links": dangling,
        "clean": (same is True and not dangling) if a.all else not (left or dangling),
    })
    (out / "VIEW.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{out}: kept {len(keep_set)} of {len(corpus)}; "
          f"{len(report['campaigns_removed'])} campaigns removed, "
          f"{sum(len(v) for v in report['sections_cut'].values())} sections cut, "
          f"{sum(report['rows_cut'].values())} rows cut, "
          f"{len(report['claims_pruned'])} claims pruned; "
          f"{len(left)} residual mentions, {len(dangling)} dangling links; clean={report['clean']}")
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
