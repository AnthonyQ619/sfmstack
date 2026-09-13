---
module: PoseEssentialToPnP
module_version: 1.3.0
upstream: OpenCV essential matrix + SQPnP, the COLMAP incremental strategy
curated_at: 2026-09-13
sources: 4
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 13 parameters documented, starting with `min_triangulation_angle_deg` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Uncalibrated scenes" |
| you are reading what it wrote | **`artifact`** — the layout of `poses/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `registered_fraction`, `registered_images`, `points_triangulated`.

**Diagnostics it can raise:** `uncalibrated_scene`, `no_viable_initial_pair`, `partial_registration`, `high_reprojection_error`, `points_escaped`, `local_ba_not_converging`, and 2 more.

## What this module is for


Incremental structure-from-motion: seed on a well-conditioned pair, then
repeatedly register whichever image has the most 2D-3D correspondences.
CPU-only, deterministic given fixed RANSAC seeds, no weights.

**Use when** the scene is calibrated and the tracks are healthy. It is the
classical baseline and the only pose estimator here that needs nothing but
OpenCV.

**Prefer something else when** the scene is uncalibrated (VGGT and MapAnything
estimate intrinsics and do *better* without a supplied K), or when the capture is
degenerate — planar, pure rotation, or too sparsely sampled to have parallax. See
[limitations](limitations.md).

**It consumes `tracks/v1`, not pairs.** That is the main departure from the
predecessor and it changes the failure mode: this module cannot be run without a
tracker, but a single unregisterable frame no longer truncates everything after
it. It gets `valid=False` and the run continues.

**Local BA runs during registration, not after it** (`local_ba`, on by default).
A sliding window of the last 8 registered cameras is refined with the two oldest
held fixed. This is drift control: each new pose is estimated against structure
earlier poses triangulated, so an early error becomes the frame everything later
lives in. On the full 49-image DTU set with SuperPoint + LightGlue it is the
difference between **34 and 48 images registered** — drift compounded until PnP ran
out of correspondences and registration stalled. On the classical stack, where
nothing stalls, it lowers pose error ~10% and the final post-BA number not at all.
The [tuning file](tuning.md#local-ba--what-it-buys-measured) has the full table.

**When points escape, the pipeline solves twice.** A point that leaves the image
during a window solve is counted in `escaped_points`, never judged. Above zero it
is the trigger for a second solve at a wider window, which the service runs once
the model is refined and keeps unless it fails or the verifier vetoes it — see
[limitations](limitations.md#escaped-points-start-a-second-solve).

This does not replace [BundleAdjustmentLocal](../../ba_local/skills/SKILL.md).
That module repairs an existing `sparse_model/v1` at a window you choose; this
happens while the model is being built, which is the only time the drift can still
be removed cheaply.

**Scale is arbitrary and unrecoverable.** The seed pair's baseline is fixed to
unit length, so every distance downstream is in that unit. Nothing in an image-only
pipeline can fix this; it needs a known length in the scene or metric depth.

**The two metrics that matter most, in order:**

1. `registered_fraction` — below 1.0, some images have no pose. Consumers must
   honour the `valid` array; `poses/v1` makes it mandatory for exactly this reason.
2. `median_triangulation_angle` — low means the structure is poorly conditioned in
   depth *even when reprojection error looks fine*. The two genuinely disagree,
   and this one is the more honest.

**Cheapest thing that usually works:** defaults. On a small calibrated set with a
connected view graph they register every image at sub-pixel reprojection error in
seconds, and across a seventeen-capture sweep defaults were the settled answer on
about a third of them. The one parameter worth reaching for beyond that is
`local_ba_loss_scale` — see [tuning.md](tuning.md).

**Reading the output:** [artifact.md](artifact.md). This module does not refine
globally — run [BundleAdjustmentGlobal](../../ba_global/skills/SKILL.md) after it.

## Provenance

Exercised across **109 runs at version 1.2.0** in the seventeen-capture sweep of
two benchmark families (`evidence/CORPUS.txt`) — the most-run module in the
registry; no capture outside them. Claim-by-claim citations: the `sources` skill.
