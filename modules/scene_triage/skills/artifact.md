# Artifact — SceneTriage

Produces `scene_analysis/v1`, filling three of its five groups. `SceneMotion`
fills the other two. Every group of this type is optional, which is what lets two
producers cover it without a merge step: read whichever groups are present.

---

## Files and arrays

```
metadata.npz
  n_images            ()        int64    images in the scene
  ordered             ()        bool     capture order established (heuristic)
  capture_interval_s  ()        float64  median EXIF timestamp delta   [source_dir only]
  focal_35mm          (N,)      float64  per-image EXIF focal length   [source_dir only]

photometric.npz
  illumination_change ()        float64  p75 over compared pairs
  color_shift         ()        float64
  exposure_shift      ()        float64
  combined_change     ()        float64
  pair_index          (P, 2)    int32    EXTRA -- which pairs were compared
  pair_combined       (P,)      float64  EXTRA -- the per-pair series behind the p75
  shadow_clipped      (N,)      float64  EXTRA -- per-IMAGE area share at L <= 5
  highlight_clipped   (N,)      float64  EXTRA -- per-IMAGE area share at L >= 250

texture.npz
  density             ()        float64  corner-like features per megapixel
  repetitiveness      ()        float64  median best self-correlation
  textureless_fraction()        float64  area share below the contrast floor
  sharpness           (N,)      float64  per-image Laplacian variance
  sharpness_median    ()        float64  EXTRA -- the scale `sharpness` is read against
  density_per_image   (N,)      float64  EXTRA -- corners/MP, per image
  textureless_per_image (N,)    float64  EXTRA -- area share below the floor, per image
```

**Watch the index.** `photometric.npz` mixes two: everything named `pair_*` is
indexed by `pair_index`, and `shadow_clipped` / `highlight_clipped` are per IMAGE
in scene order, alongside `texture/sharpness`. They live in `photometric` because
that is where the measurement comes from, not because they share an axis with the
pair series.

The `EXTRA` arrays are not in the type schema. That is legal under the
additive-extension rule and they are listed in the manifest's `extras` block, so
a consumer can discover them. They are there because every metric this module
reports is a median or a p75, and the advice attached to those metrics is
per-frame: *open the soft frame before dropping it*, *is the empty region blown
out or merely flat*. Only the first half of each of those fits in a scalar.

`density_per_image` and `textureless_per_image` were added in 1.2.0 for the same
reason and one more: `keypoints_min` on `features/v1` is what predicts a frame
failing to register, and it is the FRAME that starves, not the set. A scene whose
texture sits in half its frames reports the same `texture_density` as one where it
is spread evenly, and those are different captures with different plans.

`shadow_clipped` and `highlight_clipped` were being computed all along and
consumed only as a pairwise DIFFERENCE inside `exposure_shift`, which answers
"did the exposure move between two frames" and cannot answer "is this frame
burnt". Same measurement, kept rather than differenced away. Added in 1.1.0
alongside their medians as metrics.

---

## Metric names and array names

They mostly match. Two do not, and it is worth knowing which:

| Metric | Array |
| --- | --- |
| `texture_density` | `texture/density` |
| `ordered` (0 or 1) | `metadata/ordered` (bool) |

`repetitiveness` is absent from the metrics **and** the array when no image was
large enough to sample patches from — under three patch widths on either side.
The metric is then reported as null rather than as zero, because "not measurable"
and "not repetitive" are opposite conclusions.

---

## Units, and what is comparable with what

**The photometric scores are dimensionless and bounded roughly to [0, 1].** They
are weighted sums of normalised luminance deltas and Bhattacharyya histogram
distances. They are comparable across scenes, which is the whole point of fixing
the weights inside the module rather than exposing them.

**`texture_density` is corners per megapixel at the analysis resolution**, which
is why `analysis_max_side` is documented as "leave it". A count measured at 512px
and one measured at 1024px are two different quantities, and the metric is only
useful as a cross-scene comparison.

**`sharpness` is a raw Laplacian variance** and is comparable only *within* one
scene. The metric derived from it, `sharpness_ratio`, is the worst frame over the
set median, which is scale-free and is the form to compare across scenes.

**`repetitiveness` is a correlation coefficient**, so its scale is fixed — but it
never approaches 0 in practice, because some patch somewhere always correlates.
The measured floor over ten benchmark scenes is 0.62. Read it as a rank, not as a
percentage.

---

## Reading it beside `SceneLoader`

The two artifacts together are the scene description; neither is on its own.

| Question | Where the answer is |
| --- | --- |
| How much image is there to work with? | `SceneLoader`: `n_images`, `megapixels`, `downscale_factor` |
| Was the pixel budget spent on real detail? | here: `texture_density`, `textureless_fraction` |
| Will the same surface look the same twice? | here: `illumination_change`, `color_shift` |
| Will two different surfaces look the same? | here: `repetitiveness` |
| Is per-image geometry consistent? | `SceneLoader`: `mixed_resolution` |
| Did the camera move usefully between frames? | `SceneMotion`, not here |

A worked reading, from DTU scan10 at 12 images:

```
SceneLoader   n_images 12   megapixels 0.79   downscale 0.64   mixed_resolution 0
SceneTriage   combined_change 0.058   texture_density 2304/MP
              textureless_fraction 0.60   repetitiveness 0.65   sharpness_ratio 0.69
```

Which reads as: a small, photometrically stable, uniformly-sized set, where 60%
of each frame carries nothing — the black turntable background — and the
remaining 40% is densely textured and not especially self-similar. The
`textureless` warn fires and is correct and harmless: the empty area is
background nobody wanted reconstructed. That is the case the metric cannot
distinguish on its own, and it is why the warn suggests reading
`spatial_coverage` downstream rather than acting immediately.
