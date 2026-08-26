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

    # The pairwise_matches/v1 contract. Consecutive pairing over n_images gives a
    # single chain when every pair survives, and one component per gap when they
    # do not -- computed rather than asserted, so a keep_ratio that drops pairs is
    # visible here exactly as it would be in a real matcher.
    kept = {tuple(p) for p in pair_list}
    parent = list(range(n_images))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in kept:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    roots = [find(i) for i in range(n_images)]
    sizes = {r: roots.count(r) for r in set(roots)}
    out.metric("pairs_matched", len(pair_list), direction="higher_better", healthy=(1, None))
    out.metric(
        "min_matches_per_pair", min((len(r) for r in rows), default=0),
        direction="higher_better", healthy=(8, None),
    )
    out.metric("inlier_ratio", float(keep), direction="higher_better", healthy=(0.5, None))
    out.metric("graph_components", len(sizes), direction="lower_better", healthy=(None, 1))
    out.metric(
        "largest_component_fraction", max(sizes.values()) / n_images,
        direction="higher_better", healthy=(1.0, None),
    )
    # Required by the type: a component count of 1 says the graph did not split and
    # says nothing about how close it came. On this fixture's consecutive chain the
    # end images always sit at degree 1, which is exactly the shape the metric
    # exists to make visible.
    degree = [0] * n_images
    for a_i, b_i in kept:
        degree[a_i] += 1
        degree[b_i] += 1
    out.metric("min_image_degree", min(degree) if degree else 0,
               direction="higher_better", healthy=(2, None))
    # Null, not zero: this fixture does not fit a homography, and reporting 0.0
    # would claim it measured perfectly general geometry.
    out.metric("planarity", None, direction="lower_better", healthy=(None, 0.7))

    if keep < 0.15:
        out.diagnostic(
            "weak_matching",
            severity="warn",
            message=f"Inlier yield {keep:.2f} is below 0.15.",
            suggested_actions=["Raise the detector's max_keypoints."],
            see_also="tuning.md#inlier_yield-below-015",
        )

    out.note(f"{len(pair_list)} pairs, {per_pair:.0f} correspondences each.")
