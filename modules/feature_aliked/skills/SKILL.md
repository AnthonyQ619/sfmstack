---
module: FeatureDetectionALIKED
module_version: 1.2.0
upstream: lightglue package (cvg/LightGlue), ALIKED weights
curated_at: 2026-08-08
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 5 parameters documented, starting with `variant` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Descriptor discriminability" |
| you are reading what it wrote | **`artifact`** — the layout of `features/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `keypoints_per_image`, `keypoints_min`, `saturation`.

**Diagnostics it can raise:** `starved_frames`, `cap_binding`, `poor_coverage`, `no_keypoints`.

## What this module is for


Learned detector-descriptor with a deformable sampling head that adapts its
receptive field per keypoint. 128-d float descriptors, fewer parameters than
SuperPoint. GPU, weights baked into the image.

**Use when** triangulation quality is the constraint and match count is already
sufficient. ALIKED's advantage is sub-pixel *localisation*, which shows up
downstream as lower reprojection error rather than as more matches.

**Prefer SuperPoint when** matches are scarce — its 256-d descriptors are more
discriminative, and LightGlue's SuperPoint weight set is the more heavily
exercised path.

**The mistake to avoid: `detection_threshold` is 0.2 here and 0.0005 in
SuperPoint** — three orders of magnitude apart. Copying a value across the two
gives either everything or nothing, and it is the single most likely error when
swapping detectors. The module's failure message says so explicitly.

**`variant` is the parameter with the most range.** `aliked-n16rot` is trained
with rotation augmentation and is the answer to in-plane rotation, which
SuperPoint handles poorly and which SIFT handles by construction.

**Its LightGlue weights are a different set** (`aliked`, 128-d input) from
SuperPoint's. `FeatureMatchLightGlue` infers this from provenance, because the
wrong set produces confident nonsense rather than an error.

**Reading the output:** [artifact.md](artifact.md).
