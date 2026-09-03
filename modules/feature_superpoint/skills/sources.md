---
module: FeatureDetectionSuperPoint
module_version: 1.1.0
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

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `keypoints_per_image`, `spatial_coverage` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `max_keypoints`, `detection_threshold`, `nms_radius`, `resize_long_edge` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 21 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.1.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.1.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `keypoints_per_image`, `spatial_coverage` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
