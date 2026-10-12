#!/usr/bin/env python3
"""Build a reduced VIEW of the context for an ablation batch. Never run otherwise.

    tools/build_context_view.py --out DIR --all
    tools/build_context_view.py --out DIR --keep captures.txt
    tools/build_context_view.py --out DIR --n 5 --order ladder.txt
    tools/build_context_view.py --out DIR --n 5 --seed 7

The repository's `skills/` is the context, and every ordinary run reads all of it.
This tool copies `skills/` and `docs/` to DIR and cuts the copy down to the captures
you name: entries in `evidence/CORPUS.txt`, rows in `evidence/INDEX.md`, and
per-capture table rows in every campaign file. Which captures, and how many, are
arguments to the call -- there is no ladder in this file, and nothing in the stack
calls it. The harness reads a view only when `SFM_SKILLS` points at one.

Two checks decide whether the result is a view at all, and both are written to
`DIR/VIEW.json`:

  identical   with --all, the copy is byte-for-byte the repository's tree. This is
              what proves the builder faithful and the default untouched.
  residuals   every dropped capture's name, searched for across the reduced
              `skills/`. A view with residuals is NOT clean: the names survive in
              prose, in per-capture sections, in aggregate tables that cannot be cut
              by row. The harness refuses an unclean view. What is listed under
              `residuals` is exactly the work that makes the evidence tier cuttable.

What this tool does not cut, and says so under `uncut`:

  evidence/reference_profile.yaml   its value lists carry no capture labels, so it
                                    cannot be reduced by capture until it does;
  docs/                             copied whole, held fixed by declaration;
  the guidance tiers                scene-name-free by rule; a claim there carries
                                    no machine-readable capture set yet, so it is
                                    kept whole at every size.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent

# Batch aliases the evidence tier has used for a dataset directory. CORPUS.txt is
# the canonical spelling and records why the `TT/` alias matched nothing.
FAMILY_ALIASES = {
    "tt": "tanks_and_temples", "tanks_and_temples": "tanks_and_temples",
    "euroc": "euroc", "tum_vi": "tum_vi", "advio": "advio",
    "eth": "ETH", "eth3d": "ETH", "dtu": "DTU",
}


def corpus_keys(skills: Path) -> list[str]:
    text = (skills / "evidence" / "CORPUS.txt").read_text(encoding="utf-8")
    return [ln.strip().lstrip("/") for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def canonical(token: str, corpus: list[str]) -> str | None:
    """The corpus key a table cell names, or None if it names no corpus capture."""
    token = token.strip()
    if not token:
        return None
    if "/" in token:
        fam, _, leaf = token.partition("/")
        fam = FAMILY_ALIASES.get(fam.lower())
        if fam is None:
            return None
        key = f"{fam}/{leaf}"
        return key if key in corpus else None
    leaves = [k for k in corpus if k.split("/", 1)[1] == token]
    return leaves[0] if len(leaves) == 1 else None


_CELL_NOISE = re.compile(r"<a\b[^>]*></a>|\*\*|`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def first_cell_key(line: str, corpus: list[str]) -> str | None:
    """The corpus key a table row's first cell names, after the spellings seen so far:
    anchor prefixes, bold, backticks, link text, and prose after a dash or a label."""
    if not line.startswith("|"):
        return None
    cell = line.split("|", 2)[1]
    cell = _LINK.sub(r"\1", _CELL_NOISE.sub("", cell)).strip()
    cell = re.split(r"\s+[—–-]\s+|\s+`|\s{2,}", cell)[0].strip()
    return canonical(cell, corpus)


def cut_evidence_file(path: Path, keep: set[str], corpus: list[str]) -> int:
    """Drop every table row whose first cell names a corpus capture outside `keep`."""
    out, dropped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        key = first_cell_key(line, corpus)
        if key is not None and key not in keep:
            dropped += 1
            continue
        out.append(line)
    if dropped:
        path.write_text("".join(out), encoding="utf-8")
    return dropped


def cut_corpus(path: Path, keep: set[str]) -> int:
    out, dropped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        s = line.strip()
        if s and not s.startswith("#") and s.lstrip("/") not in keep:
            dropped += 1
            continue
        out.append(line)
    path.write_text("".join(out), encoding="utf-8")
    return dropped


def residuals(skills: Path, dropped: list[str]) -> list[dict]:
    """Every surviving mention of a dropped capture. `exact` is the full key in any
    spelling, anywhere under skills/; `bare` is the leaf alone, which is a scene name
    by convention only inside evidence/, so it is searched only there."""
    exact, bare = {}, {}
    for key in dropped:
        fam, leaf = key.split("/", 1)
        fams = [a for a, c in FAMILY_ALIASES.items() if c == fam] + [fam]
        exact[key] = re.compile(r"(?<![\w/])(?:%s)/%s(?![\w-])" % (
            "|".join(re.escape(f) for f in set(fams)), re.escape(leaf)), re.I)
        bare[key] = re.compile(r"(?<![\w/-])%s(?![\w-])" % re.escape(leaf))
    hits = []
    for f in sorted(skills.rglob("*")):
        if not f.is_file() or f.suffix not in (".md", ".txt", ".yaml"):
            continue
        in_evidence = "evidence" in f.relative_to(skills).parts
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for key in dropped:
                if exact[key].search(line):
                    hits.append({"capture": key, "kind": "exact",
                                 "where": f"{f.relative_to(skills)}:{n}"})
                elif in_evidence and bare[key].search(line):
                    hits.append({"capture": key, "kind": "bare",
                                 "where": f"{f.relative_to(skills)}:{n}"})
    return hits


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
    ap.add_argument("--force", action="store_true", help="replace an existing --out")
    a = ap.parse_args(argv)

    repo, out = a.repo.resolve(), a.out.resolve()
    src_skills, src_docs = repo / "skills", repo / "docs"
    if not (src_skills / "evidence" / "CORPUS.txt").is_file():
        sys.exit(f"{src_skills}: no evidence/CORPUS.txt, so not a context tree")
    corpus = corpus_keys(src_skills)

    if a.all:
        keep, mode = list(corpus), "all"
    elif a.keep:
        keep = [ln.strip().lstrip("/") for ln in a.keep.read_text().splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
        mode = f"keep:{a.keep}"
    else:
        if a.n is None or a.n < 0:
            sys.exit("--n needs a non-negative count")
        if a.order:
            order = [ln.strip().lstrip("/") for ln in a.order.read_text().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
            keep, mode = order[:a.n], f"n={a.n} order:{a.order}"
        elif a.seed is not None:
            keep = random.Random(a.seed).sample(corpus, min(a.n, len(corpus)))
            mode = f"n={a.n} seed:{a.seed}"
        else:
            sys.exit("--n needs --order or --seed")
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
    shutil.copytree(src_skills, out / "skills")
    if src_docs.is_dir():
        shutil.copytree(src_docs, out / "docs")

    cut: dict[str, int] = {}
    if dropped:
        ev = out / "skills" / "evidence"
        cut["evidence/CORPUS.txt"] = cut_corpus(ev / "CORPUS.txt", keep_set)
        for f in sorted(ev.glob("*.md")):
            n = cut_evidence_file(f, keep_set, corpus)
            if n:
                cut[f"evidence/{f.name}"] = n

    same = identical(src_skills, out / "skills") if a.all else None
    left = residuals(out / "skills", dropped) if dropped else []
    report = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(repo), "source_commit": git_head(repo), "mode": mode,
        "kept": sorted(keep_set), "dropped": dropped,
        "rows_cut": cut,
        "uncut": ["evidence/reference_profile.yaml: value lists carry no capture labels",
                  "docs/: copied whole, held fixed",
                  "plan/ judge/ health/ distill/: no claim carries a capture set yet"],
        "identical_to_source": same,
        "residuals": left,
        "clean": (same is True) if a.all else not left,
    }
    (out / "VIEW.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{out}: kept {len(keep_set)} of {len(corpus)}, "
          f"cut {sum(cut.values())} rows in {len(cut)} files, "
          f"{len(left)} residual mentions, clean={report['clean']}")
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
