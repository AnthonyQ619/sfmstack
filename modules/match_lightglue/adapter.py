"""FeatureMatchLightGlue -- scene/v1 + features/v1 -> pairwise_matches/v1.

Learned sparse matcher. Reasons about the whole match set jointly rather than
per-keypoint, which is exactly the information Lowe's ratio test throws away.

Everything after the match itself -- geometric verification, view graph,
planarity -- is the same as in the classical matchers, so the three are directly
comparable and only the correspondence step differs.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
import torch
from lightglue import LightGlue
from sfmkit import Ctx, module
from sfmkit.cycles import cycle_rates

MIN_FOR_FUNDAMENTAL = 8
MIN_FOR_HOMOGRAPHY = 4

# Which LightGlue weight set goes with which detector. LightGlue is trained
# per-descriptor, so this is not a hint -- superpoint weights on aliked
# descriptors produce confident nonsense rather than an error.
DETECTOR_WEIGHTS = {
    "FeatureDetectionSuperPoint": "superpoint",
    "FeatureDetectionALIKED": "aliked",
    "FeatureDetectionSIFT": "sift",
    "FeatureDetectionDISK": "disk",
}
EXPECTED_DIM = {"superpoint": 256, "aliked": 128, "sift": 128, "disk": 128}
# These weight sets were trained with scale and orientation as extra inputs, so
# the features artifact must carry them.
NEEDS_SCALE_ORI = {"sift", "doghardnet"}

_MODELS: dict[tuple, LightGlue] = {}


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model(weights: str, n_layers: int, depth_conf: float,
              width_conf: float, filter_threshold: float, flash: bool) -> LightGlue:
    key = (weights, n_layers, depth_conf, width_conf, filter_threshold, flash)
    if key not in _MODELS:
        _MODELS[key] = (
            LightGlue(
                features=weights,
                n_layers=n_layers,
                depth_confidence=depth_conf,
                width_confidence=width_conf,
                filter_threshold=filter_threshold,
                flash=flash,
            )
            .eval()
            .to(device())
        )
    return _MODELS[key]


def warmup() -> None:
    get_model("superpoint", 9, 0.95, 0.99, 0.1, True)


def resolve_weights(features, requested: str, desc_dim: int) -> str:
    """Decide which LightGlue weight set matches these descriptors.

    Inferred from the producing module rather than asked for, because getting it
    wrong is silent: LightGlue will happily run superpoint weights over aliked
    descriptors and return confident, meaningless matches. The descriptor width is
    a cross-check, not the primary signal, because aliked, sift and disk are all
    128-dimensional.
    """
    if requested != "auto":
        return requested

    provenance = features.manifest.produced_by
    producer = provenance.module if provenance else ""
    weights = DETECTOR_WEIGHTS.get(producer)

    if weights is None:
        raise ValueError(
            f"cannot tell which LightGlue weights suit features produced by "
            f"{producer or 'an unknown module'}. LightGlue is trained per "
            f"descriptor type, so the wrong weights give confident nonsense rather "
            f"than an error. Set `weights` explicitly to one of "
            f"{sorted(EXPECTED_DIM)}, or use a detector this module knows: "
            f"{sorted(DETECTOR_WEIGHTS)}."
        )

    expected = EXPECTED_DIM[weights]
    if desc_dim != expected:
        raise ValueError(
            f"{producer} normally produces {expected}-d descriptors and this "
            f"artifact has {desc_dim}-d. Either the detector was configured "
            f"unusually or the artifact is not what its provenance claims; set "
            f"`weights` explicitly if you know which is right."
        )
    return weights


def build_view_graph(n_images: int, pairing: str, window: int):
    if pairing == "exhaustive":
        return list(itertools.combinations(range(n_images), 2))
    return [
        (i, j)
        for i in range(n_images)
        for j in range(i + 1, min(i + window + 1, n_images))
    ]


def group_rows_by_image(image_index: np.ndarray, n_images: int) -> list[np.ndarray]:
    order = np.argsort(image_index, kind="stable")
    bounds = np.searchsorted(image_index[order], np.arange(n_images + 1))
    return [order[bounds[i] : bounds[i + 1]] for i in range(n_images)]


def feature_dict(xy, desc, size, dev, scale=None, orientation=None):
    """The batched dict LightGlue expects, with the batch dimension it requires.

    `image_size` is not decoration: LightGlue normalises keypoint coordinates by
    it internally, so a wrong size silently changes the geometry the model sees.
    """
    data = {
        "keypoints": torch.from_numpy(xy).float()[None].to(dev),
        "descriptors": torch.from_numpy(desc).float()[None].to(dev),
        "image_size": torch.tensor(size, dtype=torch.float32)[None].to(dev),
    }
    if scale is not None:
        data["scales"] = torch.from_numpy(scale).float()[None].to(dev)
    if orientation is not None:
        data["oris"] = torch.from_numpy(orientation).float()[None].to(dev)
    return data


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


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    features = ctx.inputs["features"]
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    n_images = len(names)

    if not features.has("descriptors"):
        raise ValueError(
            "FeatureMatchLightGlue needs descriptors. Detector-free matchers "
            "produce correspondences without them and emit pairwise_matches "
            "directly, so they neither need nor can use this module."
        )

    keypoints = features.load("keypoints")
    xy = keypoints["xy"].astype(np.float32)
    image_index = keypoints["image_index"]
    desc = features.load("descriptors", "desc").astype(np.float32)

    weights = resolve_weights(features, p.weights, desc.shape[1])

    scale = keypoints.get("scale")
    orientation = keypoints.get("orientation")
    if weights in NEEDS_SCALE_ORI and (scale is None or orientation is None):
        raise ValueError(
            f"the '{weights}' LightGlue weights were trained with keypoint scale "
            f"and orientation as inputs, and this features artifact carries "
            f"{'no scale' if scale is None else 'no orientation'}. Use a detector "
            f"that records them (SIFT does), or a weight set that does not need "
            f"them (superpoint, aliked, disk)."
        )

    dev = device()
    model = get_model(
        weights, p.n_layers, p.depth_confidence, p.width_confidence,
        p.filter_threshold, p.flash,
    )

    rows_of = group_rows_by_image(image_index, n_images)
    graph = build_view_graph(n_images, p.pairing, p.window)
    if not graph:
        raise ValueError(
            f"the view graph is empty: {n_images} image(s) with "
            f"pairing={p.pairing!r}, window={p.window}. At least 2 are needed."
        )

    # Per-image tensors are built once and reused across every pair the image
    # participates in. With exhaustive pairing each image appears in N-1 pairs, so
    # rebuilding them per pair would dominate the runtime.
    cache = {}
    for i in range(n_images):
        rows = rows_of[i]
        cache[i] = feature_dict(
            xy[rows], desc[rows], (int(sizes[i, 0]), int(sizes[i, 1])), dev,
            scale[rows] if scale is not None else None,
            orientation[rows] if orientation is not None else None,
        )

    kept_pairs = []
    xy_blocks, pair_idx_blocks, feat_idx_blocks, conf_blocks = [], [], [], []
    raw_counts, raw_kept, inlier_counts, planarity, all_scores = [], [], [], [], []
    weak_pairs = 0

    with torch.inference_mode():
        for step, (i, j) in enumerate(graph):
            ctx.progress(step / len(graph), f"matching {step + 1}/{len(graph)} pairs")

            result = model({"image0": cache[i], "image1": cache[j]})
            pairs = result["matches"][0].cpu().numpy()
            scores = result["scores"][0].cpu().numpy()

            raw_counts.append(len(pairs))
            if len(pairs) < p.min_matches:
                weak_pairs += 1
                continue

            gi = rows_of[i][pairs[:, 0]]
            gj = rows_of[j][pairs[:, 1]]
            pi, pj = xy[gi], xy[gj]

            mask = verify(
                pi, pj, p.geometric_model, p.ransac_threshold, p.ransac_confidence
            )
            n_in = int(mask.sum())
            if n_in < p.min_matches:
                weak_pairs += 1
                continue

            if p.measure_planarity and p.geometric_model != "homography":
                share = homography_share(
                    pi[mask], pj[mask], p.ransac_threshold, p.ransac_confidence, n_in
                )
                if share is not None:
                    planarity.append(share)

            pair_row = len(kept_pairs)
            kept_pairs.append((i, j))
            inlier_counts.append(n_in)
            raw_kept.append(len(pairs))
            all_scores.append(float(scores[mask].mean()))

            xy_blocks.append(np.hstack([pi[mask], pj[mask]]).astype(np.float32))
            pair_idx_blocks.append(np.full(n_in, pair_row, np.int32))
            feat_idx_blocks.append(np.column_stack([gi[mask], gj[mask]]).astype(np.int32))
            conf_blocks.append(scores[mask].astype(np.float32))

    if not kept_pairs:
        best_raw = max(raw_counts) if raw_counts else 0
        raise ValueError(
            f"no image pair survived matching: {len(graph)} attempted, best raw "
            f"match count {best_raw}, min_matches={p.min_matches}, weights "
            f"'{weights}'. Check the weights are right for the detector -- the "
            f"wrong ones produce few or nonsensical matches rather than an error. "
            f"Then check the detector's keypoints_min."
        )

    out = ctx.output("matches")
    # B: the per-pair count, beside the pair it belongs to. `matches_per_pair` and
    # `min_matches_per_pair` are a mean and a min, and the decisions at this stage
    # are about WHICH pair -- the same count means opposite things on a redundant
    # edge and on the only link between two halves of a capture. Every reader in a
    # ten-capture sweep rebuilt this by histogramming `pair_index` against a 60k-row
    # array, and every structural finding any of them reached came out of that
    # script. It is one line here and it rides as a recorded extra.
    pair_counts = np.bincount(
        np.concatenate(pair_idx_blocks) if pair_idx_blocks else np.zeros(0, np.int32),
        minlength=len(kept_pairs),
    ).astype(np.int32)
    out.save("pairs", image_pair=np.array(kept_pairs, np.int32),
             match_count=pair_counts)
    out.save(
        "matches",
        xy=np.concatenate(xy_blocks),
        pair_index=np.concatenate(pair_idx_blocks),
        feature_index=np.concatenate(feat_idx_blocks),
        confidence=np.concatenate(conf_blocks),
    )

    inliers = np.array(inlier_counts, dtype=float)
    raw = np.maximum(np.array(raw_kept, dtype=float), 1.0)
    mean_matches = float(inliers.mean())
    ratio = float(np.mean(inliers / raw))
    components = connected_components(n_images, kept_pairs)
    mean_planarity = float(np.mean(planarity)) if planarity else None
    mean_score = float(np.mean(all_scores))

    # 2: the denominator. scene_to_pipeline.md tells a reader to watch
    # pairs_matched "against the number of pairs your pairing proposed" -- a
    # number the module HAS (it built the list) and used to throw away. Every
    # reader recovered it as n(n-1)/2 by hand, which is right only under
    # exhaustive pairing; under a sequential window the arithmetic is
    # edge-truncated and nobody will do it reliably. It also gives weak_pairs a
    # denominator, which it has never had.
    out.metric("pairs_proposed", len(graph), direction="neutral")
    out.metric("pairs_matched", len(kept_pairs),
               direction="higher_better", healthy=(1, None))
    out.metric("matches_per_pair", round(mean_matches, 1),
               direction="higher_better", healthy=(100, None))
    # B: no band. The floor assumes a CHAIN, where every edge is load-bearing,
    # and the guide mandates exhaustive pairing, which does not produce one --
    # the thinnest pair usually sits on an image carrying nine others and
    # bounds nothing. It also fought its own fix: raising min_matches to lift
    # the weakest edge drops thin pairs, so pairs_matched falls and weak_pairs
    # rises. Four readers judged against a band the metric text disowns; one
    # used it to stop a parameter sweep. Read it beside min_image_degree and
    # the match_count array, or not at all.
    out.metric("min_matches_per_pair", int(inliers.min()),
               direction="higher_better")
    out.metric("inlier_ratio", round(ratio, 3),
               direction="higher_better", healthy=(0.7, None))
    # A: degree, not just connectivity. `graph_components` is a TERMINAL condition
    # -- it fires only once the split has already happened -- and on a small set the
    # consecutive chain almost always survives, so it reads 1 whether the graph is
    # robust or one bad pair from breaking. Across a ten-capture sweep it read 1 on
    # 54 of 59 runs. `min_image_degree` is the margin: an image on a single edge is
    # connected and one pair from being lost, and nothing else published says so.
    degree = [0] * n_images
    for i, j in kept_pairs:
        degree[i] += 1
        degree[j] += 1
    out.metric("graph_components", len(components),
               direction="lower_better", healthy=(None, 1))
    out.metric("largest_component_fraction", round(components[0] / n_images, 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("min_image_degree", int(min(degree)) if degree else 0,
               direction="higher_better", healthy=(2, None))
    # D: no band. Zero weak pairs is unreachable on any exhaustive sweep of a
    # capture that visits more than one place -- pairs that share no content are
    # SUPPOSED to be dropped, and this module's own tuning file says a pair it
    # cannot link is evidence the gap is real. The band also fought the fix for
    # a thin weakest link: raising min_matches makes this number worse by
    # definition. Count, not verdict.
    out.metric("weak_pairs", weak_pairs, direction="neutral")
    out.metric("planarity",
               None if mean_planarity is None else round(mean_planarity, 3),
               direction="lower_better", healthy=(None, 0.9))
    out.metric("mean_match_score", round(mean_score, 3),
               direction="higher_better", healthy=(0.5, None))

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
                "LightGlue handles wide baselines well; if it cannot link them, they do not overlap.",
            ],
            see_also="tuning.md#graph_components-above-1",
        )

    if ratio < 0.5:
        out.diagnostic(
            "low_inlier_ratio",
            severity="warn",
            message=(
                f"Only {ratio:.0%} of LightGlue's matches agreed with the "
                f"{p.geometric_model} model."
            ),
            suggested_actions=[
                "Verify `weights` matches the detector; wrong weights are silent.",
                f"Raise filter_threshold above {p.filter_threshold}.",
            ],
            see_also="tuning.md#inlier_ratio-below-05",
        )

    # F: one threshold, and it is the wrong-weights line. This fired at 0.5 while
    # limitations.md put the wrong-weights symptom below ~0.4 and tuning.md said
    # flatly that a low score with a healthy inlier_ratio MEANS wrong weights.
    # Three readers landed at 0.39-0.45 -- inside that gap -- with `weights: auto`
    # already resolved from provenance and cross-checked on descriptor width,
    # which is the only verification this module offers. Both old suggestions were
    # dead ends there: one was already done, the other is not a move.
    #
    # The cause was measured instead: on one capture the score moved 0.394 -> 0.575
    # on filter_threshold ALONE, weights untouched. A permissive threshold admits a
    # low-confidence tail that drags the mean, so responsiveness to that dial is
    # what separates a tail from a weight-set error.
    if mean_score < 0.4:
        out.diagnostic(
            "low_confidence",
            severity="warn",
            message=f"Mean match confidence is {mean_score:.2f}.",
            suggested_actions=[
                f"Raise filter_threshold above {p.filter_threshold} and re-read this. "
                "If the score climbs, it was a low-confidence tail, not wrong weights.",
                "If it does not move, verify `weights` -- but `auto` resolves from "
                "the features artifact's provenance and refuses on an unknown "
                "producer, so a wrong set is only possible if it was named by hand.",
            ],
            see_also="limitations.md#when-lightglue-is-not-the-answer",
        )

    if mean_planarity is not None and mean_planarity > 0.9:
        out.diagnostic(
            "degenerate_geometry",
            severity="warn",
            message=(
                f"A homography recovers {mean_planarity:.0%} of the fundamental "
                f"matrix's inliers; these pairs are planar or rotation-only."
            ),
            suggested_actions=[
                f"Widen the baseline -- raise window above {p.window}.",
                "Expect triangulation to be ill-conditioned on the affected pairs.",
            ],
            see_also="limitations.md#planar-and-rotation-only-captures",
        )

    planarity_note = "not measured" if mean_planarity is None else f"{mean_planarity:.2f}"
    out.note(
        f"LightGlue ('{weights}' weights, {p.n_layers} layers) on {dev.type} over "
        f"{n_images} images, {p.pairing} pairing (window {p.window}): "
        f"{len(kept_pairs)}/{len(graph)} pairs kept, {weak_pairs} dropped. "
        f"Mean {mean_matches:.0f} verified matches per pair (min "
        f"{int(inliers.min())}), inlier ratio {ratio:.2f}, mean confidence "
        f"{mean_score:.2f}, planarity {planarity_note}. View graph: "
        f"{len(components)} component(s)."
        + ("" if dev.type == "cuda" else " NOTE: ran on CPU, which is slow.")
    )

    # A: the two failures a two-view check cannot see, one stage before the
    # tracker reports them. A correspondence displaced onto a repeated structure
    # is epipolar-consistent by construction when the camera slides along the
    # repeat, so it counts as an INLIER here and only contradicts itself once a
    # third view is compared. Graded by displacement because the two failures cost
    # differently and the cheap one dominates by volume: a couple of pixels is one
    # point detected twice, which shortens a track, while tens of pixels is a
    # different piece of scene, which corrupts geometry. Summed into one number
    # the split rate buries the merge rate and the reading inverts.
    merge_rate, split_rate, n_chains = cycle_rates(
        np.array(kept_pairs, np.int32),
        np.concatenate(pair_idx_blocks) if pair_idx_blocks else np.zeros(0, np.int32),
        np.concatenate(feat_idx_blocks) if feat_idx_blocks else None,
        np.concatenate(xy_blocks) if xy_blocks else np.zeros((0, 4), np.float32),
    )
    out.metric("cycle_merge_rate",
               None if merge_rate is None else round(merge_rate, 6),
               direction="lower_better")
    out.metric("cycle_split_rate",
               None if split_rate is None else round(split_rate, 6),
               direction="lower_better")
