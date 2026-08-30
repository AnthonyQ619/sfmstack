---
module: FeatureDetectionSuperPoint
module_version: 1.1.0
upstream: lightglue package (cvg/LightGlue), SuperPoint weights
curated_at: 2026-08-07
sources: 3
---

Self-supervised detector and descriptor trained jointly, so the keypoints it finds
are the ones its descriptors describe well. 256-d float descriptors. GPU, weights
baked into the image.

**Use when** a GPU is available and the scene has illumination variation, moderate
texture, or wide baselines — the regimes where SIFT's contrast filter starves or
its descriptor stops matching. It is the intended partner for
[LightGlue](../../match_lightglue/skills/SKILL.md), whose `superpoint` weight set
is the most exercised path in that package.

**Prefer SIFT when** there is no GPU, or the scene is high-texture and well-lit —
SuperPoint's advantage narrows to nothing there and SIFT costs no weights and no
model load. Prefer ALIKED when keypoint *localisation* matters more than
descriptor discriminability.

**Sparser than SIFT by design.** 2048 here is roughly comparable to 4096 there,
because SuperPoint applies NMS on its own score heatmap and does not emit the
redundant near-duplicate detections that SIFT's cap has to filter. Do not read a
lower keypoint count as a worse detector.

**`nms_radius` is a real spatial control**, which SIFT does not offer at all.
Raising it is the direct fix for clustered detections, where with SIFT you would
have to go via `contrast_threshold` and hope.

**Weights are baked into the image**, not downloaded at run time. A container that
fetches weights on first use fails on an air-gapped host, re-downloads on every
cold start because the cache is in the ephemeral layer, and turns the first call
into a multi-minute stall that the duration estimator learns as normal.

**Reading the output:** [artifact.md](artifact.md). Note `mean_score` is on
SuperPoint's own scale and is not comparable to ALIKED's.
