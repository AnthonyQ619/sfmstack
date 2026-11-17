# Campaign: dense-strict-fusion-2026-11 — five record deliveries re-densified without an agent

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports live in
`DenseMVS`'s tuning ("Delivering a dense cloud"), `DenseFusion`'s tuning ("Stepping down, and when
to stop") and the dense plan ("Delivering the verified cloud").

## What was run

A context-ablation study (three agents with the tools and no written context) beat the full-context
record on five unseen captures. Each was replayed offline, no agent: the record session's own refined
sparse model (for one capture with no kept model, the record's sparse steps re-run with its
parameters) densified with one `DenseMVS` pass at the module defaults (geometric check on, fusion at
its default) and the workspace kept, then two deliveries from that one pass:

- **defaults** — the stereo pass's own fused cloud;
- **strict** — `DenseFusion` on its geometric depth maps at `min_num_pixels` 8, `max_reproj_error`
  1.0, `max_depth_error` 0.005, `max_normal_error` 10.

The record deliveries being compared against were all at the delivery anchor (geometric check off,
fusion 4), and the three sequence captures were stepped down to fusion 2, the coverage route. So each
row is the same sparse model and frames, with the dense setting changed. Scored by each benchmark's
own evaluation: studio orbits, overall mm after best fit ↓; video depth, scale-only Abs Rel ↓ (with
the fraction of pixels covered); the forest-aerial capture, F1 at 5 cm ↑. One replay per cell: the
studio-orbit differences are a few hundredths of a millimetre and could be run-to-run.

## Finding 1 — the verified stereo pass with strict fusion beat the anchor on every capture replayed

| capture | kind | record (anchor, → 2 on sequences) | defaults | strict |
| --- | --- | --- | --- | --- |
| `/DTU/scan24` | studio rig orbit | 0.332 | 0.338 | **0.306** |
| `/DTU/scan114` | studio rig orbit | 0.300 | 0.306 | **0.283** |
| `/MADMAX3/H0_scene_000` | ground-rover video, outdoor terrain | 0.0113 (cov 0.98) | 0.0098 (0.97) | **0.0094** (0.96) |
| `/FLSea/tiny_canyon_scene_000` | underwater video | 0.0102 (cov 0.86) | 0.0060 (0.79) | **0.0052** (0.68) |
| `/Fuji/west_scene_000` | forest aerial, nadir | 0.393 | **0.494** | 0.436 |

- **On the studio orbits,** strict beat both the anchor and the defaults. The defaults were level
  with the anchor, as in `dense-fixes-2026-10`, Finding 2.
- **On both video sequences,** the verified pass beat the anchor-plus-2 delivery at either fusion,
  by 17–49 % in Abs Rel. Coverage fell by a few points to 18, and the score still improved.
- **On the forest aerial,** both improved on the anchor-plus-2 delivery. The record was the more
  complete cloud (completeness at 5 cm 0.62 against 0.47 at strict) and far less accurate (0.29
  against 0.52); the defaults' fusion scored best.
- **Not replayed:** a second ground-rover sequence (`MADMAX3/C0`-like) on which the anchor-plus-2
  delivery was already well ahead of every ablation arm, and the site walks, rooms and outdoor object
  orbits of `dense-fixes-2026-10` Finding 1, where fusion 2 off the anchor scored best on every
  capture measured. Nothing here contradicts that finding on those kinds.

## Why the anchor lost here

The anchor trades accuracy for completeness. Every scorer above charges a stray point at least as
much as a hole: Abs Rel and F1 at a fixed tolerance per pixel or point, and the studio best-fit
overall through the accuracy half, which the strict fusion improved more than it cost completeness.
On these kinds the geometric check is what removes the stray depths, and it is the check the anchor
switches off.

## Provenance

Phase 10 of the experiments, salvage replay (`P10/salvage/`), 2026-11-16. Post-hoc: designed after
the ablation arms' scores were known, on the captures they won. The five captures are promoted into
`CORPUS.txt`; a later result on them is recall, not a cold test.
