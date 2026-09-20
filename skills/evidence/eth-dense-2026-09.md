# Campaign — dense reconstruction of built and vegetated sites, 2026-09

Nine corpus captures, each driven from raw frames to a dense cloud by one isolated agent
reading only the written context, then scored against the site's own laser scans. These
are the captures whose sparse rows are already in [INDEX.md](INDEX.md): outdoor
frontages and enclosures, vegetated sites, and built interiors — the first dense
campaign on anything other than studio orbits of compact subjects.

**Four further captures of the same dataset were held out and are deliberately absent
from this file.** They exist, they were scored, and their numbers are not recorded here
or anywhere else in the context, so they remain available to test whether what is
written below transfers.

## What ran

One agent per capture, context frozen, no interaction. Every capture delivered a scored
cloud. The working resolution was the loader's own — about a quarter of the capture's
long edge, and the same resolution every earlier campaign in this series used. Four of
the nine were delivered through a fusion step, the rest straight from the stereo pass.

## Protocols

Two, because dense results on this dataset are published under two and they are not
interchangeable.

**A — the dataset's own multi-view evaluation.** Its public program, unmodified, against
the laser scans, with the scans' beam geometry modelling free space. It reports the share
of cloud points that reach the scan (accuracy), the share of scan points the cloud reaches
(completeness), and their harmonic mean, at tolerances in metres. Each cloud is first
placed by fitting its own registered camera centres to the reference centres — no scan
geometry in that fit — and the published basis then refits the cloud itself to the scan.

**B — the point-map evaluation the learned dense methods report.** One point per
ground-truth pixel of every fifth view, against the dataset's own depth maps, aligned by
correspondence and ICP, scored as mean and median distance with no cutoff. Ported from the
reference implementation and checked first: that implementation's own model, scored
through the port, lands within 4% of its published distances and 0.01 of its published
normal consistency.

## Protocol A, per capture — published basis, percentages

| capture | registered | points | accuracy @2 cm | completeness @2 cm | F1 @2 cm | F1 @5 cm | placement, cm |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ETH/courtyard | 38/38 | 1 817 605 | 74.2 | 36.0 | 48.4 | 80.2 | 1.1 |
| ETH/delivery_area | 44/44 | 3 397 959 | 85.2 | 56.8 | 68.2 | 85.6 | 0.4 |
| ETH/electro | 40/45 | 1 445 419 | 88.3 | 42.4 | 57.3 | 73.7 | 0.5 |
| ETH/facade | 45/50 | 1 716 450 | 69.6 | 28.4 | 40.3 | 69.5 | 0.8 |
| ETH/kicker | 31/31 | 1 260 953 | 81.2 | 45.4 | 58.2 | 74.6 | 0.2 |
| ETH/meadow | 15/15 | 261 397 | 78.0 | 25.8 | 38.8 | 58.8 | 3.6 |
| ETH/office | 26/26 | 678 209 | 70.4 | 27.0 | 39.0 | 56.2 | 0.2 |
| ETH/playground | 38/38 | 1 663 017 | 76.5 | 45.4 | 56.9 | 73.4 | 0.4 |
| ETH/relief | 31/31 | 1 335 207 | 96.8 | 53.3 | 68.7 | 81.2 | 0.1 |

Means over the nine, published basis:

| tolerance | accuracy | completeness | F1 |
| --- | --- | --- | --- |
| 1 cm | 62.0 | 20.9 | 30.4 |
| 2 cm | 80.0 | 40.0 | 52.9 |
| 5 cm | 93.1 | 60.3 | 72.6 |
| 10 cm | 96.7 | 69.5 | 80.3 |

## Protocol B, per capture — metres, mean distance

The delivered cloud rendered into each sampled view, beside the same capture's per-view
stereo depth where the capture could supply it. Two of the nine could not: the stereo
pass writes per-view depth only when every undistorted view shares a resolution, and
those captures mix source sizes.

| capture | cloud, accuracy | cloud, completeness | cloud, N.C. | depth maps, accuracy |
| --- | --- | --- | --- | --- |
| ETH/courtyard | 0.056 | 0.241 | 0.959 | not available |
| ETH/delivery_area | 0.088 | 0.146 | 0.951 | 0.374 |
| ETH/electro | 0.062 | 0.368 | 0.921 | not available |
| ETH/facade | 0.041 | 0.518 | 0.934 | 0.159 |
| ETH/kicker | 0.209 | 0.232 | 0.788 | 0.610 |
| ETH/meadow | 0.184 | 0.928 | 0.800 | 0.189 |
| ETH/office | 0.018 | 0.223 | 0.870 | 0.100 |
| ETH/playground | 0.210 | 0.245 | 0.760 | 0.593 |
| ETH/relief | 0.015 | 0.044 | 0.944 | 0.066 |

Means over the seven that supplied both: cloud 0.109 accuracy / 0.334 completeness /
0.864 N.C.; per-view depth 0.299 / 0.296 / 0.770. The cloud was the better entry on five
of those seven.

## What was derived from these rows

| Claim | Where it is stated | Supported by |
| --- | --- | --- |
| Away from studio orbits, accuracy holds and completeness is the axis that falls; scores climb steeply with the tolerance, which is the signature of a cloud that is coarse rather than absent | `modules/dense_mvs/skills/tuning.md`, "What this was measured on"; `plan/dense.md`, "What HAS now been measured" | the Protocol A means: F1 30 → 53 → 73 → 80 across 1, 2, 5 and 10 cm, with accuracy already at 80 by 2 cm |
| Deliver the fused cloud, not the raw per-view depth, on sites carrying sky, foliage or glass | `modules/dense_mvs/skills/limitations.md`, "Per-view depth is not a deliverable" | Protocol B: the cloud beat per-view depth on five of seven, and by roughly three times on accuracy in the mean |
| Per-view depth cannot be written at all when a capture's views differ in resolution | `modules/dense_mvs/skills/limitations.md` | two of nine captures produced no depth maps for that reason |
| Placement by the capture's own cameras is sound on this kind of site | not stated as guidance; recorded here | eight of nine placed within 1.1 cm, the ninth at 3.6 cm with four of its cameras misplaced by the sparse stage |

## What these rows do NOT support

- **Nothing about the tuning ranges themselves.** Every capture was delivered at the
  region already written; no capture swept a dial. These rows say the delivered region
  produces this shape of result on these sites, not that the region is optimal for them.
- **Nothing about resolution.** One working resolution, so the completeness reading and
  the resolution cannot be separated here. That the two are linked is a reading of the
  tolerance curve, not a measurement against a second resolution.
- **Nothing about generalisation.** All nine are corpus captures; the context was fitted
  on them. The four held-out captures of this dataset are what that question needs.
