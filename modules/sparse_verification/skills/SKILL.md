---
module: SparseVerification
module_version: 1.0.1
upstream: none -- numpy, and OpenCV for undistortion only
curated_at: 2026-09-13
sources: 0
---

## Where to go next

This file is the router. The detail lives in the other four documents.

| If | Fetch |
| --- | --- |
| a model was vetoed, or you are deciding what the veto means | **`limitations`** — starting with "What a contradiction means" |
| a parameter needs moving, or `nothing_held_out` fired | **`tuning`** — 2 parameters documented |
| you are reading the per-pair array | **`artifact`** — the layout of `custom/verification/v1` |
| you want to know where a claim came from | **`sources`** — what was measured, and what rests on nothing |

**First reading on this module's output:** `heldout_residual_px`, then `pairs_verified`.

**Diagnostics it can raise:** `contradicted_by_held_out_evidence`, `nothing_held_out`.

## What this module is for

It is a **veto**. It asks one question of a finished sparse model — do the
matcher's correspondences that the model never used contradict it? — and its one
decision is whether to reject the model.

**You normally do not call it.** The service runs it automatically after every
optimization module that produces a sparse model, wires the model's own matches
from its lineage, and delivers the result as `verification` beside the health
profile. Call it yourself only to check against *different* evidence — another
matcher's matches of the same scene — or to check a model that did not come
through an optimization step.

**Why it is a fixed step and not a judgement call.** Every other reading on a
sparse model is computed over what the model kept, and the solve minimised
exactly that. A model that settled into a wrong but self-consistent
configuration therefore passes all of them, and has been measured passing them
*better* than the correct model of the same capture. An agent deciding whether to
check would be deciding from those same readings.

**How to use the verdict:**

- **Contradicted** — veto. Do not keep this model. If another solve of the same
  capture exists and passes, keep that one; if not, solve again with a
  deliberately different setting before tuning anything. Never rescue a vetoed
  model on its reprojection error or registration.
- **Consistent** — no veto. The model does not contradict evidence it was not fit
  on. That is **not** a certificate of accuracy and **not** a ranking: see below.
- **Unverified** — nothing was held out, so nothing was tested. Supply other
  evidence.

**It does not choose between two models it accepts.** When two solves of one
capture both pass, keep the one the pipeline prefers for its own reasons, not the
one with the lower reading. Picking by the lower reading was measured keeping the
worse model more often than that. The reading separates models that drifted from
models that did not; below that, it is not fine enough to rank.

**Its job is the case that should not happen.** A second solve with a
deliberately different setting is usually the better model, and the pipeline
keeps it. The veto is what stops that preference when the second solve itself
went somewhere wrong — the one failure nothing else in the stack would catch.

## Provenance

Built after a capture solved repeatedly from identical correspondences produced
models an order of magnitude apart against reference geometry, with every
self-reported reading preferring the wrong ones. The design choices, and the three
designs that failed first, are recorded in the adapter's module docstring and in
`sources`.
