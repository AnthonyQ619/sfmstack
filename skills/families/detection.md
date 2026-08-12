# Feature detection — choosing a detector

Everything that produces `features/v1`. The choice constrains two later stages, so
it is made earlier than it looks.

---

## The axes

### 1. Where the invariance comes from

A **classical** detector (`FeatureDetectionSIFT`, `FeatureDetectionORB`) is
invariant *by construction* — a scale-space pyramid gives scale invariance, a
dominant-orientation assignment gives rotation invariance, and both are properties
of the algorithm rather than of any data it has seen.

A **learned** detector (`FeatureDetectionSuperPoint`, `FeatureDetectionALIKED`) is
invariant *by training*, which means invariant to whatever its training
distribution contained.

The consequence is not that one is better. It is that **they fail differently**.
Classical degrades predictably as a scene leaves its design assumptions — strong
affine distortion, extreme scale change — and the degradation is smooth. Learned
degrades unpredictably as a scene leaves its training distribution, and the
degradation can be a cliff. On an unusual capture, "SIFT will get worse" is a
safer prediction than "the network will generalise".

### 2. The descriptor type decides the matcher

This is the coupling that makes the choice early.

| detector | descriptor | matcher it admits |
| --- | --- | --- |
| ORB | binary | Hamming distance — `FeatureMatchFLANN` with LSH, `FeatureMatchNN` |
| SIFT | float | L2 with a ratio test, or a learned matcher |
| SuperPoint | float, learned | anything; **and LightGlue is trained against it** |
| ALIKED | float, learned | anything; LightGlue has ALIKED weights too |

Picking ORB commits you to Hamming matching. Picking SuperPoint or ALIKED opens
the trained detector/matcher pairs, which is most of their value — a learned
matcher and the detector it was trained against are one system, not two choices.

### 3. Coverage is the metric, not count

`keypoints_per_image` is a parameter as much as a result — every detector here has
a cap. **`spatial_coverage` is the number that predicts whether the pipeline
works.** Four thousand keypoints on one textured corner reconstruct that corner;
one thousand spread across the frame reconstruct the scene.

`keypoints_min` matters for the same reason `min_frame_observations` does later:
the weakest frame is the one that fails to register, and an average cannot see it.

### 4. CPU or GPU

Classical detectors are CPU. Learned ones need a GPU and a multi-gigabyte image.
On a large set this is often the deciding constraint rather than a quality
judgement.

---

## Which end to reach for

**Classical** when the pipeline must run on CPU, when the scene resembles nothing a
network was trained on, or when a predictable failure mode is worth more than a
better average.

**Learned** when illumination or viewpoint change is large — that is what they are
trained for — and when a learned matcher will follow. Choosing SuperPoint and then
matching it with a ratio test discards most of the reason to have chosen it.

**Neither**, when the detector fires on nothing: a textureless, blurred or
low-contrast capture is a case for a detector-free matcher, which skips this stage
entirely. See [matching.md](matching.md).

---

## What has NOT been measured

Nothing in this family has been compared quantitatively here. The axes above are
structural; everything below needs evidence.

| Question | Needs |
| --- | --- |
| **Repeatability under controlled change** | Image pairs with known homographies or ground-truth poses, swept over viewpoint and illumination. HPatches-style, not a reconstruction. |
| **Where the learned cliff is** | Scenes deliberately outside the training distribution — thermal, medical, aerial nadir, synthetic. The claim that learned degrades abruptly is an argument, not a measurement. |
| **ALIKED against SuperPoint** | They are close enough that a preference needs several scenes to be worth anything. |
| **Whether coverage predicts registration** | `spatial_coverage` is asserted to matter more than count. Correlating it against downstream `registered_fraction` across scenes would establish it. |
