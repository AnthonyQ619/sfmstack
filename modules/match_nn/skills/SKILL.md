---
module: FeatureMatchNN
module_version: 1.0.0
upstream: OpenCV 5.x BFMatcher + USAC_MAGSAC
curated_at: 2026-08-07
sources: 5
---

Brute-force descriptor matching with Lowe's ratio test, a mutual consistency
check, and RANSAC geometric verification. CPU-only, deterministic, no weights.

**Use when** you have descriptors and want a baseline. It is the first matcher to
run on any new scene, not because it is the best but because it is the one whose
failures you can read: it has no learned prior to hide behind, so its metrics say
something about the *scene* rather than about the model's training distribution.

**Prefer something else when** `inlier_ratio` stays below ~0.3 after the tuning in
[tuning.md](tuning.md), or the scene is low-texture, repetitive, or has wide
baselines. Those are the regimes learned matchers were built for, and no amount
of ratio-test tuning recovers them. See [limitations](limitations.md).

**Deterministic** in matching; the RANSAC stage uses a fixed OpenCV seed, so
identical parameters give identical artifacts and a re-run is a cache hit.

**The two things worth knowing before you tune anything:**

1. `window` is the biggest lever here, and it is not a matching parameter at all —
   it decides which pairs exist. A track cannot span two frames that were never
   compared. On a 12-image uniform sample of DTU scan1, going from window 1 to
   window 4 took `long_track_fraction` from 0.06 to 0.32 while every matching
   parameter stayed fixed.

2. `graph_components` above 1 is an error, not a warning to weigh against others.
   It means the images fall into groups with no correspondence between them, and
   the reconstruction will come out in that many disconnected pieces however good
   every other metric looks. Fix it before reading anything else.

**Cheapest thing that usually works:** `pairing: sequential`, `window: 3`,
everything else default. Check `graph_components` is 1 and `inlier_ratio` is above
0.5, then move on to the tracker.

**Reading the output:** [artifact.md](artifact.md). The metric most likely to
mislead you is `matches_per_pair` — it is a mean over *surviving* pairs, so
loosening a filter can lower it by admitting thin pairs that were previously
dropped. Read it beside `pairs_matched`.
