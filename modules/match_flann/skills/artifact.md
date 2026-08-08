---
module: FeatureMatchFLANN
module_version: 1.0.0
produces: pairwise_matches/v1
curated_at: 2026-08-07
---

# Reading a FeatureMatchFLANN artifact

## Layout

Identical to `FeatureMatchNN`'s, deliberately:

```
data/pairs.npz
    image_pair       (M, 2) int32     [image_i, image_j]
data/matches.npz
    xy               (N, 4) float32   [x1, y1, x2, y2]
    pair_index       (N,)   int32     row of image_pair
    feature_index    (N, 2) int32     rows of the features artifact's keypoints
    confidence       (N,)   float32   1 - (best distance / second best)
```

Everything in [`FeatureMatchNN`'s artifact notes](../../match_nn/skills/artifact.md)
applies — the flat layout, the global `feature_index`, what `confidence` means, and
what is deliberately absent.

The two modules produce interchangeable artifacts. That is the point: a consumer
cannot tell which matcher ran except by reading provenance, so swapping them is a
one-line change anywhere downstream.

## `confidence` is computed from approximate distances

`1 - d1/d2` where both `d1` and `d2` come from the approximate search. At high
`match_agreement` this is indistinguishable from the exact value; at low agreement
it is systematically optimistic, because a missed true nearest neighbour makes the
returned best look more distinctive than it is.

Do not compare `confidence` distributions across the two matchers without checking
`match_agreement` first.

## `match_agreement` is a single-pair spot check

Not an average over the run. It is measured on the **first pair that produced any
matches**, by brute-forcing that one pair and comparing.

That makes it cheap and slightly arbitrary. It is a smoke test for the
approximation, not a rigorous estimate — a scene with heterogeneous content could
have one easy pair and many hard ones. If the number matters to a decision, run
`FeatureMatchNN` on the same features and compare `inlier_ratio` directly.

It is `null` when `measure_agreement` is off, or when no pair produced matches
before the check could run.

## Which index was used

Not stored as an array. It follows from the features artifact's `binary` flag —
LSH for binary descriptors, randomised KD-trees for float — and the parameters that
configured it are in `produced_by.params`, hence in the artifact id.

So a KD-tree run and an LSH run on the same scene are distinct artifacts, and
`sfm_compare` will show `trees` / `lsh_tables` among the diverging parameters.
