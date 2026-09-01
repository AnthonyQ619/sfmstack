---
module: SparseTriangulation
module_version: 1.1.0
upstream: OpenCV DLT triangulation
curated_at: 2026-08-07
sources: 3
---

Turns tracks plus known poses into a 3D point cloud. Pure OpenCV/numpy, no GPU,
no weights, deterministic.

**Use when** you have poses from anything. It consumes `poses/v1` and knows
nothing about how those poses were obtained, so the incremental PnP estimator,
VGGT and MapAnything all feed it identically.

**This module did not exist in the predecessor.** Triangulation lived inside each
pose estimator *and* inside each sparse reconstructor — four implementations with
four sets of thresholds, whose point clouds could not be compared because the
filtering differed. Splitting it out means swapping the pose estimator changes
exactly one thing. See `docs/design/DECISIONS.md`.

**What it does per track:** triangulate from the widest-baseline pair of views
that observed it, then verify in *every* observing view. A point that reprojects
badly in any single view is discarded rather than kept with a large residual,
because one bad observation is enough to drag a bundle adjustment.

**When to reach for `SparseTriangulationGTSAM` instead:** when tracks are long.
Solving from the widest PAIR is the right cheap answer and it discards evidence —
a track seen in eight views is placed by two of them. Measured against the all-view
module on two scenes and three trackers: **identical at two observations**, ~5%
worse at three or four, and **12–21% worse at five or more**. Read
`track_survival_5` on the tracks artifact to know which regime you are in.

**That difference does not survive bundle adjustment**, which finds the same
optimum from either starting point — after refinement the two agree to three
decimals on shared points. What the all-view module keeps is more points, because
its better initial estimate passes this same reprojection filter more often — but
bounded by what THIS module was losing in the first place. **Read this module's own
`yield` to price the swap: the most the all-view estimator can win is `1 - yield`.**
At 0.99 that is one percent and the swap is nearly free of consequence; well below
that, there is something to win. So: no BA stage, or yield matters and there is
headroom → switch. Two-view-dominated tracks, a yield already near 1.0, or you would
rather not carry GTSAM → stay here and give up almost nothing.
See [`docs/import_lessons.md`](../../../docs/import_lessons.md).

**The metric that reads upstream:** `rejected_cheirality`. Points landing behind a
camera is a *pose* problem, not a threshold problem — no setting here fixes it.
Above ~5% go and look at the pose artifact.

**Cheapest thing that usually works:** defaults. On one short contiguous arc of
twelve calibrated frames around a small, well-textured object on a plain backdrop,
with poses from `PoseEssentialToPnP`, that gives 6941 points from 7014 tracks
(99% yield), 22743 observations, 0.376px mean reprojection error, 15.7° median
angle, zero cheirality rejections, in 1.3s.

**Reading the output:** [artifact.md](artifact.md). The cloud is unrefined —
`BundleAdjustmentGlobal` took it from 0.376px to 0.253px on that same run.
