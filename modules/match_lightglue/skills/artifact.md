---
module: FeatureMatchLightGlue
module_version: 1.6.0
produces: pairwise_matches/v1
curated_at: 2026-08-08
---

# Reading a FeatureMatchLightGlue artifact

## Layout

Identical to the classical matchers', deliberately:

```
data/pairs.npz
    image_pair       (M, 2) int32
data/matches.npz
    xy               (N, 4) float32   [x1, y1, x2, y2]
    pair_index       (N,)   int32
    feature_index    (N, 2) int32     rows of the features artifact's keypoints
    confidence       (N,)   float32   LightGlue match confidence
```

A consumer cannot tell which matcher ran except by reading provenance. That is the
point — swapping matchers is a one-line change anywhere downstream, which is what
made the comparison table in [SKILL.md](SKILL.md) possible at all.

## `confidence` means something different here

In the classical matchers it is `1 - d1/d2` from the ratio test — a *descriptor*
distinctiveness measure. Here it is LightGlue's own match confidence, a learned
quantity from the assignment layer.

They are both in [0, 1] and they are **not** comparable. Do not carry a confidence
threshold across matchers, and do not compare confidence distributions between them.

`mean_match_score` in the metrics is the mean of this over verified matches, and is
the primary signal for a mismatched weight set.

## Matches are a partial assignment

LightGlue produces at most one match per keypoint per pair, by construction — the
assignment layer enforces it. So within a single pair there are no many-to-one
matches, which is what the classical matchers need the `mutual` check to achieve.

That does **not** prevent contradictory tracks. Across different pairs, union-find
can still fuse two distinct scene points, and on a capture inside the classical
detector's envelope it did so at 20x the classical
rate. Per-pair injectivity is not global consistency.

## Which weight set ran

In `produced_by.params` as `weights`, and therefore part of the artifact id — but
note that `auto` is recorded as `auto`, not as the resolved value. The resolved set
is named in the narrative body.

That is a small wart: two runs with `weights: auto` on differently-produced features
have different resolved weights and the same parameter value. They still get
different artifact ids because the input artifact ids differ, so nothing is
conflated — but reading the parameter alone does not tell you what ran.

## What is NOT here

**Unmatched keypoints.** Only matched pairs are recorded.

**The pruning and early-exit behaviour.** `depth_confidence` and `width_confidence`
change how much computation each pair received; nothing records how many layers a
given pair actually used. If that mattered for diagnosis it would be an additive
per-pair array.

**Per-pair confidence spread.** `mean_match_score` is a mean over verified matches
across the whole run. A capture with a few easy pairs and many hard ones reads the
same as a uniformly mediocre one.

## Metrics that mislead

`matches_per_pair` and the tracker's `long_track_fraction` both look better for
LightGlue than for the classical matchers on such a capture, and the final reconstruction is
worse. Read the tracker's `inconsistent_rate` and the bundle adjuster's
`reprojection_error_after` before concluding anything from match counts.

`inlier_ratio` has a higher healthy floor here (0.7) than for classical matchers
(0.5), because the raw matches are already learned-filtered. The same number means
something worse.
