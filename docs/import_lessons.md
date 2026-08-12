# Important lessons

A personal record of findings worth remembering — measured results and the
conclusions drawn from them. Newest last.

Distinct from [`design/DECISIONS.md`](design/DECISIONS.md), which logs *why the
architecture is the way it is*. This file logs *what the experiments said*.

---

## 2026-08-11 — VGGT poses vs incremental SfM, one variable changed

**The question.** How much worse are feed-forward poses than classical ones, and
does bundle adjustment absorb the difference?

**What was run.** A full reconstruction on both branches, not a pose-error
comparison — DTU's `calibration_DTU_new.npz` has `baseline_ext: None`, so there
are no ground-truth extrinsics to compare against.

```
SceneLoader (DTU scan1, 12 images, sampling: head, max_edge: 1024)
  └─ FeatureDetectionSIFT (defaults)
       └─ FeatureMatchNN (pairing: exhaustive)
            └─ FeatureTrackUnionFind (defaults)  →  art_df2aae98301a, 7014 tracks
                 ├─ PoseEssentialToPnP  ─┐
                 └─ PoseVGGT            ─┴─ SparseTriangulation → BundleAdjustmentGlobal
```

Both branches consumed **the same tracks artifact** — literally the same id, since
the recipe is identical — and the same triangulator and bundle adjuster at
defaults. The only variable is the pose source.

**Results.** All on GPU, in containers, on one A6000.

| pose source | pose time | registered | pose err | tri points | tri err | `yield` | BA points | BA err | BA iters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `PoseEssentialToPnP` | 9.0 s | 12/12 | 0.413 px | 6900 | 0.365 px | **0.984** | 6900 | 0.2508 | 173 |
| `PoseVGGT` | 21.5 s | 12/12 | *null* | 5899 | 1.051 px | **0.841** | 5899 | 0.2274 | 374 |

Both bundle adjustments converged, but only after raising `max_iterations` — at
the default 300 the VGGT branch reported `converged=0` at the cap.

**Conclusions.**

1. **`yield` is the comparable number: 0.984 vs 0.841.** Given identical tracks,
   VGGT's poses cause **14% of them to fail** triangulation's angle, cheirality
   and reprojection filters. That is the pose-quality difference, measured on a
   common input, and it is the number to quote.

2. **The post-BA errors are NOT comparable.** 0.2274 on 5899 points against
   0.2508 on 6900. The smaller model is the easier one, and ~1000 of the classical
   branch's points are ones VGGT's poses could not support. Reading "VGGT wins
   after BA" from that would repeat the exact trap already recorded twice in this
   repository — error is never comparable across differing model sizes.

3. **Bundle adjustment absorbs most of the initialisation gap.** 2.9x worse at the
   start (1.051 vs 0.365 px), both near 0.23–0.25 px at the end. What it does not
   absorb is the missing 14% of structure, and it pays 2.2x the iterations to get
   there.

4. **"Initialisation-grade" is the right description, and now it is measured.**
   VGGT is the right call when correspondences are what is failing or the scene is
   uncalibrated. It is not the right call on a calibrated, well-textured scene
   where the classical estimator works — it is slower here (21.5 s vs 9.0 s),
   loses structure, and makes the bundle adjuster work harder.

**Caveat on generality.** DTU scan1 is a calibrated, well-textured, turntable
capture — the case classical SfM is best at. The comparison says what VGGT costs
where the classical path already works. It says nothing about the case VGGT exists
for, which needs a textureless or uncalibrated scene to measure. ETH3D courtyard
or an interior would be the honest next test, and has not been run.

---

## 2026-08-11 — RoMa's fused kernel is about memory, not speed

**The question.** `pip install romatch[fused-local-corr]` provides the `local_corr`
CUDA extension RoMa wants. Is it worth taking?

**What was run.** Same 4 DTU pairs at 1024 px, same weights, one A6000, both
backends.

| backend | per pair | peak GPU memory |
|---|---:|---:|
| fused kernel | 0.64 s | **2.58 GiB** |
| pure torch | 0.65 s | 4.26 GiB |

**Conclusions.**

1. **Speed is a wash — 3%.** The published framing of the kernel as a speedup does
   not show up at this resolution on this card.
2. **Memory is 40%.** The naive path materialises the full local-correlation
   volume and the kernel fuses it. At higher resolution, on a smaller card, or with
   several RoMa jobs sharing a device, the fallback is what runs out of memory
   first — and 40% is the difference between fitting and not.
3. **The cost is a torch major version.** The wheel is built against the CUDA 13
   runtime, so the extra replaces torch 2.6.0+cu124 with 2.11.0 and the whole CUDA
   13 stack. `--no-deps` yields an image that imports `local_corr` and dies on
   `libcudart.so.13`.
4. **This is the clearest vindication of one-image-per-module so far.** RoMa can
   run on a different torch in its own image and nothing else in the repository
   moves. Default stays the plain base; the fused base exists for when memory is
   the constraint.

---

## 2026-08-11 — Merge tolerance belongs to the matcher, not to the stage

**The finding.** `FeatureTrackUnionFind.merge_eps_px` is what makes detector-free
matches chain into tracks, and the value that works is **specific to the matcher
and the resolution**, not to the stage.

| matcher | resolution | `merge_eps_px` | `inconsistent_rate` | `merge_headroom` | reading |
|---|---|---:|---:|---:|---|
| LoFTR | 640 px | 1.5 | 0.002 | +0.211 | under-merged; tracks never chain |
| RoMa | 1024 px | 4.0 | 0.196 | −0.207 | over-merged; distinct points fused |

**Conclusion.** A more accurate matcher needs a **tighter** merge, not a looser
one. A tolerance carried over from LoFTR over-merges under RoMa; one carried the
other way under-merges. Set it per matcher/resolution pair and read
`merge_headroom` and `inconsistent_rate` together — each is structurally blind to
the error the other catches.

Both runs above still reconstructed. The RoMa one registered 8/8 at 0.33 px *while
over-merging*, which is why the conflict rate is worth reading rather than
inferring health from the final error.

---

## 2026-08-11 — A wrong depth scale splays the cloud, it does not shrink it

**The question.** `DenseVGGT` unprojects VGGT's depth with poses from elsewhere,
and one scalar relates the two units. Without a `tracks/v1` input that scalar is a
parameter. How bad is getting it wrong?

**What was run.** 8 DTU views, classical poses from `PoseEssentialToPnP`, stride
2, identical in every respect except the tracks input.

| | `depth_scale` | `spread` | points | `mean_depth_confidence` |
|---|---:|---:|---:|---:|
| without tracks | 1.0000 *(parameter)* | null | 401 968 | 46.63 |
| with tracks | **4.4460** *(measured, 20+ tracks)* | 0.0039 | 401 968 | 46.63 |

**Every metric is identical.** The depth filter (`depth > 0`) and the confidence
filter are both scale-invariant, so exactly the same pixels survive. Nothing in
the artifact's numbers distinguishes a correct scale from a 4.4x wrong one.

**The geometry, measured afterwards on the two clouds.**

```
X_world(f) = C_f + R_fᵀ · ray · depth · s
```

A wrong `s` scales each view's cloud **about that view's own camera centre**, and
the centres differ. So it is not a similarity transform of the reconstruction.

| | correct (4.4460) | wrong (1.0) |
|---|---:|---:|
| bbox diagonal | 7.2506 | 3.8996 |
| median distance to nearest camera | 4.4633 | 1.0553 |

Pure shrink predicts a bbox ratio of `1/k` = 0.225. Measured: **0.538**. The gap
is eight shrunken shells sitting on eight different camera positions. Predicted
two-view disagreement at the median baseline of 1.7033 is `1.7033 · (1 − 1/4.446)`
= **1.32**, or 78% of the baseline.

**Conclusions.**

1. **A wrong scale looks like bad depth.** The failure renders as a smeared or
   doubled surface, not a small one. Anyone debugging it will suspect the depth
   prior, which is innocent.
2. **This is why `scale_unverified` is `warn` and not `info`.** It is the only
   signal, since no metric moves.
3. **The estimator was validated by the case that must return unity.** Fed
   `SparseVGGT` the poses from `PoseVGGT` — same model, same units — it returned
   **1.0044**, spread 0.004. Fed classical poses it returned 2.1164 at the same
   spread. A scale estimator that cannot recover 1.0 on its own model's poses is
   measuring something else.
4. **VGGT's depth confidence is unbounded.** Mean 46.63, not 0.4663. A
   `min_confidence` chosen as though it were a probability is either a no-op or a
   wall with nothing in between.

---

## 2026-08-11 — More dense points is not more scene

**The question.** `DenseMVS` (COLMAP PatchMatch) leaves holes and `DenseVGGT` does
not. Is the hole-free cloud better?

**What was run.** 8 DTU views, one pipeline, branching only at the dense stage so
both modules got **the same poses**:

```
SceneLoader → SIFT → NN → UnionFind → PoseEssentialToPnP
                                        ├─ SparseTriangulation ─ 4671 points ─┬─ DenseMVS (1200 px)
                                        └────────────────────────────────────-┴─ DenseVGGT (stride 3)
```

The 4671 triangulated points are the reference: multi-view verified, so a dense
point far from all of them is a point nothing else confirms. Units are the
reconstruction's, where the object's bbox diagonal is 4.6 and the median camera
separation 1.7.

| | points | secs | bbox diag | verified→cloud p50 | cloud→verified p95 | cloud >0.2 from anything verified |
|---|---:|---:|---:|---:|---:|---:|
| **DenseMVS** | 122 814 | 131 | 4.26 | **0.0077** | **0.223** | **7.5%** |
| DenseVGGT | 179 920 | 2 | 7.24 | 0.0142 | 0.585 | 26.6% |

**Conclusions.**

1. **VGGT produced 47% more points and covered the verified structure half as
   tightly.** More points, worse coverage — so point count is not a coverage
   measure. It measures willingness to guess at least as much.
2. **A quarter of VGGT's cloud sits far from anything triangulation confirmed,
   against 7.5% for MVS.** Some of that is real surface SIFT never found. The
   distinction is that MVS's extra points were photometrically verified across
   views and VGGT's were predicted, and nothing in either artifact's metrics
   separates the two.
3. **The bounding box is the cheapest tell.** 7.24 against the sparse model's 4.59.
   VGGT predicts depth everywhere, including background and empty space, and it
   lands outside the volume anything else supports.
4. **The holes are the honest part.** A dense reconstructor that never leaves one
   is not more complete; it is less willing to say it does not know. Which of the
   two is wanted is a real choice — 131 s against 2 s is the other half of it.

**Also settled by the same runs.** `geom_consistency` costs 5% of completeness
(0.717 → 0.679 at 600 px) and 44 s, and gains 610 points. It is not a point-count
feature; it is the pass that removes depths which are photometrically plausible in
one view and geometrically impossible across the set. And completeness *falls* as
resolution rises — 0.717 at 600 px, 0.650 at 1200 px — so it is never comparable
across `max_image_size`.

---

## 2026-08-11 — Telling a model your poses helps its depth, and does not move its frame

**The question.** MapAnything accepts camera poses and intrinsics as *inputs*.
Does conditioning it on the pipeline's own poses (a) improve the depth, and (b)
put the output in the pipeline's frame — which would remove the scale ambiguity
`SparseVGGT` has to estimate?

**What was run.** 8 DTU views, SIFT tracks, poses from `PoseEssentialToPnP`, one
variable. The scale below is measured by the same estimator `SparseVGGT` uses —
the ratio of triangulated depth to predicted depth, median over tracks.

| input to the model | `depth_scale` | spread | mean conf | points | `yield` |
|---|---:|---:|---:|---:|---:|
| images + intrinsics | 1.9485 | 0.0071 | 9.82 | 2198 | 0.467 |
| **+ poses, `is_metric_scale=False`** | **1.9496** | **0.0059** | **13.97** | **3047** | **0.648** |
| + poses, `is_metric_scale=True` | 1.3205 | 0.0082 | — | — | — |

**Conclusions.**

1. **(a) is yes, and it is worth a lot. `yield` 0.467 → 0.648 — 39% more surviving
   structure** from information the pipeline already had. Same tracks, same
   filters, so the difference is depth quality alone. Confidence rose 42% and the
   scale spread tightened 17%.

2. **(b) is no, and this is the finding that decided the design. The scale is
   unmoved: 1.9496 conditioned against 1.9485 not.** The model returns its own
   world frame at its own scale whatever it is told. So the frame-agnostic
   construction stays exactly as it is in `SparseVGGT`: unproject `depth_z` with
   the supplied poses, measure the scale from the tracks. Had I assumed (b)
   followed from (a), the cloud would have been in the wrong frame with nothing
   reporting it.

3. **`is_metric_scale=True` is a trap on any SfM pipeline.** MapAnything is a
   *metric* reconstructor, so `true` asserts the supplied poses are in metres and
   the model rescales its depth to honour the claim. SfM units are arbitrary, so
   the claim is always false. It moved the scale to 1.3205 and worsened the spread.
   Hardcoded false rather than exposed.

4. **Conditioning defeats the metric that would catch bad poses.**
   `depth_scale_spread` measures agreement between the depth and the poses, and
   conditioning makes the depth agree with the poses *by construction*. A wrong
   pose produces depth wrong in the same way and a spread that still looks healthy.
   The only signal left is running it both ways: worse conditioned than
   unconditioned means the poses are the problem. That is why `conditioned` is
   reported as a metric rather than left in the parameter block.

**Where all four triangulators land on this scene**, same tracks and poses:

| module | points | mean error | `yield` |
|---|---:|---:|---:|
| `SparseTriangulation` | 4671 | 0.280 px | 0.993 |
| `SparseVGGT` | 3658 | 0.956 px | 0.778 |
| `SparseMapAnything` | 3047 | 1.060 px | 0.648 |

Ray intersection wins on every axis, as it should — DTU is calibrated and
well-textured, the case it is best at. The learned pair are for the case where
correspondences are too few for intersection to work at all, which still has not
been measured here.

**One more thing that does not transfer.** `mean_depth_confidence` is 13.97 here
and 60.60 in `SparseVGGT` on the same scene. Same metric name, both unbounded
self-reports, different scales — a `min_confidence` carried between the two
modules rejects everything.

---

## 2026-08-11 — The three trackers are one trade, and no track metric shows both ends

**The question.** `tracks/v1` can be built three ways — chaining two-view matches,
predicting correspondence from a geometry model, or following points through the
set as video. How do they actually differ?

**What was run.** 8 DTU views, the same SIFT keypoints, the same pose estimator
and triangulator behind each.

| tracker | tracks | `avg_track_length` | `long_track_fraction` | `track_survival_5` |
|---|---:|---:|---:|---:|
| `FeatureTrackUnionFind` | 4702 | 2.85 | 0.431 | 0.116 |
| `FeatureTrackVGGSfM` | 4033 | 3.85 | 0.712 | 0.345 |
| `FeatureTrackTapir` | 2736 | **5.98** | **0.927** | **0.754** |

| tracker | triangulated points | mean error | `yield` |
|---|---:|---:|---:|
| `FeatureTrackUnionFind` | 4671 | **0.280 px** | 0.993 |
| `FeatureTrackVGGSfM` | 3982 | 0.502 px | 0.987 |
| `FeatureTrackTapir` | 1548 | 1.581 px | 0.566 |

**Conclusions.**

1. **It is one monotonic trade: longer tracks, less accurate positions.** Union-find
   → VGGSfM → TAPIR moves `track_survival_5` from 0.116 to 0.754 and mean
   reprojection error from 0.280 px to 1.581 px, in step, with no crossover.

2. **No `tracks/v1` metric measures the second axis.** Every metric in the type
   describes length, coverage and self-consistency. A tracker can look excellent on
   all of them and be four pixels off everywhere. The triangulator's reprojection
   error is the first number that sees it — which is an argument for reading the
   *pipeline*, not the stage.

3. **The characteristic failure flips between the routes, and each metric is blind
   to the other's.** Union-find can fuse two scene points into one track and detects
   that with `inconsistent_rate`. The learned trackers cannot — one query point
   yields one position per frame — so `inconsistent_rate` is structurally zero for
   both. What they do instead is SPLIT one physical point across query frames, which
   union-find's metric cannot see. Both learned modules now report
   `duplicate_track_rate` for it: **45%** for VGGSfM, **50%** for TAPIR. The
   predecessor deduplicated in neither, so a well-seen point entered bundle
   adjustment once per query frame that found it.

4. **Query frame choice dominates both learned trackers, and endpoints are the
   trap.** Tracking from frame 0 of the 8-frame set leaves each point visible in
   1.77 frames against 4.40 from frame 4. The predecessor forced frame 0 into every
   VGGSfM query set "matching the VGGT demo behavior". It also applied
   `sorted(ranking)[:n]`, which returns the numerically smallest frame indices
   rather than the best-ranked ones — so its `query_selection` did less than it
   appeared to.

5. **TAPIR's resolution is a downstream parameter that upstream metrics cannot
   see.** BootsTAPIR trains at 256 square; at that size on a 1024px scene, one model
   pixel is four scene pixels across.

   | `input_size` | tracks | `track_survival_5` | tri points | tri error | `yield` |
   |---:|---:|---:|---:|---:|---:|
   | 256 | 2629 | 0.738 | 887 | 1.715 | 0.337 |
   | **384** | 2736 | 0.754 | 1548 | 1.581 | **0.566** |
   | 512 | 2683 | 0.739 | 1445 | **1.434** | 0.539 |
   | 768 | 2728 | 0.692 | 1433 | 1.470 | 0.525 |

   The track metrics barely move while the yield nearly doubles from 256 to 384.
   Past 384 it regresses — the model is being taken away from its training
   distribution. Default set to 384, not to the training resolution.

6. **The anisotropic squeeze is fine here and was a bug in VGGT.** TAPIR resizes to a
   square regardless of aspect, exactly the operation that broke the VGGT modules.
   The difference is that TAPIR predicts positions and the inverse map is exact,
   while VGGT predicts intrinsics with `fx == fy` and cannot express what a
   non-uniform squeeze does to a camera. The same operation is a quality question
   for one and a correctness bug for the other.

---

## 2026-08-12 — A merge tolerance does not scale with a tracker's noise, and the metric that would set it can only guard it

**The question.** `split_rate` says a track table still holds copies of one point
apart; `dedupe_eps_px` is the tolerance that merges them. VGGSfM and TAPIR
disagreed about whether deduplication helps, and the tidy explanation was that the
tolerance should scale with each tracker's own positional noise — which
`trifocal_transfer_px` now measures. So: is `dedupe_eps_px ≈ c · trifocal_transfer_px`
a real rule?

**Why this needed four experiments.** Deduplication changes how many points exist,
and reprojection error over different point sets is not comparable — the trap
already recorded twice in this file. Each arm below is blind to a different
confound, and no single one of them would have answered the question.

### Arm A — structure only, poses held fixed

DTU `scan1` and `scan24`, 8 images, `max_edge: 1024`. One pose set per scene, from
a chain the sweep does not touch:

```
SceneLoader → FeatureDetectionSIFT → FeatureMatchNN (exhaustive)
            → FeatureTrackUnionFind → PoseEssentialToPnP     ── the fixed frame
SceneLoader → FeatureDetectionSIFT → tracker(dedupe_eps_px) → SparseTriangulation
                                                              (against that frame)
```

Only the structure moves. Reprojection error is read at a **fixed track length**
so the point-count trap does not apply.

| `scan1`, VGGSfM | 0 | 0.5 | 1.0 | 1.5 | 2.0 | 3.0 | 4.0 | 6.0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `split_rate` | 0.421 | 0.140 | 0.057 | 0.015 | 0.000 | 0.000 | 0.000 | 0.000 |
| `trifocal_transfer_px` | **0.584** | 0.829 | 0.857 | 0.757 | 0.994 | 1.538 | 1.987 | 4.048 |
| err @ 3 obs | **0.411** | 0.464 | 0.484 | 0.478 | 0.477 | 0.506 | 0.538 | 0.526 |
| `yield` | **0.994** | 0.992 | 0.991 | 0.989 | 0.982 | 0.940 | 0.879 | 0.778 |

`scan24`/VGGSfM and `scan24`/TAPIR have the same shape — every eps > 0 is worse on
every outcome. `scan1`/TAPIR is the only mixed case (err @ 5 obs bottoms at eps 3.0,
err @ 3 obs at 2.0, `yield` at 0).

### Arm B — poses, against ground truth

ETH3D `courtyard`, 12 images (`DSC_0286`–`DSC_0297`), `resize: fixed [1024, 682]` —
both learned trackers stack the set into one tensor and ETH3D's captures are
6208×4134, 6200×4134 and 6205×4135. Full chain per eps, then scored against
`dslr_calibration_undistorted/images.txt` on **relative** pose over all 66 pairs, so
no gauge alignment and no scale enters:

```
SceneLoader → SIFT → tracker(dedupe_eps_px) → PoseEssentialToPnP
            → SparseTriangulation → BundleAdjustmentGlobal   → vs ground truth
```

This is the only arm that can see the actual argument for deduplication — *a
duplicated point enters bundle adjustment once per copy* — because camera poses are
a fixed-size output whatever the merge does. **Arm A is structurally blind to it.**

| VGGSfM, after BA | 0 | 0.5 | 1.0 | 1.5 | 2.0 | 3.0 | 4.0 | 6.0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `trifocal_transfer_px` | 1.470 | 1.449 | 1.903 | 1.366 | 1.459 | 1.733 | 2.265 | 2.313 |
| rotation, median ° | 0.123 | 0.119 | 0.120 | 0.116 | 0.113 | **0.108** | 0.143 | 0.171 |
| translation, median ° | 0.110 | 0.110 | 0.092 | **0.081** | 0.091 | 0.094 | 0.184 | 0.238 |

A real but shallow benefit over a **broad** optimum from 1.5 to 3.0, then a collapse
at 4. TAPIR on the same scene has no coherent optimum: its rotation error improves
only where its track count has collapsed, and its translation error moves the other
way. `FeatureTrackUnionFind` on the same 12 images reaches 0.106° / 0.081° with no
dedupe knob at all.

*Null control:* `PoseEssentialToPnP` re-rolled at six `confidence` /
`max_iterations` settings on an unchanged track table gave **exactly zero** spread.
The estimator is deterministic here, so differences between eps values are real
functions of the input rather than sampling noise.

### Arm C — synthetic, where the duplicates are known

1200 points, 8 cameras on an arc, 45% of points split into two tracks, every
observation the true projection plus N(0, σ). Merges scored by pair-counting
precision and recall against the truth. This is what separates "the rule is wrong"
from "real duplicates are not what the rule assumes".

| σ | `trifocal_transfer_px` | best eps | eps/σ | eps / transfer | best F1 |
|---:|---:|---:|---:|---:|---:|
| 0.25 | 0.918 | 0.50 | 2.00 | 0.54 | 0.966 |
| 0.50 | 1.700 | 0.75 | 1.50 | 0.44 | 0.899 |
| 1.00 | 3.200 | 1.00 | 1.00 | 0.31 | 0.749 |
| 2.00 | 5.348 | 1.50 | 0.75 | 0.28 | 0.526 |
| 4.00 | 10.392 | 2.00 | 0.50 | 0.19 | 0.263 |

### Arm D — replication

At 8 images the effect is mixed (rotation 0.101 → 0.092 → 0.084 → 0.104 across eps
0/1.5/3/6; translation 0.149 → 0.164 → 0.155 → 0.191). At 16 images `eps=0` produced
a **broken** reconstruction — median relative translation error 99.1° — where 1.5 and
3.0 did not; the largest single effect seen, on a marginal scene where the
registration counts also differ, so it is not an effect size. The disjoint window
`DSC_0300`–`DSC_0311` registers **3 of 12** images for union-find and 4 for VGGSfM,
so it measures nothing about eps. That is a fact about the courtyard capture, not
about deduplication, and the replication is honestly partial.

### How much evidence is behind each merge

Measured on the raw tables: for pairs a merge at 1.5 px would fuse, how many frames
they agree in against how many frames they share.

| scene / tracker | merges | backed by 1 frame only | median agreeing / shared |
|---|---:|---:|---:|
| `scan1` / VGGSfM | 5006 | 20.4% | **1.00** |
| `scan24` / VGGSfM | 6539 | 17.9% | **1.00** |
| `scan1` / UnionFind | 860 | 24.8% | **1.00** |
| `scan1` / TAPIR | 3886 | 29.4% | **0.50** |
| `scan24` / TAPIR | 3057 | 41.5% | **0.40** |

**Conclusions.**

1. **`dedupe_eps_px ≈ c · trifocal_transfer_px` is not a rule.** VGGSfM's optimum on
   ETH3D is 1.5–3.0 at a transfer of 1.47 (c ≈ 1–2); the same c predicts 2–4 for
   TAPIR at 1.92, where nothing is better than 0.5. On DTU, VGGSfM's optimum is 0 at
   a transfer of 0.58, which no positive c produces. The ratio is not constant across
   trackers, scenes, or outcome.

2. **Arm C says the rule scales in the wrong direction, not merely with the wrong
   constant.** The best tolerance grows *sub-linearly* in the noise — roughly √σ —
   so the ratio the rule assumes fixed falls 2.8× over the range tested. And the
   achievable merge quality collapses: at σ = 4 the *best possible* F1 is 0.26. A
   noisier tracker cannot be compensated by merging more loosely, because the
   tolerance wide enough to catch its duplicates also fuses distinct points.

3. **`trifocal_transfer_px` detects a wrong tolerance; it does not choose a right
   one.** It rises monotonically once eps begins fusing distinct points — `scan24`
   VGGSfM goes 0.96 → 12.14 across the sweep — and on ETH3D the two eps values where
   it exceeded ~2.2 are exactly the two where bundle adjustment blew out. **The
   usable procedure is: raise the tolerance, re-read the metric, stop when it starts
   climbing** — available at the tracker stage, before spending a reconstruction.

4. **`split_rate` and `duplicate_track_rate` stay separate metrics.** The first is
   what the table still holds apart at a tolerance the *type* fixes; the second is
   what a module's own `dedupe_eps_px` removed. Collapsing them would lose exactly
   the comparison that made this experiment possible.

5. **The evidence behind a merge separates the two learned trackers better than the
   tolerance does.** VGGSfM's merged pairs agree in *every* frame they share — those
   are one physical point. TAPIR's agree in half or fewer — those are two points that
   coincided once. A fifth of VGGSfM's merges and two-fifths of TAPIR's rest on a
   single frame's coincidence, which `split_rate` already refuses to treat as
   evidence (`SPLIT_MIN_SHARED_FRAMES = 2`) and which both trackers' merges accept.

6. **What was NOT established.** Whether requiring two shared frames improves the
   *reconstruction*. Reading that comparison through `trifocal_transfer_px` came back
   too noisy to call, because the metric's sampled triples change when the table
   does. The claim above is about the evidence behind the merges, not about a
   downstream win.
