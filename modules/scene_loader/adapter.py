"""SceneLoader -- dataset directory + calibration -> scene/v1."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from sfmkit import Ctx, module

IMAGE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".ppm", ".pgm", ".webp",
}


def enumerate_images(image_dir: str, pattern: str) -> list[Path]:
    root = Path(image_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"image_dir does not exist or is not a directory: {root}")
    return sorted(
        p for p in root.glob(pattern)
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def subsample(paths: list[Path], n: int | None, how: str) -> list[Path]:
    """Reduce to n images.

    `uniform` spans the trajectory; the predecessor only ever truncated, so a
    capped run saw one end of the capture and its baseline statistics did not
    represent the set.
    """
    if n is None or len(paths) <= n:
        return paths
    if how == "head":
        return paths[:n]
    idx = np.linspace(0, len(paths) - 1, n, dtype=int)
    return [paths[i] for i in idx]


def target_size(w: int, h: int, policy: str, max_edge: int, target) -> tuple[int, int]:
    if policy == "none":
        return w, h

    if policy == "fixed":
        if not target or len(target) != 2:
            raise ValueError("resize: fixed requires target_resolution [width, height]")
        return int(target[0]), int(target[1])

    if policy == "square":
        size = int(target[0]) if target else 1024
        return size, size

    # auto: cap the long edge, preserve aspect
    longest = max(w, h)
    if longest <= max_edge:
        return w, h
    s = max_edge / longest
    return max(1, round(w * s)), max(1, round(h * s))


def render(img: Image.Image, policy: str, out_w: int, out_h: int) -> Image.Image:
    """Produce the working image. `square` pads before scaling, matching the
    letterboxing VGGT-family models expect."""
    if policy == "square":
        w, h = img.size
        side = max(w, h)
        canvas = Image.new("RGB", (side, side), (0, 0, 0))
        canvas.paste(img, ((side - w) // 2, (side - h) // 2))
        img = canvas
    if img.size != (out_w, out_h):
        img = img.resize((out_w, out_h), Image.Resampling.BICUBIC)
    return img


def read_calibration(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Read the .npz convention: k_mats (N,3,3), dists (N,1,5), baseline_ext."""
    with np.load(path, allow_pickle=True) as data:
        K = np.asarray(data["k_mats"], dtype=np.float64)
        dist = np.asarray(data["dists"], dtype=np.float64)
        baseline = data["baseline_ext"] if "baseline_ext" in data else None

    if K.ndim != 3 or K.shape[1:] != (3, 3):
        raise ValueError(f"{path}: k_mats must be (N,3,3), got {K.shape}")

    dist = dist.reshape(dist.shape[0], -1)  # (N,1,5) and (N,5) both occur
    if dist.shape[1] != 5:
        raise ValueError(f"{path}: dists must carry 5 OpenCV coefficients, got {dist.shape}")

    if baseline is not None:
        baseline = np.asarray(baseline.item() if baseline.ndim == 0 else baseline)
        if baseline.dtype == object or baseline.size == 0:
            baseline = None
        else:
            baseline = baseline.astype(np.float64)

    return K, dist, baseline


def scale_intrinsics(K: np.ndarray, scale: tuple[float, float]) -> np.ndarray:
    """Rescale fx, fy, cx, cy to the working resolution.

    Applied once, here. The predecessor mutated the shared calibration object in
    place, so calling it twice silently squared the scale factor.
    """
    sw, sh = scale
    out = K.copy()
    out[:, 0, 0] *= sw
    out[:, 1, 1] *= sh
    out[:, 0, 2] *= sw
    out[:, 1, 2] *= sh
    return out


@module
def run(ctx: Ctx):
    p = ctx.params
    policy = p.resize
    target = p.get("target_resolution")

    paths = subsample(
        enumerate_images(p.image_dir, p.pattern), p.get("max_images"), p.sampling
    )

    out = ctx.output("scene")

    if len(paths) < 2:
        out.diagnostic(
            "too_few_images",
            severity="error",
            message=f"Found {len(paths)} image(s) in {p.image_dir}.",
            see_also="limitations.md#empty-or-near-empty-sets",
        )
        raise ValueError(
            f"SceneLoader found {len(paths)} usable image(s) under "
            f"{p.image_dir!r} matching {p.pattern!r}. At least 2 are needed."
        )

    writing = policy != "none"
    img_dir = out.sidecar_dir("images") if writing else None

    names, out_paths = [], []
    size_original, size_current, scales = [], [], []

    for i, src in enumerate(paths):
        with Image.open(src) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
            w, h = img.size
            ow, oh = target_size(w, h, policy, p.max_edge, target)

            if writing:
                dst = img_dir / f"{i:06d}.png"
                render(img, policy, ow, oh).save(dst)
                out_paths.append(str(Path("data/images") / dst.name))
            else:
                out_paths.append(str(src.resolve()))

        names.append(src.name)
        size_original.append((w, h))
        size_current.append((ow, oh))
        scales.append((ow / w, oh / h))

    size_original = np.array(size_original, dtype=np.int32)
    size_current = np.array(size_current, dtype=np.int32)
    scales = np.array(scales, dtype=np.float64)

    digest = hashlib.sha256()
    for src in paths:
        digest.update(str(src.resolve()).encode())
        digest.update(str(src.stat().st_size).encode())
    digest.update(f"{policy}|{p.max_edge}|{target}".encode())

    out.save(
        "images",
        paths=np.array(out_paths),
        names=np.array(names),
        size_original=size_original,
        size_current=size_current,
        scale=scales,
        content_hash=np.array(digest.hexdigest()[:16]),
    )

    calibration_path = p.get("calibration_path")
    if calibration_path:
        K, dist, baseline = read_calibration(calibration_path)
        # One camera for the whole set: scale by the median, which is exact when
        # resolutions are uniform and the best single answer when they are not.
        median_scale = (float(np.median(scales[:, 0])), float(np.median(scales[:, 1])))
        arrays = {"intrinsics": scale_intrinsics(K, median_scale), "distortions": dist}
        if baseline is not None:
            arrays["baseline"] = baseline
        if K.shape[0] > 1:
            arrays["camera_index"] = np.zeros(len(paths), dtype=np.int32)
        out.save("calibration", **arrays)
    else:
        out.diagnostic(
            "uncalibrated",
            severity="info",
            message="No calibration_path given; the scene carries no intrinsics.",
            see_also="limitations.md#uncalibrated-scenes",
        )

    mixed = len(np.unique(size_original, axis=0)) > 1
    downscale = float(np.median(scales))
    megapixels = float(np.median(size_current[:, 0] * size_current[:, 1]) / 1e6)

    out.metric("n_images", len(paths), direction="neutral")
    out.metric("mixed_resolution", int(mixed), direction="neutral")
    out.metric("downscale_factor", round(downscale, 4), direction="neutral")
    out.metric("megapixels", round(megapixels, 3), direction="neutral")

    if mixed:
        out.diagnostic(
            "mixed_resolution",
            severity="info",
            message=(
                f"{len(np.unique(size_original, axis=0))} distinct source "
                f"resolutions; per-image scale is recorded."
            ),
            see_also="artifact.md#per-image-geometry",
        )

    if downscale < 0.4:
        out.diagnostic(
            "heavy_downscale",
            severity="warn",
            message=f"Median scale {downscale:.2f}; keypoint counts will fall.",
            suggested_actions=["Raise max_edge if downstream detectors are starved."],
            see_also="tuning.md#downscale_factor-below-04",
        )

    res = "mixed" if mixed else f"{size_current[0, 0]}x{size_current[0, 1]}"
    out.note(
        f"Loaded {len(paths)} images from {p.image_dir} at {res} "
        f"(resize={policy}, median scale {downscale:.3f}). "
        f"{'Calibrated.' if calibration_path else 'Uncalibrated.'}"
    )
