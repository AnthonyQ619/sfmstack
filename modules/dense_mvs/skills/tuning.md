---
module: DenseMVS
module_version: 1.0.0
curated_at: 2026-08-11
---

# Tuning DenseMVS

1. `depth_map_completeness` — did the pixels survive at all?
2. `views_contributing` against `input_registered_images` — did every view work?
3. `fusion_ratio` — did the views agree with each other?
4. Only then `point_count`, which is mostly a function of `max_image_size`.

## Reference run

A controlled-rig capture, 8 contiguous images, `max_edge: 1024`, sparse model from
`SparseTriangulation` (4671 points, 8/8 registered), on one A6000 in a container:

| metric | 600 px no geom | 600 px | 1200 px |
|---|---:|---:|---:|
| `point_count` | 46 562 | 47 172 | 128 327 |
| `views_contributing` | 8 | 8 | 8 |
| `depth_map_completeness` | 0.717 | 0.679 | 0.650 |
| `fusion_ratio` | 33.1 | 30.9 | 32.2 |
| `mean_depth_confidence` | null | null | null |
| runtime | 31 s | 75 s | 131 s |

Two things to read off it.

**`geom_consistency` costs completeness and that is what it is for.** 0.717 → 0.679
is the ~5% of pixels that were photometrically plausible in one view and
geometrically impossible across the set. It also cost 44 s and gained 610 points.
The point count barely moves; the *quality* of the points does.

**Measured against reference geometry, though, leaving it ON is the worse trade for a
dense deliverable.** Across a corpus of studio orbits, scored on the published basis
and swept over the whole fusion curve both ways: with the check off, the
accuracy/completeness frontier shifts by roughly 0.015 mm in completeness **at matched
accuracy**, all the way along it, and the best overall measured anywhere came from the
check being off. It is also half the price, because the check runs the whole search
twice.

Two caveats that keep the paragraph above true. The frontier only holds in the sane
region — with the check off AND fusion at its loosest, nothing is verifying anything
and accuracy collapses several-fold. And this was measured on well-posed captures; the
diagnostic value below is unaffected.

**Completeness falls as resolution rises.** 0.717 → 0.650 from 600 to 1200 px. More
pixels means finer detail per pixel and a harder consistency test, so the fraction
kept goes down while the absolute count goes up 2.7x. Never compare completeness
across different `max_image_size` values.

## What this was measured on, and what a second kind of site showed

Every range above comes from studio orbits of compact subjects. A second campaign put
the same delivered region on built frontages and enclosures, vegetated sites and built
interiors, scored against their laser scans, and the ranges were not swept there — so
what follows says how the region behaves away from the bench, not that it is optimal
there.

**Accuracy holds; completeness is what falls.** On those sites, at a working resolution
well below the capture's own, most of the delivered cloud reaches the reference at a
tolerance of a couple of centimetres, while barely more than a third of the reference is
reached back. Relax the tolerance and the gap closes fast — completeness roughly triples
between the tightest and the loosest tolerance measured, and the harmonic mean nearly
triples with it. That shape is a cloud that is coarse, not one with holes: read a low
completeness against a resolution before reading it against the scene.

**So resolution is the first thing to question on a large site**, and the one a dense
plan should state deliberately. A working resolution chosen for a compact subject carries
a point spacing that a site-scale reference will charge for directly, and the reading it
produces is not comparable to the bench numbers above.
Measurements: `skills/evidence/eth-dense-2026-09.md`.

## Delivering a dense cloud

**On a well-posed capture, deliver with the geometric check off and
`fusion_min_num_pixels` one step below the default.** That is one ordinary run, and
it is the best measured trade: on a corpus of studio orbits scored against reference
geometry it improved completeness substantially while keeping accuracy at the level
classical MVS is published at, and it took about half the time of the default.

The region around it, and which way to move within it:

- **The good region is a few pixels either side of the default, with the check
  off.** Across it the overall score is nearly flat — completeness and accuracy
  trade almost evenly. Move down for coverage, up for accuracy.
- **Do not combine the check off with the loosest fusion settings.** With neither
  in force nothing verifies anything, and accuracy collapsed several-fold on every
  capture measured.
- **Keep the check on when the poses are in doubt.** It is also the diagnostic for
  bad poses — see "Nothing survives the filters". The region above was measured on
  captures whose poses were sound.

**When the capture does not look like those** — an unusual subject or rig, or a
first cloud that looks wrong in a way the region does not explain — keep the stereo
pass and explore the fusion setting instead of re-running: `keep_workspace: true`,
then `DenseFusion` at several settings, seconds each. Its SKILL gives the one-call
route from an output you already have, and its tuning gives the rule for when to
stop lowering the setting without reference geometry.

## The runtime knobs, in the order to reach for them

1. **`geom_consistency: false`** — about 2.4× on a full capture, and the only one of
   these that changes what the result *means*: nothing checks the depths against each
   other across views. On a well-posed capture that is also the better delivery
   setting — see "Delivering a dense cloud" — but not when the poses are in doubt.
2. **`window_step: 2`** — about 2.2× above ~1000 px, where neighbouring pixels are
   nearly redundant. Below that it just loses accuracy. This is the cheapest real
   saving that leaves the meaning of the result alone.
3. **`max_image_size`** — **weaker than it looks, and weaker than this file used to
   say.** Halving it saved about 1.75×, not the 4× a quadratic in it predicts,
   measured on captures that ran both resolutions. It still costs point count in
   proportion, so it is a poor trade for time alone. 600 px to answer "does this
   pipeline work at all" in under a minute, then go to the real value.
4. **`num_samples`** — linear. 15 → 8 is a real saving with visible noise cost.

The per-view costs these come from are in
`skills/evidence/dtu-dense-promoted-2026-09.md`; the eight-view table above predicts
the shape of the curve but not its height at real view counts.

## Nothing survives the filters

`depth_map_completeness` near zero. Four causes, in the order worth checking:

**The poses are wrong.** Check this first, and check it before touching any filter.
Bad poses fail the *geometric* pass while sailing through the photometric one, so
the symptom is completeness that collapses when `geom_consistency` is on and
recovers when it is off. **Here** turning it off is not a fix — it is switching off the
test that caught the problem. Bundle-adjust and re-run. (That is about this diagnostic.
As a delivery setting on a capture whose poses are sound, the check off is the better
measured trade — see above.)

**The scene is low-texture.** Lower `filter_min_ncc` toward 0.05. Reflective,
transparent and untextured surfaces are where PatchMatch has nothing to correlate,
and no setting invents evidence — this is the case for `DenseVGGT` instead, whose
learned prior fills what it cannot verify. **But check first that you can reach it:**
it consumes a `poses/v1`, which no stage after the pose one produces, so a refined
model cannot feed it and a globally-reconstructed pipeline never has one. See
[plan/dense.md](../../../skills/plan/dense.md). If it is out of reach, the fusion
setting is the lever that remains.

**The baselines are small.** `filter_min_triangulation_angle` defaults to 3
degrees. A drone or handheld sequence with small steps between frames may need
1.0–1.5, and the depth it then keeps is softer along the ray.

**Each surface is seen by too few views.** Lower `filter_min_num_consistent` to 1.
That is the strictest filter in practice, and at 1 there is no multi-view
verification left — the result is closer to monocular depth than to MVS.

## `fusion_min_num_pixels` is the one filter measured to buy coverage

**Measured on a dense batch against reference geometry**, on captures spanning the
best and the worst coverage in that batch: lowering it from the default recovered
rim and thin structure on **every capture tried**, emitting roughly two-thirds again
as many points, improving completeness on all of them and paying a little of it back
in accuracy — visible on well-covered captures, absent on starved ones. Net, it is
a real gain of a few hundredths of a millimetre on the overall.

So it is a default worth revisiting when completeness is the deliverable — the
region to use is under "Delivering a dense cloud", and `DenseFusion` explores it on
one stereo pass. It is **not a fix for a starved capture**: the gain is modest and it
does not reach a capture whose photometry denied the module evidence in the first
place.

Two neighbours were measured beside it and did not move: the correlation gate
(`filter_min_ncc`) did nothing at all in either direction, and a wider correlation
window helped one capture and hurt another.

## Fusion produced nothing but completeness is healthy

Then the filters are fine and fusion is the problem: lower
`fusion_min_num_pixels`, or raise `fusion_max_depth_error` if the poses put each
view's surface at a slightly different depth. A `fusion_ratio` near 1 on a
successful run says the same thing more gently — the views are not agreeing, so
each is contributing its own copy.

## The cloud is noisy

Filter harder rather than sampling less — `stride`-style thinning removes points
uniformly, including good ones.

- `filter_min_ncc` to 0.2–0.3 on a well-textured scene.
- `filter_min_num_consistent` to 3–4 on a set with heavy overlap.
- `fusion_min_num_pixels` to 10 on a dense capture. This erodes thin structure and
  rim geometry, which is the trade.

## The cloud has holes where there is clearly surface

Expected, and read the images before tuning: the holes will be on specular
highlights, shadow, uniform paint, or glass. If they are somewhere textured and
well-seen, that is still the normal case, not a misconfigured filter: loosening
`filter_min_ncc`, `filter_min_triangulation_angle` and `filter_min_num_consistent` did
not recover such holes on any capture measured. What did recover part of them is the
operating region under "Delivering a dense cloud". Beyond it, no setting tested reaches
them.

If the holes matter more than the verification does, `DenseVGGT` will fill them —
with a prediction rather than a measurement, which
[SKILL.md](SKILL.md#measured-against-densevggt-same-scene-same-poses) quantifies.

## Metrics that mislead

**`point_count` is mostly `max_image_size`.** Quadratic in it. Two runs' point
counts are not comparable unless the resolutions match — 46 562 at 600 px and
128 327 at 1200 px are the same reconstruction.

**A larger cloud is not a better one, across methods.** On the reference scene
`DenseVGGT` produced 47% more points than `DenseMVS` and covered the triangulated
structure half as tightly, in a bounding box 70% larger. Point count measures
willingness to guess as much as it measures coverage.

**`views_contributing` equal to `input_registered_images` is the healthy case,**
and a gap is a different failure from a low `registered_images` — those views were
posed and then photometrically rejected.

**`fusion_ratio` is about overlap, not quality.** ~32 on the reference run means
about 32 depth-map pixels fused into each point. Near 1 means fusion merged
nothing.

**Nothing here measures accuracy against ground truth.** Every number is internal
consistency. A reconstruction can be complete, well-fused, and in the wrong place
if the poses were.

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. The `point_count` and
`views_contributing` bands have no diagnostic reading them — descriptions of
the captures measured so far, not judgements on yours. The specific numbers in
the tuning advice for `max_image_size`, `window_radius`, `window_step`,
`num_samples`, `num_iterations`, `filter_min_ncc` and six more parameters are
settings that worked in isolated testing, not published results — and the numbers for
`fusion_min_num_pixels` come from a dense batch measured against reference
geometry, which is the one part of this file that does not rest on isolated
testing.
