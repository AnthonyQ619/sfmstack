---
campaign: detector-free-global-2026-10
measured: 2026-10
---

# Campaign: detector-free-global-2026-10 — correspondences with no keypoint identity, through a pairs-consuming reconstructor

**This is a raw evidence table. Cite it; do not plan from it.** The reasoning built on
these rows lives in [`plan/sparse.md`](../plan/sparse.md) §2 and
[`plan/matching.md`](../plan/matching.md), stated as capture properties rather than as
scene names.

## Protocol

Three stages, all on [CORPUS.txt](CORPUS.txt) captures, all scored by the same metric as
[sparse-compositions-2026-10](sparse-compositions-2026-10.md) — AUC@30 over all 45 pairs,
unregistered charged as a miss.

1. An offline sweep, 54 solves, nine captures × two correspondence sources × three
   binning tolerances, reading the stored match artifacts and calling the real solver.
2. The shipped transform end-to-end on one capture, to check it lands where the offline
   emulation said.
3. Twenty-four corpus captures × two compositions, the transform in front of the global
   reconstructor, at one fixed tolerance.

`max_epipolar_error: 2.0` and `num_threads: 1` throughout, and both discard gates at
their defaults — neither relaxed, because a working merge should not need either.

## 1. The mechanism

A matcher that emits no `feature_index` leaves every match endpoint its own keypoint. The
correspondence graph merges observations by keypoint **identity**, not by geometry, so a
point seen in ten images becomes ten unrelated keypoints and nine independent pairs:
**no track can reach a third view**, however much the images overlap. Two independent
gates then discard what is left — the exposed minimum track length, and a retriangulation
stage that ignores two-view tracks by a default the module does not expose. Lowering the
first passes one gate and not the other.

Measured on the artifacts: 86,442 correspondence components, **zero** spanning three or
more views; the solver's own log reporting exactly 2.000 observations per track. Images
were **oriented** by rotation averaging and never **positioned** — ten finite rotations
beside ten NaN translations — because global positioning is a later stage and is skipped
when it has no tracks.

## 2. What was ruled out, and is not worth re-deriving

| explanation | verdict |
| --- | --- |
| detector-free matches cannot form tracks at all | **false** — 53,965 via proximity union-find, 31.6% long, max length 9 |
| the reconstructor requires `feature_index` | **false** — it has an explicit path that gives every endpoint its own keypoint |
| the minimum-track-length floor is what binds | **false** — at 2 the result is identical |
| the registered-image count proves cameras were placed | **false** — it counts oriented images, and a NaN translation is what unplaced looks like |

**And keeping two-view tracks is not a repair.** Flipping the unexposed gate turns the
hard failure into a working reconstruction, and it loses to the same matcher's
incremental composition on three of four captures by 0.12 to 0.53. Two-view tracks
constrain orientation well and position poorly — on one rig orbit the rotations came back
at 0.148° median while the translation direction sat at 0.939°. **That is the wrong
structure, not a thin one**, which is why the repair has to create multi-view tracks
rather than admit two-view ones.

## 3. Delivery, with the transform in front

| composition | before | with the transform |
| --- | --- | --- |
| semi-dense matcher → global | 0 of 24 | **24 of 24** |
| dense matcher → global | never run | **24 of 24** |

The shipped transform reproduces the offline emulation on the capture both were run on:
**0.9743 against 0.975** at the same tolerance, which is what makes the sweep's result
transferable to the module.

## 4. Paired within-matcher — global against the same matcher's incremental composition

Both consume the same correspondences, so capture difficulty and matcher quality cancel.

| | n | median Δ | wins >0.05 | ties | losses >0.05 |
| --- | --- | --- | --- | --- | --- |
| dense matcher | 24 | **−0.000** | 2 | **18** | 4 |
| semi-dense matcher | 24 | −0.001 | 2 | 15 | **7** |

**Both sit at median parity, and on this corpus parity is the ceiling**: every capture is
ten images with all 45 pairs matched, so there is no registration order to be robust to
and no scale to exploit. The two differ in the tail, not the median — the semi-dense
route loses materially on seven captures with a worst case of −0.747 on a capture whose
incremental reading is 0.974.

**Both sources win on the same two captures**, and both are traversals:

| capture | semi-dense Δ | dense Δ |
| --- | --- | --- |
| tum_vi/room4 | +0.196 | **+0.641** |
| euroc/MH_05_difficult | +0.266 | **+0.318** |

On `tum_vi/room4` the dense route reaches 0.765 where its incremental counterpart reads
0.124, and the best of the eleven compositions in
[sparse-compositions-2026-10](sparse-compositions-2026-10.md) is 0.616.

## 5. The binning tolerance, and a proxy that failed

Best tolerance across all eighteen capture/source pairs in the sweep: the coarsest on 8,
the finest on 7, the middle on 3 — **and on the captures where the choice discriminated
the coarsest dominated.** The count of three-or-more-view components peaks at the
**finest** tolerance, which is the setting that loses: one indoor capture went 0.124 to
0.313 and a room rig 0.186 to 0.333 from finest to coarsest **while the component count
fell the whole way**. **Track yield is not a proxy for pose accuracy** and must not be
used to choose the tolerance.

## 6. The cycle rates read the source, not the outcome

At one fixed tolerance, twenty-four captures per source:

| | n | min | median | max |
| --- | --- | --- | --- | --- |
| `cycle_merge_rate`, semi-dense | 24 | 0.222 | 0.363 | 0.478 |
| `cycle_merge_rate`, dense | 24 | 0.699 | 0.774 | 0.903 |
| `cycle_split_rate`, semi-dense | 24 | 0.001 | 0.004 | 0.034 |
| `cycle_split_rate`, dense | 24 | 0.000 | 0.002 | 0.007 |

**The merge-rate ranges are disjoint** — no capture from one source reaches the other's
nearest value — and against pose accuracy the rate correlates at **r = +0.142 over 48
paired readings**. So a value identifies which matcher produced the correspondences and
forecasts nothing. It also moves with the tolerance, so two readings are comparable only
at the same setting. On a detector-based matcher the same metric means contamination;
here the identity is an approximation the transform created, and the meaning does not
carry across.

## 7. One capture unexplained, and where it is not

`ETH/kicker` under the semi-dense matcher reads **0.464** by the gate flip, **0.465** by
the offline emulation and **0.464** by the shipped transform, while the dense matcher on
the same capture reaches **0.998**. The first keeps every track at two views and the
others build multi-view tracks from the same correspondences: **the track structure is
completely different and the number is not.** So whatever limits this capture sits
upstream of track formation, in the correspondences themselves. That rules out the
chaining stage and names no cause.

## 8. What this campaign does not establish

- **Nothing at scale.** Order-independence and large unordered collections are what the
  global route is for, and ten exhaustively-matched images cannot show either.
- **No mechanism for the tolerance optimum.** It was measured, not explained.
- **Nothing about the two sources being interchangeable.** They are not, in the tail.
