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
