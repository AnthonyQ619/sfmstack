#!/usr/bin/env python3
"""Draft the provenance sidecar from what the tree already says. A person finishes it.

    tools/provenance_draft.py                 print the draft
    tools/provenance_draft.py --merge         keep every entry of the existing sidecar
                                              that still matches, add what is missing

Two parts are mechanical and one is not.

  campaigns   every capture a campaign file names, and per section the subset that
              section names -- names are allowed there, so the file is its own map.
  profile     the table the health digest's reference distribution is rebuilt from.
  claims      every measured paragraph in plan/, judge/ and health/, with `rests_on`
              filled only where the paragraph itself links a campaign. The rest are
              left as `rests_on: ""` for a person to fill, or to turn into
              `unsourced: <why>`. The checks refuse an empty value, so a draft cannot
              be committed as if it were finished.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provenance as prov  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

PROFILE = {
    "campaign": "reference-pipeline-2026-09",
    "table": "the-health-profile-per-capture",
    "columns": {"registration": "reg", "conditioning": "cond", "composition": "comp",
                "coverage": "cov", "error": "err", "yield_obs": "y_obs",
                "yield_track": "y_trk", "pose_agreement": "pose"},
}

ALIASES = {
    "TT/Barn": "tanks_and_temples/Barn",
    "TT/Meetingroom": "tanks_and_temples/Meetingroom",
    "EUROC/MH_05_difficult": "euroc/MH_05_difficult",
    "EUROC/V2_01_easy": "euroc/V2_01_easy",
    "TUM_VI/room3": "tum_vi/room3",
    "TUM_VI/room4": "tum_vi/room4",
    "ADVIO/advio-07": "advio/advio-07",
}


def draft_campaigns(skills: Path, corpus: list[str]) -> dict:
    out = {}
    for f in sorted((skills / "evidence").glob("*-20*.md")):
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        caps = prov.mentions(text, corpus, ALIASES)
        secs = {}
        for s in prov.sections(f):
            body = "\n".join(lines[s.first - 1:s.last])
            named = prov.mentions(body, corpus, ALIASES)
            if named and named != caps:
                secs[s.anchor] = sorted(named)
        entry = {"captures": sorted(caps)}
        if secs:
            entry["sections"] = secs
        out[f.stem] = entry
    return out


def draft_claims(skills: Path, existing: dict | None) -> list[dict]:
    keep = {(c["at"], c["hash"]): c for c in (existing or {}).get("claims", [])}
    out = []
    for tier in prov.GUIDANCE:
        for path in sorted((skills / tier).glob("*.md")):
            rel = f"{tier}/{path.name}"
            for p in prov.paragraphs(path):
                if not prov.MEASURED.search(p.text):
                    continue
                at = f"{rel}#{p.anchor}"
                if (at, p.hash) in keep:
                    out.append(keep[(at, p.hash)])
                    continue
                entry = {"at": at, "hash": p.hash, "starts": p.starts}
                links = prov.CAMPAIGN_LINK.findall(p.text)
                if links:
                    camp, anchor = links[0]
                    entry["rests_on"] = f"{camp}#{anchor}" if anchor else camp
                else:
                    entry["rests_on"] = ""
                out.append(entry)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args(argv)
    skills = a.repo / "skills"
    corpus = prov.corpus_keys(skills)
    existing = prov.load(a.repo) if a.merge and (a.repo / prov.SIDECAR).is_file() else None
    side = {
        "version": 1,
        "aliases": (existing or {}).get("aliases", ALIASES),
        "fixed": (existing or {}).get("fixed", ["modules/", "docs/"]),
        "campaigns": draft_campaigns(skills, corpus),
        "profile": (existing or {}).get("profile", PROFILE),
        "claims": draft_claims(skills, existing),
    }
    blank = sum(1 for c in side["claims"] if c.get("rests_on") == "")
    print(yaml.safe_dump(side, sort_keys=False, allow_unicode=True, width=100))
    print(f"# {len(side['claims'])} claims, {blank} with rests_on still blank", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
