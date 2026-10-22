# Campaign: final-validation-2026-10 — the frozen context, two sessions per capture

**This is a raw evidence table. Cite it; do not plan from it.** The rule it supports lives
in [`plan/pose.md`](../plan/pose.md#every-reading-above-is-built-on-the-models-own-evidence),
in the paragraphs on the centre form alone.

## What was run

The ten-view sparse batch and the full-capture dense batch of
[agent-rerun-2026-10](agent-rerun-2026-10.md) run again on the context that campaign and
[dense-variance-2026-10](dense-variance-2026-10.md) revised: same captures, same protocol,
strict context, one isolated agent per capture, **two independent sessions per capture**.
Scored afterwards against reference poses (AUC@30) and each benchmark's own dense
evaluation, as placed; every sparse model each session built was read by reference
(rotation share, camera centres after a similarity fit) and by the two-estimator reading.
Only corpus captures are reported here.

## Finding 1 — on a site walk the threshold rebuild did not clear the centre form; the other route did

`/ETH/meadow`, ten views, sparse deliverable. Both sessions delivered models with every
rotation right and the cameras about a quarter of the span out.

| session | reading taken | models built: centre error, % of span | delivered | AUC@30 |
| --- | --- | --- | --- | --- |
| 1 | yes; the centre form fired on every complete model (9.3 against the estimators' own spread) | incremental route only, 27.4–27.5; a rebuild at the tighter matcher threshold stayed at 27.4 | 27.4 | 0.538 |
| 2 | no | incremental 22.6–32.6; **global route 0.11 and 0.15** | 32.6 | 0.498 |

Session 1 rebuilt once, as the context asked, and with no model the reading passed it
delivered one the reading had fired on. Session 2 had two well-placed models in hand and
no reading to tell them from the rest. On the same staging the two estimators' own models
score 0.690 and 0.707
([sparse-compositions-2026-10 §7](sparse-compositions-2026-10.md#7-the-two-correspondence-free-estimators-against-each-other)),
the best composition any module reached is a global route at 0.981
([§1](sparse-compositions-2026-10.md#1-best-and-median-per-capture--the-margin-table)), and an
earlier session that bracketed the threshold found a placed incremental model at 0.977
([agent-rerun-2026-10](agent-rerun-2026-10.md#finding-2--on-the-centre-form-alone-a-rebuilt-geometric-model-was-the-right-one)).

## Finding 2 — the centre-form comparison on object orbits and enclosures

Every dense session on `/tanks_and_temples/Caterpillar`, `/tanks_and_temples/Barn` and
`/tanks_and_temples/Meetingroom` that built two or more models with every rotation right
(six of six) compared their centre forms and densified the lowest, or one within 0.01% of
the span of it; no session ranked on the lower error. One Caterpillar session built no
well-placed model (its best correct candidate at 0.64% of the span, the other session's at
0.35%) and its cloud was the worse: 57.2 against 33.8 mm.

## Finding 3 — the control rows, two sessions each

| capture | metric | session 1 | session 2 |
| --- | --- | --- | --- |
| `/DTU/scan77` | AUC@30 | 0.972 | 0.967 |
| `/ETH/kicker` | AUC@30 | 0.994 | 0.994 |
| `/ETH/relief` | AUC@30 | 0.996 | 0.996 |
| `/ETH/meadow` | AUC@30 | 0.538 | 0.498 |
| `/euroc/V2_01_easy` | AUC@30 | 0.849 | 0.849 |
| `/euroc/V1_02_medium` | AUC@30 | 0.348 | 0.628 |
| `/tum_vi/room2` | AUC@30 | 0.798 | 0.798 |
| `/DTU/scan33` | overall mm ↓ | 0.791 | 0.785 |
| `/DTU/scan15` | overall mm ↓ | 0.534 | 0.546 |
| `/ETH/delivery_area` | F1 @ 2 cm ↑ | 0.667 | 0.667 |
| `/ETH/relief` | F1 @ 2 cm ↑ | 0.681 | 0.675 |
| `/ETH/office` | F1 @ 2 cm ↑ | 0.424 | 0.424 |
| `/tanks_and_temples/Caterpillar` | overall mm ↓ | 33.8 | 57.2 |
| `/tanks_and_temples/Barn` | overall mm ↓ | 40.7 | 48.6 |
| `/tanks_and_temples/Meetingroom` | overall mm ↓ | 92.0 | 92.0 |

## Finding 4 — on a rig orbit the as-placed score moves with camera placement, the surface does not

Added 2026-10-22 from the locked-context dense batch that followed this one (same context
content; one session per capture, a second where the first moved beyond 5% of the record).
The dataset's as-placed score carries the cloud into the reference frame by a similarity
fitted from the 49 camera centres; the best-fit score refits it to the reference surface.

| capture | session 1 as placed (best fit), mm | session 2 as placed (best fit), mm | as-placed spread | best-fit spread |
| --- | --- | --- | --- | --- |
| `/DTU/scan4` | 0.906 (0.399) | 0.729 (0.403) | 0.177 (24%) | 0.004 (1%) |
| `/DTU/scan1` | 0.416 (0.308) | 0.461 (0.304) | 0.045 (10%) | 0.004 (1%) |
| `/DTU/scan48` | 1.784 (1.403) | 1.621 (1.417) | 0.163 (10%) | 0.014 (1%) |
| `/DTU/scan10` | 0.780 (0.372) | 0.785 (0.371) | 0.005 (1%) | 0.001 |

The camera fit behind every as-placed score here has an rms of 0.5–1.9 mm, so the placed
score sits at the scale of camera placement. Every model kept the calibrated intrinsics
exactly, and every model's centre error is 0.04–0.16% of the span. The fit's rms does **not**
predict which way a model moves: across the record and both sessions of the captures run
twice, a higher rms went with a larger placement penalty in 12 pairs and a smaller one in 9.
No reading an agent has resolves placement at this scale — the centre form reads 0.51–0.62 on
every model of every one of these captures.

## What this does not establish

Two sessions per capture, one context. Finding 4 rests on rig orbits only; whether a site walk's
or an enclosure's as-placed score carries the same camera-placement noise is not measured, and
there the centre form does rank placement (Finding 2). Finding 1 is one capture: it shows the threshold
rebuild is not enough there and the other route was, not that the other route always is.
Four sessions of the fifty-six did not take the two-estimator reading; why is not measured.
