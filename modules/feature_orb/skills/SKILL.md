---
module: FeatureDetectionORB
module_version: 1.0.0
upstream: OpenCV ORB + ANMS-SSC (Bailo et al. 2018)
curated_at: 2026-08-07
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 9 parameters documented, starting with `max_keypoints` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Scale and viewpoint change" |
| you are reading what it wrote | **`artifact`** — the layout of `features/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `keypoints_per_image`, `keypoints_min`, `saturation`.

**Diagnostics it can raise:** `starved_frames`, `poor_coverage`, `suppression_ineffective`, `no_keypoints`.

## What this module is for


Oriented FAST corners with rotated BRIEF binary descriptors. Roughly an order of
magnitude faster than SIFT, 32-byte descriptors matched by Hamming distance, and
patent-free.

**Use when** throughput matters more than robustness — long sequences, a first
look at a large capture, or any loop you will run many times.

**Prefer SIFT when** the capture has wide baselines, large scale change, or low
texture. ORB's descriptor is genuinely weaker there and it shows up as shorter
tracks rather than as obviously bad matches. See [limitations](limitations.md).

**The thing that makes ORB usable: `suppression: ssc`.** ORB's real problem is not
the descriptor, it is spatial distribution. FAST fires in dense clusters on
high-contrast texture, and OpenCV's `nfeatures` cap keeps the *highest-response*
corners — which are concentrated exactly where texture is already strongest, so
the default selection makes clustering worse. ANMS-SSC selects a spatially even
subset at the same count.

Measured on a controlled-rig capture, 8 contiguous images at 1024px, 4096 keypoints:

| suppression | keypoints/image | spatial_coverage |
|---|---:|---:|
| `none` | 4096 | 0.734 |
| `ssc` | 4096 | 0.850 |

Same count, 16% more of the frame covered, a few milliseconds per image.

**Descriptors are binary**, and the artifact carries a `binary` flag. Matchers
read it to select Hamming distance automatically. A uint8 descriptor matched under
L2 produces confident garbage, which is why the flag exists rather than a
convention.

**Cheapest thing that usually works:** defaults (`ssc`, 4096, `detect_multiplier: 4`).
Then read `spatial_coverage`, not the keypoint count — the count is capped and
tells you almost nothing.

**Reading the output:** [artifact.md](artifact.md).

## Provenance

**Run zero times in any pipeline.** Every claim in these skills is from isolated
testing or carried from the predecessor codebase; nothing here has been exercised
end to end. The first real run is the trigger to re-check all of it.
Claim-by-claim citations: the `sources` skill.
