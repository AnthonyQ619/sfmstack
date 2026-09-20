---
module: DenseFusion
module_version: 1.1.0
upstream: colmap/colmap stereo fusion, via pycolmap-cuda12 4.1.1
curated_at: 2026-09-16
sources: 3
---

## Before you run it

**Its input must be a `DenseMVS` output made with `keep_workspace: true`.** That is
not a default, so the `DenseMVS` output you already have almost certainly does not
qualify. The next step is always the same, and it is one call:

```
sfm_replay(run_id=<your run>, from_artifact=<the DenseMVS dense artifact>,
           overrides={"keep_workspace": true})
```

The replay re-runs that `DenseMVS` step with every other setting unchanged, so it
pays for the stereo pass once more and keeps what fusion needs. Then run this
module on the replay's `dense` output, as many times as there are settings to
compare. Each of those runs is seconds.

Run this module against an output without the workspace and it fails immediately,
naming that same call. Nothing is lost when that happens.

## Where to go next

| If | Fetch |
| --- | --- |
| choosing a setting, or a run came back empty | **`tuning`** — the measured fusion curve and the rule for stepping it |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot reach anything PatchMatch decided" |
| you are reading what it wrote | **`artifact`** — what the output carries and what it does not |
| you want to know where a claim came from | **`sources`** |

**First readings on this module's output:** `point_count`, and
`point_ratio_to_source` compared across the settings you tried.

**Diagnostics it can raise:** `no_points`.

## What this module is for

`DenseMVS` does two different things in one run. PatchMatch produces **evidence** —
a depth and a normal per pixel, and which views agree — and it costs minutes per
view. Fusion applies **policy** to that evidence — how many pixels must agree before
a point exists — and it costs seconds. Because they ship together, trying a second
policy normally means paying for the evidence twice, so in practice nobody does.

This module is fusion on its own, run on evidence that was kept. It is the same
COLMAP call with the same options, so a setting here gives the cloud `DenseMVS`
would have given at that setting.

**Use it to explore a capture that does not behave like the ones measured.** On a
capture like those, you do not need it: set `fusion_min_num_pixels` and
`geom_consistency` directly on `DenseMVS` and take one run —
`DenseMVS`'s tuning, "Delivering a dense cloud", gives the region. Reach for this
when that region is in doubt for the capture in hand: an unusual subject, an
unusual rig, a first cloud that looks wrong in a way the region does not explain.

**It is not a way to fix a stereo pass.** Filters, the geometric check and the
choice of source views all act inside PatchMatch, before anything reaches this
module. If the holes are there in the depth maps, no fusion setting fills them; that
is a new `DenseMVS` run.

## The workflow, end to end

1. `DenseMVS` with `keep_workspace: true` — or replay an existing one with that
   override, as above. Choose `geom_consistency` there; it is fixed from then on.
2. `DenseFusion` at the setting the stereo pass was delivered with, as the anchor,
   then one step lower at a time. Read `point_count` after each.
3. Stop at the step before the one that roughly doubles the cloud —
   [tuning](tuning.md#stepping-down-and-when-to-stop).

   **When nothing says whether the deliverable wants accuracy or coverage, it wants
   accuracy**, so take the anchor setting and step down only as far as the rule allows,
   never past it. The cost of the wrong choice is not symmetric: a cloud carrying the
   points a looser setting admits is not merely less accurate, it misplaces anything
   fitted to it afterwards, and a later stage cannot tell those points from the rest. A
   thinner cloud loses coverage and nothing else. Step toward coverage when the task
   says so, and say in the run summary which way you took it.
4. Deliver that artifact. The workspace is large and nothing here deletes it: say so
   in the run summary, so whoever owns the storage can remove it —
   [limitations](limitations.md#the-workspace-stays-on-disk).

## Provenance

The fusion curve and the stopping rule were measured on a corpus of studio orbits
of compact subjects, every setting scored against reference geometry. That the
module reproduces `DenseMVS`'s own fusion was checked directly: re-fusing a kept
workspace at the delivered setting gave the delivered cloud. Everything about the
three disagreement tolerances is COLMAP's documentation, not measurement.
Claim-by-claim: the `sources` skill.
