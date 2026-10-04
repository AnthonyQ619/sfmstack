---
module: SparseVerification
module_version: 1.5.0
produces: custom/verification/v1
---

# Reading a SparseVerification artifact

## Layout

Two payload files. `pairs` has one row per matched pair whose two images are both
registered in the model:

| array | shape | meaning |
| --- | --- | --- |
| `image_pair` | `[n, 2]` | scene frame indices of the pair |
| `matches` | `[n]` | the matcher's correspondences on the pair |
| `held_out` | `[n]` | of those, how many the model did not use |
| `residual_px` | `[n]` | median epipolar distance of the held-out ones under the model's relative pose; NaN where too few were held out |
| `residual_all_px` | `[n]` | the same distance over ALL the pair's correspondences, not only the held-out ones; never NaN on a scored pair |

A second payload file, `cameras`, with one row per registered camera, in
ascending frame order:

| array | shape | meaning |
| --- | --- | --- |
| `image_index` | `[m]` | scene frame index of the camera |
| `median_residual_px` | `[m]` | median held-out residual over every scored pair touching it; NaN where no such pair had enough held out |
| `pairs_scored` | `[m]` | how many pairs that median is over |

The metrics summarising them: `heldout_residual_px` and its angular twin
`heldout_residual_mrad`, `held_out_share`, `pairs_verified`, the three graph
readings `supported_components`, `supported_largest_share` and
`agreeing_pair_share`, the per-camera rollup `worst_camera_index` and
`worst_camera_residual_px`.

**A spatial column lived here through 1.4.0.** `centre_offset_ratio` asked whether a
camera was anywhere plausible rather than whether it agreed with correspondences, and
`camera_spread_ratio` summarised it. Both were retired in 1.5.0: scored on delivered
models the summary read rho +0.05 against rotation error where `heldout_residual_mrad`
reads +0.68, because the models it was built to catch had already been rejected
upstream. See `evidence/band-calibration-2026-10.md`.

`cameras` is present from module version 1.3.0 and is optional on the type, so a reader
working against an older artifact computes what it needs from `pairs` and from the
model's poses. An artifact written by 1.4.0 also carries `centre_offset_ratio`; nothing
reads it.

**Why there are two residual columns, and which to read.** `residual_px` is the
veto's: held-out correspondences are evidence the solve never saw, which is what
makes a contradiction meaningful. `residual_all_px` is not independent of the
solve and the veto ignores it — it exists because it rests on hundreds of
correspondences where the held-out median rests on tens, and the component reading
needs a per-pair estimate stable enough not to cut a sound camera loose by chance.
Built on the held-out column instead, that reading fragmented roughly a quarter of
the corpus captures that had all delivered. So: read `residual_px` to ask whether the
model is contradicted, `residual_all_px` to ask which pairs hold it together.

Artifacts written before module version 1.1.0 do not carry `residual_all_px`; it
is optional on the type for that reason.

## "Used" and "held out"

A correspondence is **used** when both its endpoints lie within a small radius of
observations of the *same* model point, one in each image. The radius is the
widest merge radius any tracker in the stack uses by default, so an observation a
tracker built from a match is always recognised as that match. Everything else is
**held out**, including correspondences the pipeline rejected as outliers.

## Pixels

Residuals are in undistorted pixels at the scene's working resolution. The
matcher's coordinates are undistorted with the scene calibration before scoring,
because a sparse model's observations are undistorted and its poses were solved
in that frame. Where the model refined its own intrinsics, those are used to form
the epipolar constraint.

## Reading the per-pair array

On a contradicted model, sort by `residual_px`. The drifted models measured so far
were contradicted on most of their pairs at once, not on a few, which is what
distinguishes a model in the wrong configuration from a model with a few bad
pairs. A handful of high pairs on an otherwise clean model is more often pairs
where the matcher's outliers are the majority; check their `held_out` against
`matches` before reading anything into them.

## The per-camera rollup

Beside `pairs`, the artifact carries a `cameras` array from 1.3.0: one row per
registered camera with the median held-out residual over every scored pair touching
it, and how many pairs that median is over.

It is published because every reader who needed it computed it by hand from `pairs`,
which is what this corpus treats as the definition of a missing metric. And it is
needed because the remedy for one bad camera is to **drop** it — `plan/pose.md` says
so — and the remedy depends on knowing which. One report put the problem exactly:
*"p90 of 127° with median 2.2° implied one bad camera; remedy depends on knowing
which."*

`worst_camera_index` names it and `worst_camera_residual_px` is its reading.

**A bad camera is not always a stray.** It can sit inside the largest agreeing
component, add nothing to `supported_stray_cameras`, and still be the camera every
pair touching it disagrees with. The two readings answer different questions: the
strays say the model is in pieces, this says which camera the evidence argues with.

Read `pairs_scored` beside the median. A camera with one or two scored pairs has a
median that a single bad pair sets.
