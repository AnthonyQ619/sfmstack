"""FeatureTrackUnionFind -- scene/v1 + pairwise_matches/v1 -> tracks/v1.

Disjoint-set merging of two-view correspondences into multi-view tracks, with
explicit handling of tracks that contradict themselves.
"""

from __future__ import annotations

import numpy as np
from sfmkit import Ctx, module

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
                      lo=0.05, hi=0.2)
    cluster = np.unique(roots, return_inverse=True)[1].ravel()

    return cluster[:n], cluster[n:], int(cluster.max()) + 1


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
    roots = union_all(node_a, node_b, n_nodes, ctx)

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
    root = roots[live]
    frame = node_frame[live]
    point = node_xy[live]

    ctx.progress(0.7, "grouping observations into tracks")

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

    if p.on_conflict == "drop":
        keep = ~conflicted[gidx]
    else:  # "first" -- keep the earliest observation per frame, discard the rest
        keep = ~duplicate

    gidx, frame, point = gidx[keep], frame[keep], point[keep]

    # Re-count after conflict handling: dropping observations changes lengths.
    lengths = np.bincount(gidx, minlength=n_groups)
    long_enough = lengths >= p.min_track_len
    survivor = long_enough[gidx]

    gidx, frame, point = gidx[survivor], frame[survivor], point[survivor]

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

    ctx.progress(0.95, "computing metrics")

    final_lengths = np.bincount(track_id.astype(np.int64), minlength=track_count)
    per_frame = np.bincount(frame, minlength=n_images)

    avg_len = float(final_lengths.mean())
    long_fraction = float(np.mean(final_lengths >= 3))
    max_len = int(final_lengths.max())
    min_frame_obs = int(per_frame.min())
    frames_covered = float(np.mean(per_frame > 0))

    out.metric("track_count", track_count,
               direction="higher_better", healthy=(200, None))
    out.metric("avg_track_length", round(avg_len, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("long_track_fraction", round(long_fraction, 3),
               direction="higher_better", healthy=(0.3, None))
    out.metric("max_track_length", max_len, direction="neutral")
    out.metric("min_frame_observations", min_frame_obs,
               direction="higher_better", healthy=(50, None))
    out.metric("frames_covered", round(frames_covered, 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("inconsistent_rate", round(inconsistent_rate, 4),
               direction="lower_better", healthy=(None, 0.05))

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
    out.note(
        f"Merged {len(xy)} matches over {n_nodes} nodes by {mode} into {n_groups} "
        f"groups; {int(conflicted.sum())} were contradictory "
        f"(on_conflict={p.on_conflict}). {track_count} tracks survived "
        f"min_track_len={p.min_track_len}: mean length {avg_len:.2f}, "
        f"{long_fraction:.0%} reaching 3+ views, longest {max_len}. "
        f"Weakest frame carries {min_frame_obs} observations; "
        f"{frames_covered:.0%} of frames are covered."
    )
