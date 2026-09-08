#!/usr/bin/env python3
"""Recompute every recorded profile from the artifacts already in the store.

    tools/phase_a_recompute.py ~/sfm-phase-a-store/phase_a_results.json

The rung definitions are the thing under test, and the campaign exists partly to
falsify them -- two were corrected by their own first reading. Re-deriving from
stored artifacts keeps that cheap: the pipeline runs once, and a definition that
changes costs seconds rather than a re-run, so there is never a reason to leave
a rung wrong because fixing it looked expensive.

The GT columns and stage metrics are left untouched; only `profile` is rebuilt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "sfmorch" / "src"))
sys.path.insert(0, str(REPO / "packages" / "sfmkit" / "src"))

from sfmkit import ArtifactStore                      # noqa: E402
from sfmorch.health import components                 # noqa: E402


def main() -> int:
    results = Path(sys.argv[1])
    rows = json.loads(results.read_text())
    store = ArtifactStore(results.parent)

    for r in rows:
        ids = r.get("artifacts")
        if not ids:
            continue
        try:
            r["profile"] = components(
                store.open(ids["refined"]),
                scene=store.open(ids["scene"]),
                tracks=store.open(ids["tracks"]),
                matches=store.open(ids["matches"]))
            print(f"[ok] {r['capture']}  comp={r['profile']['composition']:.3f} "
                  f"err={r['profile']['error']}", flush=True)
        except Exception as exc:
            print(f"[--] {r['capture']}: {type(exc).__name__}: {exc}", flush=True)

    results.write_text(json.dumps(rows, indent=2, default=str))
    print(f"rewrote {results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
