---
module: PoseVGGT
module_version: 1.0.0
upstream: facebookresearch/vggt @ a288dd0, VGGT-1B checkpoint
curated_at: 2026-08-10
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 2 parameters documented, starting with `max_images_per_pass` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot tell you whether it is right" |
| you are reading what it wrote | **`artifact`** — the layout of `poses/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `registered_fraction`, `registered_images`, `mean_reprojection_error`.

**Diagnostics it can raise:** `intrinsics_disagree`, `chunked`, `degenerate_baseline`.

## What this module is for


Feed-forward camera poses **and intrinsics** from images alone. One transformer
pass over the whole set; no matching, no triangulation, no registration order.
GPU required.

**Use when** correspondences are what is failing — weak texture, repetitive
patterns, wide baselines — or when the scene is uncalibrated. It is what
`PoseEssentialToPnP` names when it refuses an uncalibrated scene.

**Prefer PoseEssentialToPnP when** the scene is calibrated and well textured.
Triangulating one track table against both, the classical poses returned more
points at roughly a third of the reprojection error. VGGT is initialisation-grade;
follow it with bundle adjustment when precision matters.

**And note what this module cannot tell you about itself.** Its reprojection
metrics are null by construction, so nothing in its own artifact answers "is this
right" — the first number that does is a triangulator's yield, one stage later.
Across a seventeen-capture sweep every reader that ran both chose the geometric
branch on exactly that asymmetry, and none of them could have refuted the choice
at the pose stage. What running this module IS reliably worth on a calibrated
scene is `estimated_focal_ratio`: a free, independent check on the calibration the
whole geometric branch rests on.

**It fills `poses/v1` and only `poses/v1`.** The same forward pass also produces
point maps and depth; those are `SparseVGGT` and `DenseVGGT`. Three modules, three
passes — so each can be swapped for a classical counterpart independently, which
a combined module could not.

**Read `estimated_focal_ratio` first.** On a calibrated scene it is the estimate
over the calibration, and far from 1.0 means the two disagree — with the poses
computed from the estimate. It is also the metric that caught a real bug in this
module's own preprocessing; see [tuning.md](tuning.md#the-preprocessing-that-was-wrong).

**`mean_reprojection_error` is null by construction.** There are no
correspondences to measure against. A number derived from VGGT's own point maps
would report how self-consistent the network is, not how accurate it is.
Triangulate against these poses and read the triangulator's error.

**Cheapest thing that usually works:** defaults. 12 images in ~20 s on an A6000.

**Reading the output:** [artifact.md](artifact.md).
