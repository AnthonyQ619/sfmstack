"""FeatureMatchNN -- scene/v1 + features/v1 -> pairwise_matches/v1.

Brute-force descriptor matching, Lowe ratio, mutual check, MAGSAC verification.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
from sfmkit import Ctx, module
from sfmkit.cycles import cycle_rates

MIN_FOR_FUNDAMENTAL = 8  # the 8-point algorithm's floor
MIN_FOR_HOMOGRAPHY = 4


def group_rows_by_image(image_index: np.ndarray, n_images: int) -> list[np.ndarray]:
    """Global keypoint row ids belonging to each image.

    Row ids rather than a re-indexed copy, because `feature_index` in the output
    must point back into the ORIGINAL features table -- that is what lets the
    tracker union observations across pairs without a translation table.
    """
    order = np.argsort(image_index, kind="stable")
    bounds = np.searchsorted(image_index[order], np.arange(n_images + 1))
    return [order[bounds[i] : bounds[i + 1]] for i in range(n_images)]


def build_view_graph(n_images: int, pairing: str, window: int) -> list[tuple[int, int]]:
    """Which pairs to attempt.

    The predecessor hardcoded (i, i+1). That caps tracks at the length of an
    unbroken consecutive chain and makes loop closure unrepresentable, so the
    view graph is a parameter here.
    """
    if pairing == "exhaustive":
        return list(itertools.combinations(range(n_images), 2))
    return [
        (i, j)
        for i in range(n_images)
        for j in range(i + 1, min(i + window + 1, n_images))
    ]


def ratio_matches(matcher, desc_a: np.ndarray, desc_b: np.ndarray, ratio: float):
    """Nearest neighbours from a to b surviving Lowe's ratio test.

    Returns (index_in_a, index_in_b, confidence). Confidence is 1 - d1/d2, so it
    is 0 for a match the test barely admitted and approaches 1 for one whose
    nearest neighbour is far closer than its runner-up.
    """
    if len(desc_a) == 0 or len(desc_b) < 2:
        return np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0, np.float32)

    knn = matcher.knnMatch(desc_a, desc_b, k=2)
    ia, ib, conf = [], [], []
    for candidates in knn:
        if len(candidates) < 2:
            continue
        first, second = candidates[0], candidates[1]
        # A zero second-best distance would make the ratio meaningless; it means
        # two identical descriptors in b, which is itself a reason to reject.
        if second.distance <= 0:
            continue
        r = first.distance / second.distance
        if r < ratio:
            ia.append(first.queryIdx)
            ib.append(first.trainIdx)
            conf.append(1.0 - r)

    return (
        np.array(ia, np.int64),
        np.array(ib, np.int64),
        np.array(conf, np.float32),
    )


def mutual_filter(ia, ib, conf, ja, jb):
    """Keep matches that both directions agree on.

    (ia, ib) is a->b; (ja, jb) is b->a, so agreement means ib[k] maps back to
    ia[k]. Without this the ratio test happily lets several features in a claim
    the same feature in b, and those many-to-one matches are what fuse two
    distinct scene points into one track.
    """
    if len(ia) == 0 or len(ja) == 0:
        return ia[:0], ib[:0], conf[:0]

    back = {int(q): int(t) for q, t in zip(ja, jb)}
    keep = np.array(
        [back.get(int(b), -1) == int(a) for a, b in zip(ia, ib)], dtype=bool
    )
    return ia[keep], ib[keep], conf[keep]


def verify(xy_a: np.ndarray, xy_b: np.ndarray, model: str, thresh: float, conf: float):
    """Geometric verification. Returns a boolean inlier mask."""
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

    # MAGSAC returns None for both when it cannot find any consistent model,
    # which is a legitimate answer meaning "this pair does not agree".
    if mask is None:
        return np.zeros(len(xy_a), dtype=bool)
    return mask.ravel().astype(bool)


def homography_share(xy_a, xy_b, thresh, conf, n_inliers) -> float | None:
    """Homography inliers as a fraction of the model's inliers.

    Near 1.0 the pair is planar or pure rotation: a homography explains it as
    well as epipolar geometry does, and triangulating it yields confident
    nonsense. This is the check the predecessor asked the user to make in advance
    by setting RANSAC_homography; measuring it after the fact is strictly better,
    because the answer varies per pair within one scene.
    """
    if n_inliers <= 0 or len(xy_a) < MIN_FOR_HOMOGRAPHY:
        return None
    _, mask = cv2.findHomography(
        xy_a, xy_b, cv2.USAC_MAGSAC,
        ransacReprojThreshold=thresh, maxIters=10000, confidence=conf,
    )
    if mask is None:
        return 0.0
    return min(1.0, float(mask.sum()) / float(n_inliers))


def connected_components(n_images: int, edges: list[tuple[int, int]]) -> list[int]:
    """Component sizes, largest first. Over IMAGES, not features."""
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
    n_images = len(names)

    xy = features.load("keypoints", "xy").astype(np.float32)
    image_index = features.load("keypoints", "image_index")

    if not features.has("descriptors"):
        raise ValueError(
            "FeatureMatchNN needs descriptors, and this features artifact has "
            "none. Detector-free matchers (LoFTR, RoMa) produce correspondences "
            "without descriptors; they cannot be fed to a nearest-neighbour "
            "matcher, and they already produce pairwise_matches directly."
        )

    descriptors = features.load("descriptors")
    desc = descriptors["desc"]
    binary = bool(descriptors.get("binary", False))
    norm = cv2.NORM_HAMMING if binary else cv2.NORM_L2
    matcher = cv2.BFMatcher(norm)

    rows_of = group_rows_by_image(image_index, n_images)
    graph = build_view_graph(n_images, p.pairing, p.window)

    if not graph:
        raise ValueError(
            f"the view graph is empty: {n_images} image(s) with "
            f"pairing={p.pairing!r}, window={p.window}. At least 2 images are needed."
        )

    kept_pairs: list[tuple[int, int]] = []
    xy_blocks, pair_idx_blocks, feat_idx_blocks, conf_blocks = [], [], [], []
    # raw_counts covers every attempted pair (it is what the failure message
    # reports); raw_kept stays aligned with inlier_counts so the inlier ratio is
    # computed over the same pairs in both numerator and denominator.
    raw_counts, raw_kept, inlier_counts, planarity = [], [], [], []
    weak_pairs = 0

    for step, (i, j) in enumerate(graph):
        ctx.progress(step / len(graph), f"matching {step + 1}/{len(graph)} pairs")

        rows_i, rows_j = rows_of[i], rows_of[j]
        di, dj = desc[rows_i], desc[rows_j]

        ia, ib, conf = ratio_matches(matcher, di, dj, p.ratio_test)
        if p.mutual:
            ja, jb, _ = ratio_matches(matcher, dj, di, p.ratio_test)
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
        feat_idx_blocks.append(
            np.column_stack([gi[mask], gj[mask]]).astype(np.int32)
        )
        conf_blocks.append(conf[mask].astype(np.float32))

    if not kept_pairs:
        attempted = len(graph)
        best_raw = max(raw_counts) if raw_counts else 0
        raise ValueError(
            f"no image pair survived matching: {attempted} pair(s) attempted, "
            f"best raw match count was {best_raw}, min_matches={p.min_matches}. "
            f"Check the detector's keypoints_min first -- a starved frame breaks "
            f"every pair it appears in. If raw counts were healthy, verification "
            f"is what rejected them: re-run with geometric_model=none to confirm, "
            f"or raise ransac_threshold if the scene was heavily downscaled."
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
    min_matches_seen = int(inliers.min())
    ratio = float(np.mean(inliers / raw))
    components = connected_components(n_images, kept_pairs)
    mean_planarity = float(np.mean(planarity)) if planarity else None

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
    out.metric("min_matches_per_pair", min_matches_seen,
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
    out.metric(
        "planarity",
        None if mean_planarity is None else round(mean_planarity, 3),
        direction="lower_better",
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
                f"Lower min_matches below {p.min_matches} if the gaps were thin, not wrong.",
            ],
            see_also="tuning.md#graph_components-above-1",
        )

    if ratio < 0.3:
        out.diagnostic(
            "low_inlier_ratio",
            severity="warn",
            message=(
                f"Only {ratio:.0%} of descriptor matches agreed with the "
                f"{p.geometric_model} model."
            ),
            suggested_actions=[
                "Lower ratio_test toward 0.7 if the scene has repeated structure.",
                f"Raise ransac_threshold above {p.ransac_threshold} if heavily downscaled.",
            ],
            see_also="tuning.md#inlier_ratio-below-03",
        )

    if mean_matches < 100:
        out.diagnostic(
            "sparse_matches",
            severity="warn",
            message=f"Surviving pairs carry {mean_matches:.0f} matches on average.",
            suggested_actions=[
                "Raise the detector's max_keypoints or lower its contrast_threshold.",
                "Raise ratio_test toward 0.9, keeping geometric verification on.",
            ],
            see_also="tuning.md#matches_per_pair-below-100",
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
        f"{p.pairing} pairing (window {p.window}) over {n_images} images: "
        f"{len(kept_pairs)}/{len(graph)} pairs kept, {weak_pairs} dropped under "
        f"min_matches={p.min_matches}. Mean {mean_matches:.0f} verified matches "
        f"per pair (min {min_matches_seen}), inlier ratio {ratio:.2f}, planarity "
        f"{planarity_note}. View graph: {len(components)} component(s), largest "
        f"covers {components[0]}/{n_images} images."
    )
