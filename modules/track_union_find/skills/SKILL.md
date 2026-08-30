---
module: FeatureTrackUnionFind
module_version: 1.4.0
upstream: classical disjoint-set track merging
curated_at: 2026-08-07
sources: 4
---

Merges two-view correspondences into multi-view tracks by disjoint-set union.
Pure numpy — no GPU, no weights, no dependencies beyond what sfmkit already
requires.

**Use when** you have a `pairwise_matches/v1` from any matcher. It is the only
route from pairs to tracks that does not involve a learned tracker, and it works
identically for detector-based and detector-free matchers.

**Prefer something else when** you want tracks estimated directly from images —
VGGSfM, TAPIR and similar consume the scene and produce `tracks/v1` without a
matcher at all. Those are the right answer when the matcher is the bottleneck, not
this module. See [limitations](limitations.md).

**Deterministic.** Given the same matches and parameters, the same tracks.

**The one thing to understand before reading any metric here:**

This module has almost no power over its own outputs. Track length is set by the
view graph the matcher built; track count is set by the keypoints the detector
found; track correctness is set by whether the matches were right. Its parameters
can only filter and choose a conflict policy.

So when a metric here is unhealthy, the fix is nearly always **upstream**. The
module's real job is to report *which* upstream stage to fix, and its metrics are
designed for that:

| Unhealthy metric | Points at |
|---|---|
| `avg_track_length` near 2.0, `long_track_fraction` low | the matcher's view graph — widen its pairing; under `exhaustive` the ceiling is co-visibility, not pairing |
| `track_count` low with healthy lengths | the detector — raise `max_keypoints` |
| `min_frame_observations` low on one frame | that frame's detection, or its links in the view graph |
| `inconsistent_rate` above 0.05 | the matcher is producing contradictory matches |

**Cheapest thing that usually works:** run it at defaults. If
`long_track_fraction` is below 0.3, go widen the matcher's pairing (`window` under sequential; under exhaustive every pair already exists) and run it
again — do not touch anything here.

**Reading the output:** [artifact.md](artifact.md). Note that `avg_track_length`
is the single most misleading number in this pipeline: it rises both when things
get better and when they get much worse. [tuning.md](tuning.md) has the measured
case.
