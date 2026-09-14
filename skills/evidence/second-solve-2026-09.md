# Campaign: second-solve-2026-09 — escaped points, the second solve, the retry and the veto

**This is a raw evidence table. Cite it; do not plan from it.** The rules these
rows support live in `PoseEssentialToPnP`'s
[limitations](../../modules/pose_incremental/skills/limitations.md#escaped-points-start-a-second-solve)
and tuning, and in `SparseVerification`'s skill files.

## Protocol

- **Configurations.** Every configuration in the campaign stores where points
  escaped the pose stage's in-loop window: 45 in the first experiment, 46 in the
  width sweep and the retry experiment, across 14 captures. Plus one match set,
  solved three times, whose correspondences support more than one stable model;
  and 40 configurations where nothing escaped, as the control for the trigger.
- **Each run** re-solved the configuration from its cached tracks through the pose
  stage, its own triangulation and global adjustment, then the verifier. Pose-stage
  variants ran on a scratch copy of the module; the final re-run ran the committed
  module through the service.
- **Scoring.** Reference geometry, AUC@5 over image pairs, a pair touching an
  unregistered camera counted as a failure. Reference geometry scored the runs; no
  rule used it.
- **Noise floor.** A change counts only beyond 0.0064 AUC@5, the 95th percentile of
  baseline-against-repeat differences. Intervals are bootstrap 95% over
  configurations; p is a sign test on better against worse.

## What changes the finished model

45 configurations where points escaped; each variant against its own baseline.

| variant | better | worse | mean change | 95% interval | p | vetoed |
| --- | --- | --- | --- | --- | --- | --- |
| widen the in-loop window | 22 | 2 | +0.065 | +0.028 to +0.105 | <0.0001 | 0 |
| remove points beyond the reprojection bound | 16 | 5 | +0.025 | −0.008 to +0.056 | 0.03 | 1 |
| in-loop solve off | 20 | 12 | +0.040 | −0.005 to +0.086 | 0.22 | 0 |
| drop two-view tracks | 13 | 16 | −0.017 | −0.056 to +0.020 | 0.71 | 0 |
| remove escaped points | 7 | 16 | −0.020 | −0.058 to +0.017 | 0.09 | 1 |

On the match set with more than one stable answer, three repeats each, final
rotation error: first solve 0.06° to 0.67°; wider window 0.067° to 0.071°; in-loop
solve off 0.055°; points beyond the bound removed 7.6°, vetoed; escaped points
removed 19.1°, vetoed.

## Which width

46 configurations, each width against the first solve.

| width | n | better | worse | vetoed | mean change | 95% interval |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | 44 | 19 | 5 | 1 | +0.014 | −0.035 to +0.058 |
| 16 | 41 | 22 | 4 | 1 | +0.060 | +0.019 to +0.102 |
| 20 | 41 | 22 | 2 | 0 | +0.071 | +0.032 to +0.115 |
| 28 | 40 | 25 | 1 | 0 | +0.094 | +0.057 to +0.137 |
| 40 | 16 | 10 | 0 | 0 | +0.096 | +0.050 to +0.146 |
| whole capture | 46 | 26 | 2 | 0 | +0.096 | +0.059 to +0.136 |

| stopping rule, veto and failure fall back to the first solve | mean AUC@5 |
| --- | --- |
| first solve only | 0.576 |
| fixed width 20 | 0.639 |
| fixed width 28 | 0.658 |
| widen until nothing escapes | 0.621 |
| widen while escapes at least halve | 0.581 |
| best width per configuration, needs reference geometry | 0.673 |

On the configurations larger than 28 images, 40 beat 28 on 4 and lost on none.
On the multi-answer match set, widths 12 and 16 landed 10° to 20° off on every
repeat and were vetoed every time; 20 and wider landed within 0.07°.

## The trigger

Where nothing escaped (39 configurations), the wider solve left 33 unchanged, and
was better on 2 and worse on 4 — three of the four being one configuration where
the wider solve failed.

## Choosing between the two solves

85 configurations, both solves run.

| rule | mean AUC@5 | kept the worse solve |
| --- | --- | --- |
| first solve only | 0.482 | 24 |
| keep the second unless it fails or is vetoed | 0.517 | 3 |
| the same, re-solving only where points escaped | 0.516 | 4 |
| keep the one with the lower own reprojection error | 0.489 | 22 |
| keep the one with the lower verifier reading | 0.513 | 6 |
| best of the two, needs reference geometry | 0.521 | 0 |

## The retry

46 configurations, first and second solve, each with and without the retry.

| | first solve | second solve |
| --- | --- | --- |
| runs with a refused camera | 16 | 17 |
| cameras refused | 89 | 83 |
| runs where the retry registered more | 1 | 2 |
| AUC@5, better / worse / unchanged | 1 / 0 / 45 | 3 / 0 / 43 |
| AUC@5 on registered pairs only, better / worse | 1 / 1 | 1 / 0 |
| vetoes added or removed | 0 | 0 |

The second solve registered fewer cameras than the first on one configuration
without the retry, and on none with it. Every change in registration: the second
solve on a shallow-relief interior, 29 → 31 of 31 cameras, AUC@5 0.856 → 0.981; a
first solve on an enclosed courtyard, 24 → 25 of 38, AUC@5 0.293 → 0.296 but 0.747
→ 0.693 on registered pairs, the recovered camera being less accurate than its
neighbours; a second solve on an outdoor site, 24 → 25 of 45, 0.261 → 0.283.

| rule, AUC@5 with missing cameras as failures | mean |
| --- | --- |
| first solve only | 0.576 |
| second solve, no retry | 0.661 |
| second solve, no retry, never fewer cameras | 0.653 |
| second solve with the retry, with or without that condition | 0.664 |

## The registration tolerance

Every case where a second solve registered fewer cameras than the first:

| case | first solve | second solve | AUC@5 |
| --- | --- | --- | --- |
| shallow-relief interior, no retry | 31/31, accepted | 29/31 | 0.508 → 0.856 |
| multi-answer match set, repeat 0, no retry | 44/45, accepted | 42/45 | 0.771 → 0.844 |
| multi-answer match set, repeat 1, with or without the retry | 45/45, vetoed | 42/45 | 0.394 → 0.844 |

Each stayed inside the pose stage's registered-fraction band and was the better
model. Nothing near the band's edge was tested: the band is the tolerance as a cost
trade-off, not a measured turning point.

## The veto

Every finished model of the sixteen captures, held-out reading against the 3 px
threshold:

| capture | reference rotation error | reading, px | share of matches held out |
| --- | --- | --- | --- |
| DTU, seven scans | 0.078° to 0.118° | 0.103 to 0.230 | 0.20 to 0.48 |
| ETH/courtyard | 0.072° | 0.120 | 0.75 |
| ETH/facade | 0.061° | 0.126 | 0.16 |
| ETH/delivery_area | 0.048° | 0.145 | 0.28 |
| ETH/meadow | 0.136° | 0.165 | 0.91 |
| ETH/playground | 0.088° | 0.200 | 0.52 |
| ETH/kicker | 0.040° | 0.205 | 0.19 |
| ETH/electro | 0.079° | 0.309 | 0.97 |
| ETH/office | 0.090° | 0.889 | 0.30 |
| ETH/relief | 3.068° | 0.109 | 0.22 |

| multi-answer match set | reference rotation error | reading, px | verdict |
| --- | --- | --- | --- |
| three correct solves | 0.073° to 0.077° | 0.242 to 0.252 | consistent |
| intermediate | 0.664° | 0.991 | consistent |
| drifted | 7.119° | 18.07 | contradicted |
| drifted | 7.143° | 19.92 | contradicted |

The relief model 3° off reads clean: an error every pair's matches allow passes
the veto.

## The final re-run

The sixteen captures re-run through the service with the committed pose module
(1.4.0), images checked against source. Nine kept their second solve, none was
vetoed, and none gave up a camera. On the shallow-relief interior the second
solve's pose stage refused two cameras and the retry placed both. Pooled AUC@5
0.890, mean over scenes 0.901. Per-capture rows:
[agentic-campaign-2026-09](agentic-campaign-2026-09.md#the-model-shipped-for-each-capture).

## What each claim rests on

| claim | rows |
| --- | --- |
| escaped points are counted and trigger a second solve; nothing escaped, nothing gained | [What changes the finished model](#what-changes-the-finished-model), [The trigger](#the-trigger) |
| a fixed width, 28 by default and 40 as the last resort | [Which width](#which-width) |
| keep the second unless it fails or is vetoed, never on reprojection error | [Choosing between the two solves](#choosing-between-the-two-solves) |
| refused cameras are retried once | [The retry](#the-retry) |
| registration counts only against an accepted first solve, within the band | [The registration tolerance](#the-registration-tolerance) |
| the verifier is a veto, not a ranking, and blind to an error the matches allow | [The veto](#the-veto), [Choosing between the two solves](#choosing-between-the-two-solves) |
