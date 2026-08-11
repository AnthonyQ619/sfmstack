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
