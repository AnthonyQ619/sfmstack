"""FeatureMatchFLANN -- scene/v1 + features/v1 -> pairwise_matches/v1.

FeatureMatchNN with the exhaustive search replaced by an approximate index.
Everything after the search is deliberately identical, so the two modules are
directly comparable and the search is the only variable.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
from sfmkit import Ctx, module
from sfmkit.cycles import cycle_rates

MIN_FOR_FUNDAMENTAL = 8
MIN_FOR_HOMOGRAPHY = 4
FLANN_INDEX_KDTREE = 1
FLANN_INDEX_LSH = 6


def group_rows_by_image(image_index: np.ndarray, n_images: int) -> list[np.ndarray]:
    order = np.argsort(image_index, kind="stable")
    bounds = np.searchsorted(image_index[order], np.arange(n_images + 1))
    return [order[bounds[i] : bounds[i + 1]] for i in range(n_images)]


def build_view_graph(n_images: int, pairing: str, window: int):
    if pairing == "exhaustive":
        return list(itertools.combinations(range(n_images), 2))
    return [
        (i, j)
        for i in range(n_images)
        for j in range(i + 1, min(i + window + 1, n_images))
    ]


def make_matcher(binary: bool, p):
    """A FLANN index appropriate to the descriptor type.

    Binary descriptors cannot go in a KD-tree -- the space is Hamming, not
    Euclidean -- so ORB and friends get LSH. Choosing this from the artifact's
    `binary` flag rather than from a parameter means a detector swap does not
    silently produce garbage matches.
    """
    if binary:
        index = dict(
            algorithm=FLANN_INDEX_LSH,
            table_number=p.lsh_tables,
            key_size=p.lsh_key_size,
            multi_probe_level=p.lsh_probe_level,
        )
    else:
        index = dict(algorithm=FLANN_INDEX_KDTREE, trees=p.trees)
    return cv2.FlannBasedMatcher(index, dict(checks=p.checks))


def ratio_matches(matcher, desc_a, desc_b, ratio, binary):
    """Approximate nearest neighbours surviving Lowe's ratio test."""
    if len(desc_a) == 0 or len(desc_b) < 2:
        return np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0, np.float32)

    # FLANN wants float32 for KD-trees and uint8 for LSH; anything else silently
    # fails or throws deep inside the C++ layer.
    a = desc_a if binary else np.ascontiguousarray(desc_a, dtype=np.float32)
    b = desc_b if binary else np.ascontiguousarray(desc_b, dtype=np.float32)

    try:
        knn = matcher.knnMatch(a, b, k=2)
    except cv2.error:
        # LSH can fail outright on degenerate descriptor sets rather than
        # returning nothing. Treat it as "this pair produced no matches".
        return np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0, np.float32)

    ia, ib, conf = [], [], []
    for candidates in knn:
        # An approximate search can return fewer than k neighbours, which the
        # exact matcher never does. Without this guard the ratio test would index
        # past the end on a fraction of queries.
        if len(candidates) < 2:
            continue
        first, second = candidates[0], candidates[1]
        if second.distance <= 0:
            continue
        r = first.distance / second.distance
        if r < ratio:
            ia.append(first.queryIdx)
            ib.append(first.trainIdx)
            conf.append(1.0 - r)

    return np.array(ia, np.int64), np.array(ib, np.int64), np.array(conf, np.float32)


def mutual_filter(ia, ib, conf, ja, jb):
    if len(ia) == 0 or len(ja) == 0:
        return ia[:0], ib[:0], conf[:0]
    back = {int(q): int(t) for q, t in zip(ja, jb)}
    keep = np.array([back.get(int(b), -1) == int(a) for a, b in zip(ia, ib)], dtype=bool)
    return ia[keep], ib[keep], conf[keep]


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


def agreement_on(desc_a, desc_b, approx_ia, approx_ib, binary) -> float | None:
    """Fraction of the approximate nearest neighbours that are also the exact one.

    A spot check on one pair, by brute force. It is the only way to know what the
    approximation costs on THIS data rather than in general, and it is cheap
    because it runs once rather than per pair.
    """
    if len(approx_ia) == 0:
        return None
    norm = cv2.NORM_HAMMING if binary else cv2.NORM_L2
    exact = cv2.BFMatcher(norm).match(desc_a, desc_b)
    truth = {m.queryIdx: m.trainIdx for m in exact}
    hits = sum(1 for q, t in zip(approx_ia, approx_ib) if truth.get(int(q)) == int(t))
    return hits / len(approx_ia)


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    features = ctx.inputs["features"]
    p = ctx.params

    names = scene.load("images", "names")
    n_images = len(names)

    xy = features.load("keypoints", "xy").astype(np.float32)
    image_index = features.load("keypoints", "image_index")

    if not features.has("descriptors"):
        raise ValueError(
            "FeatureMatchFLANN needs descriptors, and this features artifact has "
            "none. Detector-free matchers produce correspondences without them and "
            "already emit pairwise_matches directly."
        )

    descriptors = features.load("descriptors")
    desc = descriptors["desc"]
    binary = bool(descriptors.get("binary", False))
    if binary:
        desc = np.ascontiguousarray(desc, dtype=np.uint8)

    matcher = make_matcher(binary, p)
    rows_of = group_rows_by_image(image_index, n_images)
    graph = build_view_graph(n_images, p.pairing, p.window)

    if not graph:
        raise ValueError(
            f"the view graph is empty: {n_images} image(s) with "
            f"pairing={p.pairing!r}, window={p.window}. At least 2 images are needed."
        )

    kept_pairs = []
    xy_blocks, pair_idx_blocks, feat_idx_blocks, conf_blocks = [], [], [], []
    raw_counts, raw_kept, inlier_counts, planarity = [], [], [], []
    weak_pairs = 0
    agreement = None

    for step, (i, j) in enumerate(graph):
        ctx.progress(step / len(graph), f"matching {step + 1}/{len(graph)} pairs")

        rows_i, rows_j = rows_of[i], rows_of[j]
        di, dj = desc[rows_i], desc[rows_j]

        ia, ib, conf = ratio_matches(matcher, di, dj, p.ratio_test, binary)

        if agreement is None and p.measure_agreement and len(ia) > 0:
            agreement = agreement_on(di, dj, ia, ib, binary)

        if p.mutual:
            ja, jb, _ = ratio_matches(matcher, dj, di, p.ratio_test, binary)
            ia, ib, conf = mutual_filter(ia, ib, conf, ja, jb)

        raw_counts.append(len(ia))
        if len(ia) < p.min_matches:
            weak_pairs += 1
            continue

        gi, gj = rows_i[ia], rows_j[ib]
        pi, pj = xy[gi], xy[gj]

        mask = verify(pi, pj, p.geometric_model, p.ransac_threshold, p.ransac_confidence)
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
        raw_kept.append(len(ia))

        xy_blocks.append(np.hstack([pi[mask], pj[mask]]).astype(np.float32))
        pair_idx_blocks.append(np.full(n_in, pair_row, np.int32))
        feat_idx_blocks.append(np.column_stack([gi[mask], gj[mask]]).astype(np.int32))
        conf_blocks.append(conf[mask].astype(np.float32))

    if not kept_pairs:
        best_raw = max(raw_counts) if raw_counts else 0
        raise ValueError(
            f"no image pair survived matching: {len(graph)} pair(s) attempted, "
            f"best raw match count was {best_raw}, min_matches={p.min_matches}, "
            f"checks={p.checks}"
            + (f", measured search agreement {agreement:.0%}" if agreement else "")
            + ". Raise `checks` substantially and retry. If FeatureMatchNN succeeds "
            "on the same features, the approximation is the problem; if it also "
            "fails, the features or the pairing are."
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
               direction="higher_better", healthy=(0.5, None))
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
    out.metric("match_agreement",
               None if agreement is None else round(agreement, 3),
               direction="higher_better", healthy=(0.9, None))

    if agreement is not None and agreement < 0.9:
        out.diagnostic(
            "approximation_costly",
            severity="warn",
            message=(
                f"Only {agreement:.0%} of approximate nearest neighbours were the "
                f"exact one at checks={p.checks}."
            ),
            suggested_actions=[
                f"Raise checks above {p.checks}; it is the accuracy dial.",
                "Raise trees for float descriptors, or lsh_tables for binary.",
                "Below a few thousand keypoints per image, use FeatureMatchNN instead.",
            ],
            see_also="tuning.md#match_agreement-below-09",
        )

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
                f"Raise checks above {p.checks}; a poor search thins every pair.",
            ],
            see_also="tuning.md#graph_components-above-1",
        )

    if ratio < 0.3:
        out.diagnostic(
            "low_inlier_ratio",
            severity="warn",
            message=f"Only {ratio:.0%} of matches agreed with the {p.geometric_model} model.",
            suggested_actions=[
                "Check match_agreement first; this may be search error, not matching error.",
                "Lower ratio_test toward 0.7 if the scene has repeated structure.",
            ],
            see_also="tuning.md#inlier_ratio-below-03",
        )

    index_kind = "LSH" if binary else f"{p.trees} KD-trees"
    agreement_note = "not measured" if agreement is None else f"{agreement:.0%}"
    out.note(
        f"FLANN ({index_kind}, checks={p.checks}) over {n_images} images, "
        f"{p.pairing} pairing (window {p.window}): {len(kept_pairs)}/{len(graph)} "
        f"pairs kept, {weak_pairs} dropped. Mean {mean_matches:.0f} verified matches "
        f"per pair, inlier ratio {ratio:.2f}. Search agreement with exact matching: "
        f"{agreement_note}. View graph: {len(components)} component(s)."
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
