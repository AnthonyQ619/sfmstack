---
module: FeatureDetectionSuperPoint
module_version: 1.0.0
curated_at: 2026-08-07
---

# Sources

## SuperPoint

**DeTone, Malisiewicz, Rabinovich, "SuperPoint: Self-Supervised Interest Point
Detection and Description", CVPRW 2018.**

Trained by Homographic Adaptation: a base detector is bootstrapped on synthetic
shapes, then self-labelled on real images across many random homographies, keeping
the points that survive. That procedure is why its keypoints are repeatable under
viewpoint change — and also why they are **not** repeatable under rotation beyond
what the homography sampling covered, which is the limitation in
[limitations.md](limitations.md#rotation).

The detector and descriptor share an encoder and are trained jointly. That is the
substantive difference from SIFT, where detection and description are separately
designed and the descriptor has to cope with whatever the detector hands it.

## The implementation

`lightglue.SuperPoint` from **cvg/LightGlue**, which is the SuperPoint-Pretrained
weights repackaged with a consistent interface. Installed from git in
`docker/runtime-lightglue/Dockerfile` — the first module dependency here that comes
from a repository rather than an index, which is the case the containerisation is
meant to make routine.

Defaults are the package's own: `detection_threshold=0.0005`, `nms_radius=4`,
`descriptor_dim=256`.

## Why weights are baked at build time

Not from a paper; a deployment decision, recorded because it is easy to get wrong.

`docker/runtime-lightglue/cache_weights.py` runs during the image build and
populates `TORCH_HOME=/weights`. A container that instead downloads on first use
fails on an air-gapped host, re-downloads on every cold start (the cache lives in
the ephemeral layer), and makes the first call take minutes — which the service's
`DurationEstimator` then learns as this module's normal cost, so every later call
is scheduled around a number that describes a one-off.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/features.py`, `FeatureDetectionSP`
(lines 484+), backed by a vendored copy of SuperPoint at
`sfmcore/models/features/detectors/superpoint.py`.

Differences:

- **Vendored source versus a pinned dependency.** The predecessor carried the model
  code in-tree, so upstream fixes required a manual copy and the version in use was
  whatever had been pasted. Here it is a pinned git install in one Dockerfile.
- **`max_keypoints` was the only exposed parameter** (default 1024).
  `detection_threshold` and `nms_radius` were fixed at the vendored defaults, so
  the two knobs that decide whether the cap or the threshold binds were not
  reachable.
- **Weights were untracked files in the source tree.** The overview of the
  predecessor records 4.8 GB of untracked weights inside the repo; this repo's
  `.gitignore` refuses them by rule and the images carry them instead.
