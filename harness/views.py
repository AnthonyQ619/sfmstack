"""What `sfmx image` hands the agent on a sealed run (P11 scene-information ablation).

On a sealed run (`SFM_SEALED=1`, `launch.py --sealed`) the agent may not read the store, so every
image it looks at is a copy this module writes under the capture's `scratch/views/`, named by an
opaque hash. What the copy is depends on what is withheld (harness/withhold.py):

  frame images (the scene's own frames, the dense workspace's undistorted copies)
      visual        refused
      motion        the scene's frames only, and only under per-run aliases that do not encode the
                    frame's place in the sequence; the listing is a shuffled sample. Real names
                    are refused. The dense workspace's copies are refused.
      illumination  per-frame grey-world white balance, then luminance histogram equalisation
  the contact sheet (SceneDescription)
      illumination or motion   re-rendered here from the browse set: normalised thumbnails, and
                    under motion in shuffled order labelled with the aliases
  coloured cloud renders (`browse/cloud_views.png`)
      visual or illumination   replaced by an uncoloured, depth-shaded render of the same points,
                    for checking geometry

With nothing withheld, a sealed run gets byte-identical copies. The alias key lives in the capture
directory (not scratch), which a sealed agent cannot read.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import re
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

FRAME_RE = re.compile(r"^(images|workspace/images)/[^/]+\.(png|jpe?g)$", re.I)
SHEET = "contact_sheet.jpg"
RENDER = "browse/cloud_views.png"
SAMPLE = 12          # frames listed under motion when no browse set exists yet
THUMB = 384
REFUSE_FRAMES = "Images of the capture's frames are not available on this run."
REFUSE_NAMES = ("On this run frames are opened by the names `sfmx image <scene>` lists, "
                "not by file name.")


class Views:
    def __init__(self, home: Path, store, signals: set[str]):
        self.home, self.store, self.signals = Path(home), store, set(signals)
        self.out = self.home / "scratch" / "views"
        self.keyfile = self.home / ".views_key.json"
        if self.keyfile.exists():
            self.key = json.loads(self.keyfile.read_text())
        else:
            self.key = {"secret": os.urandom(16).hex(), "aliases": {}}
            self._save()

    # ------------------------------------------------------------------ aliases
    def _save(self):
        tmp = self.keyfile.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.key, indent=1))
        os.replace(tmp, self.keyfile)

    def alias(self, scene_id: str, name: str) -> str:
        h = hmac.new(bytes.fromhex(self.key["secret"]), f"{scene_id}:{name}".encode(),
                     hashlib.sha256).hexdigest()[:10]
        a = f"frame_{h}{Path(name).suffix.lower()}"
        if a not in self.key["aliases"]:
            self.key["aliases"][a] = [scene_id, name]
            self._save()
        return a

    def unalias(self, alias: str) -> tuple[str, str] | None:
        v = self.key["aliases"].get(alias)
        return tuple(v) if v else None

    # ------------------------------------------------------------------ helpers
    def _available(self, art) -> list[str]:
        d = art.data_dir.resolve()
        return sorted(str(p.relative_to(d)) for p in d.rglob("*")
                      if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg"))

    def _log(self, **kw):
        with (self.home / ".views_log.jsonl").open("a") as fh:
            fh.write(json.dumps(kw) + "\n")

    def _write(self, img: Image.Image | Path, tag: str, suffix: str) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(f"{self.key['secret']}:{tag}".encode()).hexdigest()[:16] + suffix
        path = self.out / name
        if isinstance(img, Path):
            shutil.copyfile(img, path)
        else:
            img.save(path, quality=90) if suffix == ".jpg" else img.save(path)
        return path

    @staticmethod
    def normalise(img: Image.Image) -> Image.Image:
        """Grey-world white balance, then luminance histogram equalisation, per frame."""
        a = np.asarray(img.convert("RGB"), dtype=np.float64)
        means = a.reshape(-1, 3).mean(0) + 1e-6
        a = np.clip(a * (means.mean() / means), 0, 255).astype(np.uint8)
        y, cb, cr = Image.fromarray(a).convert("YCbCr").split()
        return Image.merge("YCbCr", (ImageOps.equalize(y), cb, cr)).convert("RGB")

    @staticmethod
    def uncoloured(xyz: np.ndarray, w: int = 1800, h: int = 600) -> Image.Image:
        """Three orthographic views along the cloud's principal axes, grey, nearer = lighter."""
        xyz = np.asarray(xyz, dtype=np.float64)
        xyz = xyz[np.isfinite(xyz).all(1)]
        if len(xyz) > 2_000_000:
            xyz = xyz[np.random.default_rng(0).choice(len(xyz), 2_000_000, replace=False)]
        c = np.median(xyz, 0)
        r = np.linalg.norm(xyz - c, axis=1)
        xyz = xyz[r < np.percentile(r, 99)]
        _, _, vt = np.linalg.svd(xyz - xyz.mean(0), full_matrices=False)
        p = (xyz - xyz.mean(0)) @ vt.T                       # principal frame
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        pw = w // 3
        for k, (u, v, d, label) in enumerate(((0, 1, 2, "along axis 3"), (0, 2, 1, "along axis 2"),
                                              (1, 2, 0, "along axis 1"))):
            uv = p[:, [u, v]]
            lo, hi = np.percentile(uv, 0.5, 0), np.percentile(uv, 99.5, 0)
            s = 0.9 * min((pw - 20) / max(hi[0] - lo[0], 1e-9), (h - 40) / max(hi[1] - lo[1], 1e-9))
            px = ((uv - (lo + hi) / 2) * s + [pw / 2, (h - 20) / 2]).astype(int)
            depth = p[:, d]
            ok = (px[:, 0] >= 0) & (px[:, 0] < pw) & (px[:, 1] >= 0) & (px[:, 1] < h - 20)
            px, depth = px[ok], depth[ok]
            zb = np.full((h - 20, pw), -np.inf)
            np.maximum.at(zb, (px[:, 1], px[:, 0]), depth)
            has = np.isfinite(zb)
            panel = np.full((h - 20, pw), 255, np.uint8)
            if has.any():
                z = zb[has]
                t = (z - z.min()) / max(np.ptp(z), 1e-9)
                panel[has] = (40 + 150 * t).astype(np.uint8)
            canvas.paste(Image.fromarray(panel).convert("RGB"), (k * pw, 0))
            draw.text((k * pw + 8, h - 16), label, fill=(60, 60, 60), font=ImageFont.load_default())
        return canvas

    def _sheet(self, desc_art, aliases: bool) -> Image.Image:
        grp = desc_art.load("description") if desc_art.has("description") else {}
        scene_id = desc_art.manifest.scene
        scene = self.store.open(scene_id)
        names = [str(n) for n in scene.load("images", "names")]
        paths = [str(x) for x in scene.load("images", "paths")]
        picked = [str(n) for n in grp["browsed"]] if "browsed" in grp else None
        if picked is None:                                # the un-described sheet: SceneDescription's default browse set
            n = min(int(desc_art.metric("browse_images") or SAMPLE), len(names))
            picked = [names[i] for i in np.linspace(0, len(names) - 1, n, dtype=int)]
        order = list(range(len(picked)))
        if aliases:
            random.Random(self.key["secret"]).shuffle(order)
        thumbs, labels = [], []
        for pos, i in enumerate(order):
            rel = paths[names.index(picked[i])]
            img = Image.open(scene.resolve(rel)).convert("RGB")
            if "illumination" in self.signals:
                img = self.normalise(img)
            img.thumbnail((THUMB, THUMB), Image.Resampling.LANCZOS)
            thumbs.append(img)
            frame = rel[len("data/"):] if rel.startswith("data/") else rel
            labels.append(f"[{pos}] {self.alias(scene_id, frame) if aliases else picked[i]}"[:38])
        cols = 4
        cw, ch = max(t.width for t in thumbs), max(t.height for t in thumbs) + 16
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (cw + 4) + 4, rows * (ch + 4) + 4), (24, 24, 24))
        dr = ImageDraw.Draw(sheet)
        for k, (t, lab) in enumerate(zip(thumbs, labels)):
            x, y = 4 + (k % cols) * (cw + 4), 4 + (k // cols) * (ch + 4)
            sheet.paste(t, (x + (cw - t.width) // 2, y))
            dr.text((x + 2, y + t.height + 2), lab, fill=(210, 210, 210), font=ImageFont.load_default())
        return sheet

    # ------------------------------------------------------------------ the call
    def listing(self, art) -> list[str]:
        avail = self._available(art)
        frames = [a for a in avail if FRAME_RE.match(a)]
        others = [a for a in avail if a not in frames]
        if "visual" in self.signals:
            return others
        if "motion" in self.signals:
            if art.type.startswith("scene/"):
                sample = sorted(frames)
                if len(sample) > SAMPLE:
                    sample = random.Random(self.key["secret"] + art.id).sample(sample, SAMPLE)
                al = [self.alias(art.id, f) for f in sample]
                random.Random(self.key["secret"]).shuffle(al)
                return others + al
            return others
        return avail

    def serve(self, artifact_id: str, name: str = "") -> dict:
        signals = self.signals
        hit = self.unalias(name) if name.startswith("frame_") else None
        if hit:
            artifact_id, name = hit
        art = self.store.open(artifact_id)
        if not name:
            imgs = self.listing(art)
            if len(imgs) != 1:
                return {"artifact": art.id, "type": art.type, "images": imgs,
                        "hint": f"{len(imgs)} images; pass one as `name`." if imgs
                        else "this artifact carries no images on this run."}
            return self.serve(artifact_id, imgs[0])
        src = (art.data_dir / name).resolve()
        if not src.is_relative_to(art.data_dir.resolve()) or not src.is_file():
            raise SystemExit(f"artifact {art.id} has no image '{name}'. Available: {self.listing(art)}")
        is_frame = bool(FRAME_RE.match(name))
        if is_frame:
            if "visual" in signals:
                raise SystemExit(REFUSE_FRAMES)
            if "motion" in signals:
                if not hit:
                    raise SystemExit(REFUSE_NAMES)
                if not art.type.startswith("scene/"):
                    raise SystemExit(REFUSE_FRAMES)
            shown = self.alias(art.id, name) if "motion" in signals else name
            self._log(artifact=art.id, name=name, kind="frame",
                      transform="normalised" if "illumination" in signals else "copy")
            if "illumination" in signals:
                path = self._write(self.normalise(Image.open(src)), f"{art.id}:{name}:norm", ".png")
            else:
                path = self._write(src, f"{art.id}:{name}", src.suffix.lower())
            return {"artifact": art.id, "type": art.type, "name": shown, "path": str(path),
                    "mime_type": "image/png" if path.suffix == ".png" else "image/jpeg"}
        if name.endswith(SHEET) and ({"illumination", "motion"} & signals):
            if "visual" in signals:
                raise SystemExit(REFUSE_FRAMES)
            path = self._write(self._sheet(art, "motion" in signals), f"{art.id}:sheet", ".jpg")
            self._log(artifact=art.id, name=name, kind="sheet",
                      transform="+".join(t for t, on in (("normalised", "illumination" in signals),
                                                         ("shuffled", "motion" in signals)) if on))
        elif name.endswith(SHEET) and "visual" in signals:
            raise SystemExit(REFUSE_FRAMES)
        elif name == RENDER and ({"visual", "illumination"} & signals):
            xyz = np.asarray(art.load("points")["xyz"])
            path = self._write(self.uncoloured(xyz), f"{art.id}:render", ".png")
            self._log(artifact=art.id, name=name, kind="render", transform="uncoloured")
        else:
            path = self._write(src, f"{art.id}:{name}", src.suffix.lower())
            self._log(artifact=art.id, name=name, kind="sheet" if name.endswith(SHEET) else
                      "render" if name == RENDER else "other", transform="copy")
        return {"artifact": art.id, "type": art.type, "name": name, "path": str(path),
                "mime_type": "image/png" if path.suffix == ".png" else "image/jpeg"}

    def alias_text(self, obj, scene_ids: set[str]):
        """Under motion: every frame name of these scenes, in SceneDescription's answers, as its alias."""
        if "motion" not in self.signals or not scene_ids:
            return obj
        pat = re.compile(r"(?:data/)?images/[^\s'\"/,\]]+\.(?:png|jpe?g)", re.I)

        def sub(s: str) -> str:
            def one(m):
                n = m.group(0)
                n = n[len("data/"):] if n.startswith("data/") else n
                return self.alias(next(iter(scene_ids)), n)
            return pat.sub(one, s)

        def walk(x):
            if isinstance(x, dict):
                return {k: walk(v) for k, v in x.items()}
            if isinstance(x, list):
                return [walk(v) for v in x]
            if isinstance(x, str):
                return sub(x)
            return x
        return walk(obj)
