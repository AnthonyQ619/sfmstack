---
module: SparseVerification
module_version: 1.0.0
upstream: none -- numpy, and OpenCV for undistortion only
curated_at: 2026-09-12
sources: 0
---

## Where to go next

This file is the router. The detail lives in the other four documents.

| If | Fetch |
| --- | --- |
| a model was contradicted, or you are choosing between two models | **`limitations`** — starting with "What a contradiction means" |
| a parameter needs moving, or `nothing_held_out` fired | **`tuning`** — 2 parameters documented |
| you are reading the per-pair array | **`artifact`** — the layout of `custom/verification/v1` |
| you want to know where a claim came from | **`sources`** — what was measured, and what rests on nothing |

**First reading on this module's output:** `heldout_residual_px`, then `pairs_verified`.

**Diagnostics it can raise:** `contradicted_by_held_out_evidence`, `nothing_held_out`.

## What this module is for

It asks one question of a finished sparse model: do the matcher's
correspondences that the model never used agree with it?

**You normally do not call it.** The service runs it automatically after every
optimization module that produces a sparse model, wires the model's own matches
from its lineage, and delivers the result as `verification` beside the health
profile. Call it yourself only to verify against *different* evidence — another
matcher's matches of the same scene — or to verify a model that did not come
through an optimization step.

**Why it is a fixed step and not a judgement call.** Every other reading on a
sparse model is computed over what the model kept, and the solve minimised
exactly that. A model that settled into a wrong but self-consistent
configuration therefore passes all of them, and has been measured passing them
*better* than the correct model of the same capture. An agent deciding whether to
verify would be deciding from those same readings.

**How to read it:**

- **Consistent** — the held-out residual sits under the inlier threshold. The
  model does not contradict evidence it was not fit on. That is not a
  certificate of accuracy; see `limitations`.
- **Contradicted** — an error. Solve again from the same inputs before tuning
  anything, and keep the solve that reads clean. Do not pick between the two on
  reprojection error.
- **Unverified** — nothing was held out, so nothing was tested. Supply other
  evidence.

**Prefer something else when** — you want accuracy rather than consistency.
Nothing in an image-only pipeline measures accuracy; this is the closest reading
that a self-consistent wrong model cannot satisfy by construction.

## Provenance

Built after a capture solved repeatedly from identical correspondences produced
models an order of magnitude apart against reference geometry, with every
self-reported reading preferring the wrong ones. The design choices, and the three
designs that failed first, are recorded in the adapter's module docstring and in
`sources`.
