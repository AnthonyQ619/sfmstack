"""SceneTriage -- scene/v1 -> scene_analysis/v1. CPU only.

The photometric block is a port of the predecessor's `illumination_analysis.py`.
The measurements and their weights are carried over unchanged so numbers remain
comparable across the two systems; what changed is the output. That version
returned a pre-formatted English paragraph with LOW/MEDIUM/HIGH labels baked in,
and named specific modules in its recommendations. This one writes numbers into
the artifact, leaves the prose to `artifact.md`, and names capabilities the
registry can resolve rather than modules that may be gone.

Texture and metadata are new. They exist because the photometric block answers
"does this scene look the same twice" and says nothing about "is there anything
here to match", which is the other half of whether a detector-based pipeline has
a chance.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from sfmkit import Ctx, module

# Local-standard-deviation window for the textureless test, in analysis-resolution
# pixels. Small enough to see through a window frame, large enough that sensor
# noise on a flat wall does not register as texture.
STD_WINDOW = 8

# Corner detector settings for texture_density. Fixed rather than exposed: the
# metric is a comparison across scenes, and a threshold the caller can move is not
# one.
CORNER_MAX = 8000
CORNER_QUALITY = 0.01
CORNER_MIN_DISTANCE = 8

EXIF_DATETIME_ORIGINAL = 36867
EXIF_FOCAL_35MM = 41989


# --------------------------------------------------------------------------- #
# Per-image measurement
# --------------------------------------------------------------------------- #


def _norm_hist(hist: np.ndarray) -> np.ndarray:
    hist = hist.astype(np.float32)
    total = hist.sum()
    return hist if total <= 1e-8 else hist / total


def image_stats(bgr: np.ndarray) -> dict:
    """Photometric and texture measurements for one image.

    LAB rather than RGB because the L channel is a perceptual luminance and the
    a/b channels are chroma with luminance already removed -- which is what lets
    "the sun moved" and "the white balance drifted" be separated at all.
    """
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0].astype(np.float32)
    A = lab[:, :, 1].astype(np.float32)
    B = lab[:, :, 2].astype(np.float32)

    chroma = np.sqrt((A - 128.0) ** 2 + (B - 128.0) ** 2)

    return {
        "mean_luminance": float(L.mean() / 255.0),
        "median_luminance": float(np.median(L) / 255.0),
        "std_luminance": float(L.std() / 255.0),
        # Clipping is counted separately from brightness: a region at 0 or 255 has
        # lost its detail permanently, where a merely dark region has not.
        "shadow_clip": float(np.mean(L <= 5)),
        "highlight_clip": float(np.mean(L >= 250)),
        "mean_a": float((A.mean() - 128.0) / 127.0),
        "mean_b": float((B.mean() - 128.0) / 127.0),
        "colorfulness": float(chroma.mean() / 181.0),  # 181 ~= sqrt(127^2 + 127^2)
        "lum_hist": _norm_hist(
            cv2.calcHist([lab], [0], None, [64], [0, 256])
        ),
        "ab_hist": _norm_hist(
            cv2.calcHist([lab], [1, 2], None, [32, 32], [0, 256, 0, 256])
        ),
    }


def texture_stats(gray: np.ndarray, floor: float) -> dict:
    """Texture measurements for one image, at the analysis resolution."""
    g = gray.astype(np.float32)

    # Local standard deviation via box filters: E[x^2] - E[x]^2 over a sliding
    # window. Two convolutions rather than a per-pixel loop.
    mean = cv2.boxFilter(g, -1, (STD_WINDOW, STD_WINDOW), normalize=True)
    mean_sq = cv2.boxFilter(g * g, -1, (STD_WINDOW, STD_WINDOW), normalize=True)
    local_std = np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))

    corners = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=CORNER_MAX,
        qualityLevel=CORNER_QUALITY,
        minDistance=CORNER_MIN_DISTANCE,
    )
    megapixels = gray.size / 1e6

    return {
        "textureless": float(np.mean(local_std < floor)),
        "density": float((0 if corners is None else len(corners)) / megapixels),
        # Laplacian variance: the classical no-reference focus measure. Absolute
        # values mean little across scenes, which is why only the ratio to this
        # set's own median is reported as a metric.
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
    }


# --------------------------------------------------------------------------- #
# Pairwise photometric change
# --------------------------------------------------------------------------- #


def pair_change(a: dict, b: dict) -> dict:
    """Weighted change scores between two images.

    Weights carried over from the predecessor unchanged. They are a judgement
    about what matters, not a derivation, and they are here rather than exposed
    as parameters because a score whose weights move is not comparable across
    scenes -- which is the only thing this score is for.
    """
    d_mean = abs(a["mean_luminance"] - b["mean_luminance"])
    d_median = abs(a["median_luminance"] - b["median_luminance"])
    d_std = abs(a["std_luminance"] - b["std_luminance"])
    d_shadow = abs(a["shadow_clip"] - b["shadow_clip"])
    d_highlight = abs(a["highlight_clip"] - b["highlight_clip"])

    # Bhattacharyya distance, already in [0, 1] and comparing distribution SHAPE
    # rather than moments -- so a scene that gained a bright window scores high
    # here even when its mean is unchanged.
    lum_dist = float(
        cv2.compareHist(a["lum_hist"], b["lum_hist"], cv2.HISTCMP_BHATTACHARYYA)
    )
    color_dist = float(
        cv2.compareHist(a["ab_hist"], b["ab_hist"], cv2.HISTCMP_BHATTACHARYYA)
    )

    wb = np.array([a["mean_a"] - b["mean_a"], a["mean_b"] - b["mean_b"]])
    wb_shift = float(np.clip(np.linalg.norm(wb) / np.sqrt(2.0), 0.0, 1.0))

    illumination = 0.35 * d_mean + 0.25 * d_median + 0.15 * d_std + 0.25 * lum_dist
    color = 0.65 * color_dist + 0.35 * wb_shift
    exposure = 0.45 * d_mean + 0.25 * d_shadow + 0.25 * d_highlight + 0.05 * d_std

    return {
        "illumination": float(illumination),
        "color": float(color),
        "exposure": float(exposure),
        "combined": float(0.45 * illumination + 0.35 * color + 0.20 * exposure),
    }


def choose_pairs(n: int, pairing: str, cap: int) -> list[tuple[int, int]]:
    if pairing == "consecutive":
        return [(i, i + 1) for i in range(n - 1)]
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(pairs) <= cap:
        return pairs
    # Uniform subsample rather than a prefix: the first `cap` pairs of an
    # exhaustive list are all pairs involving image 0, which measures one image.
    idx = np.linspace(0, len(pairs) - 1, cap, dtype=int)
    return [pairs[i] for i in idx]


# --------------------------------------------------------------------------- #
# Self-similarity
# --------------------------------------------------------------------------- #


def repetitiveness(gray: np.ndarray, n_patches: int, size: int) -> list[float]:
    """For each sampled patch, the best correlation it achieves elsewhere.

    Patches are taken at corners rather than at random, because the question is
    about the locations a detector will actually fire on. A patch of blank sky
    correlating with other blank sky is not what defeats matching; a window that
    looks exactly like sixteen other windows is.
    """
    h, w = gray.shape
    half = size // 2
    if h < 3 * size or w < 3 * size:
        return []

    corners = cv2.goodFeaturesToTrack(
        gray, maxCorners=n_patches * 4, qualityLevel=0.01, minDistance=size
    )
    if corners is None:
        return []

    scores = []
    for x, y in corners.reshape(-1, 2)[: n_patches * 4]:
        cx, cy = int(round(x)), int(round(y))
        if not (half <= cx < w - half and half <= cy < h - half):
            continue

        patch = gray[cy - half:cy + half, cx - half:cx + half]
        if patch.std() < 1.0:  # flat patch correlates with everything; uninformative
            continue

        response = cv2.matchTemplate(gray, patch, cv2.TM_CCOEFF_NORMED)

        # Suppress the patch's own location and its immediate surroundings. Without
        # this the answer is 1.0 everywhere, and with too small a radius a patch
        # correlates with itself shifted by two pixels.
        rh, rw = response.shape
        tx, ty = cx - half, cy - half
        x0, x1 = max(0, tx - size), min(rw, tx + size + 1)
        y0, y1 = max(0, ty - size), min(rh, ty + size + 1)
        response[y0:y1, x0:x1] = -1.0

        scores.append(float(response.max()))
        if len(scores) >= n_patches:
            break

    return scores


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #


def trailing_number(name: str) -> int | None:
    digits = ""
    for ch in reversed(Path(name).stem):
        if ch.isdigit():
            digits = ch + digits
        elif digits:
            break
    return int(digits) if digits else None


def filenames_are_ordered(names) -> bool:
    """Whether the filenames carry a capture index.

    A heuristic, and named as one in limitations.md. `0001.jpg .. 0040.jpg` and
    `DSC_0287.JPG .. DSC_0326.JPG` both pass; an internet collection of
    `eiffel_tower_by_jane.jpg` does not. The density test is what separates a
    capture sequence from filenames that merely happen to contain a number.
    """
    numbers = [trailing_number(str(n)) for n in names]
    if any(v is None for v in numbers):
        return False
    if any(b <= a for a, b in zip(numbers, numbers[1:])):
        return False
    span = numbers[-1] - numbers[0] + 1
    return span <= 4 * len(numbers)


def read_exif(source_dir: str, names) -> tuple[list, list]:
    """(timestamps in seconds, focal lengths in 35mm equivalent), best effort."""
    from datetime import datetime

    from PIL import Image

    times, focals = [], []
    for name in names:
        path = Path(source_dir) / str(name)
        if not path.exists():
            continue
        try:
            with Image.open(path) as img:
                exif = img.getexif()
        except Exception:
            continue
        raw = exif.get(EXIF_DATETIME_ORIGINAL)
        if raw:
            try:
                times.append(datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").timestamp())
            except ValueError:
                pass
        focal = exif.get(EXIF_FOCAL_35MM)
        if focal:
            focals.append(float(focal))
    return times, focals


# --------------------------------------------------------------------------- #


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    p = ctx.params

    paths = scene.load("images", "paths")
    names = [str(n) for n in scene.load("images", "names")]
    n = len(paths)

    stats, texture, sharpness, grays = [], [], [], []

    for i, rel in enumerate(paths):
        ctx.progress(i / n, f"measuring {i + 1}/{n}")
        path = scene.resolve(str(rel))
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise FileNotFoundError(
                f"could not read image {path}. If the scene was built with "
                f"resize: none it references the dataset directly, which must "
                f"then be reachable from here too."
            )

        h, w = bgr.shape[:2]
        scale = p.analysis_max_side / max(h, w)
        if scale < 1.0:
            bgr = cv2.resize(
                bgr, (max(1, round(w * scale)), max(1, round(h * scale))),
                interpolation=cv2.INTER_AREA,
            )

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        stats.append(image_stats(bgr))
        t = texture_stats(gray, p.texture_floor)
        texture.append(t)
        sharpness.append(t["sharpness"])
        grays.append(gray)

    # ------------------------------------------------------------ photometric
    pairs = choose_pairs(n, p.pairing, p.max_pairs)
    changes = [pair_change(stats[i], stats[j]) for i, j in pairs]

    def p75(key: str) -> float:
        # p75 rather than mean or max: one bad pair in forty is a frame to drop,
        # where a quarter of pairs being bad is a property of the capture. The
        # mean hides the first and the max cannot tell them apart.
        return float(np.percentile([c[key] for c in changes], 75))

    illumination = p75("illumination")
    color = p75("color")
    exposure = p75("exposure")
    combined = p75("combined")

    # --------------------------------------------------------------- texture
    sample = np.linspace(0, n - 1, min(p.repetitiveness_images, n), dtype=int)
    repeat_scores: list[float] = []
    for k, i in enumerate(sample):
        ctx.progress(k / len(sample), f"self-similarity {k + 1}/{len(sample)}")
        repeat_scores += repetitiveness(grays[i], p.repetitiveness_patches, p.patch_size)

    repeat = float(np.median(repeat_scores)) if repeat_scores else None
    density = float(np.median([t["density"] for t in texture]))
    textureless = float(np.median([t["textureless"] for t in texture]))

    sharp = np.array(sharpness, dtype=np.float64)
    median_sharp = float(np.median(sharp))
    sharp_ratio = float(sharp.min() / median_sharp) if median_sharp > 0 else 0.0

    # -------------------------------------------------------------- metadata
    times, focals = ([], [])
    source_dir = p.get("source_dir")
    if source_dir:
        times, focals = read_exif(source_dir, names)

    ordered = (
        bool(np.all(np.diff(times) > 0)) if len(times) == n
        else filenames_are_ordered(names)
    )

    # ----------------------------------------------------------------- write
    out = ctx.output("analysis")

    metadata = {"n_images": np.int64(n), "ordered": np.bool_(ordered)}
    if len(times) >= 2:
        metadata["capture_interval_s"] = float(np.median(np.diff(sorted(times))))
    if len(focals) == n:
        metadata["focal_35mm"] = np.asarray(focals, dtype=np.float64)
    out.save("metadata", **metadata)

    out.save(
        "photometric",
        illumination_change=illumination,
        color_shift=color,
        exposure_shift=exposure,
        combined_change=combined,
        # Extra, and recorded as such: the per-pair series behind the p75, so a
        # caller can ask WHERE the instability is rather than only how much.
        pair_index=np.asarray(pairs, dtype=np.int32),
        pair_combined=np.asarray([c["combined"] for c in changes], dtype=np.float64),
    )

    tex = {
        "density": density,
        "textureless_fraction": textureless,
        "sharpness": sharp,
    }
    if repeat is not None:
        tex["repetitiveness"] = repeat
    out.save("texture", **tex)

    out.metric("illumination_change", round(illumination, 4),
               direction="lower_better", healthy=(None, 0.12))
    out.metric("color_shift", round(color, 4),
               direction="lower_better", healthy=(None, 0.12))
    out.metric("exposure_shift", round(exposure, 4),
               direction="lower_better", healthy=(None, 0.12))
    out.metric("combined_change", round(combined, 4),
               direction="lower_better", healthy=(None, 0.12))
    out.metric("texture_density", round(density, 1),
               direction="higher_better", healthy=(400.0, None))
    out.metric("repetitiveness", None if repeat is None else round(repeat, 4),
               direction="lower_better", healthy=(None, 0.75))
    out.metric("textureless_fraction", round(textureless, 4),
               direction="lower_better", healthy=(None, 0.35))
    out.metric("sharpness_ratio", round(sharp_ratio, 4),
               direction="higher_better", healthy=(0.4, None))
    out.metric("ordered", int(ordered), direction="neutral")

    # ----------------------------------------------------------- diagnostics
    if combined > 0.28:
        worst = int(np.argmax([c["combined"] for c in changes]))
        i, j = pairs[worst]
        out.diagnostic(
            "illumination_unstable",
            severity="warn",
            message=(
                f"combined_change {combined:.3f} at p75 over {len(pairs)} pairs "
                f"(illumination {illumination:.3f}, colour {color:.3f}, exposure "
                f"{exposure:.3f}). Worst pair: {names[i]} / {names[j]}."
            ),
            suggested_actions=[
                "Read the three components separately; the fix differs per cause.",
                "For luminance drift, normalise exposure at detection before changing family.",
                "If inlier_ratio confirms it, resolve a detector-free matcher with "
                "sfm_find_alternatives(produces='pairwise_matches/v1', "
                "not_consuming='features/v1').",
            ],
            see_also="tuning.md#combined_change-above-028",
        )

    # 0.80 rather than the band's 0.75: a warn that fires on most scenes is noise,
    # and the ten-scene sample runs 0.62-0.81 with no gap in it. This trips on the
    # top of that range only, and the message carries the number so the reader can
    # judge a borderline case rather than trusting the cut.
    if repeat is not None and repeat > 0.80:
        out.diagnostic(
            "repetitive_texture",
            severity="warn",
            message=(
                f"Median patch correlates at {repeat:.2f} with a DIFFERENT location "
                f"in its own image, over {len(repeat_scores)} patches at "
                f"{p.patch_size}px."
            ),
            suggested_actions=[
                "Expect confident wrong matches, not missing ones: watch inlier_ratio.",
                "No ratio-test threshold recovers from this; it is a capability choice.",
                "Resolve a globally-reasoning matcher with "
                "sfm_find_alternatives(produces='pairwise_matches/v1').",
            ],
            see_also="limitations.md#repetitive-structure",
        )

    if textureless > 0.35:
        out.diagnostic(
            "textureless",
            severity="warn",
            message=(
                f"{textureless:.0%} of the median frame is below the texture floor; "
                f"corner density {density:.0f}/MP."
            ),
            suggested_actions=[
                "Watch spatial_coverage on features/v1, not keypoint count.",
                "A detector-free matcher does not need a keypoint to exist first.",
            ],
            see_also="limitations.md#textureless-scenes",
        )

    if sharp_ratio < 0.4:
        blurred = [names[k] for k in np.argsort(sharp)[:3] if sharp[k] < 0.4 * median_sharp]
        out.diagnostic(
            "blurred_frames",
            severity="warn",
            message=(
                f"Sharpest-to-worst spread: worst frame is {sharp_ratio:.2f}x the "
                f"set median. Softest: {', '.join(blurred)}."
            ),
            suggested_actions=[
                "These frames are candidates for exclusion; re-run SceneLoader without them.",
                "A soft frame usually fails to register rather than corrupting the model.",
            ],
            see_also="tuning.md#sharpness_ratio-below-04",
        )

    if not ordered:
        out.diagnostic(
            "unordered_capture",
            severity="info",
            message="Filenames do not form a capture sequence.",
            suggested_actions=[
                "Sequential pairing is not valid; use exhaustive or retrieval pairing.",
                "A video-trained tracker takes image order as real input; prefer one that does not.",
            ],
            see_also="limitations.md#order-is-inferred-from-filenames",
        )

    if not times:
        out.diagnostic(
            "exif_unavailable",
            severity="info",
            message=(
                "No EXIF timestamps read; capture_interval_s and focal_35mm omitted."
                + ("" if source_dir else " source_dir was not supplied.")
            ),
            suggested_actions=[
                "Expected when the scene applied a resize policy, which re-encodes and drops EXIF.",
                "Pass source_dir pointing at the original images to recover it.",
            ],
            see_also="limitations.md#exif-does-not-survive-the-scene-artifact",
        )

    out.note(
        f"Triage over {n} images ({len(pairs)} pairs, {p.pairing}). "
        f"Photometric: combined {combined:.3f} "
        f"(illumination {illumination:.3f}, colour {color:.3f}, exposure {exposure:.3f}). "
        f"Texture: {density:.0f} corners/MP, {textureless:.0%} textureless, "
        f"repetitiveness {'n/a' if repeat is None else f'{repeat:.2f}'}. "
        f"Sharpness ratio {sharp_ratio:.2f}. "
        f"{'Ordered' if ordered else 'UNORDERED'} capture."
    )
