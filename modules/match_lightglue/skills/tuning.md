---
module: FeatureMatchLightGlue
module_version: 1.0.0
curated_at: 2026-08-08
---

# Tuning FeatureMatchLightGlue

Two things to establish before tuning anything: that `weights` is right, and that
LightGlue is actually the better matcher for this capture. Both are cheap to check
and both invalidate everything downstream if wrong.

## First: is the weight set right?

`weights: auto` handles the known detectors. If you set it by hand, verify with
`mean_match_score` — **below ~0.4 with a healthy `inlier_ratio` is the
wrong-weights signature**, and that is the only threshold on this number; the
`low_confidence` diagnostic fires there too. This used to say healthy was above
~0.5 and that a low score *means* wrong weights, stated absolutely, while
`limitations.md` put the signature below ~0.4. Readers landed between the two —
0.39 to 0.45 — with `weights: auto` already resolved from the features artifact's
provenance, and went hunting a weight-set bug that could not exist.

**Between ~0.4 and ~0.5 is an ordinary reading on a permissive threshold, not a
fault.** The mean is dragged by a low-confidence tail, and the way to tell that
from a real problem is one run: raise `filter_threshold` and read the score again.
Measured on one capture, 0.394 → 0.575 with weights untouched. If the score climbs,
it was the tail. If it does not move, the descriptors and the weight set are worth
suspecting — but `auto` refuses rather than guessing on an unknown producer, so a
wrong set is only reachable by naming one by hand.

## Second: is LightGlue winning?

Run `FeatureMatchNN` on the same features and compare the **final** reprojection
error after bundle adjustment, not the match count. Inside the classical
detector's envelope the classical stack won
by 2.6x on the output metric while losing on every intermediate one — see
[SKILL.md](SKILL.md).

This is not a formality. The comparison costs one pipeline run.

## `filter_threshold` — the quality dial

Defaults to 0.1, which is deliberately permissive because geometric verification
follows. On an easy scene that permissiveness is where the conflicts come from.

**Start at 0.2-0.3 and sweep upward.** That band was written as the answer and it
is about half of where the dial works: settled values across six captures came out
at 0.5, 0.5, 0.55, 0.6 and 0.7, and on two of them the inherited value was already
inside the band and still producing a badly contradictory track table — a reader
obeying the band had no next move.

**Judge it by the tracker's `inconsistent_rate`**, not by `matches_per_pair` and
not by `inlier_ratio`. The match count going down is the intended effect. And
`inlier_ratio` is actively misleading here: it read 0.93-0.99 on every run that
still needed tightening, and it *rises* as you tighten, so it confirms whatever you
just did. Two-view verification structurally cannot see this error — a match
displaced onto a repeated structure satisfies the epipolar constraint by
construction — which is the whole reason the criterion lives one stage downstream.

**Where to stop, which is the harder half.** `inconsistent_rate` keeps falling long
after tightening has started buying it by deleting the graph, so it cannot be its
own stopping rule. Stop when the graph begins to pay:

- `pairs_matched` against `pairs_proposed`
- `min_image_degree` — the margin, not `graph_components`, which stays at 1 while
  pairs quietly disappear
- the tracker's `max_track_length`, which falls when real chains start being cut

One capture kept improving on both headline metrics at 0.8 while shedding two pairs
and a degree with `graph_components` still reading 1. Guard the final step with
`trifocal_transfer_px`, and read `trifocal_triples` beside it before believing a
small difference — that median is not stable across different
track tables, which is exactly the comparison a sweep makes.

**Pricing the sweep without spending it.** The matches artifact publishes
`matches/confidence` and `pair_index`. Thresholding that array per pair predicts,
before any run, how many matches survive at a candidate value and which pairs fall
below `min_matches`. One capture predicted its surviving match count exactly and
named the pair it would lose; that turns a blind six-run search into one
calculation, and it is the cheapest thing on this page.

## `graph_components` above 1

Raise `window`, or use `exhaustive`.

Worth knowing: LightGlue tolerates far wider baselines than SIFT, so a large
`window` is genuinely productive here where a classical matcher would find nothing.
Try 4-8 before concluding the capture is too sparsely sampled.

Conversely — if LightGlue *cannot* link two images, they probably do not overlap.
It is the strongest evidence available that a gap is real rather than a matcher
limitation.

## `inlier_ratio` below 0.5

The healthy floor here is **higher** than for classical matchers (0.7 against 0.5),
because LightGlue's raw output is already filtered by a learned criterion. Below
0.5, in order:

1. **Check `weights`.** This is the most common cause and it is silent.
2. Raise `filter_threshold`.
3. Only then consider the scene degenerate — check `planarity`.

## Speed

`depth_confidence` is the good lever, not `n_layers`. It lets easy pairs exit after
fewer layers while hard pairs still get the full stack; reducing `n_layers` weakens
every pair uniformly. Lower `depth_confidence` to 0.9 for a useful speedup at
minimal cost — the pairs it affects are the easy ones by definition.

`width_confidence` complements it by pruning unpromising keypoints between layers.
Lower to 0.95 when images carry many keypoints. Set either to -1 to disable when
you are measuring accuracy rather than throughput.

`flash` should stay on: faster, less memory, no accuracy effect, and it falls back
silently when unavailable — including on CPU.

## Cost, and a caveat on the numbers

**The recorded timings may not describe your environment.** They were taken when
this stack could not reach a GPU, and GPU passthrough has since been observed
working -- a run of this module has failed with a CUDA out-of-memory error raised
inside the container, which is only possible with a device attached. So treat any
absolute number here as a lower bound on speed and nothing more, and check
`device` in the artifact's own note for what actually ran.

**Read cost as relative, not absolute.** What transfers is the shape: this stage
grows with the pair count, and the pair count grows with the square of the image
count under exhaustive pairing. What does not transfer is seconds on a machine
whose configuration changed under the file. A recorded wall-clock figure is a fact
about a host, and a skill file is the wrong place to keep one.

**The metrics are unaffected either way** -- inference is deterministic and
device-independent; only the timing and the `expected_duration_s` calibration
differ.

Concretely: the same exhaustive sweep this file once recorded at tens of seconds
has since run in about two seconds on a small set. **Do not let a stale cost note
argue you out of exhaustive pairing on a set of a dozen images** -- that pairing is
what the planning guide asks for on any capture whose graph is at risk, and at this
size the A/B against another matcher is close to free.

The metrics are unaffected: inference runs under `inference_mode` and is
device-independent.

## Per-image tensors are cached

Not a parameter, but it explains the cost shape: keypoint and descriptor tensors
are built once per image and reused across every pair that image appears in. With
exhaustive pairing each image participates in N-1 pairs, so rebuilding them per
pair would dominate. Cost therefore scales with pair count, not with pair count
times keypoints.
