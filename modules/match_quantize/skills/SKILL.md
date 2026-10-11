---
module: MatchQuantize
module_version: 1.0.1
upstream: none -- numpy and opencv only
curated_at: 2026-10-10
---

# MatchQuantize

**Gives detector-free correspondences the keypoint identity they do not have.**
`pairwise_matches/v1` in, `pairwise_matches/v1` out, with `feature_index` filled.

## When to reach for it

**Exactly one condition: a detector-free matcher upstream, and a consumer downstream
that needs multi-view tracks.** Nothing else.

A detector-free matcher runs each pair independently, so one physical point gets its
own sub-pixel estimate in every pair it appears in. There is no keypoint table and no
`feature_index`, and a correspondence graph that merges by identity can then build
nothing longer than a two-view track — however many images see the point [S1].

The global reconstructor is the consumer that cannot survive that, and it cannot
survive it twice: its track filter demands three views, and its retriangulation stage
discards two-view tracks by a default no parameter of it reaches. **Both gates sit on
the same wall** [S2], which is why relaxing the track-length floor buys a much longer
run and the same empty cloud.

**You do not need this module for the incremental route.** A tracker merges
detector-free endpoints by proximity itself, controlled by its own `merge_eps_px`, and
that route reconstructs these matches without help. This module exists for the
consumers that take PAIRS rather than tracks and so never see the tracker.

## What it costs

**Sub-pixel accuracy, deliberately.** Binning replaces each endpoint with its lattice
point, which is the same trade the published method makes and for the same reason:
consistency is worth more than precision when the alternative is no model at all.
Expect a working reconstruction, not the best one available — on the captures measured
it reached parity with the incremental route for one detector-free matcher and a worse
but working result for the other [S5]. Read [limitations.md](limitations.md) before planning
around it.

## Reading the output

[artifact.md](artifact.md). The reading that matters is **`multiview_fraction`** — the
share of correspondence components spanning three or more images. It is 0.0 on the
input by construction, and if it is still near 0 on the output the module did nothing
useful. Everything else is secondary to that one number.

## Provenance

Exercised across **54 runs at version 1.0.0** in the detector-free global sweep: nine
captures of two benchmark families and three visual-inertial ones, two detector-free
matchers, three grid sizes, scored on pose against reference extrinsics
(`evidence/CORPUS.txt`); no capture outside them. Claim-by-claim citations: the
`sources` skill.
