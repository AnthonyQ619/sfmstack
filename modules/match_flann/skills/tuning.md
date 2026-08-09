---
module: FeatureMatchFLANN
module_version: 1.0.0
curated_at: 2026-08-07
---

# Tuning FeatureMatchFLANN

The first question is not how to tune it. It is whether to use it at all — see the
timing table in [SKILL.md](SKILL.md), where it loses to brute force by 6x on a
normal-sized problem.

Once you are using it, `checks` is the parameter and everything else is secondary.

## Reference run

DTU scan1, 8 contiguous images, 1024px, SIFT at 4096 keypoints, exhaustive pairing:

| setting | time | matches/pair | inlier_ratio | match_agreement |
|---|---:|---:|---:|---:|
| `checks: 50` (default) | 4.2 s | 438.9 | 0.948 | 0.998 |
| `checks: 200` | 11.8 s | 466.8 | 0.961 | 0.999 |
| (`FeatureMatchNN`) | 0.7 s | 466.7 | 0.964 | — |

`checks: 200` reproduces the exact matcher's numbers almost precisely — 466.8
against 466.7 matches per pair — which is the expected behaviour and also the sign
you have tuned yourself back into brute force at 17x the cost.

ORB on the same scene: FLANN/LSH 3.2s at 204 matches per pair against
`FeatureMatchNN` 0.3s at 200. Same conclusion.

## `match_agreement` below 0.9

The approximation is missing true nearest neighbours, and both terms of the ratio
test are affected — the second-best is as approximate as the best.

1. **Raise `checks`.** It is the accuracy dial and the first thing to try. Cost is
   roughly linear.
2. **Raise `trees`** (float descriptors) to 8. More randomised trees means better
   recall for the same `checks`, at higher build cost.
3. **Raise `lsh_tables`** (binary descriptors) toward 20, or `lsh_probe_level` to 3.
4. **Reconsider using this module.** If you need `checks` high enough to fix
   agreement, you have given back the speed that was the reason to be here.

## What approximation does to the ratio test

Worth understanding rather than just tuning around.

Lowe's criterion compares the best match to the **true** second best, and the
published calibration (about 90% of false matches eliminated, about 5% of correct
ones lost) is measured against exact search. With an approximate second-best the
ratio is a slightly different quantity.

In practice, at high agreement, it makes no measurable difference — 0.948 against
0.964 inlier ratio at 99.8% agreement. But if you are porting a tuned `ratio_test`
value from `FeatureMatchNN`, verify it here rather than assuming it transfers.

## `mutual` matters more here

Leave it on. An approximate search is **asymmetric**: matching a→b and b→a can
disagree purely because of index structure, with no ambiguity in the descriptors at
all. The mutual check therefore filters search error as well as matching error,
which is a job it does not have in the exact matcher.

## `graph_components` above 1

Same fix as in the exact matcher — raise `window` or use `exhaustive` — with one
addition specific to this module: a poor search thins *every* pair uniformly, which
can push marginal pairs under `min_matches` and disconnect a graph that would
otherwise be connected. Check `match_agreement` before concluding the capture is at
fault.

## The view-graph parameters

`pairing`, `window`, `ratio_test`, `geometric_model`, `ransac_threshold`,
`min_matches`, `measure_planarity` all behave exactly as in `FeatureMatchNN`,
because they are the same code operating on the search's output. Its
[tuning file](../../match_nn/skills/tuning.md) applies unchanged, including the
window sweep and the warning that `matches_per_pair` falls as the graph improves.

## `inlier_ratio` below 0.3

The geometric model kept less than a third of what the ratio test passed. Before
reaching for the exact matcher, separate the two things that can cause it here:

1. **Search error.** Check `match_agreement` first. Below ~0.9 the approximation is
   returning genuinely different neighbours from the exact search, and those wrong
   matches are exactly what RANSAC is rejecting. Raise `n_checks`, or `trees` for a
   KD-tree index — this is the cause specific to this module.
2. **Everything else.** With `match_agreement` healthy, the approximation is not at
   fault and the [exact matcher's
   guidance](../../match_nn/skills/tuning.md) applies unchanged: tighten
   `ratio_test`, check `planarity` for a degenerate pair, and read
   `ransac_threshold` in working-resolution pixels.

The order matters. Tightening the ratio test to compensate for a bad index throws
away correct matches to hide incorrect ones.
