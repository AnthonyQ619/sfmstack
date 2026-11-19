#!/usr/bin/env python3
"""Stage captures under opaque names for a sealed experiment (P11 scene-information ablation).

    stage_anon.py <source_batch.json> <out_batch.json> [--controls cap1,cap2]

The source batch is the usual list of {capture, image_dir, calibration_path}. Each capture is staged
as /home/anthonyq/datasets/anon/<token>/{images/NNNNNN.<ext>, calibration.npz}: frames in the
loader's own (sorted) order, renamed by position; PNGs without metadata are hard links (no space),
any frame that carries metadata -- EXIF timestamps, camera model, PNG text -- is copied with the
metadata removed losslessly (JPEG APPn/COM segments, PNG ancillary text and time chunks). The out
batch names each capture `scenes/<token>` and carries only the staged paths, so nothing the agent is
given names the dataset. The key -- token to source -- is written to anon/.keys/<token>.json, which a
sealed agent may not read (launch.py), and sfmx applies the corpus guard to the source it names.
A capture in the planning corpus is refused unless named in --controls.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import struct
import sys
from pathlib import Path

DATASETS = Path("/home/anthonyq/datasets")
ANON = DATASETS / "anon"
REPO = Path(__file__).resolve().parent.parent
EXTS = {".png", ".jpg", ".jpeg"}
PNG_DROP = {b"tEXt", b"iTXt", b"zTXt", b"tIME", b"eXIf"}


def strip_jpeg(data: bytes) -> bytes:
    """The same JPEG without APP1..APP15 and COM segments (APP0/JFIF kept). Entropy data untouched."""
    assert data[:2] == b"\xff\xd8", "not a JPEG"
    out, i = bytearray(b"\xff\xd8"), 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("bad JPEG marker stream")
        marker = data[i + 1]
        if marker == 0xDA:                      # start of scan: the rest is image data
            out += data[i:]
            break
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        seg = data[i:i + 2 + length]
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):
            out += seg
        i += 2 + length
    return bytes(out)


def strip_png(data: bytes) -> bytes:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    out, i = bytearray(data[:8]), 8
    while i < len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        chunk = data[i:i + 12 + n]
        if kind not in PNG_DROP:
            out += chunk
        i += 12 + n
    return bytes(out)


def stage_one(entry: dict, controls: set[str]) -> dict:
    src = Path(entry["image_dir"])
    corpus = [ln.strip() for ln in (REPO / "skills/evidence/CORPUS.txt").read_text().splitlines()
              if ln.strip() and not ln.startswith("#")]
    hit = next((c for c in corpus if c.rstrip("/") + "/" in str(src).rstrip("/") + "/"), None)
    # The corpus names windows in the staged-inputs layout (/Fuji/west_scene_000, /MADMAX3/H0_scene_000);
    # the raw datasets hold the same frames as .../west/scene_000/images. Match on the window's name too.
    parts = [x for x in src.parts if x != "images"]
    if parts and parts[-1].startswith("scene_") and len(parts) >= 2:
        window = f"{parts[-2]}_{parts[-1]}"
        hit = hit or next((c for c in corpus if c.rstrip("/").endswith("/" + window)), None)
    if hit and entry["capture"] not in controls:
        sys.exit(f"{entry['capture']} is in the planning corpus ({hit}); name it in --controls to stage it")
    frames = sorted(p for p in src.iterdir() if p.suffix.lower() in EXTS)
    if not frames:
        sys.exit(f"{entry['capture']}: no frames in {src}")
    token = "c" + secrets.token_hex(3)
    dst = ANON / token / "images"
    dst.mkdir(parents=True)
    copied = 0
    for k, f in enumerate(frames):
        out = dst / f"{k:06d}{f.suffix.lower()}"
        data = f.read_bytes()
        clean = strip_jpeg(data) if f.suffix.lower() in (".jpg", ".jpeg") else strip_png(data)
        if clean == data:
            os.link(f, out)
        else:
            out.write_bytes(clean)
            copied += 1
    calib = ANON / token / "calibration.npz"
    os.link(entry["calibration_path"], calib)
    capture = f"scenes/{token}"
    key = {"token": token, "capture": capture, "source": entry, "frames": len(frames),
           "copied_without_metadata": copied,
           "redact": [[str(src), str(dst)], [entry["calibration_path"], str(calib)],
                      [entry["capture"], capture]]}
    (ANON / ".keys").mkdir(parents=True, exist_ok=True)
    (ANON / ".keys" / f"{token}.json").write_text(json.dumps(key, indent=1))
    out = {"capture": capture, "image_dir": str(dst), "calibration_path": str(calib)}
    for k in ("objective",):
        if k in entry:
            out[k] = entry[k]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--controls", default="")
    a = ap.parse_args()
    controls = {c for c in a.controls.split(",") if c}
    staged = [stage_one(e, controls) for e in json.loads(Path(a.source).read_text())]
    Path(a.out).write_text(json.dumps(staged, indent=1))
    for s in staged:
        print(s["capture"], s["image_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
