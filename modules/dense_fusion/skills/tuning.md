---
module: DenseFusion
module_version: 1.1.0
curated_at: 2026-09-16
---

# Tuning DenseFusion

There is one setting worth moving, `min_num_pixels`, and one decision already made
before this module ran: whether the stereo pass used the geometric check. The rest
are tolerances nobody has measured.

## The fusion curve

Measured on a corpus of studio orbits, one stereo pass per capture, every setting
re-fused from it and scored against reference geometry. The shape was the same on
every capture:

- **Lowering `min_num_pixels` trades accuracy for completeness, monotonically.**
  Each step down fills rim and thin structure and places a little more of the cloud
  where it should not be. There is no free step; there is a good region.
- **The good region is a few pixels either side of the default.** Inside it, the
  overall score is nearly flat — completeness and accuracy exchange almost evenly —
  so the choice is about which of the two the deliverable needs.
- **Below it, accuracy collapses.** At the loosest settings the cloud grows several
  times over and most of the growth is noise. This happened on every capture, and
  far harder when the stereo pass ran without the geometric check, where the
  loosest setting leaves nothing verifying anything.
- **The capture sets the height of the curve, not its shape.** The hardest capture
  in the corpus was less accurate at every setting, and lost accuracy faster as the
  setting fell.

## Stepping down, and when to stop

There is no reference geometry on a real capture, so accuracy cannot be read.
`point_count` can, and it carries the signal:

**While each step down grows the cloud by a modest, steady factor, it is adding
surface. The step that roughly doubles the cloud or more is adding noise — go back
up one.** On every capture measured, that jump arrived exactly where accuracy began
to fall away. It also arrived earlier and larger on the hardest capture, so the rule
stops sooner where lowering hurts more.

`point_ratio_to_source` is the same count against the fusion the stereo pass was
delivered with, which makes the steps easy to compare. Compare **step to step**, not
each setting to the source alone: the rule is about the jump between neighbours.

When the deliverable is accuracy first, stay at or above the default. When it is
coverage, take the lowest step the rule allows. Raising the setting well above the
default gives a cleaner cloud and erodes whatever is seen from few views.

**And when the deliverable names neither, it is accuracy** — see
[SKILL.md](SKILL.md), step 3. That resolves what reads as a conflict with `DenseMVS`:
its "Delivering a dense cloud" names one step below the default, and this file's
coverage branch names the lowest step the rule allows. They are not two rules for one
situation. **The delivery anchor is `DenseMVS`'s**, and this file's stepping is how to
explore around it once coverage has actually been asked for. Two captures reached the
two settings by those two routes and had nothing to choose between them.

**The doubling rule is a break in the trend, not a threshold, and off a studio orbit
it can fail to give you one.** Compare each step's growth against the step before it
and stop where the factor jumps. On built and vegetated sites the growth instead
accelerated smoothly — one capture stepped 1.2, 1.4, 1.8 with no break to find — and
the rule cannot be applied as written. When no jump appears, do not keep stepping down
looking for one: stay at the anchor, which is the accuracy default the paragraph above
gives you.

## The geometric check was decided upstream

`input_type: auto` fuses whatever the stereo pass produced, and that is almost
always right: a workspace made with the check has both kinds of depth map, and
auto takes the checked ones. Forcing `photometric` on such a workspace fuses the
unchecked maps. Those are an intermediate of the checked run, not what a stereo pass
run without the check delivers, so this is not a cheap way to answer that question.

To compare with and without the check, it takes two `DenseMVS` runs with
`keep_workspace: true`. `DenseMVS`'s tuning records which was the better measured
trade.

## It produced nothing

`no_points`. First read the **input** artifact's own `point_count`: if the stereo
pass delivered a cloud, the evidence is there and `min_num_pixels` is simply too
strict for this capture — lower it. If the input's cloud was empty too, the problem
is in PatchMatch, and `DenseMVS`'s tuning, "Nothing survives the filters", is where
to go. Nothing here can recover it.

## What here rests on nothing

`max_reproj_error`, `max_depth_error` and `max_normal_error` are COLMAP's defaults
and have never been moved in a measured run. `check_num_images` likewise. Treat any
advice about them as untested. The bands above describe studio orbits of compact
subjects; the stopping rule has not yet been checked on a different kind of
capture.
