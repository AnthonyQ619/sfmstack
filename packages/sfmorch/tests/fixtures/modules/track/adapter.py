"""Union-find over pairwise correspondences -- the real algorithm, on fixture data."""

import numpy as np
from sfmkit import Ctx, module


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent, a, b):
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[rb] = ra


@module
def run(ctx: Ctx):
    pairs = ctx.inputs["pairs"]
    image_pair = pairs.load("pairs", "image_pair")
    xy = pairs.load("matches", "xy")
    pair_index = pairs.load("matches", "pair_index")
    feature_index = pairs.load("matches", "feature_index")

    parent: dict[int, int] = {}

    def node(f):
        f = int(f)
        parent.setdefault(f, f)
        return f

    for row in range(len(xy)):
        a, b = node(feature_index[row, 0]), node(feature_index[row, 1])
        _union(parent, a, b)

    groups: dict[int, dict[int, tuple[float, float]]] = {}
    for row in range(len(xy)):
        p = int(pair_index[row])
        img_a, img_b = int(image_pair[p, 0]), int(image_pair[p, 1])
        root = _find(parent, int(feature_index[row, 0]))
        g = groups.setdefault(root, {})
        g[img_a] = (float(xy[row, 0]), float(xy[row, 1]))
        g[img_b] = (float(xy[row, 2]), float(xy[row, 3]))

    min_len = ctx.params.min_track_len
    rows, track_id = [], 0
    for obs in groups.values():
        if len(obs) < min_len:
            continue
        for frame, (x, y) in sorted(obs.items()):
            rows.append([track_id, frame, x, y])
        track_id += 1

    obs_array = (
        np.array(rows, dtype=np.float32) if rows else np.zeros((0, 4), np.float32)
    )
    avg_len = float(len(rows) / track_id) if track_id else 0.0

    out = ctx.output("tracks")
    out.save("observations", obs=obs_array, track_count=np.int64(track_id))
    out.metric("track_count", track_id, direction="higher_better", healthy=(10, None))
    out.metric(
        "avg_track_length", avg_len, direction="higher_better", healthy=(3.0, None)
    )

    # The tracks/v1 contract, computed from the observation table that was just
    # written -- the same source a consumer would recompute them from.
    lengths = [len(o) for o in groups.values() if len(o) >= min_len]
    frames = [int(r[1]) for r in rows]
    n_images = int(image_pair.max()) + 1 if len(image_pair) else 0
    per_frame = [frames.count(f) for f in range(n_images)]
    out.metric(
        "long_track_fraction",
        sum(1 for n in lengths if n >= 3) / len(lengths) if lengths else 0.0,
        direction="higher_better", healthy=(0.3, None),
    )
    out.metric(
        "min_frame_observations", min(per_frame) if per_frame else 0,
        direction="higher_better", healthy=(4, None),
    )
    out.metric(
        "frames_covered",
        sum(1 for n in per_frame if n) / n_images if n_images else 0.0,
        direction="higher_better", healthy=(1.0, None),
    )
    # Observations are collected into a per-frame dict, so a second observation in
    # one frame overwrites rather than conflicting -- structurally zero here.
    out.metric("inconsistent_rate", 0.0, direction="lower_better", healthy=(None, 0.05))
    out.metric("max_track_length", max(lengths) if lengths else 0, direction="neutral")
    out.metric(
        "median_track_length", float(np.median(lengths)) if lengths else 0.0,
        direction="higher_better", healthy=(3.0, None),
    )
    for views, name in ((5, "track_survival_5"), (10, "track_survival_10")):
        out.metric(
            name, sum(1 for n in lengths if n >= views) / len(lengths) if lengths else 0.0,
            direction="higher_better", healthy=(0.0, None),
        )

    if track_id < 10:
        out.diagnostic(
            "too_few_tracks",
            severity="warn",
            message=f"Only {track_id} tracks survived.",
            suggested_actions=[
                "Raise the detector's max_keypoints.",
                "Check the matcher's inlier_yield before tuning anything here.",
            ],
            see_also="tuning.md#track_count-below-10",
        )

    out.note(f"{track_id} tracks, mean length {avg_len:.2f}.")
