# Campaign: dense-variance-2026-10 — how far a dense score moves with nothing changed

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports live
in [`plan/dense.md`](../plan/dense.md) and, for reading dense comparisons, in
[`EVIDENCE.md`](EVIDENCE.md).

## What was run

Five corpus captures, two independent agent sessions each on one context, full captures,
strict context. Then, with no agent: each delivered dense step replayed twice more on its
own inputs; and every other sparse model a session built that was correct by reference
(every camera pair within 5° of the reference rotation, centres within 1% of the span
after a similarity fit) densified once with the delivered dense settings. Scored by each
benchmark's own evaluation, as placed; camera centres scored against reference poses.

## Finding 1 — stereo on a fixed input reproduces itself

Three draws per session agreed to 0.01 mm on the three outdoor-and-enclosure captures,
0.0001 mm on the rig orbit, and exactly on the built interior. The geometric stereo module
adds no spread of its own.

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

## What this does not establish

Five captures, two sessions each, one context. No reading available to an agent has yet
been tested against placement at this scale. The interior's spread is not explained.
