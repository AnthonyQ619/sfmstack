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

Exit status is 1 when anything has drifted, or when an image could not be
checked because docker did not answer in time, so this can gate a campaign: an
image nobody could read is not an image anyone can vouch for. On a loaded
shared machine a container can take minutes to start; the check says so by
name rather than dying with a traceback nobody sees.
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


def in_image(tag: str, paths: list[str]) -> dict[str, str] | None:
    """md5 of each path inside the image, from ONE container, or None if the
    image is absent. Raises subprocess.TimeoutExpired if docker does not answer."""
    out = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "md5sum", tag,
         *[f"/module/{p}" for p in paths]],
        capture_output=True, text=True, timeout=180,
    )
    sums = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].removeprefix("/module/")] = parts[0]
    if out.returncode != 0 and not sums:
        return None
    return sums


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    needle = args[0] if args else ""

    drifted, missing, unchecked, checked = [], [], [], 0
    for module_dir in sorted((REPO / "modules").iterdir()):
        if not (module_dir / "module.yaml").is_file():
            continue
        if needle and needle not in module_dir.name:
            continue
        tagged = image_tag(module_dir)
        if tagged is None:
            continue
        tag, _version = tagged

        files = [f for f in TRACKED if (module_dir / f).is_file()]
        try:
            got = in_image(tag, files)
        except subprocess.TimeoutExpired:
            unchecked.append((module_dir.name, tag))
            continue
        if got is None:
            missing.append((module_dir.name, tag))
            continue
        for fname in files:
            checked += 1
            want = hashlib.md5((module_dir / fname).read_bytes()).hexdigest()
            if got.get(fname) != want:
                drifted.append((module_dir.name, tag, fname))

    for name, tag in missing:
        print(f"MISSING  {name:24s} {tag}  (no such image built)")
    for name, tag, fname in drifted:
        print(f"DRIFTED  {name:24s} {tag}  {fname} differs from source")
    for name, tag in unchecked:
        print(f"UNCHECKED {name:23s} {tag}  (docker did not answer in 180s)")
    print(f"\n{checked} file(s) checked; {len(drifted)} drifted, "
          f"{len(missing)} image(s) absent, {len(unchecked)} unchecked.")
    if drifted:
        print("Rebuild with: tools/build_images.sh <module_dir>")
    if unchecked:
        print("Unchecked is not clean: re-run the check when the machine is quieter.")
    return 1 if drifted or unchecked else 0


if __name__ == "__main__":
    raise SystemExit(main())
