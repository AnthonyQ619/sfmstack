---
module: BundleAdjustmentLocal
module_version: 1.2.1
upstream: pycolmap 4.1.1 / Ceres
curated_at: 2026-08-08
sources: 2
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 5 parameters documented, starting with `window_size` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot correct drift between distant cameras" |
| you are reading what it wrote | **`artifact`** — the layout of `sparse_model/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`.

**Diagnostics it can raise:** `bundle_adjustment_diverged`, `points_escaped`, `window_covers_model`, `did_not_converge`, `no_improvement`, `points_dropped_by_min_track_len`, `too_few_points`.

## What this module is for


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

## Provenance

**Run zero times in any pipeline.** Every claim in these skills is from isolated
testing or carried from the predecessor codebase; nothing here has been exercised
end to end. The first real run is the trigger to re-check all of it.
Claim-by-claim citations: the `sources` skill.
