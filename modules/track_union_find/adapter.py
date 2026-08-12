"""FeatureTrackUnionFind -- scene/v1 + pairwise_matches/v1 -> tracks/v1.

Disjoint-set merging of two-view correspondences into multi-view tracks, with
explicit handling of tracks that contradict themselves.
"""

from __future__ import annotations

import numpy as np
from sfmkit import Ctx, module, split_rate

PROGRESS_EVERY = 50_000  # union steps between progress reports


def build_nodes_from_feature_index(feature_index: np.ndarray):
    """Exact merging: a node IS a keypoint in the features table.

    `feature_index` cites rows of features/v1, which are already globally unique
    across images, so no re-keying is needed and two matches share a node exactly
    when they cite the same keypoint.
    """
    node_a = feature_index[:, 0].astype(np.int64)
    node_b = feature_index[:, 1].astype(np.int64)
    n_nodes = int(max(node_a.max(), node_b.max())) + 1 if len(node_a) else 0
    return node_a, node_b, n_nodes


GRID_OFFSETS = ((0.0, 0.0), (0.5, 0.0), (0.0, 0.5), (0.5, 0.5))


def proximity_edges(frame: np.ndarray, pts: np.ndarray, eps: float):
    """Edges linking endpoints that a grid of `eps` puts in the same cell.

    Four grids, each offset by half a cell in x, y, or both. A SINGLE grid is not
    enough: two endpoints 0.1px apart that happen to straddle a cell boundary
    land in different cells and never merge, and that straddling is exactly the
    subpixel jitter a dense matcher produces on the same physical point. With
    four offset grids, any two points within eps/2 on each axis are guaranteed to
    share a cell in at least one of them.

    The converse bound is loose -- points up to eps*sqrt(2) apart may share a
    cell -- but merging is transitive here regardless, so an exact radius was
    never on offer. `merge_eps_px` is the guaranteed-merge distance times two.
    """
    edges_a, edges_b = [], []
    for ox, oy in GRID_OFFSETS:
        cell = np.column_stack(
            [frame, np.floor(pts[:, 0] / eps + ox), np.floor(pts[:, 1] / eps + oy)]
        ).astype(np.int64)
        inverse = np.unique(cell, axis=0, return_inverse=True)[1].ravel()

        # Chain each cell's members: m points in a cell need m-1 edges, not m^2.
        order = np.argsort(inverse, kind="stable")
        same_cell = inverse[order][1:] == inverse[order][:-1]
        edges_a.append(order[:-1][same_cell])
        edges_b.append(order[1:][same_cell])

    return np.concatenate(edges_a), np.concatenate(edges_b)


def build_nodes_by_proximity(xy, img_a, img_b, eps: float, ctx: Ctx):
    """Approximate merging for detector-free input.

    A separate, earlier union pass. It has to be its own step rather than extra
    edges thrown into the main one: a node must mean "one feature in one frame",
    and if proximity-merged endpoints stayed distinct nodes, every successful
    merge would look like two observations of one track in the same image --
    which is the signature this module reports as a contradiction. Clustering
    first keeps that signal meaning what it says.
    """
    n = len(xy)
    frame = np.concatenate([img_a, img_b])
    pts = np.vstack([xy[:, :2], xy[:, 2:]])

    edges_a, edges_b = proximity_edges(frame, pts, eps)
    roots = union_all(edges_a, edges_b, 2 * n, ctx, label="clustering endpoints",
                      lo=0.05, hi=0.15)
    cluster = np.unique(roots, return_inverse=True)[1].ravel()
    n_clusters = int(cluster.max()) + 1

    return cluster[:n], cluster[n:], n_clusters


def union_all(
    node_a: np.ndarray,
    node_b: np.ndarray,
    n_nodes: int,
    ctx: Ctx,
    *,
    label: str = "merging",
    lo: float = 0.2,
    hi: float = 0.6,
):
    """Disjoint-set union over every edge, returning each node's root.

    Union by size with path halving. The loop is Python because path compression
    is inherently sequential; at a few hundred thousand matches it costs seconds,
    which is why it reports progress.
    """
    # Python lists, not numpy arrays: this loop does scalar reads and writes, and
    # numpy scalar indexing costs several times what a list index does. The arrays
    # around it stay numpy; only the hot loop is worth de-vectorising for.
    parent = list(range(n_nodes))
    size = [1] * n_nodes

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # halving: shorten the path as we walk
            x = parent[x]
        return x

    total = len(node_a)
    list_a, list_b = node_a.tolist(), node_b.tolist()
    for k in range(total):
        ra, rb = find(list_a[k]), find(list_b[k])
        if ra == rb:
            continue
        if size[ra] < size[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        size[ra] += size[rb]
        if k % PROGRESS_EVERY == 0:
            ctx.progress(lo + (hi - lo) * k / total, f"{label} {k}/{total}")

    ctx.progress(hi, "resolving roots")
    return np.array([find(i) for i in range(n_nodes)], dtype=np.int64)


def build_tracks(node_a, node_b, n_nodes, img_a, img_b, xy,
                 min_track_len, on_conflict, ctx, *, lo, hi):
    """Union the match edges, group into tracks, apply the conflict policy.

    Factored out because the under-merge probe has to run the whole thing a second
    time at a wider tolerance -- measuring the effect on TRACK structure, which is
    the thing that matters, rather than on some cheaper proxy.
    """
    roots = union_all(node_a, node_b, n_nodes, ctx, lo=lo, hi=hi)

    # One node is one observation: a keypoint sits in exactly one frame at one
    # position, however many matches cite it. Building the table per NODE rather
    # than per MATCH is what keeps duplicates out without a dedupe pass.
    node_frame = np.full(n_nodes, -1, dtype=np.int64)
    node_xy = np.zeros((n_nodes, 2), dtype=np.float32)
    node_frame[node_a] = img_a
    node_xy[node_a] = xy[:, :2]
    node_frame[node_b] = img_b
    node_xy[node_b] = xy[:, 2:]

    live = np.flatnonzero(node_frame >= 0)
    root, frame, point = roots[live], node_frame[live], node_xy[live]

    order = np.lexsort((frame, root))
    root, frame, point = root[order], frame[order], point[order]

    # Group index per row: 0 for the first group, incrementing at each root change.
    new_group = np.empty(len(root), dtype=bool)
    new_group[0] = True
    new_group[1:] = root[1:] != root[:-1]
    gidx = np.cumsum(new_group) - 1
    n_groups = int(gidx[-1]) + 1

    # A repeat of (group, frame) means one scene point projected to two places in
    # one view. At least one of the matches that built this track is wrong.
    duplicate = np.zeros(len(root), dtype=bool)
    duplicate[1:] = (~new_group[1:]) & (frame[1:] == frame[:-1])

    conflicted = np.zeros(n_groups, dtype=bool)
    conflicted[gidx[duplicate]] = True
    inconsistent_rate = float(conflicted.mean()) if n_groups else 0.0

    keep = ~conflicted[gidx] if on_conflict == "drop" else ~duplicate
    gidx, frame, point = gidx[keep], frame[keep], point[keep]

    # Re-count after conflict handling: dropping observations changes lengths.
    lengths = np.bincount(gidx, minlength=n_groups)
    survivor = (lengths >= min_track_len)[gidx]
    gidx, frame, point = gidx[survivor], frame[survivor], point[survivor]

    return gidx, frame, point, n_groups, conflicted, inconsistent_rate


def long_fraction_of(gidx, n_groups, min_track_len) -> float:
    """Fraction of surviving tracks seen in 3+ views."""
    if len(gidx) == 0:
        return 0.0
    lengths = np.bincount(gidx, minlength=n_groups)
    lengths = lengths[lengths >= min_track_len]
    return float(np.mean(lengths >= 3)) if len(lengths) else 0.0


HEADROOM_LADDER = (2.0, 4.0, 8.0)


def measure_headroom(xy, img_a, img_b, p, ctx, current: float):
    """How much long_track_fraction would rise at a wider merge tolerance.

    Returns (best improvement, the multiplier that achieved it).

    A LADDER rather than a single doubling. A one-step probe answers only "is the
    tolerance too tight by about a factor of two" -- measured on synthetic data
    with a 4px per-pair spread, a 2x probe reads exactly 0.0 at every tolerance
    from 0.5 to 3.0px, all of which are badly too tight. A metric that is silent
    when the parameter is wrong by an order of magnitude repeats the failure it
    was written to prevent.

    8x is still a bound, not a guarantee. It is a local gradient with a bounded
    lookahead, and the honest way to use it is to follow it: raise the tolerance,
    re-check, repeat until it reads zero.
    """
    best, best_at = 0.0, 0.0
    for step, multiplier in enumerate(HEADROOM_LADDER):
        ctx.progress(
            0.61 + 0.02 * step, f"probing merge headroom at {multiplier:g}x tolerance"
        )
        try:
            wide_a, wide_b, wide_n = build_nodes_by_proximity(
                xy, img_a, img_b, multiplier * p.merge_eps_px, ctx
            )
            wide_gidx, _, _, wide_groups, _, _ = build_tracks(
                wide_a, wide_b, wide_n, img_a, img_b, xy,
                p.min_track_len, p.on_conflict, ctx,
                lo=0.62 + 0.02 * step, hi=0.63 + 0.02 * step,
            )
        except (ValueError, IndexError):
            # The probe must never fail the run it is only measuring.
            continue
        gain = long_fraction_of(wide_gidx, wide_groups, p.min_track_len) - current
        if gain > best:
            best, best_at = gain, multiplier

    # A negative result is informative too: nothing improved, so report the 2x
    # figure rather than a floor of zero, which would hide "already too wide".
    if best <= 0.0:
        try:
            wide_a, wide_b, wide_n = build_nodes_by_proximity(
                xy, img_a, img_b, 2.0 * p.merge_eps_px, ctx
            )
            wide_gidx, _, _, wide_groups, _, _ = build_tracks(
                wide_a, wide_b, wide_n, img_a, img_b, xy,
                p.min_track_len, p.on_conflict, ctx, lo=0.68, hi=0.69,
            )
            return (
                long_fraction_of(wide_gidx, wide_groups, p.min_track_len) - current,
                0.0,
            )
        except (ValueError, IndexError):
            return 0.0, 0.0
    return best, best_at


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    matches = ctx.inputs["matches"]
    p = ctx.params

    n_images = len(scene.load("images", "names"))

    image_pair = matches.load("pairs", "image_pair")
    match_arrays = matches.load("matches")
    xy = match_arrays["xy"].astype(np.float32)
    pair_index = match_arrays["pair_index"].astype(np.int64)

    if len(xy) == 0:
        raise ValueError("the pairwise_matches artifact contains no matches.")

    img_a = image_pair[pair_index, 0].astype(np.int64)
    img_b = image_pair[pair_index, 1].astype(np.int64)

    feature_index = match_arrays.get("feature_index")
    detector_based = feature_index is not None
    if detector_based:
        node_a, node_b, n_nodes = build_nodes_from_feature_index(feature_index)
    else:
        if p.merge_eps_px <= 0:
            raise ValueError(
                "these matches carry no feature_index, so they came from a "
                "detector-free matcher and endpoints must be merged by proximity. "
                "merge_eps_px=0 makes that impossible; use 1-2px at a 1600px "
                "working resolution."
            )
        node_a, node_b, n_nodes = build_nodes_by_proximity(
            xy, img_a, img_b, p.merge_eps_px, ctx
        )

    ctx.progress(0.2, f"{len(xy)} matches over {n_nodes} nodes")
    gidx, frame, point, n_groups, conflicted, inconsistent_rate = build_tracks(
        node_a, node_b, n_nodes, img_a, img_b, xy,
        p.min_track_len, p.on_conflict, ctx, lo=0.2, hi=0.6,
    )

    # Under-merge probe: rebuild the whole thing at twice the tolerance and see how
    # much long_track_fraction would move.
    #
    # `inconsistent_rate` detects OVER-merging and is structurally blind to the
    # opposite error -- splitting one physical point into several tracks produces
    # no same-frame duplicate and no contradiction of any kind. This is its
    # counterpart, and it is the metric that would have caught the synthetic
    # experiment that set merge_eps_px's default: there the endpoints that should
    # merge sat at distance exactly 0.0, so doubling the tolerance changes nothing
    # and the headroom is ~0. On real detector-free input at too tight a tolerance
    # it is strongly positive. See skills/tuning.md.
    #
    # A cheaper probe on CLUSTER COUNT was tried first and does not work: cluster
    # counts are dominated by endpoints seen in a single pair, which dilutes the
    # signal to nothing exactly where it is needed.
    merge_headroom, headroom_at = None, 0.0
    if not detector_based and p.probe_merge_headroom:
        merge_headroom, headroom_at = measure_headroom(
            xy, img_a, img_b, p, ctx, long_fraction_of(gidx, n_groups, p.min_track_len)
        )

    out = ctx.output("tracks")

    if len(gidx) == 0:
        out.diagnostic(
            "too_few_tracks",
            severity="error",
            message="No track survived the conflict policy and length filter.",
            see_also="tuning.md#track_count-below-200",
        )
        raise ValueError(
            f"no tracks survived: {n_groups} group(s) merged, "
            f"{int(conflicted.sum())} were contradictory (on_conflict={p.on_conflict!r}), "
            f"and the rest fell under min_track_len={p.min_track_len}. Raise the "
            f"matcher's window so pairs actually chain, before touching anything here."
        )

    # Dense track ids in [0, track_count), as tracks/v1 requires.
    track_id = np.unique(gidx, return_inverse=True)[1].ravel().astype(np.float32)
    track_count = int(track_id.max()) + 1

    obs = np.column_stack([track_id, frame.astype(np.float32), point]).astype(np.float32)
    out.save("observations", obs=obs, track_count=np.int64(track_count))

    # The other half of inconsistent_rate, at the tolerance tracks/v1 fixes rather
    # than at merge_eps_px -- the point of the metric is comparison across
    # trackers, so a module-chosen tolerance would defeat it. Distinct from
    # merge_headroom, which asks what a LOOSER merge would have changed by
    # rebuilding; this asks what the output as written still holds apart.
    fragmentation = split_rate(obs, track_count)

    ctx.progress(0.95, "computing metrics")

    final_lengths = np.bincount(track_id.astype(np.int64), minlength=track_count)
    per_frame = np.bincount(frame, minlength=n_images)

    avg_len = float(final_lengths.mean())
    long_fraction = float(np.mean(final_lengths >= 3))
    max_len = int(final_lengths.max())
    # The survival curve the predecessor reported, at 3/5/10 views. Its
    # "Fragmentation" and "Obs. per Track" are deliberately absent: the second is
    # avg_track_length renamed and the first is its exact reciprocal.
    median_len = float(np.median(final_lengths))
    survival_5 = float(np.mean(final_lengths >= 5))
    survival_10 = float(np.mean(final_lengths >= 10))
    min_frame_obs = int(per_frame.min())
    frames_covered = float(np.mean(per_frame > 0))

    out.metric("track_count", track_count,
               direction="higher_better", healthy=(200, None))
    out.metric("avg_track_length", round(avg_len, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("long_track_fraction", round(long_fraction, 3),
               direction="higher_better", healthy=(0.3, None))
    out.metric("max_track_length", max_len, direction="neutral")
    out.metric("median_track_length", round(median_len, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("track_survival_5", round(survival_5, 3),
               direction="higher_better", healthy=(0.1, None))
    out.metric("track_survival_10", round(survival_10, 3),
               direction="higher_better", healthy=(0.0, None))
    out.metric("min_frame_observations", min_frame_obs,
               direction="higher_better", healthy=(50, None))
    out.metric("frames_covered", round(frames_covered, 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("inconsistent_rate", round(inconsistent_rate, 4),
               direction="lower_better", healthy=(None, 0.05))
    out.metric("split_rate", round(fragmentation, 4),
               direction="lower_better", healthy=(None, 0.1))
    out.metric(
        "merge_headroom",
        None if merge_headroom is None else round(merge_headroom, 4),
        direction="lower_better", healthy=(None, 0.03),
    )

    if track_count < 200:
        out.diagnostic(
            "too_few_tracks",
            severity="error",
            message=f"Only {track_count} tracks survived; reconstruction will not start.",
            suggested_actions=[
                "Raise the matcher's window so more pairs link, before touching this module.",
                "Raise the detector's max_keypoints.",
            ],
            see_also="tuning.md#track_count-below-200",
        )

    if long_fraction < 0.3:
        out.diagnostic(
            "mostly_two_view",
            severity="warn",
            message=(
                f"Only {long_fraction:.0%} of tracks reach a third view "
                f"(mean length {avg_len:.2f})."
            ),
            suggested_actions=[
                "Raise the matcher's window, or switch it to pairing: exhaustive.",
                "Check the matcher's graph_components -- isolated pairs cannot merge.",
            ],
            see_also="tuning.md#long_track_fraction-below-03",
        )

    if inconsistent_rate > 0.1:
        out.diagnostic(
            "high_conflict_rate",
            severity="warn",
            message=(
                f"{inconsistent_rate:.0%} of merged groups were observed twice in "
                f"one image; the matcher is producing contradictory correspondences."
            ),
            suggested_actions=[
                "Lower the matcher's ratio_test toward 0.7.",
                "Ensure the matcher's mutual check is on.",
            ],
            see_also="limitations.md#contradictory-tracks-come-from-the-matcher",
        )

    if merge_headroom is not None and merge_headroom > 0.03:
        out.diagnostic(
            "under_merged",
            severity="warn",
            message=(
                f"Doubling merge_eps_px would raise long_track_fraction by "
                f"{merge_headroom:+.3f} (from {long_fraction:.3f}) at "
                f"{headroom_at:g}x the current tolerance. Endpoints that are one "
                f"physical point are being split into separate tracks."
            ),
            suggested_actions=[
                f"Raise merge_eps_px toward {p.merge_eps_px * headroom_at:g} and re-check.",
                "inconsistent_rate cannot see this; it only detects over-merging.",
            ],
            see_also="tuning.md#merge_headroom-above-003",
        )

    if min_frame_obs < 50:
        weakest = int(np.argmin(per_frame))
        name = str(scene.load("images", "names")[weakest])
        out.diagnostic(
            "weak_frames",
            severity="warn",
            message=(
                f"Frame {weakest} ({name}) carries {min_frame_obs} observations "
                f"and will likely fail to register."
            ),
            suggested_actions=[
                "Check the detector's keypoints_min for that frame.",
                "Raise the matcher's window so the frame links to more neighbours.",
            ],
            see_also="tuning.md#min_frame_observations-below-50",
        )

    mode = "feature_index" if detector_based else f"proximity ({p.merge_eps_px}px)"
    if merge_headroom is not None:
        at = f" at {headroom_at:g}x" if headroom_at else ""
        mode += f", merge headroom {merge_headroom:+.3f}{at}"
    out.note(
        f"Merged {len(xy)} matches over {n_nodes} nodes by {mode} into {n_groups} "
        f"groups; {int(conflicted.sum())} were contradictory "
        f"(on_conflict={p.on_conflict}). {track_count} tracks survived "
        f"min_track_len={p.min_track_len}: mean length {avg_len:.2f}, "
        f"{long_fraction:.0%} reaching 3+ views, longest {max_len}. "
        f"Weakest frame carries {min_frame_obs} observations; "
        f"{frames_covered:.0%} of frames are covered."
    )
