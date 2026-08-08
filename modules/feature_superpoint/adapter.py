"""FeatureDetectionSuperPoint -- scene/v1 -> features/v1.

Learned detector-descriptor. Weights are baked into the image and loaded once by
warmup(), so a warm server pays only inference.
"""

from __future__ import annotations

import cv2
import numpy as np
import torch
from lightglue import SuperPoint
from sfmkit import Ctx, module

COVERAGE_GRID = 8

# Loaded at warmup and reused for every job on this server. Keyed by the
# parameters that change the model's construction, because those cannot be
# changed after instantiation -- everything else is per-call.
_MODELS: dict[tuple, SuperPoint] = {}


def device() -> torch.device:
    """The device this job should use.

    CUDA_VISIBLE_DEVICES is set by the backend when the GPU broker granted a
    lease, so `cuda:0` here is already the leased device. Falling back to CPU
    rather than failing matters more than it looks: a host whose Docker daemon
    lacks the NVIDIA container toolkit has GPUs the container cannot see, and a
    slow result beats no result.
    """
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model(max_keypoints: int, threshold: float, nms_radius: int) -> SuperPoint:
    key = (max_keypoints, threshold, nms_radius)
    if key not in _MODELS:
        _MODELS[key] = (
            SuperPoint(
                max_num_keypoints=max_keypoints,
                detection_threshold=threshold,
                nms_radius=nms_radius,
            )
            .eval()
            .to(device())
        )
    return _MODELS[key]


def warmup() -> None:
    """Pull the weights onto the device before the first job.

    Called by the module server at startup. Without it the first request pays
    model construction and a host-to-device copy, which the duration estimator
    then learns as this module's normal cost.
    """
    get_model(2048, 0.0005, 4)


def load_image(path, long_edge: int | None):
    """Read an image as a (3, H, W) float tensor in [0, 1], plus its scale.

    OpenCV rather than lightglue's own loader so this module needs no Pillow, and
    so the BGR/RGB conversion is explicit rather than implied.
    """
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(
            f"could not read image {path}. If the scene was built with "
            f"resize: none it references the dataset directly, which must then be "
            f"reachable from here too."
        )
    scale = 1.0
    if long_edge:
        h, w = bgr.shape[:2]
        if max(h, w) > long_edge:
            scale = long_edge / max(h, w)
            bgr = cv2.resize(
                bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
            )
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    return tensor, scale


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

    dev = device()
    model = get_model(p.max_keypoints, p.detection_threshold, p.nms_radius)
    long_edge = p.get("resize_long_edge") or None

    xy_all, idx_all, score_all, desc_all = [], [], [], []
    per_image, coverage, scores_mean = [], [], []

    with torch.inference_mode():
        for i, rel in enumerate(paths):
            ctx.progress(i / len(paths), f"detecting {i + 1}/{len(paths)}")

            image, scale = load_image(scene.resolve(str(rel)), long_edge)
            out_dict = model.extract(image.to(dev))

            kp = out_dict["keypoints"][0].cpu().numpy()
            sc = out_dict["keypoint_scores"][0].cpu().numpy()
            desc = out_dict["descriptors"][0].cpu().numpy()

            # Coordinates go back to SCENE pixels whatever resolution inference
            # ran at, so resize_long_edge is invisible to every consumer.
            if scale != 1.0:
                kp = kp / scale

            if len(kp) == 0:
                per_image.append(0)
                coverage.append(0.0)
                scores_mean.append(0.0)
                continue

            xy_all.append(kp.astype(np.float32))
            idx_all.append(np.full(len(kp), i, dtype=np.int32))
            score_all.append(sc.astype(np.float32))
            desc_all.append(desc.astype(np.float32))

            per_image.append(len(kp))
            coverage.append(spatial_coverage(kp, int(sizes[i, 0]), int(sizes[i, 1])))
            scores_mean.append(float(sc.mean()))

    out = ctx.output("features")

    if not xy_all:
        out.diagnostic(
            "no_keypoints",
            severity="error",
            message="SuperPoint detected nothing in any image.",
            see_also="limitations.md#when-superpoint-finds-nothing",
        )
        raise ValueError(
            f"SuperPoint detected no keypoints in any of {len(paths)} images at "
            f"detection_threshold={p.detection_threshold}. Lower it toward 1e-4, "
            f"or check the images decoded and are not blank."
        )

    out.save(
        "keypoints",
        xy=np.concatenate(xy_all),
        image_index=np.concatenate(idx_all),
        scores=np.concatenate(score_all),
    )
    out.save("descriptors", desc=np.concatenate(desc_all))

    counts = np.array(per_image)
    mean_kp = float(counts.mean())
    min_kp = int(counts.min())
    saturation = float(np.mean(counts >= p.max_keypoints))
    mean_cov = float(np.mean(coverage))
    mean_score = float(np.mean(scores_mean))

    out.metric("keypoints_per_image", round(mean_kp, 1),
               direction="higher_better", healthy=(400, None))
    out.metric("keypoints_min", min_kp, direction="higher_better", healthy=(150, None))
    out.metric("saturation", round(saturation, 3), direction="neutral")
    out.metric("spatial_coverage", round(mean_cov, 3),
               direction="higher_better", healthy=(0.35, None))
    out.metric("mean_score", round(mean_score, 5), direction="neutral")

    if min_kp < 150:
        worst = int(np.argmin(counts))
        out.diagnostic(
            "starved_frames",
            severity="warn",
            message=(
                f"Image {worst} ({str(scene.load('images', 'names')[worst])}) "
                f"yielded {min_kp} keypoints."
            ),
            suggested_actions=[
                f"Lower detection_threshold below {p.detection_threshold}.",
                f"Lower nms_radius below {p.nms_radius}.",
            ],
            see_also="tuning.md#keypoints_min-below-150",
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
                f"Raise nms_radius above {p.nms_radius} to force spatial spread.",
                "Lower detection_threshold to reach flatter regions.",
            ],
            see_also="limitations.md#textureless-regions",
        )

    out.note(
        f"SuperPoint on {dev.type} over {len(paths)} images: {mean_kp:.0f} keypoints "
        f"per image (min {min_kp}), coverage {mean_cov:.2f}, cap binding on "
        f"{saturation:.0%} of frames, mean score {mean_score:.4f}. "
        f"Descriptors are 256-d float; LightGlue with features='superpoint' is the "
        f"intended matcher."
        + ("" if dev.type == "cuda" else " NOTE: ran on CPU, which is slow.")
    )
