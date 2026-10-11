---
module: MatchQuantize
module_version: 1.0.1
curated_at: 2026-10-10
---

# Where MatchQuantize's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not browsed.**
The provenance summary rides `SKILL.md`; unsourced-default warnings sit in the audit
section of `tuning.md`.

| | Kind | Rests on | Scope |
| --- | --- | --- | --- |
| S1 | measured here | The defect this module repairs: detector-free correspondences form **two-view components only**. Union-find over the verified inliers of one rig-orbit capture gave 86,442 components with a single-bucket length histogram, and the reconstructor's own log reported 70,217 tracks from 140,434 observations — exactly 2.000 each. Measured through `SparseGlobalCOLMAP` 1.4.0 at `max_epipolar_error = 2.0`, `num_threads = 1`. | One capture, two detector-free matchers; the arithmetic is independent of n |
| S2 | measured here | The two gates that discard two-view tracks, and that only one is reachable: `min_track_len` = 3 at the track filter, and the retriangulation stage's own two-view exclusion which this stack exposes no parameter for. A/B at `min_track_len = 2` kept all 70,217 tracks, ran positioning and bundle adjustment, and still produced zero points; flipping the unreachable default produced 81,137. `SparseGlobalCOLMAP` 1.4.0. | One capture; mechanism, not a band |
| S3 | measured here | The `grid_px` default of 4.0, and that the benchmark families are insensitive to it. **54 runs at 1.0.0** — nine captures, two detector-free matchers, `grid_px` ∈ {1, 2, 4}, scored on pose against reference extrinsics at `max_epipolar_error = 2.0`, `num_threads = 1`. 4.0 won 8 of 18 capture/matcher pairs and dominated the discriminating captures; the two rig orbits were flat to three decimals under every value. | Nine captures of five scene kinds, one working resolution; scope pinned by `evidence/CORPUS.txt` |
| S4 | measured here | **That track yield does not predict pose accuracy**, which is the warning at the head of `tuning.md`. The same 54 runs at 1.0.0, read against the three-view component counts of the same inputs: the grid maximising component count was worst for pose on three captures, moving 0.124→0.313, 0.186→0.333 and 0.094→0.158 from the finest grid to the coarsest while the count fell throughout. | Three captures showed the inversion; two matchers |
| S5 | measured here | The parity bound in `SKILL.md` and `limitations.md`: the global route through this module reached parity with the incremental route on the same correspondences for one detector-free matcher (median \|Δ\| 0.028 over nine captures) and a worse but working result for the other (0.063), against a route that returned nothing on every capture before. 54 runs at 1.0.0. | Nine captures, two matchers, single runs |
| S6 | Predecessor source | That a conflict must be reported rather than resolved by arrival order. `sfmcore`'s track assembly resolved a cell claiming two partners by letting the last write win, silently, which put a wrong observation into bundle adjustment and reported nothing. `on_conflict` and `conflict_rate` exist because of it. | Design constraint, not a measurement |
| S7 | *Detector-Free Structure from Motion*, He, Sun, Wang, Peng, Huang, Bao & Zhou, CVPR 2024 | The method: binning match locations to a grid to force consistency, stated there as striving for consistency by sacrificing accuracy; the pair-dependent nature of coarse-to-fine detector-free matching as the cause; and that quantization alone is a coarse stage their refinement phase then improves on. | External |
| S8 | Classical practice | That single-linkage clustering chains, and so a radius merge is not a partition while lattice rounding is — the reason `grid_px` is a grid and not an epsilon. | External |
| S9 | measured here | That `cycle_merge_rate` is **not** an over-merge alarm on this module's output: it falls as the grid coarsens rather than rising, and did not track the outcome. One rig-orbit capture through the full chain at **1.0.0**, `grid_px` = 1.0 against `grid_px` = 4.0, `max_epipolar_error = 2.0`, `num_threads = 1`: rate 0.671 against 0.388, pose 0.9744 against 0.9743. | **One capture, two settings.** Enough to retract the alarm reading, not enough to replace it with a mechanism |
| S10 | measured here | That `cycle_merge_rate` reads the correspondence SOURCE rather than the outcome. Twenty-four corpus captures per source through the full chain at **1.0.0**, `grid_px` = 4.0, `max_epipolar_error = 2.0`, `num_threads = 1`: the two sources occupy disjoint ranges (0.222-0.478 against 0.699-0.903) and the rate against AUC@30 correlates at r = +0.142 over 48 paired readings. Supersedes the scope of S9, which reached the same conclusion from one capture. | Strong — n=24 per source, two sources, one fixed grid. Says nothing about other grids |
| | | | |
| | 6 healthy bands: **4 structural arguments, 2 chosen, 0 measured** | — see the audit section in `tuning.md` | |
