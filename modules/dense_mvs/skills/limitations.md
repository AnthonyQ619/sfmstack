---
module: DenseMVS
module_version: 1.1.0
curated_at: 2026-08-11
---

# What DenseMVS cannot do

## It inherits the sparse model's depth range

COLMAP does not search all of space for each pixel. It derives a depth interval
per view from the sparse points that view already sees, and searches inside it. So
a sparse model that is thin, or that misses a part of the scene entirely, produces
depth maps that are empty exactly there — and the failure looks like MVS failing
rather than like the input being incomplete.

`sparse_too_thin` fires below 20 multi-view points per view. Bundle-adjust and
triangulate more before blaming the filters.

The corollary: **the 2D observation coordinates in the sparse model are never
used.** Depth ranges and source-view selection both come from track membership
alone. What has to be right is which images see which points.

## Only posed views contribute

A view with `valid=False` gets no camera, no image, and no depth map. Coverage
follows the sparse model's `registered_images`, which is why that number is
carried through as `input_registered_images` — a thin dense cloud is far more
often an upstream registration failure than an MVS one.

## It cannot see what it cannot correlate

Textureless walls, specular metal, glass, water, and anything that moved between
exposures. No parameter fixes this; the evidence is not in the images. What
changes with tuning is only whether the module admits noise in those regions or
leaves them empty, and empty is the more useful answer.

**The holes are photometric, not geometric, and that has now been measured.**
Against reference geometry on studio orbits, with occlusion modelled, nearly all of
the surface this module missed was visible and unoccluded in five or more of the
capture's own views — on the worst capture, practically all of it. Geometry and
visibility were not the constraint. The module declined to certify pixels it could
see, which is the design working, and it means **no filter setting is the answer**:
the recovery has to come from the photometry or from the structure upstream.

**One reading predicts it before the run.** Across a batch, the fraction of blown
highlights in the capture tracked this module's own `depth_map_completeness` more
strongly than any parameter moved it, and in the expected direction. `SceneTriage`
publishes it as `highlight_clipped_fraction`. A capture reading high there will
lose dense coverage whatever this module is set to.

**Escape:** a learned depth prior, which predicts through the gap instead.

```
find(produces="dense_model/v1", consumes="poses/v1")
```

## No confidence channel

PatchMatch expresses uncertainty by deleting pixels, not by scoring them, so
`mean_depth_confidence` is null and no per-point confidence is written.
`depth_map_completeness` is the same information at the image level, and the holes
in the cloud are it at the point level.

The consequence for a consumer: there is no threshold to raise after the fact. To
get a cleaner cloud the module has to run again with stricter filters.

## Depth maps are in the UNDISTORTED frame

When `write_depth_maps` is on, the maps COLMAP produced are written as-is. They
are indexed in the *undistorted* image, which for a scene with distortion is
neither the scene's pixel grid nor the same size as it. Indexing them with scene
pixel coordinates gives silently wrong depths.

They are also omitted whenever the undistorted views do not all share a
resolution, because `dense_model/v1` can only express depth as one array.

## It is not a mesh

Points and colours, no surface. Poisson reconstruction is a separate step and
lives in no module here.

## Runtime is not a detail

Around half a minute to a minute per view at the working resolution, measured over
a hundred runs on shared hardware — so a full capture is a half-hour to an hour, and
three times that when the device is contended. A pipeline that reaches this module
having burned its budget upstream will not get to run it at a resolution worth
having. Plan the dense stage first and the sparse stage around it.

**Dropping the resolution is the weak lever, not the strong one.** Halving
`max_image_size` saves under half the time, not three quarters — the cost is far from
quadratic in it at these sizes. Turning the geometric check off saves more, and
`window_step: 2` saves about as much; both are in [tuning](tuning.md#the-runtime-knobs-in-the-order-to-reach-for-them),
and the check is the one that changes what the result means.

## Per-view depth is not a deliverable

`write_depth_maps` exists for diagnosis and for feeding another stage, not for handing a
surface to whoever asked for one. On sites carrying sky, foliage or glass, the raw depth
of a single view keeps what those surfaces put in front of the camera; fusion's
consistency check is what removes it, and a cloud scored straight from the depth maps was
about three times less accurate than the fused cloud of the same runs, losing on five of
the seven captures that could supply both. On studio orbits the comparison ran the other
way, where a fused cloud's own stray points were the larger error. Deliver the fused
cloud; reach for the depth maps when you need to see what one view thought.

**They are also not always available.** The maps are written only when every undistorted
view shares a resolution. A capture whose frames came from more than one camera setting
produces none, and the run succeeds silently without them — check the artifact rather
than assuming. Measurements: `skills/evidence/eth-dense-2026-09.md`.
