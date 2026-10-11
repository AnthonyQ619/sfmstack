---
campaign: sparse-compositions-2026-10
measured: 2026-10
---

# Campaign: sparse-compositions-2026-10 — eleven compositions, twenty-four corpus captures

**This is a raw evidence table. Cite it; do not plan from it.** The reasoning built on
these rows lives in [`plan/sparse.md`](../plan/sparse.md),
[`plan/pose.md`](../plan/pose.md), [`health/ladder.md`](../health/ladder.md) and
[`health/smells.md`](../health/smells.md), stated as capture properties rather than as
scene names.

## Protocol

Eleven compositions assembled from the registry, each run end-to-end on every one of the
twenty-four [CORPUS.txt](CORPUS.txt) captures at full frame coverage. Scored by one
metric throughout: AUC@30 on relative pose over all 45 image pairs, with an unregistered
image charged as a miss, so a smaller model is not thereby a better one.

Configuration pinned across every row: `num_threads: 1` on the one module that exposes a
thread count, and fixed random seeds. **That pinning is load-bearing and not a
formality** — see §4.

**What is NOT in this file.** A second sweep ran the same eleven compositions on
twenty-three further captures, and **those captures are not named here**: seven of them
are reserved for measuring whether this context generalises, and a holdout read into
context is no longer one. Aggregate counts from that sweep appear in §3 because a count
over unnamed runs leaks nothing; no per-capture row from it does.

## 1. Best and median per capture — the margin table

`margin` is best minus median across the compositions that returned a scored model.

| capture | n | best | median | margin | winner |
| --- | --- | --- | --- | --- | --- |
| DTU/scan1 | 10 | 0.977 | 0.974 | 0.003 | superpoint_incremental |
| DTU/scan4 | 10 | 0.973 | 0.971 | 0.001 | superpoint_global |
| DTU/scan9 | 10 | 0.975 | 0.974 | 0.001 | roma_incremental |
| DTU/scan10 | 10 | 0.982 | 0.979 | 0.003 | aliked_global |
| DTU/scan15 | 10 | 0.977 | 0.975 | 0.002 | sift_global |
| DTU/scan23 | 10 | 0.975 | 0.973 | 0.003 | sift_incremental |
| DTU/scan33 | 10 | 0.975 | 0.974 | 0.001 | roma_incremental |
| DTU/scan48 | 10 | 0.944 | 0.595 | **0.349** | aliked_global |
| DTU/scan75 | 10 | 0.976 | 0.975 | 0.001 | roma_incremental |
| DTU/scan77 | 9 | 0.974 | 0.941 | 0.033 | loftr_incremental |
| ETH/courtyard | 8 | 0.465 | 0.464 | 0.001 | sift_incremental |
| ETH/delivery_area | 10 | 0.575 | 0.173 | **0.402** | mapanything_feedforward |
| ETH/electro | 8 | 0.565 | 0.268 | **0.297** | superglue_global |
| ETH/facade | 10 | 0.944 | 0.797 | 0.147 | sift_global |
| ETH/kicker | 10 | 0.997 | 0.895 | 0.103 | roma_incremental |
| ETH/meadow | 10 | 0.981 | 0.653 | **0.329** | superpoint_global |
| ETH/office | 10 | 0.604 | 0.530 | 0.074 | loftr_incremental |
| ETH/playground | 10 | 0.721 | 0.323 | **0.398** | aliked_global |
| ETH/relief | 9 | 0.998 | 0.332 | **0.666** | roma_incremental |
| advio/advio-07 | 6 | 0.102 | 0.024 | 0.078 | superpoint_global |
| euroc/MH_05_difficult | 10 | 0.739 | 0.217 | **0.522** | mapanything_feedforward |
| euroc/V2_01_easy | 10 | 0.881 | 0.127 | **0.754** | mapanything_feedforward |
| tum_vi/room3 | 10 | 0.446 | 0.210 | 0.235 | mapanything_feedforward |
| tum_vi/room4 | 10 | 0.616 | 0.300 | **0.315** | vggt_feedforward |

## 2. The margin by capture kind — the boundary is a subject, not a dataset

| capture kind | n | median margin | range |
| --- | --- | --- | --- |
| **rig orbit of one object** (DTU) | 10 | **0.002** | 0.001 – 0.349 |
| **walk around built structure** (ETH) | 9 | **0.297** | 0.001 – 0.666 |
| **aerial / room-rig / phone walk** | 5 | **0.315** | 0.078 – 0.754 |

Ratios of the medians: traversal-to-orbit **142x**, site-walk-to-orbit **134x**,
traversal-to-site-walk **1.06x**.

**So the split is rig orbits against everything else.** Site walks carry reference
calibration and controlled capture and still behave like the traversals, not like the
orbits. An earlier reading of this table grouped them with the orbits on the strength of
the dataset they come from; the medians say otherwise, and that is why the guidance names
a single controlled subject against a traversal rather than a benchmark against a
visual-inertial set.

**No composition won more than four captures, and six different ones won at least one.**

## 3. Which modules ever returned nothing

Counted per module over this campaign and the unnamed second sweep — nineteen modules,
roughly three hundred runs, each counted only on the input it accepts.

| module | returned nothing |
| --- | --- |
| `FeatureTrackVGGSfM` | **8 of 46** |
| `SparseGlobalCOLMAP` | **8 of 140** |
| `PoseEssentialToPnP` | **3 of 92** |

**Sixteen never returned nothing**, including every detector, every matcher,
`FeatureTrackUnionFind`, triangulation, bundle adjustment and **both learned-prior pose
estimators**. Compositions built on a learned prior were reported as the unreliable
choice during this campaign; the estimators did not fail, and the tracker in those
compositions did.

`SparseGlobalCOLMAP`'s count is on correspondences carrying a keypoint index. Given
correspondences without one it returned nothing on every run; that is
[detector-free-global-2026-10](detector-free-global-2026-10.md).

## 4. The repeat measurements — and why the pinning is load-bearing

Two executions of an identical recipe, in separate stores so both genuinely ran.

| composition | what moved |
| --- | --- |
| a long incremental chain | bit-identical through detection, matching and tracking, then **a fraction of a percent** apart in point count at the pose stage |
| a learned-prior estimator | **0.237 apart** on the pose metric, 0.574 against 0.337, on one rig-orbit capture |
| the other learned-prior estimator | **bit-identical** on the same capture |
| a fully pinned geometric chain | **zero** |

The mechanism for the first is a multithreaded solve inside the loop: the same residuals
summed in a different order differ in the last bits, and an incremental method feeds that
into its next decision. **So "feed-forward is the non-deterministic part" is wrong on
this stack** — one learned estimator is the reproducible one, and an unpinned geometric
solve is not.

## 5. The parameter sweep

**`max_epipolar_error` is the dial that moves the result and no value of it is the
optimum.** A three-capture sweep read 2.0 as better than 1.0 by up to +0.160. Re-measured
on twelve captures with threads pinned: 2.0 materially better on three, 1.0 materially
better on three, six ties, median difference **+0.004**, and swings of **+0.465** and
**−0.291** in opposite directions. **One of the original three reverses under pinned
threads**, and on that capture the 1.0 reading repeated exactly while the 2.0 reading did
not — consistent with the 0.237 in §4, though not established as the cause.

The focal length was the obvious predictor and was tested across 191 to 2900 working
pixels: median difference +0.001 above 800 px and +0.004 below, with 2.0 winning at both
2900 and 438 px and 1.0 at both 884 and 191 px. **Falsified.**

**Defaults won outright on a third of the captures swept.** Two dials carrying more prose
than this one moved the result only in combination with it, or on the hardest capture
alone.

## 6. What this campaign does not establish

- **Nothing about which composition to choose.** Six won at least one capture and the
  winner does not follow from any reading available before the run.
- **No per-capture optimum for any parameter.** Nothing measured here transferred between
  captures.
- **Nothing at scale.** Every capture is ten images with all 45 pairs matched
  exhaustively, so order-independence and large-collection behaviour are untested.
- **The visual-inertial families are n=2, n=2 and n=1 here.** The margin finding's
  traversal half rests on five captures in this file plus the unnamed second sweep.
