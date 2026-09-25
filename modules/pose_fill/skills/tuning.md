---
module: PoseFill
module_version: 1.0.0
curated_at: 2026-09-25
---

# Tuning

Three parameters. Two of them change nothing about whether a fill is delivered, and
the third is the whole decision.

| Parameter | Default | Effect |
| --- | --- | --- |
| `max_shared_residual` | 0.03 | **The gate.** Above it the fill is refused. |
| `min_shared_cameras` | 6 | How much overlap is required before a fit is attempted. |
| `trim` | 0.2 | Which shared cameras the fit and the residual describe. |

## `max_shared_residual` — the only one that decides anything

The median distance between where the two tables put the cameras they share, after
the similarity, over the span of the core's own cameras. Scale-free by
construction, so it means the same on a studio rig and a city block.

**It is not fitted.** It sits where a fit that has found a common frame plainly
falls below and a fit that has not plainly falls above. Read `shared_residual`
against what a capture of this kind reads rather than against this number, the same
way the corpus reads every other residual.

Raising it to make a capture pass is the one move to avoid. The reading is the only
check the filled cameras get; loosening it does not make the fill better, it makes
the failure silent.

## `min_shared_cameras` — raise it, never lower it

Four is the algebraic minimum for a similarity. Six is the working floor, because a
residual computed on four cameras is a fit to four points and says nothing about
whether the frames agree.

Raising it makes the module refuse more often, which is the safe direction. Do not
lower it to get a capture through: a core sharing fewer than four cameras with the
estimator has not registered enough to be a core.

## `trim` — what the residual is a verdict on

A plain least-squares similarity is pulled by its worst correspondence, and the
worst shared camera is the one most likely to be misplaced in one of the two
tables. Trimming makes the fit describe the cameras that agree.

0.2 matches the trim this corpus uses elsewhere for the same reason. Set it to 0
when you want the residual to be a verdict on the **whole** overlap rather than on
its agreeing part — which is the honest setting if you suspect the disagreement is
spread rather than concentrated. Compare `shared_cameras_kept` against
`shared_cameras` to see which it is.

## What to do when the gate fires

Nothing in this module. There is no setting that makes a drifting estimator agree
with the core, and turning one until the gate passes destroys the only check the
operation has. Deliver the core, name the missing frames, and say the capture was
not fully solved — `plan/pose.md`'s fourth row.

## Audit

**The gate default, the shared-camera floor and the trim rest on nothing measured
in a campaign.** The fill rule they serve is measured — see `sources.md` — but
these three numbers are implementation choices, and the `expected_duration_s` is a
single-machine observation.
