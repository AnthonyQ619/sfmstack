"""FeatureMatchLoFTR -- scene/v1 -> pairwise_matches/v1.

Detector-free matching. Consumes IMAGES, not features -- there is no keypoint
detection stage at all, which is the entire point: a textureless region has no
repeatable interest point, and LoFTR does not need one.

The output therefore carries NO `feature_index`, and its absence is the signal the
tracker branches on to merge endpoints by proximity instead of by identity.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
import torch
from sfmkit import Ctx, module

MIN_FOR_FUNDAMENTAL = 8
MIN_FOR_HOMOGRAPHY = 4

_MODELS: dict[str, object] = {}


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model(setting: str):
    if setting not in _MODELS:
        import kornia.feature as KF

        _MODELS[setting] = KF.LoFTR(pretrained=setting).eval().to(device())
    return _MODELS[setting]


def warmup() -> None:
    get_model("outdoor")


def load_gray(path, long_edge: int | None):
    """Grayscale (1, 1, H, W) float tensor in [0, 1], plus the scale applied.

    LoFTR is fully convolutional over an 8x8 coarse grid, so both dimensions must
    be divisible by 8. Padding rather than resizing to reach that, because a
    resize changes the coordinates and a pad does not.
    """
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(
            f"could not read image {path}. If the scene was built with "
            f"resize: none it references the dataset directly, which must then be "
            f"reachable from here too."
        )
    scale = 1.0
    if long_edge:
        h, w = gray.shape
        if max(h, w) > long_edge:
            scale = long_edge / max(h, w)
            gray = cv2.resize(
                gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
            )

    h, w = gray.shape
    pad_h, pad_w = (-h) % 8, (-w) % 8
    if pad_h or pad_w:
        gray = cv2.copyMakeBorder(gray, 0, pad_h, 0, pad_w, cv2.BORDER_REPLICATE)

    tensor = torch.from_numpy(gray).float()[None, None] / 255.0
    return tensor, scale, (h, w)


def verify(xy_a, xy_b, model, thresh, conf):
    if model == "none":
        return np.ones(len(xy_a), dtype=bool)
    floor = MIN_FOR_HOMOGRAPHY if model == "homography" else MIN_FOR_FUNDAMENTAL
    if len(xy_a) < floor:
        return np.zeros(len(xy_a), dtype=bool)
    if model == "homography":
        _, mask = cv2.findHomography(
            xy_a, xy_b, cv2.USAC_MAGSAC,
            ransacReprojThreshold=thresh, maxIters=10000, confidence=conf,
        )
    else:
        _, mask = cv2.findFundamentalMat(
            xy_a, xy_b, cv2.USAC_MAGSAC,
            ransacReprojThreshold=thresh, maxIters=10000, confidence=conf,
        )
    if mask is None:
        return np.zeros(len(xy_a), dtype=bool)
    return mask.ravel().astype(bool)


def homography_share(xy_a, xy_b, thresh, conf, n_inliers):
    if n_inliers <= 0 or len(xy_a) < MIN_FOR_HOMOGRAPHY:
        return None
    _, mask = cv2.findHomography(
        xy_a, xy_b, cv2.USAC_MAGSAC,
        ransacReprojThreshold=thresh, maxIters=10000, confidence=conf,
    )
    if mask is None:
        return 0.0
    return min(1.0, float(mask.sum()) / float(n_inliers))


def connected_components(n_images, edges):
    parent = list(range(n_images))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    sizes: dict[int, int] = {}
    for i in range(n_images):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    return sorted(sizes.values(), reverse=True)


def build_view_graph(n_images: int, pairing: str, window: int):
    if pairing == "exhaustive":
        return list(itertools.combinations(range(n_images), 2))
    return [
        (i, j)
        for i in range(n_images)
        for j in range(i + 1, min(i + window + 1, n_images))
    ]


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    p = ctx.params

    paths = scene.load("images", "paths")
    names = scene.load("images", "names")
    n_images = len(names)

    dev = device()
    model = get_model(p.setting)
    long_edge = p.get("resize_long_edge") or None

    graph = build_view_graph(n_images, p.pairing, p.window)
    if not graph:
        raise ValueError(
            f"the view graph is empty: {n_images} image(s) with "
            f"pairing={p.pairing!r}, window={p.window}. At least 2 are needed."
        )

    # Decoded images are cached across the pairs each one appears in. With
    # exhaustive pairing an image is in N-1 pairs, so decoding per pair would
    # dominate; the cost is holding the whole set in memory as float tensors.
    cache: dict[int, tuple] = {}

    def image_for(i):
        if i not in cache:
            cache[i] = load_gray(scene.resolve(str(paths[i])), long_edge)
        return cache[i]

    kept_pairs = []
    xy_blocks, pair_idx_blocks, conf_blocks = [], [], []
    raw_counts, raw_kept, inlier_counts, planarity, scores = [], [], [], [], []
    weak_pairs = 0

    with torch.inference_mode():
        for step, (i, j) in enumerate(graph):
            ctx.progress(step / len(graph), f"matching {step + 1}/{len(graph)} pairs")

            t0, s0, _ = image_for(i)
            t1, s1, _ = image_for(j)

            out_dict = model({"image0": t0.to(dev), "image1": t1.to(dev)})
            kp0 = out_dict["keypoints0"].cpu().numpy()
            kp1 = out_dict["keypoints1"].cpu().numpy()
            confidence = out_dict["confidence"].cpu().numpy()

            keep = confidence >= p.min_confidence
            kp0, kp1, confidence = kp0[keep], kp1[keep], confidence[keep]

            if p.max_matches and len(kp0) > p.max_matches:
                best = np.argsort(-confidence)[: p.max_matches]
                kp0, kp1, confidence = kp0[best], kp1[best], confidence[best]

            # Back to SCENE pixels. Padding was bottom/right only, so padded
            # coordinates need no shift -- but a resize does need undoing.
            if s0 != 1.0:
                kp0 = kp0 / s0
            if s1 != 1.0:
                kp1 = kp1 / s1

            raw_counts.append(len(kp0))
            if len(kp0) < p.min_matches:
                weak_pairs += 1
                continue

            mask = verify(
                kp0.astype(np.float32), kp1.astype(np.float32),
                p.geometric_model, p.ransac_threshold, p.ransac_confidence,
            )
            n_in = int(mask.sum())
            if n_in < p.min_matches:
                weak_pairs += 1
                continue

            if p.measure_planarity and p.geometric_model != "homography":
                share = homography_share(
                    kp0[mask].astype(np.float32), kp1[mask].astype(np.float32),
                    p.ransac_threshold, p.ransac_confidence, n_in,
                )
                if share is not None:
                    planarity.append(share)

            pair_row = len(kept_pairs)
            kept_pairs.append((i, j))
            inlier_counts.append(n_in)
            raw_kept.append(len(kp0))
            scores.append(float(confidence[mask].mean()))

            xy_blocks.append(np.hstack([kp0[mask], kp1[mask]]).astype(np.float32))
            pair_idx_blocks.append(np.full(n_in, pair_row, np.int32))
            conf_blocks.append(confidence[mask].astype(np.float32))

    if not kept_pairs:
        best_raw = max(raw_counts) if raw_counts else 0
        raise ValueError(
            f"no image pair survived matching: {len(graph)} attempted, best raw "
            f"match count {best_raw}, min_confidence={p.min_confidence}, "
            f"min_matches={p.min_matches}, setting '{p.setting}'. Lower "
            f"min_confidence toward 0.2 first, and check `setting` matches the "
            f"scene -- indoor and outdoor are separately trained models."
        )

    out = ctx.output("matches")
    out.save("pairs", image_pair=np.array(kept_pairs, np.int32))
    # No feature_index: there is no keypoint table to cite. Its absence is what
    # tells the tracker to merge endpoints by proximity instead of by identity.
    out.save(
        "matches",
        xy=np.concatenate(xy_blocks),
        pair_index=np.concatenate(pair_idx_blocks),
        confidence=np.concatenate(conf_blocks),
    )

    inliers = np.array(inlier_counts, dtype=float)
    raw = np.maximum(np.array(raw_kept, dtype=float), 1.0)
    mean_matches = float(inliers.mean())
    ratio = float(np.mean(inliers / raw))
    components = connected_components(n_images, kept_pairs)
    mean_planarity = float(np.mean(planarity)) if planarity else None
    mean_score = float(np.mean(scores))

    out.metric("pairs_matched", len(kept_pairs),
               direction="higher_better", healthy=(1, None))
    out.metric("matches_per_pair", round(mean_matches, 1),
               direction="higher_better", healthy=(200, None))
    out.metric("min_matches_per_pair", int(inliers.min()),
               direction="higher_better", healthy=(50, None))
    out.metric("inlier_ratio", round(ratio, 3),
               direction="higher_better", healthy=(0.6, None))
    out.metric("graph_components", len(components),
               direction="lower_better", healthy=(None, 1))
    out.metric("largest_component_fraction", round(components[0] / n_images, 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("weak_pairs", weak_pairs, direction="lower_better", healthy=(None, 0))
    out.metric("planarity",
               None if mean_planarity is None else round(mean_planarity, 3),
               direction="lower_better")
    out.metric("mean_match_score", round(mean_score, 3),
               direction="higher_better", healthy=(0.4, None))

    if len(components) > 1:
        out.diagnostic(
            "broken_chain",
            severity="error",
            message=(
                f"The view graph has {len(components)} components "
                f"(sizes {components[:5]}); only {components[0]}/{n_images} images "
                f"can end up in one model."
            ),
            suggested_actions=[
                f"Raise window above {p.window}, or use pairing: exhaustive.",
                "Lower min_confidence toward 0.2.",
            ],
            see_also="tuning.md#graph_components-above-1",
        )

    if ratio < 0.4:
        out.diagnostic(
            "low_inlier_ratio",
            severity="warn",
            message=f"Only {ratio:.0%} of matches agreed with the {p.geometric_model} model.",
            suggested_actions=[
                f"Raise min_confidence above {p.min_confidence}.",
                f"Check `setting` -- '{p.setting}' is a separately trained model.",
            ],
            see_also="tuning.md#inlier_ratio-below-04",
        )

    if mean_planarity is not None and mean_planarity > 0.9:
        out.diagnostic(
            "degenerate_geometry",
            severity="warn",
            message=(
                f"A homography recovers {mean_planarity:.0%} of the fundamental "
                f"matrix's inliers; these pairs are planar or rotation-only."
            ),
            suggested_actions=[f"Widen the baseline -- raise window above {p.window}."],
            see_also="limitations.md#planar-and-rotation-only-captures",
        )

    out.diagnostic(
        "detector_free_output",
        severity="info",
        message=(
            "These matches carry no feature_index; the tracker will merge "
            "endpoints by proximity, controlled by its merge_eps_px."
        ),
        suggested_actions=[
            "Set the tracker's merge_eps_px to 1-2px at a 1600px working resolution.",
            "Watch the tracker's inconsistent_rate for over-merging.",
        ],
        see_also="artifact.md#no-feature_index",
    )

    planarity_note = "not measured" if mean_planarity is None else f"{mean_planarity:.2f}"
    out.note(
        f"LoFTR ('{p.setting}') on {dev.type} over {n_images} images, {p.pairing} "
        f"pairing (window {p.window}): {len(kept_pairs)}/{len(graph)} pairs kept, "
        f"{weak_pairs} dropped. Mean {mean_matches:.0f} verified matches per pair "
        f"(min {int(inliers.min())}), inlier ratio {ratio:.2f}, mean confidence "
        f"{mean_score:.2f}, planarity {planarity_note}. View graph: "
        f"{len(components)} component(s). Detector-free: no feature_index, so the "
        f"tracker merges endpoints by proximity."
        + ("" if dev.type == "cuda" else " NOTE: ran on CPU, which is very slow.")
    )
