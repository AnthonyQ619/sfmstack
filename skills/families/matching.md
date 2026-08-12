# Feature matching — choosing a matcher

Everything that produces `pairwise_matches/v1`. One of its axes reaches forward
into the tracker, which is why this choice is not local.

---

## The axes

### 1. Detector-based or detector-free — and what it costs downstream

A **detector-based** matcher (`FeatureMatchNN`, `FeatureMatchFLANN`,
`FeatureMatchLightGlue`, `FeatureMatchSuperGlue`) consumes `features/v1` and
matches a fixed keypoint table. Every correspondence names *which* keypoint it
matched, so `feature_index` is written.

A **detector-free** matcher (`FeatureMatchLoFTR`, `FeatureMatchRoMa`) consumes
images and produces correspondences directly. There is no keypoint table, so there
is no `feature_index`.

**That difference propagates into the tracker and changes how tracks are built.**
With `feature_index`, chaining is *exact*: two matches share a node when they cite
the same keypoint. Without it, the tracker must merge endpoints by **proximity**,
controlled by `merge_eps_px` — and the value that works is specific to the matcher
*and* the working resolution, not to the stage. A tolerance carried from one
detector-free matcher to another over-merges or under-merges.

So choosing a detector-free matcher commits you to tuning a tolerance in a
different module. That is a real cost, and it is invisible if you only look at this
stage.

### 2. Independent or joint

`FeatureMatchNN` and `FeatureMatchFLANN` decide each match on its own descriptor
distance and a ratio test. Nothing about match *A* informs match *B*.

`FeatureMatchLightGlue`, `FeatureMatchSuperGlue` and the detector-free pair reason
about all correspondences in a pair **jointly** — attention across both keypoint
sets, and an assignment that must be globally consistent. That is what lets them
survive repetitive structure, where a per-match ratio test has no way to prefer the
right one of several identical candidates.

Repetitive texture is therefore the clearest signal for a learned matcher: a
façade, a tiled floor, a row of identical windows.

### 3. Pairing is a graph decision priced as a matcher parameter

`pairing: exhaustive` is O(n²) pairs; a sequential window is O(n). This dominates
the cost of the whole stage and it decides the **view graph**, which decides
everything downstream — `graph_components`, track length, whether registration
stalls.

An exhaustive sweep on an unordered collection is usually necessary. A window on a
sequential capture is usually sufficient, and loop closure is what it misses.

### 4. Verification belongs here

Geometric verification is this stage's job, not the tracker's. `inlier_ratio` is
reported over the verified set, and everything downstream assumes it happened.

A consequence worth knowing: **a two-view epipolar check cannot catch an error that
only appears in three views.** Pairs are verified independently, so a correspondence
can satisfy every pairwise constraint and still not be one 3D point. That failure
is the tracker's `trifocal_transfer_px` to find.

### 5. `planarity` is the one metric here whose answer is not a matcher

`planarity` is homography inliers over fundamental inliers, averaged over pairs.
Near 1 it says the correspondences are explained by a *plane* as well as they are
by a *baseline* — and a baseline is what every geometric stage downstream needs.

**It is not a matching failure.** The matches may be perfect; `inlier_ratio` will
often be excellent alongside it. Nothing in this family fixes it, and tuning here
is the wrong response. That is why the metric is in the type at all: it is the
signal to change what you are doing, not how you are doing it.

**Two causes hide behind one number, and the fixes differ.**

| cause | what is true | what to do |
| --- | --- | --- |
| **Pure rotation** — the camera turned without translating | no parallax, so there is no structure to recover from these views at any quality of matching | no parameter helps. Drop the offending frames, or use views that do have translation. If most of the set is like this, the capture cannot be reconstructed and the honest answer is to say so |
| **Planar scene** — real baseline, but the structure is one plane | structure exists; it is the *two-view essential-matrix decomposition* that is ill-conditioned | avoid bootstrapping from two views: `SparseGlobalCOLMAP` solves the view graph globally, and `PoseVGGT` never decomposes an E at all. Or keep the incremental route and raise `init_min_angle_deg` so the seed is chosen from whatever non-planar pair exists |

**Distinguishing the two is not this metric's job.** `planarity` is per-pair and
averaged; it cannot tell "no translation" from "flat wall". What separates them is
whether *other* pairs in the set carry parallax — and the type designed to answer
it directly is `scene_analysis/v1`, whose `degeneracy` group holds
`pure_rotation_risk` and `planar_dominance` as separate numbers. That family is
designed and not yet built, so today the separation is a judgment call made from
the pose stage's behaviour: a seed pair that cannot be found (`init_min_angle_deg`
rejecting everything) points at rotation; a seed that is found and yields a
reconstruction that drifts points at a plane.

**Where it lands downstream.** `PoseEssentialToPnP` fails to seed and names this
metric in its diagnostic; `SparseGlobalCOLMAP` reports degenerate pairs failing
verification correctly; `BundleAdjustmentGlobal`'s limitations read it beside
`median_triangulation_angle`. All three are describing the same upstream fact.

**Null is legal** — it means the matcher was told not to measure it
(`measure_planarity: false`), which is a saving worth taking only when the capture
is already known to have baseline.

---

## Which end to reach for

**Nearest-neighbour / FLANN** when the scene is well-textured and distinctive, or
the pipeline must run on CPU. They are not a fallback; on an easy scene they are
the right answer and cost nothing.

**A learned detector-based matcher** when the scene is repetitive, the baselines
are wide, or illumination varies — and pair it with the detector it was trained
against.

**Detector-free** when the detector is the thing that failed: `keypoints_min` low,
`spatial_coverage` low, a textureless or blurred capture. Expect to tune
`merge_eps_px` in the tracker afterwards, and read the tracker's
`inconsistent_rate` and `split_rate` together when you do — each is blind to the
error the other catches.

**Nothing here at all** is also an option: `FeatureTrackVGGSfM` and
`FeatureTrackTapir` consume `features/v1` directly, so a pipeline can go
scene → detect → track with no matcher. See [tracking.md](tracking.md).

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **How much a learned matcher buys on repetitive structure** | A repetitive scene. Everything measured here so far is a well-textured object with no repetition, where the ratio test is not under stress. |
| **Where detector-free overtakes detector-based** | A sweep along texture strength. The rule "reach for detector-free when the detector fails" has a direction and no threshold. |
| **Whether `merge_eps_px` can be derived rather than tuned** | Its right value is known to depend on matcher and resolution. Whether it is predictable *from* the matcher's own reported precision is open, and would remove a manual step. |
| **The cost of an exhaustive sweep against what it recovers** | Loop closures found per extra pair, on a sequential capture. This decides pairing on every large set and is currently a guess. |
