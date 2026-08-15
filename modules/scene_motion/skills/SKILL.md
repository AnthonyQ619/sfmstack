---
module: SceneMotion
module_version: 1.0.0
upstream: ported from scene_agent/breadth_agent/src/agent/core/utility/optical_flow.py
curated_at: 2026-08-14
sources: 5
---

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

**Displacement is not reported as a risk, on purpose.** There was a
`large_motion_risk` here, inherited from the predecessor; it read 0.82–1.00 on all
ten benchmark scenes measured, every one of which reconstructs, and it was cut.
Displacement is a weak proxy for matching difficulty — a rotation-invariant
descriptor does not care how far a point moved, it cares how much the view
changed. **Read `high_motion_tail` corroborated by `rotation_median_deg`.**

`low_baseline_risk` survives on different grounds: it read 0.00 on all ten, but
none of the ten is a dense capture, so it is untested rather than uninformative.
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
