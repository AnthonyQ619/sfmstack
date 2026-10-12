"""The provenance sidecar: what every piece of context rests on, kept beside the context.

`skills/evidence/provenance.yaml` is machine-facing. It is YAML, so the skill resolver
never serves it, and it changes no file it describes: a guidance paragraph is addressed
by file, heading anchor and a hash of its own text, a campaign section by the anchor
the file already has. Three checks in `tests/context_checks.py` keep it current, and
`tools/build_context_view.py` reads it to cut a reduced view for an ablation batch.

This module is the one place the addressing is defined, so the drafting tool, the
checks and the builder cannot disagree about what a paragraph is or how it is hashed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SIDECAR = Path("skills") / "evidence" / "provenance.yaml"
GUIDANCE = ("plan", "judge", "health")

# Batch aliases the evidence tier has used for a dataset directory. CORPUS.txt is
# the canonical spelling and records why the `TT/` alias matched nothing.
FAMILY_ALIASES = {
    "tt": "tanks_and_temples", "tanks_and_temples": "tanks_and_temples",
    "euroc": "euroc", "tum_vi": "tum_vi", "advio": "advio",
    "eth": "ETH", "eth3d": "ETH", "dtu": "DTU",
}

# A paragraph counts as measured when it states a number the corpus produced: a
# decimal, a percentage, an "N of M", an explicit n, or a spelled corpus count.
MEASURED = re.compile(
    r"\d+\.\d+|\d+\s?%|\b\d+ of \d+\b|\bn ?= ?\d+\b|"
    r"\b(fourteen|sixteen|seventeen|nineteen|twenty-four|thirty-five|forty-eight|"
    r"seventy-five)\b", re.I)

EXPLICIT_ANCHOR = re.compile(r"""<a\s+(?:id|name)\s*=\s*["']([^"']+)["']""")
CAMPAIGN_LINK = re.compile(r"evidence/([a-z0-9-]+-20\d\d-\d\d)\.md(?:#([\w-]+))?")


def slug(heading: str) -> str:
    """GitHub's slugger, exactly as `tests/context_checks.slug` has it: lower-case,
    drop what is not a word character, space or hyphen, each space to a hyphen."""
    s = re.sub(r"[^\w\s-]", "", heading.strip().lower(), flags=re.UNICODE)
    return s.strip().replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    out = {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*)$", text, re.M)}
    return out | set(EXPLICIT_ANCHOR.findall(text))


@dataclass(frozen=True)
class Para:
    anchor: str      # slug of the nearest heading above, "" before the first
    hash: str        # sha256 of the normalised text, first 12 hex
    starts: str      # the first 48 characters, for a human reader
    text: str        # normalised: whitespace collapsed
    first: int       # 1-based line of the first line
    last: int        # 1-based line of the last line


def normalise(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def paragraphs(path: Path) -> list[Para]:
    """Every paragraph: a run of non-blank lines that are not headings. Tables, lists
    and fenced blocks are paragraphs like any other; a fence is kept whole."""
    out: list[Para] = []
    anchor, buf, start, fenced = "", [], 0, False

    def flush(end: int):
        if buf:
            text = normalise(buf)
            out.append(Para(anchor, digest(text), text[:48], text, start, end))
        buf.clear()

    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            fenced = not fenced
            if not buf:
                start = i
            buf.append(line)
            if not fenced:
                flush(i)
            continue
        if fenced:
            buf.append(line)
            continue
        if re.match(r"^#{1,6}\s+", line):
            flush(i - 1)
            anchor = slug(line.lstrip("#").strip())
        elif not line.strip():
            flush(i - 1)
        else:
            if not buf:
                start = i
            buf.append(line)
    flush(len(lines))
    return out


@dataclass(frozen=True)
class Section:
    anchor: str
    level: int
    first: int       # 1-based line of the heading
    last: int        # 1-based last line before the next heading of this level or higher


def sections(path: Path) -> list[Section]:
    lines = path.read_text(encoding="utf-8").splitlines()
    heads = [(i, len(m.group(1)), slug(m.group(2).strip()))
             for i, line in enumerate(lines, 1)
             if (m := re.match(r"^(#{1,6})\s+(.*)$", line))]
    out = []
    for k, (i, level, anchor) in enumerate(heads):
        last = len(lines)
        for j, lv, _ in heads[k + 1:]:
            if lv <= level:
                last = j - 1
                break
        out.append(Section(anchor, level, i, last))
    return out


def corpus_keys(skills: Path) -> list[str]:
    text = (skills / "evidence" / "CORPUS.txt").read_text(encoding="utf-8")
    return [ln.strip().lstrip("/") for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def canonical(token: str, corpus: list[str], aliases: dict[str, str] | None = None) -> str | None:
    """The corpus key a token names, or None. `aliases` are whole-key aliases from the
    sidecar; the family aliases above are applied after."""
    token = token.strip()
    if not token:
        return None
    if aliases and token in aliases:
        return aliases[token] if aliases[token] in corpus else None
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


def first_cell_key(line: str, corpus: list[str], aliases: dict[str, str] | None = None) -> str | None:
    """The corpus key a table row's first cell names, after every spelling seen so far:
    anchor prefixes, bold, backticks, link text, and prose after a dash or a label."""
    if not line.startswith("|"):
        return None
    cell = line.split("|", 2)[1]
    cell = _LINK.sub(r"\1", _CELL_NOISE.sub("", cell)).strip()
    # A key followed by anything -- a kind label, a parenthesised tag, prose after a
    # dash -- is still the key: the first token decides when it carries a slash.
    head = cell.split(None, 1)[0] if cell else ""
    if "/" in head and (key := canonical(head, corpus, aliases)):
        return key
    cell = re.split(r"\s+[—–-]\s+|\s+\(|\s{2,}", cell)[0].strip()
    return canonical(cell, corpus, aliases)


def mentions(text: str, corpus: list[str], aliases: dict[str, str] | None = None,
             bare: bool = True) -> set[str]:
    """Every corpus capture a passage names: the full key in any family spelling, and
    (when `bare`) the leaf alone, which is a name by convention only inside evidence/."""
    found = set()
    fams = {}
    for key in corpus:
        fam, leaf = key.split("/", 1)
        fams.setdefault(fam, [a for a, c in FAMILY_ALIASES.items() if c == fam] + [fam])
        pat = r"(?<![\w/])(?:%s)/%s(?![\w-])" % ("|".join(re.escape(f) for f in set(fams[fam])), re.escape(leaf))
        if re.search(pat, text, re.I):
            found.add(key)
        elif bare and re.search(r"(?<![\w/-])%s(?![\w-])" % re.escape(leaf), text):
            found.add(key)
    for alias, key in (aliases or {}).items():
        if alias in text and key in corpus:
            found.add(key)
    return found


def load(root: Path) -> dict:
    return yaml.safe_load((root / SIDECAR).read_text(encoding="utf-8")) or {}


def support(claim: dict, side: dict) -> set[str] | None:
    """The captures a claim rests on, through the campaign's section map. None for an
    unsourced claim, which is a declaration and not a measurement."""
    if "rests_on" not in claim:
        return None
    camp, _, anchor = claim["rests_on"].partition("#")
    c = side.get("campaigns", {}).get(camp, {})
    if anchor and anchor in c.get("sections", {}):
        return set(c["sections"][anchor])
    return set(c.get("captures", []))
