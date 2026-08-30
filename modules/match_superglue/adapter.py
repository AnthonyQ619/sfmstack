"""FeatureMatchSuperGlue -- scene/v1 + features/v1 -> pairwise_matches/v1.

Attentional GNN over both keypoint sets, then a Sinkhorn optimal-transport
assignment. SuperPoint descriptors only -- the 256-dimensional width is baked into
the trained weights.

Everything after the correspondence step is identical to the other matchers here,
so all five differ in exactly one stage and their metrics compare directly.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
import torch
from models.superglue import SuperGlue  # /opt/superglue, cloned at image build
from sfmkit import Ctx, module
from sfmkit.cycles import cycle_rates

MIN_FOR_FUNDAMENTAL = 8
MIN_FOR_HOMOGRAPHY = 4
SUPERPOINT_DIM = 256

_MODELS: dict[tuple, SuperGlue] = {}


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model(weights: str, threshold: float, iterations: int) -> SuperGlue:
    key = (weights, threshold, iterations)
    if key not in _MODELS:
        _MODELS[key] = (
            SuperGlue({
                "weights": weights,
                "match_threshold": threshold,
                "sinkhorn_iterations": iterations,
            })
            .eval()
            .to(device())
        )
    return _MODELS[key]


def warmup() -> None:
    """Called once at server startup so the first job does not pay for the load."""
    get_model("outdoor", 0.2, 20)


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


def top_k(rows: np.ndarray, scores: np.ndarray | None, k: int) -> np.ndarray:
    """The k highest-scoring keypoints of an image, in the original row order.

    Truncating by score rather than by position matters: keypoint tables are
    ordered by the detector's own convention, and taking the first k of a
    spatially-sorted table would sample one corner of the image.
    """
    if len(rows) <= k:
        return rows
    if scores is None:
        # No scores to rank by. Uniform subsampling at least keeps the spatial
        # spread that the detector's coverage metric described.
        return rows[np.linspace(0, len(rows) - 1, k).astype(int)]
    keep = np.argpartition(scores[rows], -k)[-k:]
    return rows[np.sort(keep)]


def verify(xy_a, xy_b, model, thresh, conf):
    if model == "none":
        return np.ones(len(xy_a), dtype=bool)
    floor = MIN_FOR_HOMOGRAPHY if model == "homography" else MIN_FOR_FUNDAMENTAL
    if len(xy_a) < floor:
        return np.zeros(len(xy_a), dtype=bool)
    fn = cv2.findHomography if model == "homography" else cv2.findFundamentalMat
    _, mask = fn(
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
        root = find(i)
        sizes[root] = sizes.get(root, 0) + 1
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
            "FeatureMatchSuperGlue needs descriptors. Detector-free matchers "
            "produce correspondences without them and emit pairwise_matches "
            "directly, so they neither need nor can use this module."
        )

    keypoints = features.load("keypoints")
    xy = keypoints["xy"].astype(np.float32)
    image_index = keypoints["image_index"]
    scores = keypoints.get("scores")
    desc = features.load("descriptors", "desc").astype(np.float32)

    if desc.shape[1] != SUPERPOINT_DIM:
        out = ctx.output("matches")
        out.diagnostic(
            "wrong_descriptor_width",
            severity="error",
            message=f"Descriptors are {desc.shape[1]}-dimensional, not {SUPERPOINT_DIM}.",
            see_also="limitations.md#superpoint-only",
        )
        produced_by = features.manifest.produced_by
        raise ValueError(
            f"SuperGlue is trained for {SUPERPOINT_DIM}-dimensional SuperPoint "
            f"descriptors and this features artifact carries {desc.shape[1]}-"
            f"dimensional ones from "
            f"{produced_by.module if produced_by else 'an unknown module'}. There "
            f"is no weight set for other detectors -- use "
            f"FeatureDetectionSuperPoint upstream, or FeatureMatchLightGlue, which "
            f"has weight sets for ALIKED and SIFT as well."
        )

    if scores is None:
        # SuperGlue's keypoint encoder takes the detector score as an input, so an
        # artifact without one cannot be fed truthfully. Ones are the neutral value
        # -- every keypoint equally confident -- rather than zeros, which the
        # encoder reads as "certainly spurious" for all of them.
        scores = np.ones(len(xy), dtype=np.float32)
    scores = scores.astype(np.float32)

    dev = device()
    model = get_model(p.weights, p.match_threshold, p.sinkhorn_iterations)

    rows_of = group_rows_by_image(image_index, n_images)
    kept_rows = [top_k(rows_of[i], scores, p.max_keypoints) for i in range(n_images)]
    used = float(np.mean([len(r) for r in kept_rows]))
    detected = float(np.mean([len(r) for r in rows_of]))

    graph = build_view_graph(n_images, p.pairing, p.window)
    if not graph:
        raise ValueError(
            f"the view graph is empty: {n_images} image(s) with "
            f"pairing={p.pairing!r}, window={p.window}. At least 2 are needed."
        )

    cache = {}
    for i in range(n_images):
        rows = kept_rows[i]
        cache[i] = {
            "kpts": torch.from_numpy(xy[rows]).to(dev)[None],
            "desc": torch.from_numpy(desc[rows].T).to(dev)[None],
            "scores": torch.from_numpy(scores[rows]).to(dev)[None],
            # Upstream reads `data['image0'].shape[2:]` to normalise keypoints, so
            # it wants a TENSOR shaped like the image, not the image size. An empty
            # (1, 1, H, W) carries the only part it reads and allocates nothing
            # meaningful. (The predecessor's vendored copy was edited to take an
            # `image_size0` key instead; upstream has no such key.)
            "shape": torch.empty(
                1, 1, int(sizes[i, 1]), int(sizes[i, 0]), device=dev
            ),
        }

    kept_pairs = []
    xy_blocks, pair_idx_blocks, feat_idx_blocks, conf_blocks = [], [], [], []
    raw_counts, raw_kept, inlier_counts, planarity, all_scores = [], [], [], [], []
    weak_pairs = 0

    with torch.inference_mode():
        for step, (i, j) in enumerate(graph):
            ctx.progress(step / len(graph), f"matching {step + 1}/{len(graph)} pairs")

            result = model({
                "keypoints0": cache[i]["kpts"], "keypoints1": cache[j]["kpts"],
                "descriptors0": cache[i]["desc"], "descriptors1": cache[j]["desc"],
                "scores0": cache[i]["scores"], "scores1": cache[j]["scores"],
                "image0": cache[i]["shape"], "image1": cache[j]["shape"],
            })
            # matches0[k] is the index in image 1 matched to keypoint k of image 0,
            # or -1. The assignment is already mutually exclusive, so there is no
            # cross-check to do here.
            matches0 = result["matches0"][0].cpu().numpy()
            scores0 = result["matching_scores0"][0].cpu().numpy()
            valid = matches0 > -1

            raw_counts.append(int(valid.sum()))
            if valid.sum() < p.min_matches:
                weak_pairs += 1
                continue

            gi = kept_rows[i][np.flatnonzero(valid)]
            gj = kept_rows[j][matches0[valid]]
            pi, pj = xy[gi], xy[gj]
            pair_scores = scores0[valid]

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
            raw_kept.append(int(valid.sum()))
            all_scores.append(float(pair_scores[mask].mean()))

            xy_blocks.append(np.hstack([pi[mask], pj[mask]]).astype(np.float32))
            pair_idx_blocks.append(np.full(n_in, pair_row, np.int32))
            feat_idx_blocks.append(np.column_stack([gi[mask], gj[mask]]).astype(np.int32))
            conf_blocks.append(pair_scores[mask].astype(np.float32))

    if not kept_pairs:
        out = ctx.output("matches")
        out.diagnostic(
            "no_pairs_matched",
            severity="error",
            message=f"None of {len(graph)} pairs reached min_matches.",
            see_also="tuning.md#nothing-matched",
        )
        raise ValueError(
            f"no image pair survived matching: {len(graph)} attempted, best raw "
            f"match count {max(raw_counts) if raw_counts else 0}, "
            f"min_matches={p.min_matches}, match_threshold={p.match_threshold}, "
            f"weights '{p.weights}'. Lower match_threshold toward 0.1, and try the "
            f"other weight set -- indoor and outdoor are trained on different data, "
            f"not merely tuned differently."
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
    components = connected_components(n_images, kept_pairs)
    ratio = float(np.mean(inliers / raw))
    mean_planarity = float(np.mean(planarity)) if planarity else None

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
    out.metric("matches_per_pair", round(float(inliers.mean()), 1),
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
    # J: no module-local band. Three files gave three different answers and a
    # capture sat in the gap between them with nothing firing. The bands live
    # in the type now, together with the reason a mid-range reading is a real
    # state rather than a fault, and the warning that this number moves with
    # ransac_threshold and between matchers on identical features.
    out.metric("planarity",
               None if mean_planarity is None else round(mean_planarity, 3),
               direction="lower_better", healthy=(None, 0.9))
    # D: no band. Zero weak pairs is unreachable on any exhaustive sweep of a
    # capture that visits more than one place -- pairs that share no content are
    # SUPPOSED to be dropped, and this module's own tuning file says a pair it
    # cannot link is evidence the gap is real. The band also fought the fix for
    # a thin weakest link: raising min_matches makes this number worse by
    # definition. Count, not verdict.
    out.metric("weak_pairs", weak_pairs, direction="neutral")
    out.metric("mean_match_score", round(float(np.mean(all_scores)), 3),
               direction="higher_better", healthy=(0.4, None))
    out.metric("keypoints_used", round(used, 1), direction="neutral")

    if len(components) > 1:
        out.diagnostic(
            "broken_chain",
            severity="error",
            message=(
                f"The view graph has {len(components)} components, sizes "
                f"{components[:5]}."
            ),
            suggested_actions=[
                f"Raise window above {p.window}, or use pairing: exhaustive.",
                f"Lower min_matches below {p.min_matches} if the links are thin but real.",
            ],
            see_also="tuning.md#graph_components-above-1",
        )

    if ratio < 0.5:
        out.diagnostic(
            "low_inlier_ratio",
            severity="warn",
            message=f"Geometric verification kept {ratio:.0%} of proposed matches.",
            suggested_actions=[
                f"Raise match_threshold above {p.match_threshold}.",
                f"Try the '{'indoor' if p.weights == 'outdoor' else 'outdoor'}' weights.",
                "Check planarity; a degenerate pair fails verification correctly.",
            ],
            see_also="tuning.md#inlier_ratio-below-05",
        )

    if used < detected - 1.0:
        out.diagnostic(
            "keypoints_truncated",
            severity="info",
            message=(
                f"max_keypoints={p.max_keypoints} kept {used:.0f} of "
                f"{detected:.0f} detected keypoints per image."
            ),
            suggested_actions=[
                f"Raise max_keypoints above {p.max_keypoints}, at quadratic cost.",
                "Or lower the detector's max_keypoints so its metrics describe "
                "what was actually matched.",
            ],
            see_also="tuning.md#keypoints_used-below-the-detectors-count",
        )

    out.note(
        f"SuperGlue '{p.weights}' at match_threshold {p.match_threshold}: "
        f"{len(kept_pairs)} of {len(graph)} pairs kept, {inliers.mean():.0f} "
        f"verified matches each, inlier ratio {ratio:.2f}, mean assignment score "
        f"{np.mean(all_scores):.2f}. Fed {used:.0f} of {detected:.0f} detected "
        f"keypoints per image. View graph has {len(components)} component(s). "
        f"Assignment scores are not comparable to LightGlue's -- different head, "
        f"different calibration."
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
