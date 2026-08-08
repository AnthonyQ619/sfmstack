"""FeatureDetectionORB -- scene/v1 -> features/v1.

Oriented FAST + rotated BRIEF, with optional ANMS-SSC spatial suppression.
"""

from __future__ import annotations

import cv2
import numpy as np
from sfmkit import Ctx, module

COVERAGE_GRID = 8


def ssc(keypoints, target: int, tolerance: float, width: int, height: int):
    """Adaptive Non-Maximal Suppression via Square Covering.

    Bailo et al. 2018. Binary-searches a suppression radius such that keeping one
    keypoint per radius-sized cell yields about `target` keypoints, then keeps the
    strongest in each cell.

    This exists because ORB's own selection makes clustering worse, not better:
    OpenCV keeps the highest-response corners, and FAST responds most strongly
    exactly where texture is already dense. A spatially even subset of the same
    size is a strictly better set to match with.
    """
    n = len(keypoints)
    if n <= target:
        return list(range(n))

    xs = np.array([k.pt[0] for k in keypoints], dtype=np.float64)
    ys = np.array([k.pt[1] for k in keypoints], dtype=np.float64)

    # Closed-form bounds on the radius, from the paper: the solution to a
    # quadratic relating the covering radius to the requested count.
    exp1 = height + width + 2 * target
    exp2 = (
        4 * width
        + 4 * target
        + 4 * height * target
        + height * height
        + width * width
        - 2 * height * width
        + 4 * height * width * target
    )
    exp3 = np.sqrt(max(exp2, 0.0))
    exp4 = target - 1
    if abs(exp4) < 1e-9:
        return list(range(min(n, target)))

    low = max((exp1 - exp3) / (4 * exp4), 1.0)
    high = max((exp1 + exp3) / (4 * exp4), low + 1.0)

    best: list[int] | None = None
    for _ in range(64):
        radius = 0.5 * (low + high)
        cell = radius / np.sqrt(2.0)
        if cell < 1e-6:
            break

        cols = int(width / cell) + 1
        rows = int(height / cell) + 1
        taken: dict[int, int] = {}
        for i in range(n):
            c = int(xs[i] / cell)
            r = int(ys[i] / cell)
            taken.setdefault(r * cols + c, i)

        selected = list(taken.values())
        count = len(selected)

        if abs(count - target) <= tolerance * target:
            return selected
        if best is None or abs(count - target) < abs(len(best) - target):
            best = selected

        # Larger radius -> coarser cells -> fewer keypoints.
        if count > target:
            low = radius
        else:
            high = radius
        if high - low < 1e-3:
            break

        del rows  # only cols indexes the cell key

    return best if best is not None else list(range(min(n, target)))


def spatial_coverage(xy: np.ndarray, width: int, height: int) -> float:
    if len(xy) == 0:
        return 0.0
    col = np.clip((xy[:, 0] / width * COVERAGE_GRID).astype(int), 0, COVERAGE_GRID - 1)
    row = np.clip((xy[:, 1] / height * COVERAGE_GRID).astype(int), 0, COVERAGE_GRID - 1)
    return len(np.unique(row * COVERAGE_GRID + col)) / (COVERAGE_GRID**2)


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    p = ctx.params

    paths = scene.load("images", "paths")
    sizes = scene.load("images", "size_current")

    use_ssc = p.suppression == "ssc"
    detect_cap = (
        int(p.max_keypoints * p.detect_multiplier) if use_ssc else p.max_keypoints
    )

    detector = cv2.ORB_create(
        nfeatures=detect_cap,
        scaleFactor=p.scale_factor,
        nlevels=p.n_levels,
        edgeThreshold=p.edge_threshold,
        fastThreshold=p.fast_threshold,
        WTA_K=p.wta_k,
        scoreType=cv2.ORB_HARRIS_SCORE,
    )

    xy_all, idx_all, score_all, scale_all, ori_all, desc_all = [], [], [], [], [], []
    per_image, coverage = [], []
    detected_total, kept_total = 0, 0

    for i, rel in enumerate(paths):
        ctx.progress(i / len(paths), f"detecting {i + 1}/{len(paths)}")
        path = scene.resolve(str(rel))
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise FileNotFoundError(
                f"could not read image {path}. If the scene was built with "
                f"resize: none it references the dataset directly, which must "
                f"then be reachable from here too."
            )

        keypoints = detector.detect(gray, None)
        detected_total += len(keypoints)

        if use_ssc and len(keypoints) > p.max_keypoints:
            # SSC assumes response-sorted input: it keeps the FIRST keypoint it
            # sees per cell, so the ordering is what makes that the strongest one.
            keypoints = sorted(keypoints, key=lambda k: -k.response)
            chosen = ssc(
                keypoints, p.max_keypoints, p.ssc_tolerance,
                int(sizes[i, 0]), int(sizes[i, 1]),
            )
            # SSC hits the target within ssc_tolerance, so it can overshoot. Trim
            # the excess by response rather than letting the count exceed a
            # parameter documented as a cap. Trimming the weakest is spatially
            # benign -- SSC already spread the selection, and what goes is the
            # isolated weak corners rather than a region.
            chosen = sorted(chosen, key=lambda j: -keypoints[j].response)
            keypoints = [keypoints[j] for j in chosen[: p.max_keypoints]]
        elif len(keypoints) > p.max_keypoints:
            keypoints = sorted(keypoints, key=lambda k: -k.response)[: p.max_keypoints]

        keypoints, desc = detector.compute(gray, keypoints)

        if desc is None or not keypoints:
            per_image.append(0)
            coverage.append(0.0)
            continue

        kept_total += len(keypoints)
        xy = np.array([k.pt for k in keypoints], dtype=np.float32)

        xy_all.append(xy)
        idx_all.append(np.full(len(keypoints), i, dtype=np.int32))
        score_all.append(np.array([k.response for k in keypoints], dtype=np.float32))
        scale_all.append(np.array([k.size for k in keypoints], dtype=np.float32))
        ori_all.append(np.array([k.angle for k in keypoints], dtype=np.float32))
        desc_all.append(desc.astype(np.uint8))

        per_image.append(len(keypoints))
        coverage.append(spatial_coverage(xy, int(sizes[i, 0]), int(sizes[i, 1])))

    out = ctx.output("features")

    if not xy_all:
        out.diagnostic(
            "no_keypoints",
            severity="error",
            message="ORB detected nothing in any image.",
            see_also="limitations.md#when-orb-finds-nothing",
        )
        raise ValueError(
            f"ORB detected no keypoints in any of {len(paths)} images at "
            f"fast_threshold={p.fast_threshold}. Lower it toward 5-10, or check "
            f"the images decoded at all. ORB degrades on low texture faster than "
            f"SIFT does."
        )

    out.save(
        "keypoints",
        xy=np.concatenate(xy_all),
        image_index=np.concatenate(idx_all),
        scores=np.concatenate(score_all),
        scale=np.concatenate(scale_all),
        orientation=np.concatenate(ori_all),
    )
    # `binary` is what tells a matcher to use Hamming rather than L2. A uint8
    # descriptor without this flag would be matched under L2 and produce garbage
    # that still looks like matches.
    out.save(
        "descriptors",
        desc=np.concatenate(desc_all),
        binary=np.array(True),
    )

    counts = np.array(per_image)
    mean_kp = float(counts.mean())
    min_kp = int(counts.min())
    saturation = float(np.mean(counts >= p.max_keypoints))
    mean_cov = float(np.mean(coverage))
    ratio = kept_total / max(detected_total, 1)

    out.metric("keypoints_per_image", round(mean_kp, 1),
               direction="higher_better", healthy=(500, None))
    out.metric("keypoints_min", min_kp, direction="higher_better", healthy=(200, None))
    out.metric("saturation", round(saturation, 3), direction="neutral")
    out.metric("spatial_coverage", round(mean_cov, 3),
               direction="higher_better", healthy=(0.35, None))
    out.metric("suppression_ratio", round(ratio, 3), direction="neutral")

    if min_kp < 200:
        worst = int(np.argmin(counts))
        out.diagnostic(
            "starved_frames",
            severity="warn",
            message=(
                f"Image {worst} ({str(scene.load('images', 'names')[worst])}) "
                f"yielded {min_kp} keypoints."
            ),
            suggested_actions=[
                f"Lower fast_threshold below {p.fast_threshold}.",
                "Consider SIFT; ORB degrades faster on low texture.",
            ],
            see_also="tuning.md#keypoints_min-below-200",
        )

    if mean_cov < 0.35:
        out.diagnostic(
            "poor_coverage",
            severity="warn",
            message=(
                f"Keypoints occupy {mean_cov:.0%} of an "
                f"{COVERAGE_GRID}x{COVERAGE_GRID} grid on average."
            ),
            suggested_actions=(
                ["Set suppression: ssc."] if not use_ssc
                else [f"Raise detect_multiplier above {p.detect_multiplier}."]
            ) + [f"Lower fast_threshold below {p.fast_threshold}."],
            see_also="tuning.md#spatial_coverage-below-035",
        )

    if use_ssc and ratio > 0.9:
        out.diagnostic(
            "suppression_ineffective",
            severity="info",
            message=f"Suppression kept {ratio:.0%} of what was detected.",
            suggested_actions=[
                f"Raise detect_multiplier above {p.detect_multiplier}.",
            ],
            see_also="tuning.md#suppression_ratio-near-10",
        )

    mode = f"SSC from {p.detect_multiplier}x" if use_ssc else "response-ranked"
    out.note(
        f"ORB over {len(paths)} images, {mode} selection: {mean_kp:.0f} keypoints "
        f"per image (min {min_kp}), coverage {mean_cov:.2f}, cap binding on "
        f"{saturation:.0%} of frames, suppression kept {ratio:.0%} of "
        f"{detected_total} detections. Descriptors are 32-byte binary; a matcher "
        f"must use Hamming distance, which the `binary` flag signals."
    )
