---
module: SceneMotion
module_version: 1.3.0
upstream: ported from scene_agent/breadth_agent/src/agent/core/utility/optical_flow.py
curated_at: 2026-08-14
sources: 5
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 6 parameters documented, starting with `stride` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Planar and rotational degeneracy are the same measurement" |
| you are reading what it wrote | **`artifact`** — the layout of `scene_analysis/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `stride`, `n_pairs`, `fastest_pair`.

**Diagnostics it can raise:** `low_baseline`, `planar_scene`, `pure_rotation`, `uncalibrated_scene`, `flow_fit_failed`.

## What this module is for


Dense optical flow between image pairs, summarised into camera-motion scores and
the two degeneracy tests that decide whether a reconstruction is possible at all.

**The one knob is `stride`.** Flow between two nearly identical frames measures
the sampling rate, not the capture. On dense video every consecutive pair looks
like a low-baseline failure and none of them is. Set `stride` to the spacing the
reconstruction will actually match at — and if `low_baseline_risk` is high on a
video-like capture, raise it before concluding anything.

**Read the degeneracy pair together, in order.** `planar_dominance` says a
homography explains the correspondences at least as well as a fundamental matrix.
That has two causes with opposite prognoses:

| | cause | prognosis |
| --- | --- | --- |
| `pure_rotation_risk` high | the camera turned without translating | **terminal.** No parallax, no structure, no matcher fixes it |
| `pure_rotation_risk` low | a genuine plane viewed from two positions | recoverable, but essential-matrix pose is ill-conditioned |

Separating them needs intrinsics, so on an uncalibrated scene
`pure_rotation_risk` is **omitted rather than guessed** and `planar_dominance`
alone cannot tell you which case you are in.

**This is the same measurement `planarity` makes on `pairwise_matches/v1`**, run
in seconds instead of after a matcher has processed every pair. That is the whole
argument for the module: it is the cheap version of a decision you would
otherwise make expensively and after the fact.

**Displacement is reported raw rather than as a risk fraction.** There was a
`large_motion_risk` here, inherited from the predecessor; it fired on every
benchmark capture measured and was cut on the belief that all of them
reconstruct. **That belief was untested and is false** — run to a sparse model,
the highest-displacement captures drop between a quarter and three quarters of
their frames under a classical detector and ratio-test matcher. The fraction is
not restored, because the raw values carry the same information without a welded
cut point, but do not read its removal as evidence that displacement is harmless.

**`overall_magnitude` and `high_motion_tail` are the most predictive numbers this
module produces.** They measure adjacent-frame overlap, and a capture that covers
ground quickly between neighbours shares less between distant frames — which is
what an exhaustive view graph is built from. A high reading predicts a sparse
graph: plan exhaustive pairing and budget for a learned detector and matcher. See
[limitations.md](limitations.md) and `skills/scene_to_pipeline.md`.

`low_baseline_risk` survives on different grounds: it has never fired, but no
capture in the corpus is a dense video-rate sequence, so it is untested rather
than uninformative.
Both stories are in
[limitations.md](limitations.md#what-the-displacement-thresholds-did-and-did-not-show).

**Cheapest thing that usually works:**

```
defaults, then raise stride if low_baseline_risk is high on a dense capture
```

**Cost:** the cheapest GPU module here. RAFT ships inside torchvision, which the
shared torch base already carries, so the image adds OpenCV and a 20 MB
checkpoint. One forward pass per pair at 640px.

**The other half of the scene** is `SceneTriage` — CPU, no model, fills the
`photometric`, `texture` and `metadata` groups of the same type. Run that one
unconditionally; run this one when the capture geometry is in question.

**Reading the output:** [artifact.md](artifact.md).
