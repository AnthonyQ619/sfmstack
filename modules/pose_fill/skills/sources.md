---
module: PoseFill
module_version: 1.0.0
curated_at: 2026-09-25
---

# Where PoseFill's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit in
`tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| **that the fill beats both the geometric model as delivered and the feed-forward estimator run alone, at every threshold**, on the captures where the trigger fires; and that refining the filled cameras badly damages them while helping the core | measured; [`evidence/sparse-pose-2026-09.md`](../../../skills/evidence/sparse-pose-2026-09.md) |
| that the trigger is a verifier reading firing TOGETHER WITH cameras the view graph cannot justify, and that filling a capture already holding its cameras on evidence it has is a downgrade | measured on a promoted corpus capture; same campaign file |
| the similarity convention: a world rescaled by `s` puts `s` in the camera translation and leaves the rotation block a rotation | derived, and checked numerically against random poses |
| that a filled camera becomes its own component in `SparseVerification`, so an unmarked fill trips `model_not_supported_by_its_own_evidence` | read directly from that module's component construction over posed cameras |
| that a filled camera holding no structure yields an empty depth map rather than a corrupted one, so the fill is dense-neutral | `plan/dense.md` on `min_frame_points` and MVS source-view selection |
| **the gate default, the shared-camera floor, the trim** | **nothing** — see the audit section in `tuning.md` |
| **behaviour in a real pipeline** | **nothing** — this module is new and has not run a campaign |
