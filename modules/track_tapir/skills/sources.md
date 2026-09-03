---
module: FeatureTrackTapir
module_version: 1.5.0
curated_at: 2026-08-11
---

# Sources

## TAPIR: Tracking Any Point with per-frame Initialization and temporal Refinement
Doersch, Yang, Vecerik, Gokay, Gupta, Aytar, Carreira, Zisserman — ICCV 2023.
<https://arxiv.org/abs/2306.08637> · <https://deepmind-tapir.github.io>

## BootsTAP: Bootstrapped Training for Tracking-Any-Point
Doersch et al., 2024. <https://arxiv.org/abs/2402.00847> · <https://bootstap.github.io>

BootsTAPIR is TAPIR trained with self-supervised bootstrapping on unlabelled real
video. Architecturally it is TAPIR with `extra_convs=True`, and nothing else
distinguishes it.

Checkpoint: `bootstapir_checkpoint_v2.pt` from
`storage.googleapis.com/dm-tapnet/bootstap/`, 209 MB, 54.7M parameters, baked into
the image. At `pyramid_level=1` it loads with **0 missing and 0 unexpected** keys,
which the build step asserts — the module loads with `strict=False` so that a
non-default `pyramid_level` is possible, and `strict=False` would otherwise hide a
mismatched checkpoint completely.

## Two outputs worth knowing about

TAPIR predicts, per point per frame, an **occlusion** logit and an
**expected-distance** logit. The confidence used here is the product
`(1 − σ(occlusion)) · (1 − σ(expected_dist))`, which is what the upstream demos
use. Keeping the occlusion term reported separately as `mean_occlusion` is this
module's addition, and it is what lets "the point left view" be told apart from
"the model cannot localise it".

## Conventions that are easy to get wrong

- **Query points are `(t, y, x)`**, not `(x, y)`. On a non-square image, swapping
  them does not crash — it tracks the transpose of the scene.
- **Output tracks are `(B, N, T, 2)`** — points first, then time. The opposite
  order to VGGSfM's tracker, whose output is `(B, T, N, 2)`.
- **Video is channel-last `(B, T, H, W, 3)` in [−1, 1]**, which is neither torch's
  usual channel-first layout nor the [0, 1] range every other module here uses.

## The package, and `--no-deps`

<https://github.com/google-deepmind/tapnet>, Apache 2.0, at commit `c2cbab8`.

`tapnet`'s declared dependencies are JAX-first — chex, jax, jaxline, optax,
dm-haiku, dm-tree and more — and none of that is on the torch code path.
`tapnet.torch.tapir_model` needs numpy, torch, `dm-tree` and `einshape`, which the
image installs explicitly; `tapnet/__init__.py` is lazy, so importing the torch
submodule never touches the JAX ones. The alternative is a 2 GB JAX stack sitting
unused next to torch, with two frameworks competing for the same GPU allocator.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/featuretracking.py`,
`FeatureTrackingTapir`.

Differences:

- **No deduplication**, as with its VGGSfM tracker. Each query point became its
  own track, so a point found by three query frames entered bundle adjustment
  three times. Measured here: 5506 raw tracks where 2736 are distinct — 50%
  duplicates.
- **No bounds check.** Predicted positions outside the image were written as
  observations.
- **`resize_to` defaulted to None**, so with no explicit setting the model ran at
  the scene's full resolution — far outside its training distribution, and the
  measurements here say 768 is already worse than 384 on every track metric.
- Its `_tapir_visibility_from_logits` returned only the product, so the occlusion
  term was computed and discarded. It is reported here.
- It hardcoded a local checkpoint path
  (`/home/anthonyq/projects/repos/tapnet/checkpoints/...`) with a URL fallback.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `track_count`, `avg_track_length`, `long_track_fraction`, `trifocal_transfer_px`, `split_rate`, `track_survival_5`, and 1 more declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `query_frame_num`, `input_size`, `min_confidence`, `pyramid_level`, `dedupe_eps_px` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.5.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `track_count`, `avg_track_length`, `long_track_fraction`, and 4 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
