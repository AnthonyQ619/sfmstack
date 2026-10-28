# Campaign: dense-variance-2026-10 — how far a dense score moves with nothing changed

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports live
in [`plan/dense.md`](../plan/dense.md), in
[`health/ladder.md`](../health/ladder.md#when-the-ladder-runs-out-and-two-models-still-disagree)
and, for reading dense comparisons, in [`EVIDENCE.md`](EVIDENCE.md).

## What was run

Five corpus captures, two independent agent sessions each on one context, full captures,
strict context. Then, with no agent: each delivered dense step replayed twice more on its
own inputs; and every other sparse model a session built that was correct by reference
(every camera pair within 5° of the reference rotation, centres within 1% of the span
after a similarity fit) densified once with the delivered dense settings. Scored by each
benchmark's own evaluation, as placed; camera centres scored against reference poses.

A second pass, with no agent, took every sparse model those sessions built with every
camera pair within 5° of the reference rotation — 45 of 75 — densified each one not yet
densified with its session's delivered settings, and read every reading an agent has on
each model against its centre error. The learned dense module was also drawn three times
on two fixed inputs.

## Finding 1 — stereo on a fixed input reproduces itself

Three draws per session agreed to 0.01 mm on the three outdoor-and-enclosure captures,
0.0001 mm on the rig orbit, and exactly on the built interior. The geometric stereo module
adds no spread of its own. Neither does the learned one: three draws on each of two fixed
inputs gave 90.968 mm three times on the outdoor object orbit and 89.880 mm three times on
the enclosure.

## Finding 2 — two sessions on one context differ by a third to double

| capture | metric | session 1 | session 2 | spread |
| --- | --- | --- | --- | --- |
| `/tanks_and_temples/Caterpillar` | mm ↓ | 62.9 | 29.3 | 115% |
| `/tanks_and_temples/Meetingroom` | mm ↓ | 135.8 | 91.6 | 48% |
| `/tanks_and_temples/Barn` | mm ↓ | 39.0 | 52.1 | 34% |
| `/DTU/scan15` | mm ↓ | 0.546 | 0.546 | 0 |
| `/ETH/office` | F1 @ 2 cm ↑ | 0.300 | 0.421 | 0.121 |

Every delivered model had every camera pair within 5° of the reference rotation.

## Finding 3 — the spread follows which sparse model is densified, through its placement

Densifying another correct model of the same capture with the same settings moved the
cloud as far as the sessions did. Within a capture the better cloud sat on the model whose
camera centres were closer to the reference, at differences well under 1% of the span:

| capture | centre error, median % of span → cloud |
| --- | --- |
| Caterpillar | 0.20 → 29.3 and 30.8 mm; 0.68 → 62.9 mm |
| Barn | 0.12–0.21 → 37.8 to 52.1 mm; 0.56 → 94.3 mm |
| Meetingroom | 0.28 → 91.6 mm; 2.82 → 135.8 mm |
| scan15 | 0.06 on every model → 0.518 to 0.548 mm |

The built interior is the exception: two models both at 0.12% gave 0.300 and 0.379 F1,
so something besides placement moves it there. Not isolated.

## Finding 4 — the rotation share does not see placement

Three models had every camera pair within 5° of the reference rotation and centres beyond
1% of the span (2.82%, 1.92%, 1.44%); one of them was delivered and gave the worst
Meetingroom cloud. A model inside both thresholds (share 0.99, 0.56%) gave the worst
Barn cloud. Pose truth in the earlier campaigns of this series was the rotation share.

## Finding 5 — the centre form of the two-estimator reading ranks placement, below its fire level

Each model was read against both correspondence-free estimators in the centre form — its
camera-centre disagreement with each estimator over the estimators' disagreement with each
other — and every candidate reading was tested for ranking the 45 models by centre error
within each capture. The test asked two things: does it order the three pairs whose clouds
differ most (Caterpillar 0.20% against 0.68%, Barn 0.12–0.21% against 0.56%, Meetingroom
0.28% against 2.82%), and does it rank strongly (ρ ≥ 0.8) on most captures. Only the centre
form did both:

| capture | centre form | centre disagreement with one estimator alone, the lower of the two | rotation form |
| --- | --- | --- | --- |
| Caterpillar | 0.96 | 0.96 | 0.68 |
| Barn | 0.93 | 0.16 | 0.67 |
| scan15 | 0.93 | 0.08 | −0.37 |
| Meetingroom | 0.80 | 0.80 | 0.80 |
| office | 0.49 | 0.32 | 0.35 |

Within-capture rank correlation with centre error, per reading. Every model, verifier and
health reading besides these was strong on two captures at most, and several change sign
between captures; the mean reprojection error is Finding 6.

The clouds follow it, with the same dense settings within a session:

| capture | centre form → cloud |
| --- | --- |
| Caterpillar | 0.78–0.82 → 29.0–30.8 mm; 1.60 → 62.9 mm; 2.15–3.39 → 68.0–79.3 mm |
| Barn | 1.07 → 37.8–39.6 mm; 1.09–1.11 → 40.4–52.1 mm; 1.14 → 68.1 mm; 1.15 → 94.3 mm; 1.26 → 122.9 mm |
| Meetingroom | 1.23–1.25 → 91.6 mm; 4.56–4.79 → 128.9–135.8 mm |
| scan15 | 0.50 on every model → 0.518–0.548 mm |
| office | 0.63–0.75 → 0.30–0.43 F1, in no order |

On all three outdoor-and-enclosure captures the candidate the centre form read lowest gave
the best cloud, and none of those readings reached the fire level of 2. Caveats: on the
rig orbit every model reads alike, so its 0.93 ranks differences that do not matter; on
the enclosure the ranking rests on four models; on Barn readings 0.08 apart separated
clouds 2.5× apart, so a small difference in the reading is not a small difference in the
cloud. On the built interior it does not rank (Finding 3's exception).

## Finding 6 — lower reprojection error went with worse placement

On the three outdoor-and-enclosure captures the mean reprojection error ranked the models
against their centre error (Barn −0.79, Caterpillar −0.79, Meetingroom −0.80): the model
with the lower error was the one placed further out. On the rig orbit and the built interior
it ran weakly the other way (0.54, 0.30). One of Finding 2's sessions met exactly this: it
took the two-estimator reading on its two finalists, read both as quiet (1.60 and 0.82),
then chose by the ladder's dense tie-break — lower error in every bucket — and delivered
the 62.9 mm cloud over a 30.8 mm one. The two were not a model and its refinement but the
incremental and global routes' models of the same capture.

## Finding 7 — across the two routes on an outdoor object orbit, the lower centre form was the worse placement

A later pair of sessions on a later context built both routes on each of two outdoor object
orbits, read both models quiet, and densified the one the centre form read lower: the
incremental route's second solve both times. With no agent, the other model of each session was
densified with the same settings (1600 px, consistency off, fusion 2), and each delivered model
was re-densified as a control. Both controls reproduced their delivered scores exactly.

| capture | route | centre form | centre error, median % of span | cloud |
| --- | --- | --- | --- | --- |
| Barn | incremental, second solve (delivered) | 0.93 | 0.24–0.28 | 83.1 mm |
| Barn | global reconstructor + BA | 1.09 | 0.21 | 48.5 mm |
| a second outdoor object orbit, outside the corpus | incremental, second solve (delivered) | 0.871 | 0.16 | 21.9 mm |
| the same | global reconstructor + BA | 0.895 | 0.13 | 19.2 mm |

Finding 3 held: the better cloud sat on the model placed closer to the reference. Finding 5 did
not hold across routes: the lower reading was the worse placement, at gaps of 1.17× and 1.03×,
while Finding 5's own Barn models ranked correctly across routes at 1.04×. No gap in the reading
separates the two cases. What every measured outdoor object orbit shares (Barn and Caterpillar
here and in Finding 5, and the orbit outside the corpus) is that each quiet global model gave a
better cloud than each incremental one. Finding 6 held as well: the incremental models carried
the lower reprojection error (0.45 against 0.68–0.72 px; 0.67–0.74 against 0.98 px).

The exception, and its scope: on an indoor enclosure outside the corpus, quiet global models
read 1.29–1.42 and sat 18–23% of the span from the reference, while the incremental model read
0.69 and sat at 1.3%. There the reading was right, and preferring the global route would have
been wrong by an order of magnitude. Across every recorded dense session, preferring the global
route between quiet models on outdoor object orbits, unless the other route reads at least 1.5×
lower, changes four deliveries, and all four move to a model placed closer to the reference.

## Finding 8 — on a site walk at full frame count, a detector-based global chain gave the best cloud

Two sessions on a site walk followed the detector-free matcher the capture's row names, and
registered 41 and 34 of 45 cameras incrementally. The detector-free global model fired the
centre form at 11×. Densified with the same settings (1600 px, consistency off, fusion 2):

| capture | chain | cameras | F1 @ 2 cm, as placed |
| --- | --- | --- | --- |
| electro | RoMa → incremental, verified core (delivered) | 34 of 45 | 0.491 |
| electro | the same core with the missing cameras filled | 45 of 45 | 0.447 |
| electro | SIFT+CLAHE → NN → global reconstructor + BA, an earlier session | 43 of 45 | 0.664 |

The delivered model's control reproduced its score exactly. The detector-based global chain had
not been tried on this capture in the campaign the row cites (alternatives there were on the
incremental route at 1024 px).

## What this does not establish

Five captures, two sessions each, one context. Finding 5 is a ranking among candidates of
one capture, not a threshold: no centre-form value marks a model good, and the reading was
tested only among models whose rotations were already correct. It was not tested on a
capture where only one model was built. The interior's spread is not explained.

Findings 7 and 8 are two outdoor object orbits and one site walk, one session each, with
placement scored against reference cameras. The preference they support between routes was
checked against every recorded dense session, not run forward on new captures.
