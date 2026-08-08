import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    feats = ctx.inputs["features"]
    xy = feats.load("keypoints", "xy")
    image_index = feats.load("keypoints", "image_index")

    n_images = int(image_index.max()) + 1
    keep = ctx.params.keep_ratio

    pair_list, rows, pair_idx, feat_idx = [], [], [], []
    for i in range(n_images - 1):
        a = np.flatnonzero(image_index == i)
        b = np.flatnonzero(image_index == i + 1)
        n = int(min(len(a), len(b)) * keep)
        if n == 0:
            continue
        p = len(pair_list)
        pair_list.append([i, i + 1])
        rows.append(np.concatenate([xy[a[:n]], xy[b[:n]]], axis=1))
        pair_idx.append(np.full(n, p, dtype=np.int32))
        feat_idx.append(np.stack([a[:n], b[:n]], axis=1).astype(np.int32))

    out = ctx.output("pairs")
    out.save("pairs", image_pair=np.array(pair_list, dtype=np.int32).reshape(-1, 2))
    out.save(
        "matches",
        xy=np.concatenate(rows).astype(np.float32)
        if rows
        else np.zeros((0, 4), np.float32),
        pair_index=np.concatenate(pair_idx)
        if pair_idx
        else np.zeros((0,), np.int32),
        feature_index=np.concatenate(feat_idx)
        if feat_idx
        else np.zeros((0, 2), np.int32),
    )

    per_pair = float(np.mean([len(r) for r in rows])) if rows else 0.0
    out.metric("inlier_yield", float(keep), direction="higher_better", healthy=(0.15, None))
    out.metric("matches_per_pair", per_pair, direction="higher_better", healthy=(8, None))

    if keep < 0.15:
        out.diagnostic(
            "weak_matching",
            severity="warn",
            message=f"Inlier yield {keep:.2f} is below 0.15.",
            suggested_actions=["Raise the detector's max_keypoints."],
            see_also="tuning.md#inlier_yield-below-015",
        )

    out.note(f"{len(pair_list)} pairs, {per_pair:.0f} correspondences each.")
