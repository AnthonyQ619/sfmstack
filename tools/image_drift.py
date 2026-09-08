#!/usr/bin/env python3
"""Does each module's built image still match the source it claims to be?

    tools/image_drift.py            check every module
    tools/image_drift.py match_     only modules whose directory matches

A module image is tagged with the manifest's `version`, and the orchestrator's
cache key is built from that version -- not from the adapter source. So an image
built before an adapter edit keeps the same tag, keeps satisfying the cache, and
keeps running last week's code. `docs/mcp-tools.md` records that as a known
property of the cache; this is the check that turns it from a thing you have to
remember into a thing you can ask.

It is not a hypothetical. The reference campaign's first attempt was invalidated
by exactly this: `match_lightglue` at 1.6.0 was running an image built before the
guard that stops one degenerate image pair from killing a whole exhaustive
matching run, so a capture failed in a way the repository's own source says
cannot happen.

Exit status is 1 when anything has drifted, so this can gate a campaign.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "sfmorch" / "src"))

# Files whose drift changes behaviour. The manifest is included because it
# carries the parameter defaults, the healthy bands and the diagnostics -- a
# module whose image holds an older manifest publishes different metrics than
# the one the skills describe.
TRACKED = ("adapter.py", "module.yaml")


def image_tag(module_dir: Path) -> tuple[str, str] | None:
    import yaml
    doc = yaml.safe_load((module_dir / "module.yaml").read_text())
    image = doc.get("image")
    if not image:
        return None
    return image, doc.get("version", "")


def in_image(tag: str, path: str) -> str | None:
    out = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "md5sum", tag, f"/module/{path}"],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        return None
    return out.stdout.split()[0]


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    needle = args[0] if args else ""

    drifted, missing, checked = [], [], 0
    for module_dir in sorted((REPO / "modules").iterdir()):
        if not (module_dir / "module.yaml").is_file():
            continue
        if needle and needle not in module_dir.name:
            continue
        tagged = image_tag(module_dir)
        if tagged is None:
            continue
        tag, _version = tagged

        for fname in TRACKED:
            src = module_dir / fname
            if not src.is_file():
                continue
            want = hashlib.md5(src.read_bytes()).hexdigest()
            got = in_image(tag, fname)
            checked += 1
            if got is None:
                missing.append((module_dir.name, tag))
                break
            if got != want:
                drifted.append((module_dir.name, tag, fname))

    for name, tag in missing:
        print(f"MISSING  {name:24s} {tag}  (no such image built)")
    for name, tag, fname in drifted:
        print(f"DRIFTED  {name:24s} {tag}  {fname} differs from source")
    print(f"\n{checked} file(s) checked; {len(drifted)} drifted, "
          f"{len(missing)} image(s) absent.")
    if drifted:
        print("Rebuild with: tools/build_images.sh <module_dir>")
    return 1 if drifted else 0


if __name__ == "__main__":
    raise SystemExit(main())
