---
module: FeatureDetectionSIFT
module_version: 1.1.0
upstream: OpenCV 5.x cv2.SIFT_create
curated_at: 2026-08-08
sources: 4
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 6 parameters documented, starting with `max_keypoints` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Repetitive structure" |
| you are reading what it wrote | **`artifact`** — the layout of `features/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `keypoints_per_image`, `keypoints_min`, `saturation`.

**Diagnostics it can raise:** `starved_frames`, `cap_binding`, `poor_coverage`.

## What this module is for


Classical scale- and rotation-invariant keypoint detection with RootSIFT
descriptors. CPU-only, deterministic, no weights to download, seconds per image.

**Use when** the scene is well lit and genuinely textured — building facades with
real surface detail, cluttered tabletops, textured objects on a turntable — and
especially when the capture has wide baselines or large rotations, which SIFT
handles by construction.

**Prefer something else when** the scene is low-texture or photometrically
unstable across frames.

**On a repetitive scene, change the MATCHER and keep these keypoints.** The
failure this module has on repeated structure is a matching failure wearing a
detector's name: near-identical patches produce near-identical descriptors, and it
is the *ratio test* that then cannot separate them. Swapping to a more invariant
detector makes the wrong match more confident, not less — it reaches the wrong way.
A joint matcher that reasons over the whole image, which accepts these descriptors
directly, is the fix. See [limitations](limitations.md#repetitive-structure).

**And ask connectivity before you ask about repetition.** If the capture also
covers ground quickly between adjacent frames, the connectivity question outranks
this one and can send you to a learned detector after all — for a completely
different reason. `skills/families/detection.md` has the order.

**Deterministic**, so re-running with identical parameters is a cache hit, and
comparing two parameter settings is a clean A/B with no seed noise.

**Cheapest thing that usually works:** leave everything at defaults and set
`max_keypoints` from what downstream needs — 4096 for a first look, 8192+ once
you know track survival is the binding constraint. If keypoint counts are low at
the default cap, the contrast filter is binding rather than the cap, and
`contrast_threshold` is the knob. See [tuning](tuning.md).

**Reading the output:** [artifact.md](artifact.md). Note that `keypoints_min`
matters more than the mean — one starved frame breaks the track chain through it
regardless of how good the average is.
