---
module: FeatureTrackVGGSfM
module_version: 1.0.0
curated_at: 2026-08-11
---

# Sources

## VGGSfM: Visual Geometry Grounded Deep Structure From Motion
Wang, Karaev, Rupprecht, Novotny — CVPR 2024.
<https://arxiv.org/abs/2312.04563> · <https://github.com/facebookresearch/vggsfm>

Only the **tracker** is used here — VGGSfM's coarse-to-fine point tracker, not its
camera predictor or triangulator. Weights are `vggsfm_v2_tracker.pt` from
`facebook/VGGSfM` on the HuggingFace hub, 186 MB, baked into the image.

Architecture, because it explains two parameters: a `BasicEncoder` at stride 4 with
a further down-ratio of 2 produces a stride-8 correlation map, and coarse tracking
iterates on that (`coarse_iters`). A `ShallowEncoder` at stride 1 then refines
locally (`fine_tracking`). Turning refinement off leaves positions accurate to the
coarse map's resolution, which is several pixels.

## Reached through VGGT's vendored copy, not the vggsfm repository

`vggt.dependency.vggsfm_tracker` and `vggt.dependency.vggsfm_utils`, at vggt commit
`a288dd0`. Same architecture, same weights.

That choice avoids a second research-licensed clone and, more practically, a
pytorch3d dependency: `vggsfm.models.__init__` imports the full `VGGSfM` model,
which pulls in the triangulator, which needs pytorch3d. Nothing this module calls
does.

Three things about the vendored copy worth knowing:

- **It computes no per-observation score.** `refine_track` is called with
  `compute_score=False` and returns `None`, so the `score_threshold` the
  predecessor exposed is inert on this code path. It is not exposed here.
- **Its architecture is hardcoded**, where the vggsfm repo's `TrackerPredictor`
  took hydra configs. The predecessor built those configs and passed a dozen
  architecture parameters through its own signature; none of them can vary here,
  which is why they are absent from this manifest.
- **The import chain is heavier than the code used.** `vggsfm_utils` imports
  `pycolmap`, `hydra` and `lightglue` at module scope, none of which this module
  calls. They are in the image because the import fails without them.

## Licensing

The VGGSfM **weights** are CC-BY-NC 4.0, like the repository they come from.
Recorded rather than enforced, the same treatment as SuperGlue's research licence
and MapAnything's default checkpoint.

## Query frame selection

`generate_rank_by_dino` (in `vggsfm_utils`) ranks frames by DINOv2 CLS-token
similarity and farthest-point-samples a spread. It loads `dinov2_vitb14_reg` from
torch hub — a second 330 MB download, baked alongside the tracker weights, and the
easy one to miss: it only happens under `query_selection: dino`, so an image built
without it works under `interval` and fails under `dino`.

The other two selections are local to this module and are not upstream's. The
predecessor's `interval` anchored at frame 0 and its selection always *prepended*
frame 0 regardless, "matching the VGGT demo behavior". Measured on 8 DTU views,
tracking from frame 0 leaves each point visible in a mean of 1.77 frames against
4.40 from frame 4 — an endpoint of a sequential capture sees the least of the
scene, so both behaviours are dropped here.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/featuretracking.py`,
`FeatureTrackingVGGSfM`.

Differences:

- **No deduplication.** Each query point became its own track, so a point found by
  five query frames entered bundle adjustment five times. Measured: 7329 raw tracks
  where 4033 are distinct — 45% duplicates.
- **Frame 0 always in the query set**, for the reason above.
- **`sorted(...)[:n]` on the ranking**, which returns the numerically smallest
  frame indices rather than the best-ranked ones — so `query_selection` had less
  effect than it appeared to. This module truncates the ranking and *then* sorts.
- **No bounds check.** The tracker extrapolates outside the image; those predicted
  positions were written as observations. Here they are dropped and counted.
- It exposed a `score_threshold` that its own code path could not populate.
