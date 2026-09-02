---
module: FeatureDetectionALIKED
module_version: 1.2.0
upstream: lightglue package (cvg/LightGlue), ALIKED weights
curated_at: 2026-08-08
sources: 3
---

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
