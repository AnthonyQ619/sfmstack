# Campaign: fill-and-view-graph-2026-10 — two held questions, recorded

**This is a raw evidence table. Cite it; do not plan from it.** Finding 1 records a
question still open between [`plan/pose.md`](../plan/pose.md#when-it-fires-fill-rather-than-swap--and-do-not-refine-the-fill)
and PoseFill's page. Finding 2 records a check of the view-graph rule in
[`plan/scene_to_pipeline.md`](../plan/scene_to_pipeline.md#textureless_fraction--meaningless-without-empty_regions).

## What was run

**Fill cases.** The standing SuperPoint-to-global composition on all 24 ten-view corpus
stagings, verified, no agent. Each model that registered 6 to 9 of 10 cameras with no
error-severity verifier diagnostic was finished twice: the core alone, and the core plus
`PoseFill` (`PoseVGGT` primary, `PoseMapAnything` second), triangulated and refined.
Scored by AUC@30. Four qualifying captures were needed to decide anything.

**View-graph check.** Agent sessions, one per capture, strict context, on the context
that added the view-graph rule: four ten-view stagings and one full capture with closely
spaced views.

## Finding 1 — three fill cases, too few to decide

| capture | core: registered, AUC | filled cameras | core + fill: AUC |
| --- | --- | --- | --- |
| `/ETH/relief` | 6 of 10, 0.332 | 4 | 0.853 |
| `/ETH/office` | 8 of 10, 0.588 | 2 | 0.596 |
| `/tum_vi/room4` | 8 of 10, 0.490 | 2 | 0.494 |

The fill never lost; it gained beyond 0.05 once.

## Finding 2 — the view-graph rule was read and followed

| capture | first detector | classical attempts before switching | cites the graph | AUC or mm (before the rule) |
| --- | --- | --- | --- | --- |
| `/DTU/scan77` | SIFT | 1 (3 components, a camera on one pair) | yes | 0.967 (0.972) |
| `/ETH/meadow` | SIFT | 1 (2 components) | yes, quotes the rule | 0.962 (0.977) |
| `/euroc/V2_01_easy` | SuperPoint | — | no | 0.849 (0.849) |
| `/tum_vi/room2` | SuperPoint | — | yes | 0.798 (0.798) |
| `/DTU/scan15`, closely spaced, full capture | SIFT, kept | — | yes, checked and kept | 0.534 mm (0.534) |

Before the rule, the scan77 session spent three classical runs
([agent-rerun-2026-10](agent-rerun-2026-10.md#finding-5--a-classical-detectors-view-graph-broke-first-and-the-reading-said-so)).
No result moved beyond 0.05; the closely spaced capture kept its classical detector.

## What this does not establish

One session per capture for Finding 2; three cases for Finding 1, all ahead or level for
the fill, none where the core won.
