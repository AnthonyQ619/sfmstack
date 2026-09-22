---
module: SparseVerification
module_version: 1.1.0
produces: custom/verification/v1
---

# Reading a SparseVerification artifact

## Layout

One payload file, `pairs`, with one row per matched pair whose two images are
both registered in the model:

| array | shape | meaning |
| --- | --- | --- |
| `image_pair` | `[n, 2]` | scene frame indices of the pair |
| `matches` | `[n]` | the matcher's correspondences on the pair |
| `held_out` | `[n]` | of those, how many the model did not use |
| `residual_px` | `[n]` | median epipolar distance of the held-out ones under the model's relative pose; NaN where too few were held out |
| `residual_all_px` | `[n]` | the same distance over ALL the pair's correspondences, not only the held-out ones; never NaN on a scored pair |

The metrics summarising it: `heldout_residual_px` and its angular twin
`heldout_residual_mrad`, `held_out_share`, `pairs_verified`, and the three graph
readings `supported_components`, `supported_largest_share` and
`agreeing_pair_share`.

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
