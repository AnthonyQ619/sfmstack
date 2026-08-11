---
module: PoseVGGT
module_version: 1.0.0
curated_at: 2026-08-10
---

# Tuning PoseVGGT

There is very little to tune — the model is fixed at 518×518 and poses every image
it is shown. Almost all the value is in reading the output correctly.

1. `estimated_focal_ratio` — the one number that can tell you something is wrong.
2. `chunks` — must be 1, or the poses are not in one frame.
3. `baseline_span` — whether anything can be triangulated against these poses.
4. Then triangulate and read the TRIANGULATOR's error; this module has none.

## Reference run

DTU scan1, 12 contiguous images, `max_edge: 1024`, defaults, GPU, in a container:

| metric | value |
|---|---|
| `registered_fraction` | 1.0 (12/12) |
| `estimated_focal_ratio` | 1.095 |
| `median_camera_separation` | 0.395 (arbitrary unit) |
| `baseline_span` | 0.357 |
| `chunks` | 1 |
| runtime | 20.4 s |

Triangulating the same SIFT + exhaustive-NN tracks against these poses:
5899 points, **1.051 px**, `yield` 0.841. The classical poses on identical tracks:
6900 points, 0.365 px, `yield` 0.983.

## The preprocessing that was wrong

Recorded because the failure was silent and the metric is what caught it.

The first version squeezed each image anisotropically into 518×518 and undid the
squeeze per axis. VGGT predicts **fx == fy** — square pixels — and cannot know the
aspect ratio was changed, so the recovered K came out with `fx/fy` = 1.329, which
is exactly 1024/768, and a focal length 1.48× the scene's calibration. It looked
like a model/calibration disagreement and was an input bug.

| | anisotropic squeeze | letterbox |
|---|---:|---:|
| `estimated_focal_ratio` | 1.48 | **1.095** |
| points triangulated | 1315 | **5899** |
| reprojection error | 1.943 px | **1.051 px** |
| `yield` | 0.187 | **0.841** |

Images are now letterboxed the way upstream's `load_and_preprocess_images` does
it: aspect preserved, long side 518, short side padded white to square. One scale
inverts it and the pad offset comes out of the principal point.

**The lesson for any feed-forward module:** a fixed-resolution model has a
preprocessing convention, and getting it wrong degrades results without raising
anything. A metric comparing the model's estimate against something known is how
you find out.

## `estimated_focal_ratio` far from 1.0

On a **calibrated** scene, the estimate and the calibration disagree, and the poses
were computed from the estimate. In order:

1. **Check the scene's calibration was scaled to the working resolution.** A K for
   1600×1200 read against a 1024×768 scene gives a ratio near 1.56, and the bug is
   in the scene, not here.
2. **Trust the calibration** — use `PoseEssentialToPnP`, which takes the
   calibration as given.
3. **Trust VGGT** — and note that downstream modules read the `intrinsics` array
   this module writes, not the scene's, so the choice propagates.

On an **uncalibrated** scene the metric is null and there is nothing to check
against. That is the case this module exists for.

## `chunks` above 1

`max_images_per_pass` split the set. Each chunk has its own world frame and its own
scale, and this module does **not** stitch them — it raises an error diagnostic and
the poses across chunks are meaningless together.

Chunking is a last resort for a set that does not fit in GPU memory. Attention is
quadratic in image count. Prefer sampling fewer images (`SceneLoader`'s
`max_images` with `sampling: uniform`), which gives one consistent frame.

## `baseline_span` low

Camera separations are dominated by a few distant pairs, or the cameras are nearly
coincident. Nothing triangulated against these poses will condition well. No
parameter here recovers translation the capture did not have.

## `dtype`

`bfloat16` is what the model was released with. `float16` saves nothing over it and
has a narrower range; `float32` roughly doubles memory for no measurable gain. The
camera head runs in full precision regardless of this setting — it decodes a
rotation, and half-precision there costs accuracy in the one place this module
cannot recover it.

## Cost

20.4 s for 12 images on an A6000, most of it the aggregator. Cost grows with image
count, not pair count — the opposite of every classical matcher, and the reason
this scales to sets where exhaustive matching does not.
