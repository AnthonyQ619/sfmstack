---
module: SparseMapAnything
module_version: 1.1.0
curated_at: 2026-08-11
---

# Sources

## MapAnything: Universal Feed-Forward Metric 3D Reconstruction
Keetha, Karhade, Ramanan, Scherer et al.
<https://github.com/facebookresearch/map-anything> · <https://map-anything.github.io>

Pinned at commit `3d10cf7`, package version 1.1.4. Not on PyPI, so it installs
from the repository — the same arrangement as SuperGlue and VGGT.

Three properties of the model that shape this module.

**It accepts geometry as input.** `intrinsics`, `camera_poses`, `depth_z`,
`ray_directions` and `is_metric_scale` are all optional inputs, and the model
predicts whatever is missing. This is the capability no other model here has, and
it is worth 39% more surviving structure on the reference run.

**It does not adopt the supplied frame.** Measured: the estimated depth scale is
1.9496 with poses supplied against 1.9485 without. The output `camera_poses` and
`pts3d` are in the model's own frame at its own scale regardless. So the module
reads `depth_z`, which is per-view and frame-agnostic, and unprojects it with the
supplied poses.

**It is metric, which makes `is_metric_scale` a trap.** Setting it true asserts
the supplied poses are in metres; the model then rescales its depth to honour that
claim. On SfM poses, whose units are arbitrary, that is always false. Measured, it
moved the scale to 1.3205 and worsened the spread from 0.0059 to 0.0082. It is
hardcoded false rather than exposed as a parameter, because no pose artifact in
this system is metric.

**Confidence is unbounded and near 1 at rest**, like VGGT's, but on a different
scale: 13.97 here against VGGT's 60.60 on the same eight views.

## Preprocessing

`mapanything.utils.image.preprocess_inputs` picks one aspect-preserving target
from a fixed table — 4:3 becomes 518x392 — and centre-crops to reach it exactly.
The whole image set gets one target, chosen from the *average* aspect ratio.

The pixel map from scene coordinates into that frame is recovered from the
intrinsics `preprocess_inputs` returns, rather than reimplemented. A crop-and-resize
is affine, so K in and K out determine it exactly, and the module cannot drift out
of step if upstream changes the table. This is the direct lesson of the VGGT
preprocessing bug recorded in `docs/design/DECISIONS.md`: the resize convention is
where a model wrapper silently goes wrong, so derive it rather than assume it.

## Model licensing

Two checkpoints, same architecture and same API:

| | licence |
|---|---|
| `facebook/map-anything` | CC-BY-NC 4.0 — **the default here**, matching the predecessor |
| `facebook/map-anything-apache` | Apache 2.0, trained on a commercial-safe subset |

The code itself is Apache 2.0. Which checkpoint is baked is a build arg on
`docker/runtime-mapanything/Dockerfile`, so switching is a rebuild rather than a
code change:

```
docker build --build-arg MAPANYTHING_MODEL_ID=facebook/map-anything-apache ...
```

**The default is not commercially usable.** Same treatment as SuperGlue's research
licence: recorded here rather than enforced.

## Baking the weights

`save_pretrained` cannot be used to re-save the model at a fixed path — its config
carries class objects and json refuses them. So the image instead points `HF_HOME`
and `TORCH_HOME` at a baked directory, downloads there at build time, and sets
`HF_HUB_OFFLINE=1` at run time, which turns a cache miss into an immediate error
rather than a network fetch.

Two downloads happen and the second is easy to miss: the checkpoint from the
HuggingFace hub, and the **DINOv2 code** from torch hub. `_from_pretrained` sets
`torch_hub_pretrained=False` so the encoder's weights are not fetched redundantly,
but the repository itself still is.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/scenereconstruction.py`,
`Sparse3DReconstructionMapAnything`.

Differences:

- It squeezed images to 518x518 with `F.interpolate` and scaled intrinsics by
  `518/width` on **both** axes — the same anisotropic-resize bug found in the VGGT
  modules, and here more clearly wrong because upstream's own table has a 4:3
  entry. This uses `preprocess_inputs`.
- It read `pts3d`, the model's point maps, in the model's world frame. That is
  correct only when the poses also came from MapAnything. This unprojects `depth_z`
  with the supplied poses.
- It had no scale handling, because reading point maps made the question invisible.
- It set `is_metric_scale=False` and was right to, with the comment "COLMAP data is
  non-metric". That choice is kept and the measurement behind it is now recorded.
- It accepted `conf_maps` and never read them; the observation chosen per track was
  `views[0]`. This picks the highest-confidence observation.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`, `p05_triangulation_angle`, `point_count`, `observation_count`, and 5 more declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `use_model_mask`, `min_track_len`, `min_confidence`, `amp_dtype` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.1.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`, and 8 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
