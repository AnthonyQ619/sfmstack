# Campaign: detector-free-2026-10 — which of the two detector-free matchers, and which weights?

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports
live in [`plan/matching.md`](../plan/matching.md), on reaching for RoMa first, and in
[`plan/scene_to_pipeline.md`](../plan/scene_to_pipeline.md), in the `environment` row of
the scene-field table.

## The question

`plan/matching.md` named `FeatureMatchLoFTR` and `FeatureMatchRoMa` only as a pair, and
`plan/scene_to_pipeline.md` said of the `setting: indoor | outdoor` parameter they share:
*"Nothing measured distinguishes these … expect to try both."* Across the
seventy-five-capture pose batch agents reached for RoMa on 42 captures and LoFTR on
**none**.

That asymmetry had a cause, and it was not a selection rule. The two modules' opening
lines are *"The strongest detector-free matcher here"* and *"The escape hatch for scenes
where interest points do not exist."* An agent choosing between the strongest and the
escape hatch picks the strongest, on every scene.

## Method

The seven corpus captures that span `studio`, `indoor` and `outdoor` — DTU/scan1,
DTU/scan48, ETH/courtyard, ETH/electro, ETH/meadow, TUM_VI/room4, EUROC/V2_01_easy —
each matcher at each setting, fourteen configurations per matcher. Run on the **stored**
scene artifact of each capture so the loader and working resolution are held fixed, with
`pairing=exhaustive`, which is what agents used on 77 of 78 recorded detector-free runs.

An earlier pass used the module default `sequential, window=1`. On a ten-image capture
that tries 9 pairs rather than 45 and fragments any capture whose frames are not
adjacent in file order — a DTU orbit, for one — so its numbers are not comparable to the
batch and are not reported here.

LoFTR refused outright on five of these configurations at its default
`min_confidence=0.2` / `min_matches=30`. The module allows 0.0 and 8, so those were
re-run at that floor; three then completed and one of the three was usable. Condemning a
matcher on its defaults would be condemning a default.

A configuration counts as **usable** when the view graph is complete: one component,
`min_image_degree` ≥ 8 of 9, at most two weak pairs. This is not a quality threshold —
an image at degree zero has no surviving pair and cannot register at all.

## Result

| matcher | setting | configs | completed | **usable** | median matches/pair |
|---|---|---|---|---|---|
| RoMa | indoor | 7 | 7 | **7** | ~3000 |
| RoMa | outdoor | 7 | 5 | **5** | ~3100 |
| LoFTR | indoor | 7 | 6 | **1** | ~340 |
| LoFTR | outdoor | 7 | 6 | **2** | ~950 |

**Every RoMa run that completed gave a complete graph — twelve of twelve. LoFTR managed
three of fourteen**, and nine of its twelve completions left the graph in pieces or an
image at degree zero.

Per capture, `d` is `min_image_degree` out of 9:

| capture | RoMa indoor | RoMa outdoor | LoFTR indoor | LoFTR outdoor |
|---|---|---|---|---|
| DTU/scan1 `studio` | OK d9 | OK d9 | frag d0 | OK d9 |
| DTU/scan48 `studio` | OK d9 | OK d9 | frag d0 | frag d3 |
| ETH/courtyard `outdoor` | OK d9 | OK d9 | frag d2 | OK d8 |
| ETH/electro `outdoor` | OK d9 | OK d9 | frag d0 | frag d3 |
| ETH/meadow `outdoor` | OK d9 | OK d9 | OK d9 | refused |
| EUROC/V2_01 `indoor` | OK d9 | **refused** | frag d4 | refused |
| TUM_VI/room4 `indoor` | OK d9 | **refused** | frag d3 | frag d4 |

## The two answers

**Which matcher: RoMa, and the zero-of-seventy-five preference was already correct.**
LoFTR returns roughly a third to a tenth of the correspondences and fragments the view
graph on three quarters of the captures it completes, including at its permissive floor.
It remains the right thing to try where RoMa will not run or runs out of memory, and it
is about three times faster.

**Which weights: the `environment` value decides it, and not symmetrically.** On
`indoor`, `setting: indoor` is required — `outdoor` weights refused to match on both
interior captures while `indoor` worked on both. On `outdoor` and `studio`, `setting:
outdoor` wins on `inlier_ratio` on four of five and never refused, so `studio` maps to
`outdoor` rather than to neither.

## What this campaign does not settle

**Match quality is not registration.** These readings are structural, and a complete
graph does not guarantee a complete reconstruction. The reading also cannot be validated
against delivered registration from the existing batch, because RoMa returned
`min_image_degree` 9, `weak_pairs` 0 and `graph_components` 1 on **all 42** recorded runs
— it is constant on real data and discriminates only against LoFTR.

Nothing here measures what either matcher does to the dense stage, and nothing here
re-tests the `pairing` or `ransac_threshold` advice in either module's `tuning.md`, which
both still rest on nothing.
