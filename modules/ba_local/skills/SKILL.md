---
module: BundleAdjustmentLocal
module_version: 1.1.0
upstream: pycolmap 4.1.1 / Ceres
curated_at: 2026-08-08
sources: 2
---

Bundle adjustment over a window of cameras, holding the rest of the model fixed.
CPU-only.

**Use when** you want refinement you can afford to run repeatedly — inside an
incremental loop, or as a targeted repair on the worst part of a model. Global BA
costs grow with the whole model; this one's do not.

**It is not a cheaper substitute for global BA.** Cameras outside the window are
constant, so drift *between* distant parts of the model cannot be corrected — only
local geometry improves. The usual shape is local BA repeatedly during
registration, global BA once at the end.

**Judge it on `window_error_after`, not `reprojection_error_after`.** The global
figure is diluted by the cameras that were deliberately not touched. Measured on
one short contiguous arc of twelve calibrated frames around a small, well-textured
object on a plain backdrop (window 5, `anchor: last`):

| metric | before | after |
|---|---:|---:|
| window (5 refined cameras) | 0.4855 | **0.3536 px** |
| whole model (12 cameras) | 0.4713 | 0.3842 px |

The window improved by 27%; the model-wide figure shows 18% because seven cameras
were fixed.

**`anchor` picks where the window sits.** `last` for the incremental case, `first`
to interrogate the initialisation, `largest_error` to repair the worst part. On the
reference scene `largest_error` correctly selected a window starting at 0.5458px
against `last`'s 0.4855 — the selection works.

**Check `converged`.** A local solve at the default 50 iterations did *not*
converge on the reference scene; at 400 it did, with an identical result. The
answer was already there, and only the flag revealed the difference. That flag was
itself wrong until recently — see [sources](sources.md).

**Reading the output:** [artifact.md](artifact.md). Same type in and out, so it
chains and is idempotent in shape.
