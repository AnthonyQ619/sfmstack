---
module: FeatureMatchFLANN
module_version: 1.6.0
upstream: OpenCV FlannBasedMatcher (KD-tree / LSH)
curated_at: 2026-08-07
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 9 parameters documented, starting with `pairing` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It is slower than brute force at ordinary scales" |
| you are reading what it wrote | **`artifact`** — the layout of `pairwise_matches/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `pairs_proposed`, `pairs_matched`, `matches_per_pair`.

**Diagnostics it can raise:** `approximation_costly`, `broken_chain`, `low_inlier_ratio`.

## What this module is for


`FeatureMatchNN` with the exhaustive search replaced by an approximate index.
Everything after the search — ratio test, mutual check, MAGSAC verification, view
graph, planarity — is deliberately identical, so the two are directly comparable
and the search is the only variable.

**Measure before you switch.** On a turntable capture of a compact object, 8 contiguous images at 1024px, 4096
SIFT keypoints, exhaustive pairing:

| matcher | time | matches/pair | inlier_ratio | agreement |
|---|---:|---:|---:|---:|
| `FeatureMatchNN` | **0.7 s** | 466.7 | 0.964 | — |
| FLANN `checks: 50` | 4.2 s | 438.9 | 0.948 | 0.998 |
| FLANN `checks: 200` | 11.8 s | 466.8 | 0.961 | 0.999 |

FLANN is **six times slower** here, and the approximation is nearly exact. At this
scale the index build dominates and there is nothing to approximate away — brute
force over 4096×4096 float descriptors is a single well-optimised matrix operation,
and building a KD-tree per pair is not.

**So: use this only when the exact matcher is genuinely the bottleneck**, which
means far more keypoints per image than this, or descriptor sets large enough that
one index can be amortised over many queries. Below that, `FeatureMatchNN` is both
faster and better.

**Binary descriptors (ORB) use LSH**, selected automatically from the features
artifact's `binary` flag — a KD-tree cannot index Hamming space.

**The metric that justifies the module:** `match_agreement`. It brute-forces one
pair and reports what fraction of the approximate nearest neighbours were the exact
one. It measures what `checks` is buying on *your* data rather than in general, and
it costs one extra pass.

**Reading the output:** [artifact.md](artifact.md) — identical in shape to
`FeatureMatchNN`'s, deliberately.

## Provenance

Exercised across **4 runs at version 1.6.0** in the seventeen-capture sweep of two
benchmark families (`evidence/CORPUS.txt`); no capture outside them.
Claim-by-claim citations: the `sources` skill.
