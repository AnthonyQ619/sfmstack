---
module: FeatureMatchNN
module_version: 1.6.0
produces: pairwise_matches/v1
curated_at: 2026-08-07
---

# Reading a FeatureMatchNN artifact

## Layout

```
data/pairs.npz
    image_pair       (M, 2) int32     [image_i, image_j]
data/matches.npz
    xy               (N, 4) float32   [x1, y1, x2, y2]
    pair_index       (N,)   int32     row of image_pair this match belongs to
    feature_index    (N, 2) int32     rows of the features artifact's keypoints
    confidence       (N,)   float32   1 - (best distance / second best)
```

`M` is pairs **kept**, not pairs attempted. Attempted is
`pairs_matched + weak_pairs`.

## The flat layout

There is no per-pair array-of-arrays and no ragged nesting: every correspondence
in the scene is one row of one table, and `pair_index` says which pair it belongs
to. Slicing pair `k` is `xy[pair_index == k]`.

This is the same decision the features type makes for keypoints, for the same
reason — variable-length per-pair arrays cannot go into an npz without pickling,
and every consumer wants a vectorized table anyway.

## `feature_index` is a global row, not a per-image one

Both columns index directly into the features artifact's `keypoints/xy` table,
which is itself concatenated across images. So:

```python
kp = features.load("keypoints", "xy")
fi = matches.load("matches", "feature_index")
assert np.allclose(kp[fi[:, 0]], xy[:, :2])   # holds exactly
```

No per-image offset table, no translation step. This is what lets the tracker
merge by identity — two correspondences cite the same integer exactly when they
saw the same keypoint — and it is why the tracker's exact path needs no tolerance
parameter at all.

A matcher with no keypoint table to cite (LoFTR, RoMa) omits this array entirely,
and its absence is the signal a consumer needs. The tracker branches on it.

## `confidence`

`1 - d1/d2` from the ratio test: 0 for a match the test barely admitted,
approaching 1 when the nearest neighbour is far closer than the runner-up. It is a
*descriptor* confidence and says nothing about geometric agreement — every match
in the artifact already passed verification, so a low-confidence match here is
geometrically consistent but descriptively ambiguous.

Useful for weighting in bundle adjustment. Not useful for filtering: the ratio
test already did that, and re-filtering on the same quantity just re-applies it.

## What is NOT here

**Rejected matches.** The artifact holds inliers only. If you need to know what
verification discarded, re-run with `geometric_model: none` and compare — that is
the documented diagnostic, and it is why `none` is an allowed setting.

**The estimated F or H.** Deliberately not stored. It is cheap to recompute from
the inliers, it would be a large per-pair array of limited use, and storing a
model estimated from a *superset* of the final inliers invites a consumer to use
it as if it were the final estimate.

**Pairs that were attempted and dropped.** Only their count survives, as
`weak_pairs`. If which pairs failed matters, the pair set is deterministic from
`pairing` and `window`, so it can be reconstructed exactly.
