"""FeatureDetectionSIFT -- scene/v1 -> features/v1."""

from __future__ import annotations

import cv2
import numpy as np
from sfmkit import Ctx, module

EPS = 1e-7
COVERAGE_GRID = 8  # 8x8 cells over the frame


def root_sift(desc: np.ndarray) -> np.ndarray:
    """L1-normalise then square-root.

    Makes the Euclidean distance between descriptors behave like the Hellinger
    distance between the underlying histograms, which is a strictly better match
    criterion for histogram-like descriptors and costs two vector ops.
    """
    desc = desc / (desc.sum(axis=1, keepdims=True) + EPS)
    return np.sqrt(desc, out=desc)


def spatial_coverage(xy: np.ndarray, width: int, height: int) -> float:
    """Fraction of a coarse grid holding at least one keypoint.

    Counts alone hide clustering, and a thousand keypoints in one corner give a
    degenerate two-view geometry no matter how many there are.
    """
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

    detector = cv2.SIFT_create(
        nfeatures=p.max_keypoints,
        nOctaveLayers=p.n_octave_layers,
        contrastThreshold=p.contrast_threshold,
        edgeThreshold=p.edge_threshold,
        sigma=p.sigma,
    )
    clahe = (
        cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        if p.grayscale_clahe
        else None
    )

    xy_all, idx_all, score_all, scale_all, ori_all, desc_all = [], [], [], [], [], []
    per_image, coverage = [], []

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
        if clahe is not None:
            gray = clahe.apply(gray)

        kps, desc = detector.detectAndCompute(gray, None)

        if desc is None or len(kps) == 0:
            per_image.append(0)
            coverage.append(0.0)
            continue

        xy = np.array([k.pt for k in kps], dtype=np.float32)
        desc = desc.astype(np.float32)
        if p.root_sift:
            desc = root_sift(desc)

        xy_all.append(xy)
        idx_all.append(np.full(len(kps), i, dtype=np.int32))
        score_all.append(np.array([k.response for k in kps], dtype=np.float32))
        scale_all.append(np.array([k.size for k in kps], dtype=np.float32))
        ori_all.append(np.array([k.angle for k in kps], dtype=np.float32))
        desc_all.append(desc)

        per_image.append(len(kps))
        coverage.append(spatial_coverage(xy, int(sizes[i, 0]), int(sizes[i, 1])))

    out = ctx.output("features")

    if not xy_all:
        raise ValueError(
            "SIFT detected no keypoints in any image. The scene is likely "
            "textureless, severely underexposed, or the images failed to decode."
        )

    out.save(
        "keypoints",
        xy=np.concatenate(xy_all),
        image_index=np.concatenate(idx_all),
        scores=np.concatenate(score_all),
        scale=np.concatenate(scale_all),
        orientation=np.concatenate(ori_all),
    )
    out.save("descriptors", desc=np.concatenate(desc_all))

    counts = np.array(per_image)
    mean_kp = float(counts.mean())
    min_kp = int(counts.min())
    saturation = float(np.mean(counts >= p.max_keypoints))
    mean_cov = float(np.mean(coverage))

    out.metric("keypoints_per_image", round(mean_kp, 1),
               direction="higher_better", healthy=(500, None))
    out.metric("keypoints_min", min_kp,
               direction="higher_better", healthy=(200, None))
    out.metric("saturation", round(saturation, 3), direction="neutral")
    out.metric("spatial_coverage", round(mean_cov, 3),
               direction="higher_better", healthy=(0.35, None))

    if min_kp < 200:
        worst = int(np.argmin(counts))
        out.diagnostic(
            "starved_frames",
            severity="warn",
            message=(
                f"Image {worst} ({str(scene.load('images', 'names')[worst])}) "
                f"yielded {min_kp} keypoints; the track chain will break there."
            ),
            suggested_actions=[
                "Lower contrast_threshold toward 0.01.",
                "Enable grayscale_clahe if exposure varies across the set.",
            ],
            see_also="tuning.md#keypoints_min-below-200-while-the-mean-is-healthy",
        )

    if saturation > 0.8:
        out.diagnostic(
            "cap_binding",
            severity="info",
            message=f"{saturation:.0%} of images hit max_keypoints={p.max_keypoints}.",
            suggested_actions=["Raise max_keypoints if track survival is short."],
            see_also="tuning.md#saturation-near-10",
        )

    if mean_cov < 0.35:
        out.diagnostic(
            "poor_coverage",
            severity="warn",
            message=(
                f"Keypoints occupy {mean_cov:.0%} of an "
                f"{COVERAGE_GRID}x{COVERAGE_GRID} grid on average."
            ),
            suggested_actions=[
                "Lower contrast_threshold to reach flatter regions.",
                "Consider a detector-free matcher if large areas are textureless.",
            ],
            see_also="limitations.md#textureless-regions",
        )

    out.note(
        f"SIFT over {len(paths)} images: {mean_kp:.0f} keypoints per image "
        f"(min {min_kp}), coverage {mean_cov:.2f}, "
        f"cap binding on {saturation:.0%} of frames."
    )
