# Decisions log

Design choices made while porting the 23 modules, written down because they are
the ones worth arguing with. Newest section last.

Each entry: what was decided, what the alternatives were, and what would make me
change my mind. Anything marked **NEEDS A DECISION** is something I picked a
default for so work could continue, and which you should overrule if you disagree.

---

## 2026-08-07 — Session context

Starting point: `SceneLoader`, `FeatureDetectionSIFT`, `FeatureMatchNN`,
`FeatureTrackUnionFind` built and tested. 226 tests. The chain runs
scene → features → pairs → tracks across four containers.

Goal for this session: the remaining 20 of the 23 legacy modules, and a real
end-to-end reconstruction with numbers.

Priority order chosen, and why:

1. **The classical critical path first** — pose, sparse, bundle adjustment. It is
   the only thing that turns the existing four modules into an actual SfM
   pipeline, it needs no model weights, and it is what produces the end-to-end
   result you asked for. Breadth is worth nothing if nothing completes.
2. **Cheap OpenCV breadth next** — ORB, FLANN. Minutes each, and they give the
   registry real alternatives so the module-swapping machinery is exercised
   against something other than fixtures.
3. **The torch stack** — SuperPoint, ALIKED, LightGlue, SuperGlue. One shared
   base image, four modules.
4. **Detector-free** — LoFTR, RoMa.
5. **Learned reconstruction** — VGGT (pose/sparse/dense), MapAnything.
6. **Direct trackers** — VGGSfM, Tapir.

Groups 5 and 6 carry the most risk: vendored repositories, large weights, and no
guarantee the upstream code still imports against a current torch. They are last
deliberately, so a failure there costs breadth rather than the pipeline.

---
## The pose estimator consumes tracks, not pairs

`CamPoseEstimatorEssentialToPnP` in the predecessor walked `pairwise_matches` in
file order, maintaining its own track structure by chaining consecutive pairs.
Ours consumes `tracks/v1` instead.

Consequences, all of which I consider improvements:

- **Registration order is driven by evidence, not by filename.** Each round picks
  whichever unregistered image has the most 2D-3D correspondences. The
  predecessor's order was fixed, so a single unregisterable frame truncated
  everything after it.
- **The seed pair is chosen, not assumed.** The predecessor hardcoded
  `init_pair_idx = 0` (with dead code above it that pretended to search, and an
  unreachable `if init_pair_idx is None` branch below). We score every candidate
  pair by inlier count *gated on median parallax*, because the pair with the most
  matches is usually the pair with the least baseline -- seeding there is the
  classic way to produce a confident wrong model.
- **A frame that will not register is skipped, not fatal.** It gets `valid=False`
  in the artifact, which `poses/v1` makes mandatory precisely so consumers cannot
  ignore it.

**Worth your attention:** this means the module cannot be run without a tracker,
whereas the predecessor went straight from matches. If you want a pose estimator
that consumes pairs directly, say so -- it is a different module, not a parameter.

## A new module the 23 did not have: SparseTriangulation

Triangulation lived inside each pose estimator *and* inside each sparse
reconstructor in the predecessor -- four implementations, four sets of
thresholds, and point clouds that could not be compared across them because the
filtering differed.

I split it into its own module: `scene + tracks + poses -> sparse_model`. Any
pose source feeds it, including VGGT and MapAnything, because it consumes
`poses/v1` and knows nothing about how the poses were obtained.

This makes 24 modules rather than 23. The alternative was to have the pose
estimator emit `sparse_model` as a second output slot, which the module contract
supports. I did not, because then swapping the pose estimator would also swap the
triangulation policy, which is exactly the coupling that made the predecessor's
clouds incomparable.

## Geometry is done in normalised camera coordinates

Every classical geometry module undistorts and applies K^-1 once, up front, then
works with plain `[R|t]` projection matrices.

This is why per-image intrinsics need no special case anywhere. A
mixed-resolution capture (ETH3D courtyard) or a multi-camera rig just works. The
predecessor carried a single `self.K_mat` and a single `self.dist` through every
routine, which is one of the reasons its mixed-resolution handling was wrong.

The cost is that reprojection error must be converted back to pixels for
reporting, which is a few lines in each module. Worth it.

**Consequence worth knowing:** `sparse_model/v1` observations are UNDISTORTED
pixels. Everything downstream, including the COLMAP export, assumes this -- the
COLMAP cameras written by the BA module are PINHOLE with no distortion terms, not
as an approximation but because the distortion was already removed.

## sparse_model/v1 gained an optional `intrinsics` file

Bundle adjustment with `refine_focal_length` had nowhere to write the refined K.
Added additively, as the type system's rules require: optional file, consumers
that do not know about it are unaffected.

The rule I applied: a consumer that finds it should PREFER it over `scene/v1`
calibration, because a BA that refined K did so jointly with the poses in the
same artifact and the two cannot be mixed with an older K. `SparseTriangulation`
and `BundleAdjustmentGlobal` both implement that precedence.

## Two pycolmap traps, both of which silently produced wrong numbers

Recording these because they are the kind of thing that produces a plausible
metric rather than an error.

**`compute_mean_reprojection_error()` returns 0.0 on a freshly built
reconstruction.** It averages a per-point `error` field that COLMAP leaves unset
until `update_point_3d_errors()` is called. The first working version of the BA
module therefore reported `reprojection_error_before: 0.0` and
`error_reduction: 0.0` -- i.e. it claimed the input was already perfect and BA
had achieved nothing, when in fact it went 0.376px -> 0.253px. With the fix, the
"before" reads 0.3763 against our own triangulator's independently computed
0.376, which is a nice cross-check between two implementations.

**`pycolmap.bundle_adjustment(rec, options)` returns `None`.** Iteration count
and convergence were being invented from a summary that did not exist. Building
the adjuster explicitly via `create_default_bundle_adjuster` costs three lines
and returns a real summary. `read_summary` now reports `converged=False` when it
cannot tell, rather than defaulting to True -- the metric exists to be trusted
when a solve goes wrong, which is exactly when a cheerful default misleads.

