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
