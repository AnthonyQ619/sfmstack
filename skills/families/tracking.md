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
`inconsistent_rate`, `split_rate` and the survival curve are all about length,
coverage or self-consistency — a tracker can look excellent on every one of them
and be several pixels off everywhere.

**`trifocal_transfer_px`** is the exception, and it is the number to compare
trackers on. It is a held-out three-view prediction: relative pose and a third
camera fitted from half the tracks common to a frame triple, and the other half's
points predicted into the third view and measured there.

One measurement is one observation of one track in one image — the distance
between where the tracker put the point and where geometry fitted from *other*
tracks says it belongs, in that image's pixels at the working resolution. The
metric is their median. It is the precision axis of the trade above, expressed in
the same units the trade is caused by.

Two views would not do. A matcher verifies pairs *independently*, so a chaining
tracker's observations satisfy every epipolar constraint by construction; three
lines meeting pairwise need not meet at a point, and that is the error which
survives pairwise verification.

Read it **within one scene, across trackers**. It is not comparable across scenes
or image counts — the absolute value depends on the baselines of the sampled
triples.

### Use it as a guard when you move a merge tolerance

Every tracker here has a tolerance that decides when two tracks are one point —
`dedupe_eps_px` on the predictive ones, `merge_eps_px` on the chaining one for
detector-free input. Set it too wide and distinct scene points get fused, which
`track_count` and `avg_track_length` report as an *improvement*: fewer tracks, and
longer ones, because merging concatenates.

**`trifocal_transfer_px` is the metric that sees the fusion.** A merge of two
copies of one point leaves the geometry consistent; a merge of two different points
cannot, so the transfer error climbs. The procedure:

> Raise the tolerance, re-read `trifocal_transfer_px`, and stop when it starts
> climbing.

This runs at the tracker stage, before a reconstruction is spent on the answer.

**It guards a tolerance; it does not choose one.** The reading is flat across a
broad band of usable values and only turns once the tolerance is too wide, so it
tells you where the ceiling is and not where the optimum sits. In particular a
tolerance derived from it — scaling the merge distance by the tracker's own
measured noise — was tested and does not hold: the tolerance that best recovers
known duplicates grows *sub-linearly* in that noise, so the ratio is not a
constant to multiply by.

### The limit of the guard: it holds for a precise tracker and not for a noisy one

Checked against ground-truth poses on three scenes, and it splits by tracker:

| | does a rising `trifocal_transfer_px` predict a worse reconstruction? |
| --- | --- |
| **VGGSfM** | **Yes, on all three.** Its worst tolerances carried its highest readings every time, and on the one scene where merging hurt at every setting, the best row also had the lowest reading. |
| **TAPIR** | **No.** On one scene the reading had no relation to the pose error at all. |

The asymmetry is the same one the whole family file is about. The guard works by
detecting that a merge has fused two *different* points, which shows up as
geometry that no longer closes. A tracker whose own positional error is already
several pixels has geometry that does not close very well to begin with, so the
signal it needs to detect sits inside its own noise floor.

**So: trust the guard where `trifocal_transfer_px` is small, and do not lean on it
where it is large — which is exactly where you would most want a guard.** That is a
limit of the metric, not a tuning problem, and no setting fixes it.

See [`docs/import_lessons.md`](../../docs/import_lessons.md).

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
