"""FeatureMatchRoMa -- scene/v1 -> pairwise_matches/v1.

Detector-free: a dense warp plus per-pixel certainty, sampled into
correspondences. Consumes no `features/v1` and emits no `feature_index`.

RoMa matches at its own internal resolution and `to_pixel_coordinates` maps the
normalised warp back to whatever pixel size it is told. It is told the SCENE's
working resolution, so every coordinate this module emits is in the same frame as
every other matcher's -- which is what lets the tracker, the pose estimator and
the reprojection thresholds downstream stay resolution-agnostic.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
import torch
from PIL import Image
from romatch import roma_indoor, roma_outdoor
from sfmkit import Ctx, module
from sfmkit.cycles import cycle_rates

MIN_FOR_FUNDAMENTAL = 8
MIN_FOR_HOMOGRAPHY = 4

_MODELS: dict[tuple, object] = {}


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model(setting: str, custom_corr: bool):
    """RoMa's local correlation has two backends.

    `use_custom_corr=True` needs a compiled CUDA extension (`local_corr`) that the
    authors ship separately and pip does not install; without it the model builds
    fine and raises ModuleNotFoundError on the first forward pass, an hour into a
    run. The pure-torch fallback is correct and slower, so it is the default here
    and the fast path is a parameter you turn on once you have built the extension.
    """
    key = (setting, custom_corr)
    if key not in _MODELS:
        factory = roma_outdoor if setting == "outdoor" else roma_indoor
        _MODELS[key] = factory(device=device(), use_custom_corr=custom_corr)
    return _MODELS[key]


def warmup() -> None:
    get_model("outdoor", False)


def build_view_graph(n_images: int, pairing: str, window: int):
    if pairing == "exhaustive":
        return list(itertools.combinations(range(n_images), 2))
    return [
        (i, j)
        for i in range(n_images)
        for j in range(i + 1, min(i + window + 1, n_images))
    ]


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
    p = ctx.params

    names = scene.load("images", "names")
    paths = scene.load("images", "paths")
    sizes = scene.load("images", "size_current")
    n_images = len(names)

    graph = build_view_graph(n_images, p.pairing, p.window)
    if not graph:
        raise ValueError(
            f"the view graph is empty: {n_images} image(s) with "
            f"pairing={p.pairing!r}, window={p.window}. At least 2 are needed."
        )

    model = get_model(p.setting, p.use_custom_corr)
    dev = device()
    resolved = [str(scene.resolve(str(pth))) for pth in paths]

    kept_pairs = []
    xy_blocks, pair_idx_blocks, conf_blocks = [], [], []
    sampled_counts, kept_sampled, inlier_counts = [], [], []
    planarity, certainties = [], []
    floor_removed, floor_total = 0, 0
    weak_pairs = 0

    with torch.inference_mode():
        for step, (i, j) in enumerate(graph):
            ctx.progress(step / len(graph), f"matching {step + 1}/{len(graph)} pairs")

            warp, certainty = model.match(resolved[i], resolved[j], device=dev)
            matches, match_certainty = model.sample(warp, certainty, num=p.max_matches)

            # to_pixel_coordinates maps the normalised warp into whatever size it
            # is given. Giving it the SCENE's working resolution -- not RoMa's
            # internal 560/864 -- is what keeps these coordinates in the same frame
            # as every other matcher's output.
            kpts_a, kpts_b = model.to_pixel_coordinates(
                matches,
                int(sizes[i, 1]), int(sizes[i, 0]),
                int(sizes[j, 1]), int(sizes[j, 0]),
            )
            pi = kpts_a.cpu().numpy().astype(np.float32)
            pj = kpts_b.cpu().numpy().astype(np.float32)
            conf = match_certainty.cpu().numpy().astype(np.float32)

            floor_total += len(conf)
            if p.min_certainty > 0.0:
                keep = conf >= p.min_certainty
                floor_removed += int((~keep).sum())
                pi, pj, conf = pi[keep], pj[keep], conf[keep]

            sampled_counts.append(len(conf))
            if len(conf) < p.min_matches:
                weak_pairs += 1
                continue

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
            # Sampled count for THIS pair, kept aligned with inlier_counts so the
            # ratio has the same pairs in numerator and denominator.
            kept_sampled.append(len(conf))
            certainties.append(float(conf[mask].mean()))

            xy_blocks.append(np.hstack([pi[mask], pj[mask]]).astype(np.float32))
            pair_idx_blocks.append(np.full(n_in, pair_row, np.int32))
            conf_blocks.append(conf[mask])

    if not kept_pairs:
        out = ctx.output("matches")
        out.diagnostic(
            "no_pairs_matched",
            severity="error",
            message=f"None of {len(graph)} pairs reached min_matches.",
            see_also="tuning.md#nothing-matched",
        )
        raise ValueError(
            f"no image pair survived matching: {len(graph)} attempted, best "
            f"sampled count {max(sampled_counts) if sampled_counts else 0}, "
            f"min_matches={p.min_matches}, min_certainty={p.min_certainty}, "
            f"setting '{p.setting}'. Lower min_certainty to 0 first -- it removes "
            f"correspondences before geometry ever sees them."
        )

    # No feature_index: there is no global keypoint table to index into. Each pair
    # is matched independently, so the same physical point has an independently
    # estimated position in every pair, and the tracker must merge by proximity.
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
        confidence=np.concatenate(conf_blocks),
    )

    inliers = np.array(inlier_counts, dtype=float)
    sampled = np.maximum(np.array(kept_sampled, dtype=float), 1.0)
    ratio = float(np.mean(inliers / sampled))
    components = connected_components(n_images, kept_pairs)
    mean_planarity = float(np.mean(planarity)) if planarity else None

    out.metric("pairs_matched", len(kept_pairs),
               direction="higher_better", healthy=(1, None))
    out.metric("matches_per_pair", round(float(inliers.mean()), 1),
               direction="higher_better", healthy=(500, None))
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
               direction="higher_better", healthy=(0.4, None))
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
               direction="lower_better")
    # D: no band. Zero weak pairs is unreachable on any exhaustive sweep of a
    # capture that visits more than one place -- pairs that share no content are
    # SUPPOSED to be dropped, and this module's own tuning file says a pair it
    # cannot link is evidence the gap is real. The band also fought the fix for
    # a thin weakest link: raising min_matches makes this number worse by
    # definition. Count, not verdict.
    out.metric("weak_pairs", weak_pairs, direction="neutral")
    out.metric("mean_certainty", round(float(np.mean(certainties)), 3),
               direction="higher_better", healthy=(0.5, None))
    out.metric(
        "certainty_floor_effect",
        round(floor_removed / max(floor_total, 1), 3) if p.min_certainty > 0 else None,
        direction="neutral",
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
        None,  # detector-free: no keypoint table to cite, so there is no
        # identity to agree about and the rates are undefined rather than 0,
        np.concatenate(xy_blocks) if xy_blocks else np.zeros((0, 4), np.float32),
    )
    out.metric("cycle_merge_rate",
               None if merge_rate is None else round(merge_rate, 6),
               direction="lower_better")
    out.metric("cycle_split_rate",
               None if split_rate is None else round(split_rate, 6),
               direction="lower_better")

    out.diagnostic(
        "detector_free_output",
        severity="info",
        message=(
            "These matches carry no feature_index; the tracker must merge "
            "endpoints by proximity."
        ),
        suggested_actions=[
            "Set the tracker's merge_eps_px to 3-4px at 640px, scaled with the resize.",
            "Read the tracker's merge_headroom -- it is the only under-merge signal.",
        ],
        see_also="limitations.md#no-feature_index",
    )

    if len(components) > 1:
        out.diagnostic(
            "broken_chain",
            severity="error",
            message=(
                f"The view graph has {len(components)} components, sizes "
                f"{components[:5]}."
            ),
            suggested_actions=[
                f"Raise window above {p.window}; each step is a full dense match per pair.",
                f"Lower min_matches below {p.min_matches} if the links are thin but real.",
            ],
            see_also="tuning.md#graph_components-above-1",
        )

    if ratio < 0.4:
        out.diagnostic(
            "low_inlier_ratio",
            severity="warn",
            message=f"Geometric verification kept {ratio:.0%} of the sampled field.",
            suggested_actions=[
                "Raise min_certainty toward 0.5-0.7 before touching ransac_threshold.",
                f"Try the '{'indoor' if p.setting == 'outdoor' else 'outdoor'}' setting.",
                "Check planarity; a degenerate pair fails verification correctly.",
            ],
            see_also="tuning.md#inlier_ratio-below-04",
        )

    out.note(
        f"RoMa '{p.setting}', detector-free: {len(kept_pairs)} of {len(graph)} "
        f"pairs kept, {inliers.mean():.0f} verified correspondences each from "
        f"{p.max_matches} sampled, inlier ratio {ratio:.2f}, mean certainty "
        f"{np.mean(certainties):.2f}. View graph has {len(components)} "
        f"component(s). No feature_index is emitted -- the tracker merges by "
        f"proximity and merge_eps_px decides whether tracks chain at all."
    )
