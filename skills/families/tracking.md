# Feature tracking — choosing a tracker

Everything that produces `tracks/v1`. Three modules, and they sit at three points
on **one** trade.

---

## The trade

**Track length and positional precision move in opposite directions, and the same
property drives both.**

A **chaining** tracker (`FeatureTrackUnionFind`) builds tracks from verified
two-view matches. A track can only be as long as the view graph's connectivity
allows — it dies at every missing edge — and its observations are *detected*
keypoints in every frame, so they carry the detector's sub-pixel accuracy.

A **predictive** tracker (`FeatureTrackVGGSfM`, `FeatureTrackTapir`) is given
keypoints in a few query frames and predicts where they land everywhere else.
Nothing truncates the track, because there is no view graph to have a hole in. But
the observations are predictions, and every such model runs at reduced resolution,
so the positional error has a floor set by the resampling before the model
contributes any of its own.

```
                    reach                              precision
  chaining          bounded by the view graph          detector sub-pixel
  predictive        bounded by nothing                 bounded by model resolution
```

The ordering is not a coincidence of one dataset. Predicting rather than matching
buys reach and costs precision, and the further a model runs from the image's
native resolution the more of both you get.

**One metric measures the precision axis and the rest do not.**
`track_count`, `avg_track_length`, `long_track_fraction`, `min_frame_observations`,
`frames_covered`, `inconsistent_rate`, `split_rate` and the survival curve are all
about length, coverage or self-consistency — a tracker can look excellent on every
one of them and be several pixels off everywhere.

**`trifocal_transfer_px`** is the exception, and it is the number to compare
trackers on. It is a held-out three-view prediction: relative pose and a third
camera fitted from half the tracks common to a frame triple, and the other half's
points predicted into the third view and measured there.

Two views would not do. A matcher verifies pairs *independently*, so a chaining
tracker's observations satisfy every epipolar constraint by construction; three
lines meeting pairwise need not meet at a point, and that is the error which
survives pairwise verification.

Read it **within one scene, across trackers**. It is not comparable across scenes
or image counts — the absolute value depends on the baselines of the sampled
triples.

---

## Which end to reach for

**Reach for chaining when the matcher works.** A calibrated, well-textured,
sufficiently overlapped capture — the matcher will verify most pairs, the view
graph will be one component, and nothing else here will beat detected keypoints
for precision. Signals: the matcher's `graph_components` is 1,
`largest_component_fraction` is near 1, `inlier_ratio` is high.

**Reach for predictive when the view graph fragments.** Signals from the matcher:
`graph_components` above 1, a low `largest_component_fraction`, or a
`min_matches_per_pair` that collapses on part of the set. Those tracks are short
because they were *cut off*, and a predictive tracker predicts through the gap. Its
lower precision costs less than structure that does not exist.

**Between the two predictive trackers**, the difference is provenance rather than
degree. VGGSfM's tracker comes from an SfM model and has no notion of image order.
TAPIR comes from video and **image order is genuine input** — a shuffled or
unordered collection is a different and harder problem than the one it was trained
on, and `mostly_occluded` on a capture that should be continuous is the symptom.
On an ordered capture TAPIR reaches furthest; on an unordered one, prefer VGGSfM.

---

## What has NOT been measured

**Nothing here is quantified, deliberately.** The trade above is structural — it
follows from where the observations come from, not from any dataset — and the
guidance is keyed on upstream metrics you have before choosing. The magnitudes are
not, and a single scene's numbers are not a pass-down.

The three questions this file should eventually answer, and the evidence each
needs:

| Question | Needs |
| --- | --- |
| **How much precision does predictive cost, where chaining works?** | Several calibrated, well-overlapped scenes across datasets — not one. |
| **How much reach does chaining lose, where it does not?** | A scene whose view graph genuinely fragments: textureless, weakly overlapped, or wide-baseline. This is the case the predictive trackers exist for and it has not been run at all. |
| **Where is the crossover?** | Both of the above, on scenes that span the range between them. Until then "reach for predictive when the view graph fragments" is a rule with a direction and no threshold. |

Until those are answered, treat the ordering as structural and the magnitudes as
unknown.

---

## Related

- Per-module detail: `FeatureTrackUnionFind`, `FeatureTrackVGGSfM`,
  `FeatureTrackTapir` — each module's `SKILL.md` and `tuning.md`.
- The full experiment, with the parameter sweeps behind it:
  [`docs/import_lessons.md`](../../docs/import_lessons.md).
- Why `inconsistent_rate` and `split_rate` are duals, and why one of them is
  structurally zero for the predictive trackers:
  [`docs/module-contract.md`](../../docs/module-contract.md#feature-tracking).
