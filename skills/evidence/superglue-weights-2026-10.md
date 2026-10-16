# Campaign: superglue-weights-2026-10 — SuperGlue's two weight sets on interiors

**This is a raw evidence table. Cite it; do not plan from it.** The rule it supports lives
on [SuperGlue's page](../../modules/match_superglue/skills/SKILL.md), in the weight-set
choice.

## The question

The page said to switch to the `indoor` weights for room interiors. Agent sessions on
interiors had found the `outdoor` weights ahead. Which, if either, is the better default
indoors?

## What was run

Nine corpus captures tagged as interiors, ten-view stagings, no agent. One fixed
composition: SuperPoint (4096 keypoints) → SuperGlue at its default threshold, once with
each weight set → the global reconstructor → bundle adjustment, threads pinned. Scored by
AUC@30 against reference poses. A difference counted beyond 0.05 AUC or a change in the
matcher's `graph_components`.

## Finding 1 — neither weight set was ahead more often

| capture | `indoor` AUC (components) | `outdoor` AUC (components) | worse |
| --- | --- | --- | --- |
| `/advio/advio-07` | 0.058 (3) | 0.026 (3) | neither |
| `/ETH/delivery_area` | 0.293 (2) | 0.209 (1) | `outdoor` |
| `/ETH/kicker` | 0.837 (1) | 0.618 (1) | `outdoor` |
| `/ETH/office` | 0.533 (3) | 0.596 (2) | `indoor` |
| `/ETH/relief` | 0.332 (3) | 0.332 (2) | neither |
| `/euroc/MH_05_difficult` | 0.211 (2) | 0.320 (2) | `indoor` |
| `/euroc/V2_01_easy` | 0.115 (4) | 0.064 (1) | `outdoor` |
| `/tum_vi/room3` | 0.207 (4) | 0.246 (1) | `indoor` |
| `/tum_vi/room4` | 0.487 (1) | 0.570 (1) | `indoor` |

`indoor` worse on four, `outdoor` worse on three, neither on two. On one capture an
agent session had found `outdoor` ahead; here `indoor` was.

## What this does not establish

One draw per weight set, ten views, one detector. Nothing here says which set suits a
given interior in advance; it says the page cannot name one.
