# Pose estimation — choosing an estimator

Everything that produces `poses/v1` — and one option that produces poses without
being in this family at all.

---

## The axes

### 1. Geometric or feed-forward

**`PoseEssentialToPnP`** needs correspondences and calibration. It picks a seed
pair, decomposes an essential matrix, and then registers images one at a time by
PnP against the structure built so far.

**`PoseVGGT`** needs neither. It attends across the whole image set and reads
camera parameters off the aggregated tokens.

What follows from that, and it is most of the decision:

| | geometric | feed-forward |
| --- | --- | --- |
| needs correspondences | yes | no |
| needs calibration | yes | **no — it estimates intrinsics** |
| can fail on one image | yes — registration stalls | no; it poses every image or none |
| per-image evidence | inlier counts, the seed pair, a threshold to relax | none |
| `mean_reprojection_error` | measured | **null by construction** |

The last row is the one that bites. A feed-forward estimator has no
correspondences, so it cannot report the error that would tell you whether it
worked. Nothing in its own artifact answers "is this right"; the first number that
does is the triangulator's `yield`, downstream.

### 2. Registration order, and drift

Incremental registration accumulates. Each image is placed against structure built
from the ones before it, so errors compound along the chain, and the compounding is
worse with learned features whose positions are less precise. **In-loop local
bundle adjustment** — a window refined as registration proceeds — exists for
exactly this, and it is a parameter of the geometric estimator rather than a
separate module.

Feed-forward has no order and therefore no drift. It has a different problem:
whatever the model gets wrong, it gets wrong everywhere at once, and there is no
per-image signal to localise it.

### 3. Estimating intrinsics changes what downstream reads

A module that estimated intrinsics writes them beside its poses, and every
consumer that finds them **prefers them over the scene's calibration** — because a
pose computed with its own K is not consistent with anyone else's.

On an uncalibrated scene that is the whole point. On a calibrated one it is a claim
to check: `estimated_focal_ratio` against 1.0 is the single most useful warning a
feed-forward estimator produces, and far from 1.0 means the two disagree and the
poses were computed with the estimate.

### 4. The third option: no pose module at all

`SparseGlobalCOLMAP` consumes `pairwise_matches/v1` and estimates poses *internally*
as part of reconstructing. Rotation averaging over the whole view graph, then global
positioning — no registration order, so nothing to stall.

That is the answer when the problem is **order** rather than correspondence quality:
an unordered collection where incremental registration cannot find a next image it
can place. It is not in this family because it produces `sparse_model/v1`; see
[sparse.md](sparse.md).

---

## Which end to reach for

**Geometric**, by default, on a calibrated scene whose matcher produced one
connected view graph. It is the only option here that reports whether it worked.

**Feed-forward** when the scene is **uncalibrated** — there is no alternative — or
when the geometric estimator reports `registered_fraction` below 1 and the missing
images are ones you need.

**Global reconstruction instead** when `registered_fraction` is low on an
*unordered* set and the matcher's `graph_components` is 1. That combination says
the correspondences are there and the order is the problem.

A geometric estimator that stalls on a scene whose view graph is already fragmented
is not the pose stage's failure. Fix the graph.

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **Absolute pose accuracy of either** | Ground-truth extrinsics. Nothing here has been compared against them — the dataset in use carries none, so every comparison so far is internal consistency. AUC at 5/10/30 degrees against a posed dataset is the missing measurement, and the report now exports poses in a form that supports it. |
| **What feed-forward buys where geometric stalls** | A scene where it genuinely stalls. Measured so far only where the geometric estimator registers everything, which is the case it is best at and says nothing about the case the alternative exists for. |
| **How far in-loop local BA carries** | Sequence length against drift, on captures long enough for drift to dominate. The mechanism is understood; the length at which it stops being enough is not. |
| **Whether estimated intrinsics are usable** | `estimated_focal_ratio` says whether a model agrees with a calibration. Whether its estimate is good enough to reconstruct with, on a scene with no calibration at all, is a different question and untested. |
