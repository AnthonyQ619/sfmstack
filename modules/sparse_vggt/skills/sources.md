---
module: SparseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
---

# Sources

## VGGT: Visual Geometry Grounded Transformer
Wang, Leroy, Cabon, Chidlovskii, Revaud et al. — CVPR 2025 (best paper).
<https://arxiv.org/abs/2503.11651> · <https://github.com/facebookresearch/vggt>

This module uses the **depth head** only, pinned at commit `a288dd0`.

API notes verified against it:

- `model.depth_head(tokens, images=images, patch_start_idx=ps)` returns
  `(depth, confidence)` shaped `(B, N, 518, 518, 1)` and `(B, N, 518, 518)`.
- `model.point_head(...)` returns point maps in VGGT's own world frame — which is
  why this module does not use them. See below.
- Preprocessing follows `load_and_preprocess_images(mode="pad")`, the same
  letterbox as `PoseVGGT`. Here it also decides which pixel an observation samples
  depth from, so getting it wrong reads depth from the wrong place as well as
  mis-scaling the intrinsics.

## Why the depth head rather than the point head

The point maps are expressed in VGGT's own world frame at VGGT's own scale.
Consuming them is correct when the poses also came from VGGT and silently wrong
otherwise: the cloud sits in one frame and the cameras in another, and nothing in
the artifact reports it.

Depth is per-view and frame-agnostic. Unprojecting it with the supplied K and pose
puts the point in the supplied world frame by construction, leaving one scale
ambiguity that is estimated from the tracks and reported with its spread.

Validation that the estimator is right rather than merely producing a number: fed
`PoseVGGT`'s own poses, `depth_scale` comes out at **1.0044** — unity, because the
units already agree. Fed classical poses on the same scene it comes out at 2.1164,
with the same 0.004 spread.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/scenereconstruction.py`,
`Sparse3DReconstructionVGGT`, and `baseclass.py::match_tracks_to_point_maps`.

Four differences, three of them corrections:

1. **It read the point maps directly**, so it was correct only with VGGT poses and
   silently wrong with any other source. This unprojects depth into the supplied
   frame instead.
2. **It took `views[0]`** — the first observation of each track — and accepted
   `conf_maps` as an argument it never read. This picks the observation VGGT is
   most confident about, which is what the confidence maps are for.
3. **Its track filter was `if views.shape[0] < minimum_observation`**, which keeps
   tracks SHORTER than the minimum. Whether that was intended is not recoverable
   from the code; `min_track_len` here keeps tracks that reach it.
4. It had no scale handling at all, because reading the point maps made the
   question invisible.
