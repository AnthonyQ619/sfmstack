# Campaign: estimator-outvote-2026-10 — when two agreeing estimators outvote the model

**This is a raw evidence table. Cite it; do not plan from it.** The rules these rows
support live in [`plan/pose.md`](../plan/pose.md), in the section on readings built on
the model's own evidence and the section on filling, and in
[`plan/dense.md`](../plan/dense.md).

## The question

[consensus-2026-09](consensus-2026-09.md) showed that two correspondence-free
estimators, read against each other, catch models no correspondence-built reading
can. It left open whether the estimators' *poses* are the better poses when they
outvote the model, what to deliver when they do, and whether the verifier can choose.
A dense control then produced the case that makes all three matter: a global solve
folded by repeated objects, every internal reading quiet, both estimators agreeing at
about one degree — and the verifier, scoring both models against the same
correspondences, vetoed the estimator model and passed the folded one.

## What was run

Offline, on stores already on disk, pre-registered before any number existed. Every
delivered model with both `PoseVGGT` and `PoseMapAnything` outputs on the same scene,
across the predecessor campaign and two later batches: 54 rows, decided on corpus
captures. The reading was computed as the agent would compute it, with no reference:
the model's disagreement with the two estimators over their disagreement with each
other, once over camera centres — the predecessor's form — and once over relative
rotations, which is what `sfm_compare` returns. Pose truth was the share of all camera
pairs whose relative rotation is within 5° of the reference, a pair touching an
unregistered camera counted as a failure. Dense runs used the delivered run's own
parameters (geometric) or the module's defaults (learned).

## Finding 1 — the two forms of the reading fire on different captures

The fire set is the same at a cut of 2 and of 3.

| capture | centre form | rotation form | pairs within 5°: delivered / VGGT / MapAnything | centre error, % of span (post hoc) |
| --- | --- | --- | --- | --- |
| `/ETH/kicker` | 14.9 | 0.67 | 1.00 / 1.00 / 1.00 | 21.0 / 0.7 / 1.0 |
| `/ETH/meadow` | 10.5 | 0.69 | 1.00 / 0.88 / 1.00 | 27.3 / 2.0 / 0.5 |
| `/tanks_and_temples/Meetingroom` | 52.3 | **66.2** | **0.44** / 1.00 / 1.00 | 28.9 / 0.5 / 0.7 |
| `/tanks_and_temples/Caterpillar`, filled delivery | 3.5 | 1.08 | 0.72 / 1.00 / 1.00 | 2.3 / 0.7 / 0.4 |
| `/tanks_and_temples/Caterpillar`, the core it filled | — | **8.7** | 0.27 / 1.00 / 1.00 | — |

**No pose-level rule survives on the centre form.** On the two site walks the
delivered rotations are as good as the estimators' — on one, better than one of them
— and what the centre form saw was camera position. The rotation form fires only where
the rotations are wrong: the folded global solve and the folded core.

**Where neither fires and the estimators are ahead anyway**, the cause is coverage or
small rotation error, not a fold: two site walks whose delivery left four or five
cameras unregistered (their registered rotations tighter than either estimator's), and
two short traversals near 3.5° median against the estimators' 1.6°–3.0°.

## Finding 2 — refining an estimator's model damages it

Every bundle adjustment run on a model triangulated from estimator poses, on a corpus
capture, against its own input.

| capture | estimator | pairs within 5°, input → refined |
| --- | --- | --- |
| `/tanks_and_temples/Meetingroom` | VGGT | 1.00 → 0.98 |
| `/euroc/V2_01_easy` | VGGT | 0.89 → 0.49, 0.89, 0.58, 0.58 (four runs) |
| `/tum_vi/room2` | VGGT | 0.91 → 0.80 |
| `/tum_vi/room2` | MapAnything | 1.00 → 0.67 |

Five of seven lost more than 0.05; none gained. Refinement fits the estimator's cameras
to the matcher's correspondences, the evidence the reading has called into question.
On the dense side the same holds: the cloud on the refined Meetingroom model scored
183.1 mm against 157.9 on the unrefined one (next table).

## Finding 3 — geometric stereo on estimator poses

Scored against the scan, overall distance in mm, as placed (lower is better).

| capture | cloud | as placed | best fit | points |
| --- | --- | --- | --- | --- |
| Meetingroom | an earlier delivery, on a correct model | 101.2 | — | — |
| Meetingroom | delivered, on the folded model | **107.8** | — | 492 k |
| Meetingroom | MapAnything poses, triangulated | 185.9 | 155.8 | 71 k |
| Meetingroom | VGGT poses, triangulated, unrefined | 157.9 | 137.1 | 109 k |
| Meetingroom | the same, after bundle adjustment | 183.1 | 170.4 | 49 k |
| Barn | delivered | **88.3** | — | 779 k |
| Barn | MapAnything poses, triangulated | 181.1 | 159.6 | 58 k |
| Caterpillar | delivered (filled) | 77.1 | — | — |
| Caterpillar | MapAnything poses, triangulated | **65.0** | 61.3 | 131 k |

**It does not go one way.** On the folded room and the sound outdoor structure the
estimator-pose cloud lost by half again or more, keeping a fifth or less of the points:
stereo needs poses tighter than an estimator's degree. On the compact orbited object it
beat both the filled delivery and every earlier record for the capture. Two of three is
not a rule in either direction.

**A dense score as placed does not certify the poses.** The folded model's cloud scored
within 7% of a correct model's on the same capture: the fit that places a cloud keeps
the cameras that agree with each other, and the folded half added little surface. Only
the pose reading said anything was wrong.

## Finding 4 — the learned dense module, where the rotation form fires and where it does not

`DenseVGGT` at its defaults on `PoseVGGT`'s poses — the module as the predecessor ran it.

| capture | rotation form | geometric delivery | `DenseVGGT`, as placed | best fit |
| --- | --- | --- | --- | --- |
| Meetingroom | 66.2 — fires | 107.8 | **89.9** | 65.0 |
| Barn | 1.51 — quiet | 88.3 | 84.8 | 69.0 |
| Caterpillar | 1.08 on the delivery — quiet | 77.1 | 91.0 | 75.7 |

Where the reading fires, the learned dense module beat the folded delivery and the earlier
correct-model record. Where it is quiet it tied on one capture and lost on the other.

## Finding 5 — a fill keeps whatever its core is

On Caterpillar the incremental core came out folded — 27% of pairs within 5°, 13.7°
median — and the fill kept the core's cameras and placed only the rest: 72% of pairs, against
100% for either estimator alone. Read on the core before filling, the rotation form
fires at 8.7. On Barn's sound core it reads 1.6, and the fill there delivered 1.00.

## Finding 6 — every fired model the agents built, not only the delivered ones

The stores hold every model an agent built. Each end-of-chain model on which the
rotation form fired at 2 or more — up to three per capture — was densified with
`DenseMVS` at the capture's delivered parameters, against `DenseVGGT` on `PoseVGGT`'s
poses for the same scene. Overall distance in mm as placed, lower is better; a win or
loss needs 5%.

| capture | rotation form | geometric cloud on the fired model | feed-forward cloud | result |
| --- | --- | --- | --- | --- |
| `/tanks_and_temples/Meetingroom` | 66.2 | 107.8 | 89.9 | win |
| `/tanks_and_temples/Meetingroom` | 66.1 | 101.0 | 89.9 | win |
| `/tanks_and_temples/Meetingroom` | 66.0 | 103.2 | 89.9 | win |
| `/tanks_and_temples/Barn` | 9.7 | 93.7 | 84.8 | win |
| `/tanks_and_temples/Barn` | 2.9 | 75.7 | 84.8 | **loss** |
| `/tanks_and_temples/Barn` | 2.7 | 118.3 | 84.8 | win |
| `/tanks_and_temples/Caterpillar` | 51.7 | 87.1 | 91.0 | tie |
| `/tanks_and_temples/Caterpillar` | 42.0 | 83.8 | 91.0 | **loss** |
| `/tanks_and_temples/Caterpillar` | 24.6 | 140.9 | 91.0 | win |

Six wins, two losses and one tie over nine models; by capture, two wins and a tie. The
median feed-forward cloud is about a tenth better, and the worst loss is 12%. No ETH3D
or DTU corpus capture fired.

**Nothing available to the agent predicts the losses.** Checked against wins and losses,
each of these overlaps: the rotation form's size, the centre form, the estimators'
spread, the model's own disagreement, the verifier's verdict and stray count, and every
reading either dense module publishes — point counts and their ratio, depth-map
completeness, fusion ratio, points per view, depth confidence. A loss is a fired model
whose geometric cloud is still good, and only reference geometry shows that.

## What this does not establish

- **Three corpus captures, nine fired models.** A rate, but a small one, all from one
  dataset.
- **Nothing about centre error as a rule.** That column was added after the
  pre-registered verdict.
- **Caterpillar was a holdout when the batch ran** and was promoted to carry findings 3
  and 5; its rows are recall from here on.
