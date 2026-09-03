---
module: FeatureMatchLoFTR
module_version: 1.7.0
upstream: kornia 0.8.3 (kornia.feature.LoFTR)
curated_at: 2026-08-08
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 7 parameters documented, starting with `setting` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It is not a general-purpose upgrade" |
| you are reading what it wrote | **`artifact`** — the layout of `pairwise_matches/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `pairs_proposed`, `pairs_matched`, `matches_per_pair`.

**Diagnostics it can raise:** `broken_chain`, `low_inlier_ratio`, `degenerate_geometry`, `detector_free_output`.

## What this module is for


Detector-free semi-dense matching, straight from images. No keypoint detection
stage exists in this path at all.

**Use when** the scene has regions no detector can find keypoints in — textureless
walls, smooth surfaces, low-contrast material. That is the one thing no amount of
detector tuning fixes, and it is what this module is for.

**It is the answer to the query** every detector's limitations file names:

```
sfm_find_alternatives(produces="pairwise_matches/v1", not_consuming="features/v1")
```

**It carries no `feature_index`,** because there is no keypoint table to cite. That
absence is a signal: `FeatureTrackUnionFind` branches on it and merges endpoints by
proximity instead of by identity. **You must set the tracker's `merge_eps_px`
accordingly** — its default of 1.5px is far too small for this input.

Measured on a turntable capture of a compact object, 5 contiguous images at 640px, exhaustive, everything else fixed:

| tracker `merge_eps_px` | long_track_fraction | conflict | registered |
|---:|---:|---:|---:|
| 1.5 (default) | 0.078 | 0.002 | **3/5** |
| 3.0 | 0.195 | 0.007 | 4/5 |
| 6.0 | 0.286 | 0.059 | 4/5 |

At the default, tracks barely chain past a single pair and two of five images
cannot be registered. Start at 3-4px for a 640px working resolution and scale with
the resize.

**Prefer a sparse matcher when** the scene has adequate texture. LoFTR is by far
the most expensive matcher here — semi-dense attention over the whole image pair,
quadratic in pair count — and inside the classical detector's envelope it is not
competitive with SIFT.

**`setting` is not cosmetic.** `indoor` (ScanNet) and `outdoor` (MegaDepth) are
separately trained. The wrong one typically halves the match count with no other
symptom.

**Reading the output:** [artifact.md](artifact.md).
