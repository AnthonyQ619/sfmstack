---
module: FeatureMatchLightGlue
module_version: 1.6.0
upstream: cvg/LightGlue
curated_at: 2026-08-08
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 9 parameters documented, starting with `weights` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Captures inside the classical detector's design envelope" |
| you are reading what it wrote | **`artifact`** — the layout of `pairwise_matches/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `pairs_proposed`, `pairs_matched`, `matches_per_pair`.

**The dial and its criterion:** `filter_threshold`, swept on this artifact's own
`cycle_merge_rate + cycle_split_rate`. Not `inlier_ratio`, which rises as you tighten
and so confirms whatever you just did; and not primarily the tracker's
`inconsistent_rate`, which has twice been measured sitting flat across the range that
decided the run. Confirm with `inconsistent_rate` once at the settled value.

**Diagnostics it can raise:** `broken_chain`, `low_inlier_ratio`, `low_confidence`, `degenerate_geometry`.

## What this module is for


Learned sparse matcher. Attends over both keypoint sets jointly rather than asking
each keypoint independently whether its best match is distinctive — which is
exactly the information Lowe's ratio test discards.

**Use when** a GPU is available and the capture is hard: repeated structure, wide
baselines, illumination change, low texture. Those are the regimes it was built
for and where it beats the ratio test decisively.

**Do not assume it wins inside the classical detector's envelope.** Measured on
a well-lit, densely and aperiodically textured turntable capture of a compact
object with short baselines and no repeated structure (10 contiguous
images, 1024px, exhaustive pairing), against the same pipeline downstream:

| stack | matches/pair | long_track% | tracker conflict | final reproj error |
|---|---:|---:|---:|---:|
| SIFT + `FeatureMatchNN` | 494.9 | 0.491 | **0.004** | **0.246 px** |
| SuperPoint + LightGlue | 649.2 | 0.607 | 0.206 | 0.645 px |
| ALIKED + LightGlue | 688.4 | 0.605 | 0.172 | 0.451 px |

LightGlue wins every intermediate metric — most matches, longest tracks — and
loses the only one that is the output. The tracker's `inconsistent_rate` is fifty
times higher, meaning one in five merged tracks is self-contradictory.

**You do not need the tracker run to see that.** This module publishes
`cycle_merge_rate` and `cycle_split_rate`, which compare a third view and catch the
same error one stage earlier and one run cheaper. Sweep `filter_threshold` on their
sum; use `inconsistent_rate` once at the end to confirm. Do not sweep on
`inlier_ratio`, which reads 0.93-0.99 on runs that are still wrong and *rises* as
you tighten.

That is a capture squarely inside the classical detector's comfort
zone and outside the regime LightGlue targets. The conclusion is not "SIFT is
better" — it is **run the comparison on your capture**, because one run settles it
and reputation does not. See [limitations](limitations.md).

**The weight set must match the detector.** LightGlue is trained per descriptor
type; SuperPoint weights over ALIKED descriptors produce confident nonsense rather
than an error. `weights: auto` (the default) infers it from the features
artifact's provenance and cross-checks the descriptor width, and fails loudly when
it cannot tell.

**`mean_match_score` is the wrong-weights detector.** A low value alongside a
healthy `inlier_ratio` is the signature: the geometry is consistent because the
matches came from one rigid scene, and the model is unsure because the descriptors
are not what it was trained on.

**Reading the output:** [artifact.md](artifact.md). Interchangeable with the
classical matchers' output by design.
