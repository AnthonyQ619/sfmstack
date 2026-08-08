# Tuning — SceneLoader

This module has no quality metric of its own to maximise; its parameters set the
budget every downstream stage then works within. So the sections below are keyed
by what you observe *downstream*, plus the one metric worth reacting to here.

Sourced claims resolve in [sources.md](sources.md).

---

## `downscale_factor` below 0.4

**Read it as:** more than half the linear resolution is gone. Scale-space
detectors have proportionally less structure to find, and keypoint counts fall
roughly with area, not with linear scale — a 0.25 scale is ~1/16 the pixels.

**Gradient:**

1. Raise `max_edge` (1600 → 2400 → 3200) if a downstream detector is reporting
   starved frames or low coverage.
   *Expect:* keypoint counts rise steeply; matcher and tracker runtime rise with
   them; memory in the features artifact rises linearly with keypoints.
2. If the source images are very large (ETH3D DSLR sets are ~6200 px on the long
   edge), the default 1600 is a ~0.26 scale and this diagnostic will always fire.
   That is often still the right choice — 1600 px is a comfortable working size —
   but decide it rather than inherit it.

**Do not** raise `max_edge` past the point where downstream runtime becomes the
constraint. A detector starved at 1600 is usually better fixed with
`contrast_threshold` than with four times the pixels.

---

## Downstream reports too few images or poor baseline coverage

**Read it as:** `max_images` is capping, or `sampling` picked the wrong subset.

**Gradient:**

1. `sampling: uniform` (the default) spans the whole trajectory. This is what you
   want for a representative look at an unfamiliar scene.
2. `sampling: head` keeps the first N contiguously. Use it when the capture is a
   video and you want genuine frame-to-frame overlap — a uniform sample of a
   1000-frame video gives baselines far too wide to match.
3. Raise `max_images`, or drop it entirely for the final run.

**The distinction matters more than it looks.** Uniform sampling of a sequential
capture produces a set whose motion statistics do not resemble the full set's, so
any scene analysis run on the subset misleads.

---

## `mixed_resolution` is 1

**Read it as:** informational, not a problem — but it invalidates any per-set
scalar scale. See [limitations.md](limitations.md#mixed-source-resolutions).

**Nothing to change here.** The scale arrays already carry per-image values. What
matters is that downstream code indexes them per image rather than taking
`scale[0]`.

---

## Choosing `resize`

| Policy | Use when |
| --- | --- |
| `auto` | Default. Caps the long edge, preserves aspect. Right for classical pipelines. |
| `square` | Required by VGGT-family models, which take letterboxed square input. Pads before scaling so aspect is preserved inside the square. |
| `fixed` | You need an exact resolution, usually to match a model's training resolution. |
| `none` | You need untouched pixels — evaluation against ground truth at native resolution, or a module that does its own resizing. Costs you self-containment: the dataset becomes a runtime dependency of every downstream container. |

**`square` and calibration interact badly.** Padding moves the principal point
relative to the image frame, and this module scales `cx`/`cy` by the resize
factor without accounting for the pad offset. For VGGT-family paths that is moot —
omit calibration entirely, they estimate their own. For anything else, do not
combine `square` with a supplied `calibration_path`.

---

## Observed

*None yet. Populated by the distillation loop.*
