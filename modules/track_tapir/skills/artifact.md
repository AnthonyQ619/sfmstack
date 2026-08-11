---
module: FeatureTrackTapir
module_version: 1.0.0
curated_at: 2026-08-11
---

# Reading a FeatureTrackTapir artifact

## Layout

`tracks/v1`: `observations` with `obs` (track_id, frame_idx, x, y), `track_count`,
and `visibility` — one value per observation, holding `(1 − σ(occlusion)) · (1 −
σ(expected_dist))`.

Note what that array contains here against what it contains in
`FeatureTrackVGGSfM`: there it is a single visibility prediction, here it is a
product of two independent ones. Both are genuine 0–1 probabilities; they are not
the same quantity, and a threshold does not carry between the modules.

Coordinates are in scene pixels, mapped back from the model's square frame.
Predictions landing outside the image are dropped, counted by
`observations_outside_frame`.

## `duplicate_track_rate` is redundancy, not error

0.50 on the reference run. Each query frame re-finds points the others already
had, so the rate rises with `query_frame_num` by construction. **Near zero is the
thing to worry about** — it means the query frames see disjoint parts of the scene.

## `inconsistent_rate` is always 0.0 here

Structural, not a health signal. See
[limitations](limitations.md#inconsistent_rate-cannot-detect-anything-here).

## Metrics that mislead

**Every track metric here flatters this module.** `avg_track_length` 5.98 against
union-find's 2.85, `track_survival_5` 0.754 against 0.116 — genuinely the best in
the repository, and the same tracks triangulate to 1548 points at 1.581 px against
union-find's 4671 at 0.280. Length and precision are separate axes. Nothing in a
`tracks/v1` artifact measures the second one; the triangulator's reprojection
error is the first number that does.

**`track_count` moves with `input_size` for reasons unrelated to quality**, and
barely — 2629 at 256, 2736 at 384 — while the downstream yield goes 0.337 to
0.566. Do not read `input_size` off the track count.

**`mean_confidence` is a product of two sigmoids** and therefore sits lower than a
single-factor confidence would. 0.71 here is healthy.

**`mean_confidence` and `mean_occlusion` read the query selection**, not the
quality of what survived — both are computed over all predictions, before
thresholding.

**`track_survival_10` is 0 on any set of fewer than 10 images.**
