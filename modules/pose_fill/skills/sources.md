---
module: PoseFill
module_version: 1.1.0
curated_at: 2026-09-25
---

# Where PoseFill's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit in
`tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| **that the fill beats the geometric model as delivered at every threshold, and is level with the feed-forward estimator run alone** (ahead at @3 and @30, behind at @5 and @10, never by more than 0.014, over seven captures of which two were controls), on the captures where the trigger fires; and that refining the filled cameras badly damages them while helping the core | measured; [`evidence/sparse-pose-2026-09.md`](../../../skills/evidence/sparse-pose-2026-09.md) |
| that the trigger is a verifier reading firing TOGETHER WITH cameras the view graph cannot justify, and that filling a capture already holding its cameras on evidence it has is a downgrade | measured on a promoted corpus capture; same campaign file |
| the similarity convention: a world rescaled by `s` puts `s` in the camera translation and leaves the rotation block a rotation | derived, and checked numerically against random poses |
| that a filled camera becomes its own component in `SparseVerification`, so an unmarked fill trips `model_not_supported_by_its_own_evidence` | read directly from that module's component construction over posed cameras |
| that a filled camera holding no structure yields an empty depth map rather than a corrupted one, so the fill is dense-neutral | `plan/dense.md` on `min_frame_points` and MVS source-view selection |
| **that the rule needs an executable drop**: two captures produced a clean fill on a core still holding one bad camera, and the finished model was vetoed; both agents recorded the missing drop in their own reports | measured; the pose batch of 2026-09-25 |
| **that the fit residual does not price the filled frames**: one capture's estimators agreed across the overlap and disagreed by tens of degrees on exactly the frames being filled | measured; same batch |
| **the gate defaults, the shared-camera floor, the trim, the filled-frame ceiling** | **nothing** — see the audit section in `tuning.md` |
| **behaviour in a real pipeline** | measured, one campaign: thirteen fill attempts over twenty captures, four delivered and six refused by a gate, every refusal scored against reference poses. `filled_agreement_deg` predicts the fill's own rotation median at rho +0.82; it is non-monotone between about 5 and 75 degrees, where two estimators cannot say which of them is the outlier. Every fill that passed both gates left the capture fully posed; every refused one left it short |
