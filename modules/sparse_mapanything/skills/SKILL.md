---
module: SparseMapAnything
module_version: 1.1.0
upstream: facebookresearch/map-anything @ 3d10cf7, depth head
curated_at: 2026-08-11
sources: 2
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 10 parameters documented, starting with `condition_on_poses` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot estimate its own poses here" |
| you are reading what it wrote | **`artifact`** — the layout of `sparse_model/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`.

**Diagnostics it can raise:** `no_points`, `depth_scale_inconsistent`, `heavily_masked`, `mostly_single_view`.

## What this module is for


Sparse structure from MapAnything's learned depth, unprojected with the **supplied**
poses. Same three inputs and same output as `SparseTriangulation`,
`SparseTriangulationGTSAM` and `SparseVGGT`, so all four are interchangeable. GPU
required.

**The capability no other module here has: it takes the poses and intrinsics as
INPUT.** MapAnything is trained to accept whatever geometry is already known and
predict the rest, so the pipeline's own calibration and camera positions become
evidence rather than something the network must infer.

## What conditioning buys, measured

Eight views of a small, well-textured object on a plain backdrop, classical
tracks, poses from `PoseEssentialToPnP`, everything else equal:

| | points | `yield` | `depth_scale_spread` | `mean_depth_confidence` |
|---|---:|---:|---:|---:|
| `condition_on_poses: true` | 3047 | **0.648** | **0.0059** | 13.97 |
| `condition_on_poses: false` | 2198 | 0.467 | 0.0071 | 9.82 |

**39% more structure survives** from information the pipeline already had. `yield`
is the comparable number here — same tracks in, same filters, so the difference is
depth quality alone.

## What conditioning does NOT buy

**It does not put the output in your frame.** The estimated depth scale is 1.9496
conditioned and 1.9485 not — unmoved. MapAnything returns its own world frame at
its own scale whatever it is told, so the depth is unprojected with the supplied
poses exactly as in `SparseVGGT`, and the scale is measured from the tracks rather
than assumed to be 1.

## Against the other three triangulators

Same 8 views, same tracks, same poses:

| module | points | mean error | `yield` |
|---|---:|---:|---:|
| `SparseTriangulation` | 4671 | 0.280 px | 0.993 |
| `SparseVGGT` | 3658 | 0.956 px | 0.778 |
| `SparseMapAnything` | 3047 | 1.060 px | 0.648 |

On a calibrated, well-textured scene the geometric triangulator wins on every
axis, and that is expected — this is the case ray intersection is best at. The
learned modules exist for the case where the correspondences are too few or the
scene too weakly textured for intersection to work, which a well-textured
small-object capture is not.

**The errors here are comparable in a way they are not after bundle adjustment**,
because all three placed points against the same poses under the same
`max_reprojection_error`. Read `yield` first regardless.

## `mean_depth_confidence` is not comparable to `SparseVGGT`'s

13.97 here against 60.60 there, same scene, same metric name. Both are unbounded
self-reports on different scales. A `min_confidence` carried between the two
modules is meaningless.

**Reading the output:** [artifact.md](artifact.md) ·
**Tuning:** [tuning.md](tuning.md) · **Limits:** [limitations.md](limitations.md)
