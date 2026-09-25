---
module: PoseMapAnything
module_version: 1.0.0
curated_at: 2026-09-25
---

# Tuning

**The short version: leave all four alone.** This module has no accuracy knobs.
Three of its four parameters trade memory or speed and do not change the answer;
the fourth changes it only by breaking it.

| Parameter | Default | What it actually does |
| --- | --- | --- |
| `max_images_per_pass` | 0 | 0 runs the whole set in one pass. **Leave it.** |
| `memory_efficient_inference` | false | Trades speed for peak GPU memory. Does not change the answer. |
| `amp_dtype` | bf16 | Autocast precision. bf16 is the tested setting. |
| `assume_uniform_scale` | true | How the estimated intrinsics map back to the scene's resolution. |

## `max_images_per_pass` — the one that can break the module

Setting this above 0 splits the set into chunks, and **each chunk gets its own world
frame and its own scale**. This module does not stitch them. A chunked answer is
therefore useless as a second opinion — the comparison needs one frame — which is
why `chunks` above 1 raises an *error* diagnostic rather than a warning.

If a pass does not fit, turn on `memory_efficient_inference` first, and sample fewer
images second. Do not chunk.

## `assume_uniform_scale` — leave true

True matches `preprocess_inputs` as written: an aspect-preserving resize plus a
centre crop. If upstream ever resizes anisotropically, this becomes wrong in the
silent way `PoseVGGT`'s first version was — the focal comes back off by the aspect
ratio and presents as a model/calibration disagreement rather than as a bug. The
symptom to watch for is `estimated_focal_ratio` sitting near the scene's aspect
ratio.

## What to do when the comparison disagrees

Nothing in this module. It has no setting that will make it agree with your model,
and turning one until it does would destroy the only thing it is for. Read
`plan/pose.md`: the disagreement is the output.

## Audit — what these numbers rest on

**Seven healthy bands and every numeric value on this page rest on nothing
measured in a pipeline sweep.** They were carried from `PoseVGGT`, whose bands were
themselves set from isolated testing, and adjusted only where this model's
behaviour is known to differ. Specifically unsourced:

- the `baseline_span` floor of 0.1 and the `registered_images` floor of 3
- `bf16` being the right precision for *this* model rather than for VGGT
- the 90-second and 24 GB figures in `SKILL.md`, which are single-machine
  observations, not a benchmark

The comparison readings this module exists to feed are measured; see `sources.md`.
The parameter advice is not.
