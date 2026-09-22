# Campaign: view-graph-support-2026-09 — does a delivered model's own evidence connect it?

**This is a raw evidence table. Cite it; do not plan from it.** The rules these rows
support live in `SparseVerification`'s
[limitations](../../modules/sparse_verification/skills/limitations.md#a-model-can-be-in-pieces-and-the-residual-will-not-say-so)
and [sources](../../modules/sparse_verification/skills/sources.md), and in
[`health/ladder.md`](../health/ladder.md) on the hole the profile has behind a global
reconstructor.

## The question

A sparse model can register every frame at a sub-pixel reprojection error and still
be assembled from internally-correct pieces held at wrong relative orientations.
Nothing in the stack reported that shape. `SparseVerification` was the closest
reading and it reduces its per-pair residuals to one weighted median, which is an
average and cannot express whether a subgraph is connected.

So: take only the pairs whose correspondences AGREE with the finished model —
per-pair median epipolar distance within `inlier_threshold_px` — and count the
connected components they induce on the registered cameras. This campaign asks what
that reads on models already known to be good.

## Protocol

- **Models.** The delivered sparse model of each of the 19 corpus captures in the
  two dense campaigns: the 10 studio-rig orbits of
  [dense-batch-2026-09](dense-batch-2026-09.md) (`scan1, 4, 9, 10, 15, 23, 33, 48,
  75, 77`) and the 9 site walks of [eth-dense-2026-09](eth-dense-2026-09.md)
  (`courtyard, delivery_area, electro, facade, kicker, meadow, office, playground,
  relief`). Every one of them delivered a dense cloud that scored against reference
  geometry, so every row here is a known success. Read from the stored artifacts;
  nothing was re-solved.
- **Computation.** The module's own functions, driven over the stored scene, model
  and matches — not a reimplementation. Undistortion with the scene's calibration,
  projection with the model's intrinsics, Sampson distance, the 2 px coincidence
  test for "the model used this correspondence".
- **No ground truth is used anywhere in this reading.** It is the model against the
  correspondences it was built from. Reference geometry enters only as the reason
  these 19 are known to be successes.

## What a delivered model reads

| | components | largest share | agreeing pairs | residual (mrad) |
|---|---|---|---|---|
| 18 of the 19 | **1** | **100%** | 69.5–100% | 0.052–1.756 |
| `kicker` | 2 (second of size **1**) | 96.8% | 99.5% | 0.235 |

Every studio-rig orbit and eight of the nine site walks read exactly one component
holding every registered camera. `kicker` is the single exception: two components
with 96.8% of its cameras in the largest, which is one camera hanging off.

**That is the whole basis for the band** — `supported_components` ceiling 1, and
`supported_second_size` ceiling 1, which is what the diagnostic gates on.

The gate was first written on `supported_largest_share` with a floor of 0.95, and
that is wrong for a reason worth recording: the share is camera-count dependent.
One stray camera reads 0.968 on `kicker`'s 31 images and would read 0.933 on
`meadow`'s 15 — the same situation on either side of any fixed floor, penalising
the smaller capture for its size. The second component's size does not move with
the camera count. Checked against all 24 models in this campaign and the ICL
batch, the two rules fire on exactly the same three; the scale-free one was kept
because it will not diverge on a capture smaller than any measured here.

**It is a description of 19 successes, not a discrimination experiment.** No capture
here reads as pieces, so this campaign fixes the healthy end of the reading and says
nothing about where the unhealthy end begins. The floor was chosen, not fitted.

## The design this replaced, and why the more independent quantity was wrong

Built first on the **held-out** residual — the obvious choice, since held-out
evidence is what the rest of the module rests on — and run over the same 19.

It fragmented five of them. `scan48` read 5 components at 81.6%, `scan15` 4 at
93.9%, `scan9` 3 at 95.9%, `electro` 3 at 95.0%, `kicker` 2 at 96.8%. **Two of
those would have raised an error on a capture that delivered a scored dense cloud.**

The cause is sample size, not geometry. A held-out median rests on tens of
correspondences where the all-correspondence median rests on hundreds, and a noisy
per-pair median drops sound pairs below the threshold and cuts cameras loose. The
ordering is visible in the table: `scan48` had the fewest scored pairs of the 19
(204) and fragmented worst.

Recomputed on the all-correspondence median, the same 19 gave the result above.

**So this reading trades independence for a stable per-pair estimate, and the trade
is sound for this question specifically:** a model in pieces is contradicted by the
correspondences it KEPT as well as by the ones it did not. Independence is what a
veto on a self-consistent wrong model needs; connectivity is a different question
and needs a well-determined edge.

The held-out residual remains the veto and is unchanged.

## What is not established here

- **No measured catch.** That the component count sees a failure the weighted median
  misses is an argument about what the two quantities are, plus the measured fact
  that correct models read one component. Producing a piecewise model on a corpus
  capture would mean deliberately corrupting a view graph, and that was not done.
- **No sensitivity.** With no corpus capture reading as pieces, nothing here says how
  fragmented a model must be before it is caught. The band is deliberately
  conservative, so a model in a few pieces whose largest holds most of the cameras
  reads above the floor and stays silent.
- **Consistency, not accuracy.** The same limit the residual carries. A capture
  whose matcher produced many wrong pairs can read one component because the
  averaging survived them.
- **`agreeing_pair_share` does not stand in for the component count.** It ranges
  0.695–1.00 across these 19, and the capture at the bottom of that range
  (`meadow`, 69.5%) reads one component holding every camera. A low share is
  context, not a fault.
