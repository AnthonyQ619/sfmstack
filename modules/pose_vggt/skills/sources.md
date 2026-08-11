---
module: PoseVGGT
module_version: 1.0.0
curated_at: 2026-08-10
---

# Sources

## VGGT: Visual Geometry Grounded Transformer
Wang, Leroy, Cabon, Chidlovskii, Revaud et al. — CVPR 2025 (best paper).
<https://arxiv.org/abs/2503.11651> · <https://github.com/facebookresearch/vggt>

The model. A transformer that alternates frame-wise and global attention over the
whole image set and reads camera parameters, depth, point maps and tracks off the
aggregated tokens in a single forward pass. This module uses the camera head only.

Read for: why it needs no correspondences at all, and why accuracy is
initialisation-grade rather than final — it is trained to be right about geometry,
not to minimise reprojection error on your scene.

Pinned to commit `a288dd0`; checkpoint `facebook/VGGT-1B` (5 GB), baked into the
base image so no job touches the network.

API notes verified against that commit:

- `model.aggregator(images)` takes `(B, N, 3, 518, 518)` — batch AND frame
  dimensions, so a single set is `images[None]`.
- `pose_encoding_to_extri_intri(pose_enc, image_hw)` returns extrinsics as
  **cam_from_world** 3×4 in OpenCV convention, matching `poses/v1` directly, and
  intrinsics in pixels of the 518-square it was given.
- `load_and_preprocess_images(paths, mode=)` documents the two preprocessing
  conventions: `crop` sets width to 518 and centre-crops height, `pad` fits the
  long side to 518 and pads the short one white. This module implements `pad`
  itself so it can invert it exactly in the intrinsics.
- The checkpoint is saved as a plain `state_dict` at a fixed path rather than left
  in the HuggingFace cache: the cache location follows `HOME`, and the container
  runs as the host uid with `HOME=/tmp`, so a hub-cached file written as root at
  build time is not where the module looks at run time.

**The preprocessing bug this module had, and the measurement that found it:**
squeezing images anisotropically into 518×518 and undoing it per axis produced
`fx/fy` = 1.329 (exactly the 1024/768 aspect ratio) and a focal 1.48× the
calibration, because VGGT predicts square pixels and cannot know the aspect was
changed. Letterboxing took `estimated_focal_ratio` from 1.48 to 1.095, points
triangulated from 1315 to 5899, and reprojection error from 1.943 px to 1.051 px.

## DUSt3R / MASt3R
Wang, Leroy et al., CVPR 2024. <https://arxiv.org/abs/2312.14132>

VGGT's predecessor in approach — pairwise pointmap regression with a global
alignment step. VGGT replaces the alignment with attention across the whole set,
which is why this module has no stitching stage and why chunking is a hard
boundary rather than something it can align away.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/camerapose.py`,
`CamPoseEstimatorVGGTModel`.

Same head, same decode. Differences: it asserted square input (`Height must equal
Width`) to sidestep the intrinsics mapping, where this module letterboxes and
handles any aspect; it rewrote the scene's calibration in place, where this writes
its estimate into its own artifact and leaves the scene alone; and it ran the
camera head inside autocast, where this runs it in full precision because the
decode produces a rotation.
