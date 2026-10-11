"""MatchQuantize -- pairwise_matches/v1 -> pairwise_matches/v1, with identity added.

A detector-free matcher runs each pair independently, so one physical point gets an
independently estimated sub-pixel position in every pair it appears in. There is no
keypoint table, `feature_index` is absent, and a correspondence graph that merges by
identity can only build TWO-view tracks. This module supplies the missing identity by
binning endpoint locations per image onto a grid: one occupied cell is one keypoint.

Why a GRID and not a radius. Merging by "within eps of each other" is single-linkage
clustering, and single linkage chains: A within eps of B, B within eps of C, and A two
eps from C, so a dense match field collapses into blobs whose size depends on arrival
order. Rounding to a lattice is a partition -- idempotent, order-independent, and
every cell exactly `grid_px` across. The tracker merges by radius for a different job,
where it has a conflict metric and an under-merge metric to steer by; here the output
is a keypoint TABLE that something else will index into, and it has to be a partition.
"""

from __future__ import annotations

import cv2
import numpy as np
from sfmkit import Ctx, module
from sfmkit.cycles import cycle_rates

MIN_FOR_FUNDAMENTAL = 8


def robust_inlier_mask(xy_a, xy_b, thresh: float, conf: float):
    """MAGSAC inlier mask, or None when the pair admits no model.

    Imported behaviour, not invented: the classical matcher treats a degenerate pair
    and an unsolvable one as the same answer, and so must this, or the two modules'
    `inlier_ratio` readings are not comparable at the same threshold.
    """
    if len(xy_a) < MIN_FOR_FUNDAMENTAL:
        return None
    try:
        _model, mask = cv2.findFundamentalMat(
            np.asarray(xy_a, dtype=np.float64),
            np.asarray(xy_b, dtype=np.float64),
            cv2.USAC_MAGSAC, thresh, conf, 10000,
        )
    except cv2.error:
        return None
    if mask is None:
        return None
    return mask.ravel().astype(bool)


def connected_components(n_images: int, edges) -> list[int]:
    """Component sizes over IMAGES, largest first."""
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


def cell_tables(xy, pair_index, image_pair, n_images, grid):
    """Per-image cell tables, and each endpoint's cell index.

    Returns (cells, rows) where cells[i] is the (k, 2) lattice-point table for image i
    and rows[m] = (cell of endpoint 1, cell of endpoint 2) for match m.
    """
    index: list[dict[tuple[int, int], int]] = [dict() for _ in range(n_images)]
    coords: list[list[tuple[float, float]]] = [[] for _ in range(n_images)]
    rows = np.zeros((len(xy), 2), dtype=np.int64)

    for m in range(len(xy)):
        i, j = image_pair[pair_index[m]]
        for side, img in ((0, int(i)), (1, int(j))):
            x, y = xy[m, 2 * side], xy[m, 2 * side + 1]
            key = (int(round(x / grid)), int(round(y / grid)))
            slot = index[img].get(key)
            if slot is None:
                slot = len(coords[img])
                index[img][key] = slot
                # The lattice point, not the member centroid. The centroid is a
                # better estimate of where the point is, and it is NOT a partition:
                # it depends on which matches happened to land in the cell, so two
                # runs over the same scene with different pairings disagree about a
                # keypoint's position. Measured at the finest useful grid the two
                # are indistinguishable anyway -- 0.9748 against 0.9746 -- so the
                # reproducible one wins.
                coords[img].append((key[0] * grid, key[1] * grid))
            rows[m, side] = slot

    cells = [np.asarray(c, dtype=np.float64).reshape(-1, 2) for c in coords]
    return cells, rows


def resolve_conflicts(rows, pair_index, n_pairs, confidence):
    """Keep at most one match per (cell_i, cell_j) and per cell on either side.

    One cell is one keypoint, and a keypoint matches at most one keypoint per pair.
    Binning can break that, and the break is not cosmetic: a keypoint table with a
    cell claiming two partners is not a valid correspondence set, and a consumer
    that writes it to a database gets whichever row it saw last. The predecessor
    resolved exactly this by last-write-wins, silently.

    Returns (keep mask, duplicates collapsed, conflicts resolved).
    """
    keep = np.zeros(len(rows), dtype=bool)
    dup = conflict = 0
    order_by_pair: dict[int, list[int]] = {}
    for m, p in enumerate(pair_index):
        order_by_pair.setdefault(int(p), []).append(m)

    for p in range(n_pairs):
        members = order_by_pair.get(p, [])
        if not members:
            continue
        if confidence is not None:
            # Highest confidence first, so the kept match is the one the matcher
            # was most sure of rather than the one that happened to be first.
            members = sorted(members, key=lambda m: -float(confidence[m]))
        seen_pair, claimed_i, claimed_j = set(), set(), set()
        for m in members:
            a, b = int(rows[m, 0]), int(rows[m, 1])
            if (a, b) in seen_pair:
                dup += 1
                continue
            if a in claimed_i or b in claimed_j:
                conflict += 1
                continue
            seen_pair.add((a, b))
            claimed_i.add(a)
            claimed_j.add(b)
            keep[m] = True
    return keep, dup, conflict


def multiview_fraction(image_pair, pair_index, rows, keep) -> tuple[float, int, int]:
    """Fraction of correspondence components spanning three or more images.

    The reading this module exists to move. Union-find over (image, cell) nodes, which
    is the same structure a downstream correspondence graph builds, so this is the
    answer that consumer will get rather than a proxy for it.
    """
    parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in np.flatnonzero(keep):
        i, j = image_pair[pair_index[m]]
        a, b = (int(i), int(rows[m, 0])), (int(j), int(rows[m, 1]))
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    members: dict[tuple[int, int], set[int]] = {}
    for node in list(parent):
        members.setdefault(find(node), set()).add(node[0])
    total = len(members)
    multi = sum(1 for imgs in members.values() if len(imgs) >= 3)
    return (multi / total if total else 0.0), multi, total


@module
def run(ctx: Ctx):
    src = ctx.inputs["matches"]
    p = ctx.params
    out = ctx.output("matches")

    image_pair = np.asarray(src.load("pairs", "image_pair"), dtype=np.int64)
    md = src.load("matches")
    xy = np.asarray(md["xy"], dtype=np.float64)
    pair_index = np.asarray(md["pair_index"], dtype=np.int64)
    feature_index = md.get("feature_index")
    confidence = md.get("confidence")
    if confidence is not None:
        confidence = np.asarray(confidence, dtype=np.float64)

    # The refusal, before anything else. Replacing exact identity with a coordinate
    # approximation is strictly worse than keeping it, and a module that silently
    # degraded its input would be impossible to notice from the artifact.
    if feature_index is not None:
        out.diagnostic(
            "already_indexed",
            severity="error",
            message=(
                f"The input already carries feature_index over "
                f"{len(xy)} matches."
            ),
            see_also="limitations.md#detector-based-input-is-refused",
        )
        raise ValueError(
            "these matches already carry feature_index, so they already have exact "
            "keypoint identity and there is nothing for this module to invent. "
            "Binning would replace that identity with a coordinate approximation, "
            "which is strictly worse. Drop this module from the plan. If the goal "
            "was to merge duplicate detections of one physical point, that is the "
            "tracker's merge_eps_px and not this."
        )

    n_images = int(image_pair.max()) + 1 if len(image_pair) else 0
    ctx.progress(0.1, f"{len(image_pair)} pairs, {len(xy)} matches, grid "
                      f"{p.grid_px}px")

    policy = p.on_conflict
    if policy == "confidence" and confidence is None:
        out.diagnostic(
            "no_confidence_to_rank",
            severity="warn",
            message="on_conflict was 'confidence' and the input carries none; "
                    "conflicting matches were dropped instead.",
            see_also="limitations.md#conflicts-need-a-confidence-to-rank",
        )
        policy = "drop"

    cells, rows = cell_tables(xy, pair_index, image_pair, n_images, float(p.grid_px))
    endpoints = 2 * len(xy)
    n_cells = int(sum(len(c) for c in cells))
    ctx.progress(0.4, f"{endpoints} endpoints -> {n_cells} cells")

    keep, dup, conflict = resolve_conflicts(
        rows, pair_index, len(image_pair),
        confidence if policy == "confidence" else None,
    )
    mv_frac, n_multi, n_components = multiview_fraction(
        image_pair, pair_index, rows, keep)
    ctx.progress(0.6, f"{int(keep.sum())} matches kept, multiview_fraction "
                      f"{mv_frac:.3f}")

    # Re-measure the view graph on the OUTPUT. Binning only ever removes matches, so
    # a pair the matcher kept can fall under the floor here, and carrying the input's
    # numbers forward would describe a match set that no longer exists.
    kept_pairs, out_xy, out_pair, out_feat, out_conf = [], [], [], [], []
    inlier_frac, counts = [], []
    for pr in range(len(image_pair)):
        sel = np.flatnonzero((pair_index == pr) & keep)
        if len(sel) < p.min_matches:
            continue
        new_index = len(kept_pairs)
        kept_pairs.append((int(image_pair[pr, 0]), int(image_pair[pr, 1])))
        out_xy.append(xy[sel])
        out_pair.append(np.full(len(sel), new_index, dtype=np.int32))
        out_feat.append(rows[sel].astype(np.int32))
        if confidence is not None:
            out_conf.append(confidence[sel])
        counts.append(len(sel))
        mask = robust_inlier_mask(xy[sel, :2], xy[sel, 2:4],
                                 float(p.ransac_threshold),
                                 float(p.ransac_confidence))
        inlier_frac.append(0.0 if mask is None else float(mask.mean()))

    if not kept_pairs:
        raise ValueError(
            f"no pair survived binning at grid_px={p.grid_px} with "
            f"min_matches={p.min_matches}: {len(xy)} input matches became "
            f"{int(keep.sum())} after {conflict} endpoint-cell conflicts and "
            f"{dup} collapsed duplicates. A grid this coarse is fusing distinct "
            f"correspondences -- lower it."
        )

    payload = dict(
        xy=np.concatenate(out_xy),
        pair_index=np.concatenate(out_pair),
        feature_index=np.concatenate(out_feat),
    )
    if out_conf:
        payload["confidence"] = np.concatenate(out_conf)
    out.save("pairs", image_pair=np.array(kept_pairs, np.int32),
             match_count=np.array(counts, np.int32))
    out.save("matches", **payload)

    components = connected_components(n_images, kept_pairs)
    degree = [0] * n_images
    for i, j in kept_pairs:
        degree[i] += 1
        degree[j] += 1

    out.metric("pairs_proposed", len(image_pair), direction="neutral")
    out.metric("pairs_matched", len(kept_pairs),
               direction="higher_better", healthy=(1, None))
    # No band on either of the next two. The classical matcher bands them from its
    # own measurements of where pose estimation gets noisy; nothing was measured HERE,
    # and both readings describe the MATCHER's work re-counted on this output rather
    # than anything this module did. Inheriting another module's cut point would be a
    # band with no basis.
    out.metric("matches_per_pair", round(float(np.mean(counts)), 1),
               direction="higher_better")
    out.metric("min_matches_per_pair", int(min(counts)),
               direction="higher_better")
    out.metric("inlier_ratio", round(float(np.mean(inlier_frac)), 3),
               direction="higher_better")
    out.metric("graph_components", len(components),
               direction="lower_better", healthy=(None, 1))
    out.metric("largest_component_fraction",
               round(components[0] / n_images, 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("min_image_degree", int(min(degree)) if degree else 0,
               direction="higher_better", healthy=(2, None))

    # Now computable, and it was null on the way in. The three-view test needs
    # keypoint identity to have something to disagree about; supplying that identity
    # is this module's whole job, so the metric the input could not report is
    # exactly the one that now measures whether the job was done safely.
    merge_rate, split_rate, _chains = cycle_rates(
        np.array(kept_pairs, np.int32), payload["pair_index"],
        payload["feature_index"], payload["xy"])
    out.metric("cycle_merge_rate",
               None if merge_rate is None else round(merge_rate, 6),
               direction="lower_better")
    out.metric("cycle_split_rate",
               None if split_rate is None else round(split_rate, 6),
               direction="lower_better")
    # Null, not a number: this module fits no homography and measuring one here
    # would be a second opinion on the matcher's geometry, not a reading about
    # anything this module did.
    out.metric("planarity", None, direction="lower_better")

    out.metric("multiview_fraction", round(mv_frac, 4),
               direction="higher_better", healthy=(0.05, None))
    out.metric("cells_per_endpoint", round(n_cells / max(endpoints, 1), 4),
               direction="neutral")
    conflict_rate = conflict / max(len(xy), 1)
    out.metric("conflict_rate", round(conflict_rate, 4),
               direction="lower_better", healthy=(None, 0.2))

    if n_multi == 0:
        out.diagnostic(
            "no_multiview_tracks",
            severity="error",
            message=(
                f"All {n_components} correspondence components span fewer than "
                f"three images at grid_px={p.grid_px}."
            ),
            see_also="tuning.md#multiview_fraction-is-zero-or-near-it",
        )
    if conflict_rate > 0.2:
        out.diagnostic(
            "high_conflict_rate",
            severity="warn",
            message=(
                f"{conflict_rate:.0%} of input matches lost their endpoint cell "
                f"to another match at grid_px={p.grid_px}."
            ),
            see_also="tuning.md#conflict_rate-is-high",
        )

    out.note(
        f"Binned {len(xy)} matches on {len(image_pair)} pairs at "
        f"{p.grid_px}px: {endpoints} endpoints became {n_cells} keypoint cells, "
        f"{int(keep.sum())} matches kept ({conflict} endpoint-cell conflicts, "
        f"{dup} duplicates collapsed), {len(kept_pairs)} pairs above "
        f"min_matches={p.min_matches}. multiview_fraction {mv_frac:.3f} "
        f"({n_multi} of {n_components} components span 3+ images), which was 0 "
        f"on the input by construction."
    )
