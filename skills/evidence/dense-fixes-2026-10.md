# Campaign: dense-fixes-2026-10 — four dense regressions replayed without an agent

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports live
in `DenseFusion`'s and `DenseMVS`'s tuning, `DenseVGGT`'s SKILL and limitations, and the
plan brief's worked-precedent field.

## What was run

After the locked-context dense batch, four captures came out worse than their record or far
behind a network. Each was replayed offline, no agent: the record runs' kept stereo workspaces
re-fused with `DenseFusion` at `min_num_pixels` 2–5 (one stereo pass, every setting from it),
and dense runs from the batch's kept sparse models with one setting changed at a time. Scored
by each benchmark's own evaluation, as placed unless stated. Re-fusing a record workspace at its
own setting reproduced the record's score exactly, so the replays measure what they change.
Only corpus captures are named; captures outside the corpus are counted.

## Finding 1 — off a studio rig orbit, stepping fusion down to 2 was best, past where the doubling rule stops

Stereo pass: geometric check off, `fusion_min_num_pixels` 4 (the delivery anchor). ETH: F1 at
2 cm ↑. Tanks and Temples: overall mm ↓.

| capture | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- |
| `/ETH/courtyard` | **0.603** | 0.562 | 0.530 | 0.507 |
| `/ETH/delivery_area` | **0.724** | 0.692 | 0.668 | 0.647 |
| `/ETH/electro` | **0.653** | 0.618 | 0.594 | 0.575 |
| `/ETH/facade` | **0.455** | 0.408 | 0.377 | 0.355 |
| `/ETH/kicker` | **0.654** | 0.605 | 0.567 | 0.535 |
| `/ETH/meadow` | **0.470** | 0.407 | 0.362 | 0.321 |
| `/ETH/office` | **0.492** | 0.454 | 0.424 | 0.404 |
| `/ETH/playground` | **0.582** | 0.552 | 0.522 | 0.498 |
| `/ETH/relief` | **0.738** | 0.705 | 0.682 | 0.665 |
| `/tanks_and_temples/Barn` | **38.4** | 39.3 | 40.7 | 42.5 |
| `/tanks_and_temples/Caterpillar` | **47.2** | 47.8 | 49.4 | 51.0 |
| `/tanks_and_temples/Meetingroom` | **78.2** | 86.2 | 92.0 | 97.7 |

Monotonic on every row. On the seven captures of these kinds outside the corpus (site walks,
outdoor object orbits), fusion 2 was best on six and the seventh was flat within 3%. The record
sessions that stepped down at all stopped at 3 by the doubling rule; the locked-context batch
never stepped down, because its tasks named no objective and `DenseFusion`'s tuning reads that
as accuracy.

On studio rig orbits the curve goes the other way: on two corpus orbits, stepping down from 5
cost accuracy or changed nothing (`/DTU/scan33` 0.777 at 5, 0.788 at 4, 0.943 at 2; `/DTU/scan15`
flat), measured in the head-to-head campaign's direct dense runs.

## Finding 2 — on a studio rig orbit the module defaults were at least as good as the anchor

Every studio rig orbit's record was densified at the module defaults (check on, fusion 5); the
batch used the anchor (check off, fusion 4). On 21 of 22 orbits the batch landed within ±5% of
the record on the best-fit score or better. On the 22nd the replay isolates the setting:

| `/DTU/scan75`, best fit mm ↓ | anchor (off, 4) | defaults (on, 5) |
| --- | --- | --- |
| the batch's sparse model | 0.821 | **0.743** |
| the record's sparse model | — | 0.745 (the record) |

## Finding 3 — on a vegetated site walk the detector-free chain's model is what densifies

`/ETH/meadow`, full capture, same images and stereo settings throughout:

| sparse model | points fused | F1 as placed | F1 best fit |
| --- | --- | --- | --- |
| RoMa → union-find → incremental → BA (the record's chain, replayed) | 261,658 | **0.371** | 0.394 |
| LightGlue chain (batch session 1) | 169,690 | 0.039 | 0.123 |
| LightGlue/NN chain, geometric check on (batch session 2) | 148,946 | 0.080 | 0.189 |

Camera placement does not separate them: the RoMa model's centres sit 27% of the span from the
reference after a similarity fit, session 1's 0.91%. The ten-view sparse deliverable on the same
site reached 0.97–0.99 without RoMa, so the matcher matters here for the dense deliverable, not
for pose accuracy. Of the 23 batch sessions on corpus captures, 5 read `INDEX.md`; 19 used the
matcher their capture's row names anyway. Of the four that did not, two lost nothing against
their record; the other two were this capture's two sessions.

## Finding 4 — DenseVGGT on another estimator's poses

On an indoor capture outside the corpus whose every geometric model was folded, two sessions
delivered `DenseVGGT` with VGGT's depth unprojected through `PoseMapAnything`'s poses (the
chain's current poses). The measured depth scale was 1.37 and 1.08 with `depth_scale_inconsistent`
raised (spread 0.65 on the first), and the cloud scored 183 mm. The same call on `PoseVGGT`'s
poses measured 1.000 (spread 0.04) and scored **48.9 mm**, ahead of VGGT run end to end on that
capture under the robust point-map protocol (accuracy / completeness 42 / 17 mm against 75 / 46).
One capture, outside the corpus; no corpus capture delivered `DenseVGGT` on mixed poses.

## Finding 5 — on an indoor capture, the stereo pass's completeness says which dense module wins

Every kept delivered model of seventeen indoor sessions was densified both ways with no agent:
`DenseMVS` (1600 px, consistency off, fusion 2) and `DenseVGGT` (stride 2, on the refined
model). Each session's own delivery reproduced its score. Completeness is the stereo pass's
`depth_map_completeness`.

| capture | completeness | `DenseMVS` | `DenseVGGT` |
| --- | --- | --- | --- |
| office (six sessions) | 0.26–0.39 | 0.329–0.492 F1 | **0.538–0.694 F1** |
| an indoor office outside the corpus | 0.32 | 90.3 mm | **40.2 mm** |
| another indoor office outside the corpus | – | 140.8 mm | **49.6 mm** |
| Meetingroom | 0.18 | 137.7 mm | **72.3 mm** |
| Meetingroom, another session | 0.53 | 110.2 mm | **96.8 mm** |
| an indoor enclosure outside the corpus | 0.64 | **115.4 mm** | 125.5 mm |
| two indoor living rooms outside the corpus | 0.78, 0.91 | **27.7, 20.9 mm** | 44.4, 60.9 mm |
| an indoor path outside the corpus | 0.51 | **0.520 F1** | 0.460 F1 |
| kicker | 0.69 | **0.660 F1** | 0.578 F1 |
| delivery_area | 0.83 | **0.723 F1** | 0.134 F1 |
| relief | 0.86 | **0.739 F1** | 0.224 F1 |

At 0.39 or below the prior won every time and by a wide margin; at 0.51 or above the verified
cloud won every time but once, a narrow loss at 0.53. Two office sessions built the identical
sparse model (poses equal to the last digit): one delivered the prior at 0.694 F1, the other
read the same 0.37 as respectable and delivered the verified cloud at 0.329. Across every
recorded dense session, delivering the prior on indoor captures below 0.45 changes seven
deliveries, and on all seven the paired run puts the prior ahead. Below 0.45 on a studio rig
orbit or outdoors, neither module was compared here.

## What this does not establish

All four are replays from kept models and workspaces: they show what the setting or input
does, not that an agent given the revised context makes the choice. Finding 1's fusion-2 result
is on the record runs' depth maps; the batch's own are deleted. Fusion 1 was not measured.
Finding 2 is one orbit isolated and 21 compared against a record built on different sparse
models. Finding 4 is one capture. Finding 5 is seventeen sessions on indoor captures only; the level
between 0.39 and 0.51 rests on the gap between them, and one capture sits inside it.
