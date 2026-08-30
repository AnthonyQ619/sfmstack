---
module: PoseEssentialToPnP
module_version: 1.2.0
curated_at: 2026-08-07
---

# Tuning PoseEssentialToPnP

Work in this order. A weak seed pair cannot be repaired by anything later, so it
comes first.

1. Did it seed well? `init_pair_angle` should be comfortably above `init_min_angle_deg`.
2. `registered_fraction` == 1.0?
3. `mean_reprojection_error` below ~1px, and `median_triangulation_angle` above 3°?
4. Only then look at `points_triangulated` / `track_utilization`.

## What a healthy run looks like

**Deliberately not a numeric reference run, and that is a correction.** This
section used to print one capture's metrics under its dataset and scene name, with
its inherited chain named beside them. Two things went wrong with that. A reader
driving that same capture found its own prior answer here and read it as
independent confirmation. And a reader driving a DIFFERENT capture of the same
dataset compared against it, found a large gap, and nearly re-ran detection to
close it — the gap was the subject (a cropped object against a dead backdrop
versus a full one), not the pipeline. The numbers also went stale as the tracking
stage was re-settled, so they described a chain that no longer existed.

**What is stable is the shape, so read for shape:**

- `registered_fraction` is the one unambiguous axis. It is 1.0 or you have a
  problem to name.
- `init_pair_angle` should clear `init_min_angle_deg` by a wide margin, not
  scrape it. A seed that only just clears the floor is worth one probe (see
  below), not an alarm.
- `mean_reprojection_error` sits far under its ceiling on a healthy run, and its
  ratio to `median_reprojection_error` tells you more than either alone — a mean
  well above the median is a few bad observations, not a wrong model.
- `median_triangulation_angle` is the honest metric and the one to judge on. It
  and reprojection error genuinely disagree, and configurations that improve the
  error while lowering the angle are usually buying a smaller, easier model.
- `track_utilization` says how much of the track table survived the filters. Read
  it against reprojection error: high utilization with good error is healthy, low
  with good error means the filters are strict, low with bad error means the
  tracks were wrong. **It is not comparable across `min_track_len` settings** —
  the denominator stays the full input table, so raising that parameter makes
  utilization fall mechanically.

**Do not compare your point count against another capture's.** It is bounded by
the subject: a cropped subject, a dead backdrop, or a capture that is two separate
sites will all return correct results that look like failures beside a full one.

**On the seed pair.** The scorer prefers parallax over match count, so on an
orbit it will usually skip the adjacent pair, which has the most matches and the
least baseline. Seeding on adjacent frames is worth one probe with
`init_min_angle_deg` — but note that index distance is not viewpoint distance on
every capture, so an adjacent-index seed is not by itself evidence of anything.
See `families/matching.md` on that precondition.

## `registered_fraction` below 1.0

Some image had fewer than `min_pnp_inliers` 2D-3D correspondences, or PnP RANSAC
could not find a consistent pose.

Check, in this order:

1. **The tracker's `min_frame_observations`** for the missing frames. A frame the
   tracker barely covers cannot be registered — that is a matching problem two
   stages upstream, not a PnP problem.
2. **The matcher's `window` / `graph_components`.** A frame in its own component
   shares no structure with the model and can never register.
3. **`min_pnp_inliers`** last. Lowering it registers more images by accepting
   weaker evidence, and an image registered at the wrong pose is worse than an
   image left out — it contributes wrong observations to every point it sees.

## `mean_reprojection_error` above 2

- Raise `min_triangulation_angle_deg`. Points from near-parallel rays have huge
  depth uncertainty and drag every pose that later registers against them. This is
  usually the fix.
- Tighten `max_reprojection_error` so bad points are discarded rather than kept.
- Then run global bundle adjustment. This module is greedy and never revisits a
  point once accepted; BA is what corrects the accumulated drift. On the reference
  run BA took 0.376 → 0.253px, a 33% reduction, on a scene whose per-stage numbers
  already looked healthy.

## `median_triangulation_angle` below 3

The structure is poorly conditioned in depth. This can coexist with excellent
reprojection error — a point far along a near-degenerate ray reprojects perfectly
into both views that created it and is still in the wrong place.

Raise `min_triangulation_angle_deg` to 3-5. Expect `points_triangulated` to fall;
that is the trade, and it is the right one if you intend to measure anything.

No parameter recovers missing parallax. See
[limitations](limitations.md#degenerate-captures).

## Local BA — what it buys, measured

Registration is interleaved with a bundle adjustment over the last
`local_ba_window` cameras in **registration order**. This is drift control, not
polish: each new pose is estimated against structure that earlier poses
triangulated, so an error early becomes the frame everything later lives in.

**READ THE IMAGE COUNT COLUMN BEFORE THE RESULT COLUMNS.** Every row below is a
16- or 49-image sequence, i.e. a set materially longer than the default 8-camera
window, where "local" and "global" are different solves and drift has a chain to
accumulate along. **On a set at or below the window size none of that holds**, and
these rows are not predictions for it — see "Short sets" below, where the same
ablation runs the other way.

Measured at `max_edge: 1024`, `pairing: exhaustive`, everything else
at defaults. `final err` is after `BundleAdjustmentGlobal`:

| stack | images | `local_ba` | registered | pose err | final err | points | pose time |
|---|---:|---|---:|---:|---:|---:|---:|
| SIFT + NN | 16 | off | 16 | 0.647 px | 0.236 px | 8749 | 3.0 s |
| SIFT + NN | 16 | **on** | 16 | **0.551 px** | 0.248 px | 8878 | 10.2 s |
| SIFT + NN | 49 | off | 49 | 0.728 px | 0.250 px | 18405 | 11.1 s |
| SIFT + NN | 49 | **on** | 49 | **0.654 px** | 0.262 px | 19235 | 27.1 s |
| SuperPoint + LightGlue | 16 | off | 16 | 1.068 px | 0.657 px | 1627 | 0.9 s |
| SuperPoint + LightGlue | 16 | **on** | 16 | **0.843 px** | 0.669 px | 1672 | 2.5 s |
| SuperPoint + LightGlue | 49 | off | **34** | 0.945 px | 0.628 px | 1014 | 0.9 s |
| SuperPoint + LightGlue | 49 | **on** | **48** | 0.888 px | **0.600 px** | 1380 | 2.0 s |

Read the last two rows first. On the full learned sequence, local BA is the
difference between **34 and 48 of 49 images registered** — drift compounded until
PnP could no longer find `min_pnp_inliers` correspondences, and registration
stalled. That is the failure this parameter exists to prevent, and it is invisible
in every other metric: the 34-image model's reprojection error (0.945 px) is
*better* than the 48-image model's (0.888 px is close, and a smaller model is an
easier one). `registered_images` is the metric that catches it.

Two honest qualifications:

- **`local_ba_gain_px` is four times larger on the learned stack** (0.34-0.39 px
  per solve vs 0.08-0.17 px classical), which is the quantitative form of the
  reason this matters most with learned detectors and trackers: their matches are
  dense and confident enough that PnP reports healthy inlier counts on a pose that
  is already drifting.
- **After global BA the final error is a wash on the sets that fully register.**
  Where every image registers either way, global BA absorbs the difference —
  0.236 vs 0.248 px classical at 16 images, with the *on* run carrying 1.5% more
  points, which is most of that gap. Local BA is not buying final accuracy on a
  short well-connected set. It is buying the model that global BA gets to start
  from, and on the long learned sequence that is 14 more cameras.

So: leave it on, and do not expect the final number to move on an easy scene.

## Short sets — where all of the above inverts

**If the image count is at or below `local_ba_window`, the window is the whole
model.** Every camera is inside it, nothing is held out, and the drift this
parameter exists to bound cannot accumulate because there is no registration chain
to accumulate along. Three consequences, all measured across a seventeen-capture
sweep of twelve-image sets:

1. **Widen the window; do not narrow it.** Reprojection error fell monotonically as
   the window grew toward the image count and then stopped changing past it —
   because past the image count there is nothing left to add. Narrowing it, which
   is what the not-converging section below would otherwise tell you to do, was
   strictly harmful on every capture that tried it.
2. **The ablation can run the other way.** On one exhaustively-matched short set,
   `local_ba: false` gave a *better* raw mean and a worse median. That is the
   robust-loss signature, not a reason to switch it off — the median is the
   statistic that survives a few bad observations — but it does mean the table
   above does not describe this shape.
3. **The one knob that reliably pays is `local_ba_loss_scale`.** See below.

**Why this was not obvious:** nothing distinguishes the two regimes by name. A
twelve-image set and a forty-nine-image set take the same parameters and read the
same metrics, and the guidance was written from the long case. Check the image
count first; it is the cheapest disambiguation in this file.

## `local_ba_loss_scale` — the knob worth reaching for first

**Set it against the run's own residuals, not against `max_reprojection_error`.**
The parameter is a Cauchy scale: residuals beyond roughly this value are
downweighted. The default of 1.0 satisfies "well below `max_reprojection_error`"
(4.0) and is nonetheless several times *above* the residual distribution on a
healthy run, where the median sits in the low tenths of a pixel. A Cauchy loss whose
scale is far above every residual it sees is a quadratic loss: it never engages,
and the robust solve you think you are running is not robust at all.

**The procedure, one run each:**

1. Run at defaults. Read `median_reprojection_error`.
2. Set `local_ba_loss_scale` to roughly that median, or a little above it.
3. Halve it once more. If the median improves again, keep going; when it turns,
   step back.

**What it buys, measured across a seventeen-capture sweep:** twelve of seventeen
captures settled on a non-default value, and none that adopted one went back.
Median reprojection error fell by roughly a quarter to a third. Settled values
clustered between about 0.15 and 0.5 — which is to say, close to each capture's own
median residual, exactly as the mechanism predicts.

**Judge it on `median_reprojection_error` and nothing else.** The mean is expected
to stay flat or rise slightly — that is the documented robust-loss signature, the
bulk pulled down while a few outliers grow. And `local_ba_gain_px` is actively
misleading here: swept downward it rises monotonically straight through the point
where the median turns and starts getting worse, so a reader optimising the gain
picks a setting past the optimum.

**Bracket the turn rather than stopping at the first improvement.** A monotone
improvement under a robust loss could be the loss reshaping residuals it is
directly downweighting; an interior minimum cannot be. Finding the turn is one
extra run and it is what makes the result credible.

## Local BA diverged

`local_ba_diverged` is an **error**, and unlike the warning below it means the run
is not usable: a window solve blew up and the poses above it are not trustworthy.
It is raised when the mean window gain comes back non-finite or absurdly large, and
`local_ba_gain_px` is suppressed to null on that run so the number cannot be read
as a measurement.

**The cause is under-constrained points entering the window solve**, and two
independent captures established it from opposite directions: on one, raising
`min_triangulation_angle_deg` until near-parallel points were excluded was the only
setting of eleven that produced a finite gain; on another, raising `min_track_len`
to 3 was the only setting of eleven that did. A two-view track and a two-degree
parallax point are the same defect — a point the window can move almost freely —
and either exclusion fixes it.

**So, in order:**

1. **Raise `min_triangulation_angle_deg`** until the divergence stops. Check the
   value binds at all first: on several captures the entire 3–5 range recommended
   elsewhere is inert because no surviving point sits in it (see below).
2. **Or raise `min_track_len` to 3**, which excludes two-view tracks. Note this
   costs a large fraction of the model and usually *raises* reprojection error, so
   prefer the angle filter if it works.
3. **If neither works, set `local_ba: false`** to get a usable model, and record
   the configuration — none of the iteration or window knobs touches this.

**It was previously reported as `info` with a first action of "nothing".** Six
captures reached it through five unrelated parameters — a loosened reprojection
filter, a raised seed angle, a matcher swap, default settings, and a *narrowed*
window — and the guidance told all of them to ignore it. There is no safe
direction; the guard is on the value now.

## `min_triangulation_angle_deg` — check that it binds before tuning it

It is described as the most important parameter for accuracy and it is, when it
binds. **On many captures it does not.** Across a seventeen-capture sweep, raising
it through the entire recommended 3–5 range produced byte-identical metrics on five
captures — no surviving point had a ray angle in that interval, so the filter had
nothing to remove.

**The check is one run and it is conclusive:** raise it, and if every metric is
identical, the knob is inert on this capture and no value in that neighbourhood
will do anything. The tell beforehand is `median_triangulation_angle`: where it
sits many times above the threshold, the distribution has no low tail to cut. The
artifact publishes only the median and no distribution, so the run is the only way
to be sure.

**And it has a cliff.** On one capture, raising it to a value inside the
recommended range cost three registrations outright. The documented cost is point
count; **registration is also a cost**, and `registered_fraction` is the thing to
watch when raising it. Raising it far past the recommended range reliably costs
both points and accuracy.

## `local_ba_gain_px` at or below zero

The solves are running and not lowering window reprojection error.

- **If `mean_reprojection_error` is already low, this is the healthy end state.**
  There is no drift to remove. It is an `info` diagnostic, not a warning, for
  exactly this reason.
- **With `local_ba_robust_loss: true` the metric can go slightly negative and the
  solve still be correct.** Ceres is minimising the Cauchy cost; this metric reports
  the raw mean. A solve that pulls the bulk of the residuals down while letting a
  few outliers grow does the right thing and reads as a small negative here.
- **If it is strongly negative** (worse than about -0.05 px consistently), suspect
  the window: `local_ba_window` below ~5 leaves almost no freedom after the two
  fixed cameras, so the solve can only move structure. Note this band is for
  *small* negatives. A value orders of magnitude outside it is a diverged solve,
  not a robust-loss artefact, and now raises `local_ba_diverged` as an error with
  the metric suppressed — see that section.
- **It does not rank settings, and two sweeps proved it.** Across `local_ba_window`
  it rises as the window narrows and the model gets worse; across
  `local_ba_loss_scale` it rises monotonically through the point where the median
  turns. Use it to see that in-loop refinement is doing something. Use
  `median_reprojection_error` to choose between settings.
- **It also understates what local BA is worth.** On a capture reading a gain of
  0.02 px per solve, the ablation — `local_ba: false` — cost 14% of the mean error.
  The per-solve window gain is not the size of the benefit.

Turning `local_ba` off because this metric is near zero saves runtime and gives up
the protection on the frames where it *would* have mattered. Prefer raising
`local_ba_interval`.

## Local BA is not converging

Ceres hit `local_ba_max_iterations`. **This is usually a non-event and the module
now says so**: the diagnostic is raised at `info` when the window is already
consistent — a small gain against the residual — and at `warn` only when there is
real drift left to remove. Hitting the cap is a Ceres termination condition, not a
statement about the model.

**Measured, so that you do not have to spend the runs.** Across a seventeen-capture
sweep it fired on every run of every capture, and:

- **Raising the cap buys nothing where the gain is small.** 25 → 50 gave metrics
  identical to three or four decimal places on most captures. One capture pushed it
  to 200: that *did* convert four of ten solves to converged, at 6.7× the Ceres work
  and 9× the runtime, and **every published metric was bit-identical.** Convergence
  is reachable and it is worth nothing.
- **Narrowing the window made the model worse on every capture that tried it**, by
  4% to 19% on the mean, and cleared the diagnostic on none. On these sets the
  advice is inverted — see "Short sets" above.
- **`local_ba_loss_scale` improved accuracy on every capture that tried it and
  cleared the diagnostic on none.** It is the right knob and it is not a fix for
  this symptom; it fixes a different and more important problem.

**So the honest reading of a persistent `local_ba_not_converging` at `info` is:
ignore it.** Two further measurements make that concrete rather than resigned. The
configuration that came *closest* to clearing it on one capture — robust loss off —
was by a wide margin the worst model that capture produced. And on another, the one
configuration that raised **no diagnostic at all** was `local_ba: false`, which was
11% worse. A reader steering by diagnostics rather than bands would ship the worse
model in both directions.

**If it is raised at `warn`**, the gain is large relative to the residual and the
window genuinely has drift it is not removing. Then, in order:

1. **Check `local_ba_loss_scale`** against the residual distribution, per its own
   section above. This is first because it is the only one of these measured to
   improve anything.
2. **Widen or narrow `local_ba_window` according to the image count.** At or below
   the image count, widen. On a sequence materially longer than the window,
   narrowing is the classical advice and is where it applies.
3. **Then raise `local_ba_max_iterations`**, and watch runtime: it multiplies by
   the number of registrations.

## `track_utilization` low

With good reprojection error, the filters are simply strict — fine. With bad
reprojection error, the tracks are wrong; check the tracker's `inconsistent_rate`
and the matcher's `inlier_ratio` before touching anything here.

**Two comparisons this metric does not support.** Its denominator is the full input
track table, so **raising `min_track_len` makes it fall mechanically** — the
numerator drops as tracks are filtered before triangulation and the denominator
does not. Several readers took that fall as evidence the setting had hurt; it is
not evidence of anything. And it is **not comparable across captures**: a cropped
subject, a mostly-empty frame, or a capture that is two disconnected sites all
bound it for reasons upstream of this module.

**If you want to know which filter is discarding tracks**, the module publishes no
per-filter breakdown and the only available method is differencing: change one
filter, hold the rest, and read the change in `points_triangulated`. Two runs
localise it between the angle filter and the reprojection filter.

## Cost

A small calibrated set runs in a couple of seconds. The dominant costs are
the seed search (quadratic in image count, though only over pairs with enough
shared tracks) and the triangulation sweep after each registration, which is re-run
from scratch every round. Past ~100 images that sweep dominates; the fix would be
incremental rather than full re-triangulation, which is a code change, not a
parameter.
