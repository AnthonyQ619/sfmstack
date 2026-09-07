---
module: FeatureMatchFLANN
module_version: 1.6.0
curated_at: 2026-09-07
---

# Where FeatureMatchFLANN's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the right ANN algorithm and parameters are data-dependent, with an auto-tuning procedure — which OpenCV does not expose, so `trees` and `checks` are hand-set here, exactly the situation the paper argues against; `match_agreement` is this module's substitute, measuring the recall actually obtained | Muja & Lowe, VISAPP 2009 and TPAMI 2014 |
| randomised KD-trees: multiple trees on random high-variance splits, shared priority queue — what makes 128-dim SIFT space searchable at all | Silpa-Anan & Hartley, CVPR 2008 |
| multi-probe LSH (`lsh_probe_level`): probe neighbouring buckets, recall without proportionally more tables; used for binary descriptors because Hamming space cannot be KD-indexed — selected automatically from the artifact's `binary` flag so an upstream swap cannot silently produce a wrong index | Lv et al., VLDB 2007 |
| FLANN measured **6× slower than brute force** at 4096 keypoints/pair — specific to per-pair index construction, recorded in [limitations.md](limitations.md) because the general claim "ANN is faster" is true and this application is not | direct measurement in this repo |
| `trees=4` (OpenCV default; predecessor used 5), `checks=50`; predecessor was sequential-only and built a KD-tree even for binary descriptors — a category error nothing would have reported | predecessor `sfmcore/featurematching.py`, `FeatureMatchFlannPair` |
| `no_pairs` was declared and never emittable — the module RAISES when no pair survives, and there is no artifact to hang a diagnostic on. The declaration is gone; a contract listing a catchable failure that actually raises is worse than none | manifest audit, corrected |
| every measured band and episode | **4 runs** at 1.6.0 in the seventeen-capture sweep; scope pinned by `evidence/CORPUS.txt` |
| 5 healthy bands; numeric values in `window`, `ratio_test`, `trees`, `lsh_tables` advice | **nothing** — see the audit section in `tuning.md` |
