---
module: SparseTriangulationGTSAM
module_version: 1.0.0
upstream: GTSAM 4.2.2 triangulatePoint3 (LOST estimator)
curated_at: 2026-08-10
sources: 3
---

Multi-view triangulation against known poses, using GTSAM's LOST estimator over
**every** observing view rather than the widest pair. CPU-only, no weights.

**Interchangeable with [SparseTriangulation](../../sparse_triangulation/skills/SKILL.md)**
by design: same three inputs, same output type, same filter names and the same
defaults for `min_triangulation_angle_deg` and `max_reprojection_error`. Swap one
for the other and nothing else changes.

**Use when** tracks are genuinely multi-view. The OpenCV path triangulates a
track seen in eight views from two of them; LOST uses all eight with the
weighting that makes the linear solution statistically optimal. That matters most
where the pairwise answer is worst — one wide baseline among several
near-coincident views.

**Prefer this module when either is true:**

- **`track_survival_5` is healthy** — the gain is a function of track length and
  nothing else. Measured against `SparseTriangulation` on two scenes and three
  trackers: identical at two observations (forced — two views is two views),
  ~5% lower reprojection error at three or four, and **12–21% lower at five or
  more**, on 87–94% of individual points in every case.
- **There is no bundle adjustment downstream.** Refinement finds the same optimum
  from either starting point, so on the points both estimators keep, a post-BA
  comparison is a coin flip (41–51% win rate, medians agreeing to three decimals).
  Without a BA stage the accuracy is yours to keep.

**With bundle adjustment, read the gain as YIELD.** The better initial estimate
passes the same reprojection filter more often, so more structure reaches the final
model: **+4% to +25% points** after BA, the large end with a predictive tracker's
long tracks. That is what this module buys in a full pipeline.

**Prefer SparseTriangulation when** `mean_track_length` is near 2.0. On a
two-view track the two are the same computation and this one costs more; the
module says so with a `mostly_two_view` diagnostic rather than letting you pay
for nothing. Also prefer it when the GTSAM dependency is not wanted — 594 MB
against 760 MB — since on a two-view-dominated scene nothing is given up.

**`optimize` and `use_lost` are not where the value is.** Both agreed to four
decimals with each other and with the plain all-view solve on every scene tested,
and `optimize` cost 2x the runtime to do it. What matters is using every view;
which estimator solves there did not move a measurement.

Full experiment: [`docs/import_lessons.md`](../../../docs/import_lessons.md).

**It also has a filter the pairwise path has no equivalent of.**
`max_landmark_distance` rejects points that escaped along near-parallel rays —
those reproject perfectly into every view that created them and sit nowhere near
the scene. Off by default because the scale is arbitrary.

**Measured on DTU scan1** (12 images, SIFT + exhaustive NN, incremental poses):

| | SparseTriangulation | SparseTriangulationGTSAM |
|---|---:|---:|
| points | 6900 | **6949** |
| mean track length | 3.26 | 3.28 |
| mean reprojection error | **0.365 px** | 0.391 px |
| runtime | 1.5 s | 2.0 s |

More points, slightly *higher* reprojection error — and that is the expected
direction, not a defect. See [artifact.md](artifact.md#why-lower-error-is-not-the-goal).

**Reading the output:** [artifact.md](artifact.md).
