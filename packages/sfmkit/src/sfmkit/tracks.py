"""Measurements over a `tracks/v1` observation table, shared by every tracker.

In sfmkit rather than in each module for the same reason `write_ply` is: the
number is meant to be compared ACROSS trackers, and a metric each module defines
for itself is not comparable to the one next to it. The tolerance is fixed here and
not exposed as a parameter for exactly that reason -- a `split_rate` measured at
one module's chosen tolerance and another's says nothing about which tracker
fragmented more.
"""

from __future__ import annotations

import numpy as np

__all__ = ["SPLIT_TOLERANCE_PX", "SPLIT_MIN_SHARED_FRAMES", "split_rate"]

# Fixed by the type, not by the module. Two pixels at the scene's working
# resolution is tight enough that two genuinely distinct scene points rarely fall
# inside it, and loose enough to catch the same point placed twice by a tracker
# that predicts positions rather than citing keypoints.
SPLIT_TOLERANCE_PX = 2.0

# Coincidence in ONE frame is not evidence. On a dense detector, two distinct
# keypoints within two pixels in a single view is ordinary; the same two tracks
# landing within two pixels in two different views, at different points in the
# scene, is not. Requiring two shared frames is what turns a proximity test into a
# statement about identity.
SPLIT_MIN_SHARED_FRAMES = 2


def split_rate(
    obs: np.ndarray,
    track_count: int | None = None,
    tolerance: float = SPLIT_TOLERANCE_PX,
    min_shared_frames: int = SPLIT_MIN_SHARED_FRAMES,
) -> float:
    """Fraction of tracks that a proximity test would merge with another track.

    The dual of `inconsistent_rate`. That metric asks whether one track holds two
    scene points -- OVER-merging, which a union-find tracker can do and a
    predictive tracker structurally cannot. This asks the opposite: whether one
    scene point is spread across several tracks, which every tracker can do and
    which `inconsistent_rate` is blind to in all of them.

    `obs` is the (N, 4) `tracks/v1` table: track_id, frame_idx, x, y.

    Grid-hashed rather than pairwise -- cells of side `tolerance` mean two
    observations within it are always in the same or an adjacent cell, so each is
    compared against a bounded neighbourhood instead of every other observation in
    its frame.

    Returns 0.0 for an empty or single-track table, which is the honest value:
    nothing can be split from nothing.
    """
    obs = np.asarray(obs, dtype=np.float64)
    if obs.ndim != 2 or obs.shape[1] < 4:
        raise ValueError(f"obs must be (N, 4), got {obs.shape}")
    if len(obs) == 0:
        return 0.0

    ids = obs[:, 0].astype(np.int64)
    n_tracks = int(track_count if track_count is not None else ids.max() + 1)
    if n_tracks <= 1:
        return 0.0

    tolerance = float(tolerance)
    if tolerance <= 0:
        return 0.0

    frames = obs[:, 1].astype(np.int64)
    # How many DISTINCT frames each unordered track pair coincides in.
    shared: dict[tuple[int, int], int] = {}

    for frame in np.unique(frames):
        rows = np.flatnonzero(frames == frame)
        cells: dict[tuple[int, int], list[int]] = {}
        for r in rows:
            key = (int(obs[r, 2] // tolerance), int(obs[r, 3] // tolerance))
            cells.setdefault(key, []).append(int(r))

        seen_here: set[tuple[int, int]] = set()
        for (cx, cy), members in cells.items():
            neighbours: list[int] = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbours.extend(cells.get((cx + dx, cy + dy), ()))
            for a in members:
                for b in neighbours:
                    if b <= a:
                        continue
                    ta, tb = int(ids[a]), int(ids[b])
                    if ta == tb:
                        # The same track seen twice in one frame is
                        # inconsistent_rate's business, not this metric's.
                        continue
                    if (abs(obs[a, 2] - obs[b, 2]) > tolerance
                            or abs(obs[a, 3] - obs[b, 3]) > tolerance):
                        continue
                    pair = (min(ta, tb), max(ta, tb))
                    # Once per frame per pair: a track pair that coincides at
                    # several keypoints in ONE view has still only agreed once.
                    if pair not in seen_here:
                        seen_here.add(pair)
                        shared[pair] = shared.get(pair, 0) + 1

    parent = list(range(n_tracks))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    merged = 0
    for (a, b), count in shared.items():
        if count < min_shared_frames:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
            merged += 1

    # `merged` is the number of successful unions, which is exactly
    # n_tracks - n_groups. Counting it directly avoids a second pass.
    return merged / n_tracks
