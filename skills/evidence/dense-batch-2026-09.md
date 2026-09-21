# Campaign: dense-batch-2026-09 — raw frames to a dense cloud, every capture, planning only from context

**Campaign run 2026-09 over 22 captures. Derivation redone 2026-09-20 against the
ten captures of [CORPUS.txt](CORPUS.txt) alone, and cross-checked on ETH3D.** The two
dates are kept apart on purpose: the runs happened when the corpus was a different set,
and restating them as though today's corpus existed then would be the same error this
re-derivation exists to fix. What the re-derivation found is in
[Replication](#replication-what-survived-a-second-dataset); it changed several verdicts
and removed nothing.

**This is a raw evidence table. Cite it; do not plan from it.** The reasoning built on these rows lives in [`plan/dense.md`](../plan/dense.md), [`plan/optimization.md`](../plan/optimization.md), [`health/ladder.md`](../health/ladder.md) and the dense modules' own skills, stated as capture properties rather than as scene names.

## Protocol

The whole tool loop over the 22 captures of this dataset's standard evaluation set, one isolated agent per capture, every module and parameter chosen from retrievable context alone, at full frame count (49 views) and with the dense stage in scope. Ground truth entered once at the end, in a separate scoring script; no plan, parameter or branch choice saw any of it.

**Scoring.** The public protocol for this dataset: each cloud thinned to one point per 0.2 mm, accuracy as the mean distance from the cloud's points inside the observability mask to the reference scan, completeness as the mean distance from the reference points above the ground plane to the cloud, distances of 20 mm or more dropped from both means, overall their average. Same constants as the widely used Python port of the original script.

**Two bases, and they answer different questions.**

- **Published basis** — the cloud fitted to the reference geometry (trimmed 7-DoF ICP) before scoring. This is what published dense results on this dataset do for methods that estimate their own cameras (a similarity by Umeyama, in some work refined by ICP), so it is the only basis on which these numbers and published ones mean the same thing.
- **As placed** — the cloud left where the capture's own sparse model put it, with the frame fixed by a robust similarity from registered camera centres to the reference rig positions. Reference *geometry* plays no part in that fit. Every error in the placement is charged to the result.

All 22 agents delivered on the first attempt, in 74–172 minutes each, and all 22 chose the photometric MVS module.

## Per capture

| capture | role at run time | sparse pipeline | dense | reg | sparse pts | thinnest view | error px | acc | comp | overall | acc placed | comp placed | overall placed | align mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-dtu-scan1"></a>DTU/scan1 | control | `sift-clahe+nn/incr@1600` | `mvs@1600` | 49/49 | 78,076 | — | 0.321 | 0.233 | 0.380 | **0.306** | 0.362 | 0.534 | 0.448 | 0.65 |
| <a id="cap-dtu-scan4"></a>DTU/scan4 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 72,173 | — | 0.321 | 0.280 | 0.566 | **0.423** | 0.648 | 1.072 | 0.860 | 0.90 |
| <a id="cap-dtu-scan9"></a>DTU/scan9 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 31,173 | — | 0.356 | 0.339 | 0.451 | **0.395** | 0.499 | 0.624 | 0.562 | 0.63 |
| <a id="cap-dtu-scan10"></a>DTU/scan10 | control | `sift+nn/incr+gtsam@1600` | `mvs@1600` | 49/49 | 27,655 | — | 0.332 | 0.286 | 0.500 | **0.393** | 0.734 | 0.922 | 0.828 | 1.09 |
| <a id="cap-dtu-scan15"></a>DTU/scan15 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 36,702 | — | 0.356 | 0.345 | 0.426 | **0.386** | 0.532 | 0.620 | 0.576 | 0.70 |
| <a id="cap-dtu-scan23"></a>DTU/scan23 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 63,154 | — | 0.305 | 0.318 | 0.483 | **0.400** | 0.786 | 1.152 | 0.969 | 0.60 |
| <a id="cap-dtu-scan33"></a>DTU/scan33 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 71,600 | — | 0.265 | 0.452 | 0.611 | **0.531** | 0.693 | 0.902 | 0.798 | 0.70 |
| <a id="cap-dtu-scan48"></a>DTU/scan48 | holdout | `sift-clahe+nn/global@1600` | `mvs@1600` | 49/49 | 2,876 | — | 0.345 | 0.373 | 2.928 | **1.651** | 0.939 | 3.513 | 2.226 | 1.67 |
| <a id="cap-dtu-scan75"></a>DTU/scan75 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 27,793 | — | 0.299 | 1.053 | 0.438 | **0.745** | 1.760 | 1.085 | 1.423 | 1.08 |
| <a id="cap-dtu-scan77"></a>DTU/scan77 | holdout | `sift+lightglue/global@1600` | `mvs@1600` | 49/49 | 4,836 | — | 0.547 | 0.803 | 0.736 | **0.770** | 1.395 | 1.326 | 1.361 | 0.77 |
| **mean, 10 corpus** | | | | | | | | **0.448** | **0.752** | **0.600** | 0.835 | 1.175 | 1.005 | |

**These are the ten corpus captures only.** The campaign ran over 22; the twelve that
are not in [CORPUS.txt](CORPUS.txt) were moved to the experiment record on 2026-09-20
(`~/sfm_experiments/DTU_dense_exp/HOLDOUT_ROWS.md`) and are deliberately not reachable
from context. They are reserved for measuring whether this context generalises, and a
holdout that has been read into context is no longer one.

The `role at run time` column is historical: it records the corpus as it stood when the
batch ran, when seven captures were named controls. scan48, scan75 and scan77 were
promoted into the corpus on 2026-09-19 and that column still calls them holdout.

For reference, the means the twelve holdout rows produce: published basis accuracy 0.355,
completeness 0.590, overall **0.473**; as placed, overall 1.016. The corpus captures are
the *harder* set on the published basis (0.600 against 0.473), because the three promoted
in 2026-09 were promoted for being difficult.

## What was derived from these rows

| Claim | Where it went | The rows behind it | Verdict, 2026-09-20 |
| --- | --- | --- | --- |
| Coverage, not purity, is what the dense stage consumes | `plan/dense.md` §Planning the sparse stage | sparse points vs completeness **−0.64**; thinnest view **−0.59**; median points per view −0.50; at equal density, models keeping two-view structure −0.45 and models pruned to long tracks +0.47 | **Weakened — do not treat as a rule — and now stated conditionally.** Its four supporting signals (point count, thinnest view, two-view structure, track length) all fail to replicate; two flip sign between datasets. Measured again on 2026-09-20 with the corpus split by dataset, the headline association is not weak everywhere but **absent on one kind of capture**: point count against dense completeness is −0.75 (p 0.013) over the ten close-range orbits and −0.19 (p 0.62) over the nine site captures. The two cannot be pooled — the datasets score completeness in different units under different protocols. `plan/dense.md` now says a thin model on a site tells you nothing. |
| The error rung cannot see metric placement | `health/ladder.md`; `plan/optimization.md` §3 | reprojection error flat at 0.26–0.55 px across the batch and **+0.29** against metric error over 74 models; two captures at 0.33 px differing five-fold in metric error | **Stands, and is understated.** The pooled correlation that looked like a contradiction is a between-capture effect. *Within* a capture the sign is capture-dependent — negative on this dataset (df 24, −0.51), positive on five of eight outdoor sites and strongly negative on two. Nothing visible to an agent says which sign a capture has, so the reading cannot rank models. See [Replication](#replication-what-survived-a-second-dataset). |
| Do not refine intrinsics on a calibrated capture | `plan/optimization.md`, `ba_global/tuning.md` | focal free: 0.44 → 0.33 px while the cloud moved 1.46 → 3.47 mm; focal + principal point → 13.36 mm at 0.28–0.33 px; recovered focal 0.877–1.055 of the shipped value | **Re-derived 2026-09-20 and it generalises.** The verdict "sample size does not bear on it" was right about the logic and wrong about the provenance: all four captures behind it were holdouts. Re-run on four corpus captures and on two site captures of a second dataset, it came out the same way **10 times out of 10** — reprojection error improved, placement worsened by 1.5× to 5×. The orbit-specific mechanism the context used to state has been removed, because sites behave identically. |
| A hole is a photometric refusal, not an absence | `plan/dense.md`; `dense_mvs/limitations.md` | 94–99.5% of missed reference surface visible and unoccluded in ≥5 of the capture's own cameras, depth-buffer occlusion test | **Re-derived 2026-09-20 on the nine corpus captures that have it, and softened.** The direction holds on all nine — missed surface is seen in fewer good views than covered surface, every time. The magnitude does not: "nearly all" was fitted with holdouts in the sample and the corpus range is wider, and the gap that made the reading useful is large only where a capture misses a tenth or more of the reference surface. On a capture that misses little, missed and covered surface are seen about equally well and the reading says nothing. `plan/dense.md` now states it conditionally. |
| Blown highlights predict dense coverage | `scene_triage/module.yaml`, its `tuning.md`, `plan/dense.md` | `highlight_clipped_fraction` vs `depth_map_completeness` **−0.92**; texture density +0.59; textureless fraction −0.56; coverage spread 0.12–0.79 | **Not replicable on ETH3D** — eight of thirteen captures have no `depth_map_completeness` and the highlight range there is 0-2% against 12-79% here. Stands on this dataset alone. |
| `fusion_min_num_pixels` is the one filter that buys coverage | `dense_mvs/tuning.md` | five captures, five improvements: completeness 0.741→0.717, 1.396→1.238, 3.513→3.305, 2.071→1.928, 0.768→0.734; points ×1.61–1.85; mean aligned overall −0.032 mm | **Unaffected.** Five paired interventions, five improvements. The strongest evidence in this table and the smallest sample — interventional beats correlational. |
| A predicted cloud is not a repair kit | `plan/dense.md`; `dense_vggt/limitations.md` | on one capture, aligned overall: MVS 0.307, predicted alone 1.164, union 1.217, hole-fill 1.585; 1.9 of 2.46 M predicted points >2 mm from any verified point | **Re-derived 2026-09-20 and split in two.** The original rested on one holdout capture; it now rests on eight across both datasets. The repair itself holds and is stronger: filling only the verified cloud's holes was **never** the best of four arms, 0 of 8. What did *not* hold is the accompanying assumption that the verified cloud always wins — on two captures whose verified completeness had collapsed, the union overtook it. Both now stated in `plan/dense.md`, with the caution that the averaged score stops discriminating there. |
| Selection is not where the dense result is won | `health/ladder.md` | delivered model metrically best in 6 of 22; best computable rule −2.4%; oracle −15.5% | **Replicates.** 6 of 22 here, 5 of 12 on ETH3D — the same rate on a different dataset. |
| MVS runtime under contention | `dense_mvs/SKILL.md` | under-predicted 1.5×–6×; 10 of 22 agents recorded it independently | **Already re-derived** (2026-09-19) on 123 timed runs across the 19 corpus captures of both datasets. |

## Replication: what survived a second dataset

Added 2026-09-20. Six of the claims above rest on correlations over the 74 sparse models
this batch's agents reported — every reading an agent CAN see, ranked against the metric
error it cannot. Those correlations were recomputed four ways: this dataset's corpus and
its holdout, and the same audit ported to ETH3D's thirteen captures
(`ETH_dense_exp/scoring/eth_alt_audit.py`, 34 models, split 9 corpus / 4 holdout).

Four cells. A relationship alive in one cell is an artifact of that cell; one alive in
three or four is a property of reconstruction.

| signal, against metric error | DTU corpus (34) | DTU holdout (40) | ETH corpus (24) | ETH holdout (10) | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| reprojection error | **+0.43** | +0.07 | **+0.63** | +0.41 | **pooled only** — see below; the sign reverses *within* a capture |
| point count (log) | **−0.79** | +0.17 | −0.08 | −0.10 | **fails** — one cell only |
| two-view fraction | **−0.48** | −0.13 | +0.30 | **+0.69** | **fails** — sign flips by dataset |
| mean track length | **+0.50** | −0.02 | **−0.41** | **−0.76** | **fails** — significant in both directions |
| p05 triangulation angle | **+0.51** | **−0.46** | −0.28 | −0.62 | **fails** — three cells negative, the positive one is this dataset's corpus |
| min frame points (log) | **−0.62** | +0.23 | −0.34 | +0.48 | **fails** — corpus negative, holdout positive, both datasets |

Bold marks significance at the 5% threshold for that cell's n (0.34, 0.31, 0.40, 0.63).

**Why the corpus cell looked so strong, and why that was the warning.** On the seven
captures that were the corpus when this batch ran, *none* of these six is significant —
+0.06, −0.10, −0.22, −0.02, −0.20, +0.07, with the metric error spanning only sd 0.14 mm.
Adding the three captures promoted in 2026-09 takes that spread to sd 0.70 mm and every
coefficient becomes significant. They were promoted for being difficult, so they extend
the range, and extending the range of a narrow set manufactures correlation. Dropping one
of them alone moves the reprojection coefficient from +0.43 to +0.26, below its threshold.
**A coefficient computed on the corpus is not the conservative reading; here it was the
optimistic one.**

**The one that replicates is a between-capture effect, and the claim it seemed to
contradict is about something else.** Pooled, reprojection error tracks metric error in
all four cells. Decomposed, it splits in two, and the halves disagree:

| | between captures | within a capture | captures whose direction is positive |
| --- | ---: | ---: | --- |
| ETH3D corpus, outdoor sites | +0.53 (ns, 8 scenes) | +0.65 (sig, df 15) | **5 of 8** |
| this dataset's corpus, studio orbits | +0.65 (sig, 10 scenes) | **−0.51** (sig, df 24) | 5 of 10 |

The ladder's question is *"which of the models I hold is better"* — a within-capture
question. Within a capture on this dataset the association is **negative**: the model
with the lower reprojection error is the one further from the reference, which is the
focal-refinement result stated another way. Outdoors it is positive on five of eight
sites and strongly negative on two (−0.96, −0.66).

**So the claim is not too strong; it is understated.** The reason the error rung cannot
see metric placement is not that the correlation is weak. It is that **the sign is a
property of the capture**, and nothing visible to an agent says which sign it has. A
model ranked by reprojection error is right about half the time and systematically wrong
on some captures. The pooled positive figure is a between-capture effect — harder scenes
have both worse reprojection and worse placement — and an agent holding one capture
cannot use it.

*(Recorded because the first pass of this re-derivation, on 2026-09-20, read the pooled
+0.63 as contradicting the claim and proposed narrowing it. That was comparing a pooled
correlation against a within-capture rule. The decomposition above is the correction.)*

**Not tested here.** The highlights correlation could not be replicated on ETH3D and
should not be reported as if it were: `depth_map_completeness` is null for eight of the
thirteen captures, and the highlight fraction there spans 0–2% against this dataset's
12–79%. Five points and a degenerate predictor cannot test anything. The claim stands on
this dataset alone until a capture set with real clipping is measured.

**What did replicate outside the correlations.** Selection: the delivered model was the
metrically best available in 6 of 22 here and 5 of 12 on ETH3D — the same rate, and on
ETH3D two captures' rejected alternatives were 2x and 3.7x nearer the reference than what
shipped.

**Five models were lost to the ETH3D audit** because their agents wrote prose into the
report field that should hold an artifact id ("(none; stopped at pose ...)", "art_... 
(unrefined)"). That is a harness defect, not a measurement one.

## The placement floor, and the six explanations that failed

Each capture's cloud sits 0.8–4.5 mm from where the reference expects it, and independently built models of one capture are displaced **identically** — median cosine +0.99 between displacement vectors, differing by 0.20 mm. That is the gap between the two bases above, and it is why pipelines should be compared on the published basis.

| tested | result |
| --- | --- |
| focal refinement | worse (1.46 → 3.47 mm) |
| focal + principal point | much worse (→ 13.36 mm) |
| BA convergence (18 of 22 hit the iteration cap) | converges by 414 iterations; geometry identical to 5 decimals |
| per-position camera-centre correction | halves the camera residual, moves the object 0.012 mm |
| the frozen per-position rotation correction | much worse for 20 of 22 (shift 1.43 → 4.56 mm) |
| distortion model | no radial trend in reprojection error (outer/inner 1.04) |

## Beside published results on this dataset

Millimetres, published basis, same evaluation set. Rows marked *given* were handed the dataset's calibration and reconstruct in the reference frame; rows marked *estimated* recovered their own cameras and were aligned before scoring, as this batch was. Published feed-forward rows sample a handful of frames per capture; every capture here used all 49 views.

| method | cameras | accuracy | completeness | overall |
| --- | --- | --- | --- | --- |
| Gipuma | given | 0.283 | 0.873 | 0.578 |
| COLMAP | given | 0.400 | 0.664 | 0.532 |
| MVSNet | given | 0.396 | 0.527 | 0.462 |
| GeoMVSNet | given | 0.331 | 0.259 | 0.295 |
| DUSt3R | estimated | 2.677 | 0.805 | 1.741 |
| MASt3R | estimated | 0.403 | 0.344 | 0.374 |
| VGGT | estimated | 0.389 | 0.374 | 0.382 |
| **this batch, all 22** | estimated | **0.398** | **0.664** | **0.531** |
| **this batch, 15 holdout** | estimated | **0.433** | **0.746** | **0.589** |

Accuracy sits with the published field; completeness is where the whole distance is. Five captures already beat the best published overall on this basis, and the batch mean is dragged by a tail of captures whose photometry denied the dense stage evidence.

## What this campaign could not measure

- **Which part of a hole is clipped and which is textureless.** The batch established that holes are photometric and that clipping predicts them; it never projected missed surface back into the images to attribute each hole. That is the first thing a follow-up needs.
- **Whether a surface reconstruction step would close the completeness gap.** Published dense numbers are often measured on a sampled surface rather than a fused point cloud; no module here produces one.
- **The fusion knob as a curve.** Five captures at one value, not a sweep — fusion is not separable from the stereo pass in the current module, so each arm costs a full MVS run.
- **Anything about captures that are not studio orbits of compact subjects.** Every row here is one rig.

## Harness note

One capture met a CUDA out-of-memory failure caused by three captures sharing a device, before the harness gated dense steps; its agent retried at lower resolution and delivered. The capture is flagged in the results and on both report pages, and the intervention is recorded in the experiment's `INTERVENTIONS.md`. Reports: `~/sfm_experiments/DTU_dense_exp/DTU_dense_results.html`.
