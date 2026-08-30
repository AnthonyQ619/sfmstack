# Feature tracking — choosing a tracker

Everything that produces `tracks/v1`. Three modules, and they sit at three points
on **one** trade.

---

## The trade

**Track length and positional precision move in opposite directions, and the same
property drives both.**

A **chaining** tracker (`FeatureTrackUnionFind`) builds tracks from verified
two-view matches. A track can only be as long as the view graph's connectivity
allows — it dies at every missing edge — and **when the matcher is detector-based**
its observations are *detected* keypoints in every frame, so they carry the
detector's sub-pixel accuracy.

**That precision claim holds only for detector-based input, and the whole trade
inverts without it.** A detector-free matcher has no keypoints to cite: it emits
coordinates of its own, and a coarse-to-fine one quantises **one endpoint of every
match** onto a lattice while refining only the other. Measured on such a capture,
one side of every correspondence took 76 distinct x-values, each an exact multiple
of the lattice pitch, against 22,000 continuous values on the other — so half of
every chained observation carried up to half a cell of pure quantisation error, and
that set the floor the precision metric sat on. Halving the pitch lowered the
reading, which is the falsifying check.

On that capture a predictive tracker won **both** ends of this table: 1.8× the
reach *and* 3.4× the precision. So read the row below as describing a
detector-based chain. Where the matcher is detector-free, chaining has no precision
advantage to trade, and the comparison has to be run rather than assumed.

A **predictive** tracker (`FeatureTrackVGGSfM`, `FeatureTrackTapir`) is given
keypoints in a few query frames and predicts where they land everywhere else.
Nothing truncates the track, because there is no view graph to have a hole in. But
the observations are predictions, and the precision floor is set by THE MODEL'S
OWN WORKING RESOLUTION RELATIVE TO THE SCENE -- which is a fact about the module,
not about predictive tracking. One of these modules runs at the scene's working
resolution and pays no resampling penalty at all; the other resamples to a fixed
square and pays the ratio between that square and the scene's working resolution.
On captures where that ratio ran well above one, the fixed-square module's transfer
error came out several times the chaining tracker's -- consistently, in the same
direction, and by a margin far outside what either tracker spans under its own
parameter changes.

**Read that ratio before paying for the run.** The fixed-square module publishes
its resampling size as a PARAMETER DEFAULT, so `sfm_describe_module` answers this
against the scene's working resolution without running anything. The
full-resolution module does not publish one, and there the fact has to be read
from the run note afterwards -- but it is also the module that has no penalty to
find.

```
                    reach                              precision
  chaining          bounded by the view graph          detector sub-pixel
                                                       (detector-BASED input only;
                                                        detector-free forfeits it)
  predictive        bounded by nothing                 bounded by the MODULE's
                                                       working resolution, which
                                                       differs between the two
```

**The precision half of that table is a claim about DETECTOR-BASED input, and
that qualifier carries the whole result.** Across a capture sweep driven through
this stage, chaining won precision on detector-based input by margins running from
a few tens of percent to several-fold, and lost decisively on the one capture
whose matcher was detector-free -- which is what the table's parenthesis already
predicts. Two detector-based captures did read better for a predictive tracker,
and both margins were small.

**Price a margin before believing it, and the yardstick is the tracker's own
span.** Sweep one cheap parameter on the tracker you are judging, with nothing
else changed, and record the range this metric covers across that sweep. A gap
between two configurations narrower than that span is not interpretable -- it is
inside the noise the tracker generates by itself. Both of the small margins above
failed that test, so they are unresolved comparisons rather than counter-examples,
and one capture's reader reached that verdict unprompted. Measured spans have run
to roughly one-and-a-half times, which is why a several-fold difference decides a
tracker choice and a twenty-percent one settles nothing. Equal `trifocal_triples`
is a precondition for comparing at all, not a substitute for this test.

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

**Skip this section if you are chaining detector-based matches.** Every tracker
here has a tolerance that decides when two tracks are one point — `dedupe_eps_px`
on the predictive ones, `merge_eps_px` on the chaining one — but the chaining
module's is **inert whenever the matches carry a `feature_index`**, because a node
is then a keypoint identity rather than a position and nothing is merged by
proximity at all. That is the common case, and on it there is no tolerance here to
guard. The section below is live on every predictive run, and on chaining only
where the matcher is detector-free. Set it too wide and distinct scene points get fused, which
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

## Read the bands, not the diagnostics

This stage is where that habit is cheapest to lose. Three of its metrics have gone
outside their published bands with **no diagnostic firing** — a conflict rate in the
gap between its ceiling and a warning that tripped later, a split rate above the
ceiling published at the time with no diagnostic defined at all, and a median track
length under its floor. On one capture the silent one was the real defect, and
fixing it improved every other reading.

**Two of those three have since been retired**: the split-rate ceiling was raised
after it was measured being breached routinely with nothing wrong, and the median
track length was dropped for carrying no information. **Take the bands from the
module manifest and never from a guide** — a guide's numbers are a snapshot and
this paragraph has already gone stale once. A capture reading a split rate between
the old ceiling and the new one followed the stale prose toward a detector
backtrack that the manifest says cannot work, and was saved only by checking the
manifest.

The conflict-rate gap is now closed, but the habit is the point: **check every
published metric against its own band, and treat diagnostics as the second pass.**
And where a metric's own text disagrees with its band — several here are documented
as unreachable given the detector or the pairing in use — the text wins. See
`scene_to_pipeline.md` §3.0.

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

**Read the rotation metric as a LOWER BOUND, because it under-reads on exactly the
captures this rule is about.** It is recovered from dense optical flow, and where
the motion is large the flow fails on most of the frame and the fitted angle
describes whatever slow region survived. Measured against a reconstruction on one
capture, it reported single-digit median rotation with the large-rotation flag at
zero while the true median was past twenty degrees. **A low reading is therefore
not evidence that a capture is slow** — a high one is evidence that it is fast.
Where the reading is low and the capture looks fast, corroborate with the matcher's
per-pair counts before trusting it, and prefer the module whose failure is graceful.

**`ordered` is necessary and nowhere near sufficient, and taken alone this rule has
mispredicted on every capture that tested it.** `SceneTriage`'s `ordered` is a
statement about filenames. What disqualifies a video-trained model is the
**magnitude of the motion between frames**, which `SceneMotion` measures and which
this file did not previously mention: a capture can be perfectly ordered and still
move further between consecutive frames than anything in a video. Read
`rotation_median_deg` and `large_rotation_risk` beside `ordered` — on captures
where the median inter-frame rotation ran to tens of degrees, TAPIR came last of
three by a wide margin.

**The ORDERING is reliable; the symptom this file used to name is not.** It
previously said to confirm with `mean_occlusion` above 0.85 and frames receiving
no observations. Measured across four captures, TAPIR came last on every one --
and `mean_occlusion` read 0.85, 0.79, 0.72 and 0.32, with `mostly_occluded` firing
on some and not others. On the capture reading 0.32 it fired nothing at all, had
the LONGEST tracks of all three trackers, and was still 3.6x the chaining
tracker's transfer error. A reader checking the stated symptom would have cleared
it. **The confirmation is `trifocal_transfer_px`, which is the only reading that
exposed it on every capture.** Where `mean_occlusion` IS high it is a statement
about the capture rather than the query selection -- changing the query frames
left it unmoved.

**Where the query frames land decides the run, and the reading that decides it is
`min_frame_observations`.** The two modules select differently — one ranks frames
by a learned image descriptor and adapts to content, the other places them
positionally and does not — and neither publishes its choice until the run is
over, so this is a check on the result rather than a pre-flight veto.

**A selection landing on frames that look thin is not by itself a reason to change
it.** On a capture where the content-adaptive rule picked the two lowest-density
frames — exactly the trap this paragraph used to warn about — it was still the
only selection of three that left every frame registerable, and both alternatives
that avoided the trap starved a frame to zero observations. Read the metric, not
the choice: a frame no query frame tracks into will not register whatever the
totals say, and which selection avoids that is not predictable from frame
density.

So: if one available selection keeps every frame populated, take it regardless of
which frames it chose. If every available selection leaves a frame at or near
zero, that is a fact about the capture rather than a parameter to tune, and it is
a reason to prefer chaining.

---

## The tracker is where the matcher gets judged, so backtracking is the normal move

**This stage is the first place a matcher's real quality becomes visible, and
going back to change it is expected rather than a failure.** Two-view
verification cannot see a match displaced onto a repeated structure: it is
epipolar-consistent by construction, so `inlier_ratio` reads excellent on exactly
the runs that produce a badly self-contradictory track table. `inconsistent_rate`
is the first reading in the pipeline that sees it.

Across a sweep of captures driven through this stage, the matcher was changed on
the tracker's evidence on more than half of them, and on one the matcher MODULE
was replaced outright — a decision the matching stage had settled the other way,
because the dial that would have saved it was swept only as far as the range
documented at the time.

**What this looks like in practice.** The tracker reports `inconsistent_rate`
above its ceiling. There is no fix on the tracker: `on_conflict` decides what to
do with the damage, not whether it happens. So you re-run the matcher at a
tighter setting, feed the new matches to the same tracker, and read again. One
matcher run plus one tracker run per step, both cheap, and the detector artifact
is shared so nothing upstream of the matcher is rebuilt.

**Do it on this stage's measurements, not on an argument.** A capture whose
description warns about repeated structure is not evidence; `inconsistent_rate`
above its band is. The counter-case is worth as much: on one capture a detector
change that every prose reading recommended was run end-to-end and made the
pipeline worse at every later stage, and on another the inherited value turned
out to be the measured optimum in both directions. A backtrack that is tried and
refuted is a result, and cheaper than carrying the doubt forward.

**Where to stop is not "when the metric is in band".** Tightening keeps lowering
the conflict rate long after it has started buying that by deleting the view
graph. Watch `pairs_matched` against `pairs_proposed`, `min_image_degree`, and
this stage's `max_track_length`. On several captures the setting that finally
cleared the band cost pairs and a degree with `graph_components` still reading 1
— the completeness metrics do not see it. Settling one notch OUTSIDE the band,
with the reason written down, is a legitimate answer.

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
