# Campaign: agent-controls-2026-10 — the loop on seven corpus captures, against what the registry has reached

The full agent loop (`harness/launch.py`, one isolated session per capture, the
procedure in `harness/PROCEDURE.md`, strict context) driven on seven corpus captures at
ten views each, to a refined sparse model, scored against reference extrinsics as
AUC@30 over all 45 pairs. Context frozen at `036dc6f`; every run directory recorded
the repository's own context. One attempt each; session wall time 0.13 to 0.27 h.

**What this file does not hold.** The same batch ran seven captures outside the corpus,
matched one-to-one with these by capture kind. Their rows are deliberately absent: a
capture named here becomes part of what the context has been shown, and those seven
remain usable as out-of-sample captures only while unnamed. Nothing below rests on them.

## How a margin is taken

Each delivery is compared with **the best any registry module has reached on that
capture**: the standing compositions of
[sparse-compositions-2026-10](sparse-compositions-2026-10.md) and the prior record's
own pipeline and two correspondence-free estimators. An external estimator that is not
a module is excluded, because no agent can reach it. Every model each agent built and
rejected was scored the same way, which separates a wrong choice among built models
from a winning composition never built.

## The seven

| capture | kind | delivered | best reached | margin | delivered chain | best rejected |
| --- | --- | --- | --- | --- | --- | --- |
| DTU/scan77 | rig orbit | 0.745 | 0.974 | **−0.230** | SIFT+CLAHE → LightGlue → global | 0.515 |
| ETH/kicker | site walk | 0.995 | 0.997 | −0.003 | SIFT+CLAHE → LightGlue → global → fill | 0.995 |
| ETH/relief | site walk | 0.996 | 0.998 | −0.002 | SIFT+CLAHE → NN → incremental | 0.997 |
| ETH/meadow | site walk | 0.500 | 0.981 | **−0.481** | SuperPoint → LightGlue 0.4 → incremental, GTSAM | 0.539 |
| euroc/V2_01_easy | traversal | 0.756 | 0.895 | −0.139 ¹ | VGGT poses + SuperPoint/LightGlue tracks, partly fixed BA | **0.849** |
| euroc/V1_02_medium | traversal | 0.361 | 0.583 | **−0.223** | one frame excluded; SuperPoint → LightGlue → global | 0.361 |
| tum_vi/room2 | traversal | 0.793 | 0.779 | +0.014 ¹ | RoMa → union-find → VGGT poses | 0.587 |

¹ a learned-prior estimator in the chain; its repeat noise is up to 0.237.

Three of seven within 0.05; median margin −0.139. **One shortfall was a choice among
built models** (`V2_01_easy`, finding 2). Every other material shortfall was
construction: the agent delivered the best model it built.

## Finding 1 — a complete detector-free view graph is not evidence of overlap

On the three traversals, the detector-free matcher "matched" every one of 45 pairs, with
654 to 1494 correspondences on the weakest pair, on ten-frame captures whose frames face
different walls. The pairs that share no content verified anyway.

| capture | detector-free route | AUC@30 | standing `roma_incremental` |
| --- | --- | --- | --- |
| euroc/V2_01_easy | → MatchQuantize → global | 0.110 (75° off both estimators) | 0.128 |
| tum_vi/room2 | → union-find → incremental | 0.208 (7/10) | 0.208 |
| tum_vi/room2 | → MatchQuantize → global | 0.325 (vetoed, 3 pieces) | — |
| euroc/V1_02_medium | → union-find | abandoned: 17% contradictory tracks | 0.314 |

**The certainty floor does not separate them.** At `min_certainty` 0.7 the floor
removed 6.1% of samples on V1_02 and inlier ratio moved 0.547 → 0.559; at 0.9 on room2
it removed 6% and all 45 pairs survived. Mean certainty read **1.00** on both,
including on pairs whose held-out residuals were 130–200 px under every model.

## Finding 2 — the pixel veto fires on an estimator's own cameras by construction

On `V2_01_easy` the geometric core registered 3 of 10, too few to fill. The agent built
the estimator's model on its own (VGGT poses, structure triangulated on them, every
camera held fixed) and the verifier returned `contradicted` at 3.88 px against a 3.0 px
gate, with 7 supported components. The agent treated the veto as final and delivered a
variant with one camera per cluster fixed. **Scored: the vetoed model 0.849, the
delivery 0.756** — one VGGT draw, so the difference is the construction, not estimator
noise. The cameras were never solved against the correspondences the verifier tests, so
on a short-focal camera a few degrees of estimator error is many pixels.

## Finding 3 — the two joint matchers trade places, and neither was considered

No session of fourteen read or ran `FeatureMatchSuperGlue`. On the corpus record, across
the 29 captures run through both joint matchers on the global route:

| | captures |
| --- | --- |
| SuperGlue ahead by more than 0.05 | 5 (largest +0.288) |
| LightGlue ahead by more than 0.05 | 8 (largest +0.427) |
| within 0.05 | 16 |

Both directions occur on site walks and on traversals, and one rig orbit (`DTU/scan48`)
favours LightGlue by 0.122; the other nine rig orbits are within 0.03. No capture-kind
label sorts the winners.

## Finding 4 — classical detection and matching on a sparse capture

On `DTU/scan77` at ten views the ratio-test matcher left three components, the
incremental route registered 3 of 10, and the agent's best classical build reached
0.745 against 0.94–0.97 for the learned and detector-free compositions. On the corpus
record at ten views, the better of the two classical compositions is more than 0.2 below
the best on **14 of 27 captures**: 2 of 10 rig orbits, 4 of 9 site walks, 8 of 8
traversals.

## Finding 5 — a camera on one or two thin pairs is placed against its own evidence

| capture | camera | its pairs | residual against its own pairs | registered |
| --- | --- | --- | --- | --- |
| ETH/kicker | one, degree 1 | a single verified pair | 133 px | 10/10 |
| euroc/V1_02_medium | one | 8–16 matches each | 163–192 px | 10/10 |

The global reconstructor placed both; `registered_fraction` read 1.0. On kicker the
global model with that camera scored 0.795 and the fill that replaced it 0.995.

## Finding 6 — one filled camera leaves the second gate with nothing to read

On `ETH/kicker`, with `poses_b` supplied and exactly one camera filled,
`filled_agreement_deg` came back null on both fills.

## Finding 7 — an INDEX row describes its capture at the frame count it ran at

`DTU/scan77`'s INDEX row records the cheap classical detector and matcher registering everything; at
ten views the same modules fragmented. `ETH/relief`'s row records the profile misleading the
choice between two models; at ten views the two agreed to 0.03°. Both rows were written
from full captures.

## The meadow isolation

`ETH/meadow` delivered 0.500; the global route has reached 0.981 on it. Run offline on the
same ten-view staging, threads pinned, one factor at a time from the defaults and from the
agent's configuration (`SuperPoint max_keypoints`, LightGlue `filter_threshold`, global
`min_track_len`, each scored before and after refinement): **no single one of the agent's
three choices moved the score by more than 0.08**, and the defaults themselves scored
0.528. The factor is `filter_threshold`, swept at both epipolar settings:

| `filter_threshold` | `max_epipolar_error` 1.0 | 2.0 |
| --- | --- | --- |
| 0.3 | 0.462 | 0.527 |
| 0.4 | 0.625 | 0.489 |
| **0.5** | **0.975** | **0.981** |
| 0.6 | 0.966 | 0.976 |
| 0.7 | 0.970 | 0.959 |

A step between 0.4 and 0.5, the same at both epipolar settings, so it is not an
interaction with that dial. The agent's own configuration at 0.5 scored 0.958 (and 0.776
at 0.6, where one camera dropped). The agent swept to 0.5 and stopped at 0.4 because
0.5 "cost 6 pairs and lowered `min_image_degree` from 4 to 2" — readings of the graph,
judged on the incremental route. On the global route the pairs that went were the ones
rotation averaging could not survive.

## What this does not establish

Seven captures, one draw each, ten views. The meadow step is one capture. Findings 1 and
5 are mechanisms observed on two or three captures and consistent with the standing
record; none is a rate.
