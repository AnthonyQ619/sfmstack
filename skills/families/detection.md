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

### 3. Coverage beats count, but only once you supply the denominator

The reasoning is sound: four thousand keypoints on one textured corner reconstruct
that corner; one thousand spread across the frame reconstruct the scene. So
`spatial_coverage` deserves to outrank `keypoints_per_image`, which is a parameter
as much as a result (see §5).

**The number as reported does not carry that reasoning, and on a large class of
captures it inverts it.** Every detector in this family scores coverage the same
way — the fraction of a fixed grid over the whole frame holding at least one
keypoint — which makes it look comparable across detectors. It is comparable only
when the whole frame could hold a keypoint.

*The failure.* On a capture where a large part of the frame is destroyed detail —
a blown-out sweep behind a lit subject, a wall of clipped sky, a sheet of white
paper at exposure — there are cells no detector should occupy. A detector that
spreads its detections evenly across the frame regardless of what is in it
occupies them anyway and scores high. A detector that stayed on the subject scores
low, and is not worse. On a studio-rig capture of a subject against a lit backdrop,
masking the destroyed pixels and recounting by hand showed the classical detector
occupying **every single grid cell that had any content at all** — its reported
number was already at its physical ceiling, which is why four separate parameter
moves each shifted it by a rounding error. The learned detector's much higher
reported number came almost entirely from the destroyed cells, and a measurable
share of its keypoints sat on pixels that were uniform white with near-zero local
variance. **On the question the metric is trying to ask, the two detectors were
tied**, and the reported ratio ranked them backwards by a wide margin.

The mechanism was then confirmed from the other direction on a second capture:
raising the learned detector's score threshold by an order of magnitude removed a
large fraction of its detections and dropped its coverage sharply. Those detections
were weak, and they were exactly what the metric had been rewarding.

*The softer version, which is more common.* The same trap applies wherever the
wanted region is a fraction of the frame even though the rest is not destroyed — a
building facade with a band of loose gravel below it and sky above. There the extra
coverage is genuine, but it is spent on regions the description calls unwanted or
non-repeatable. Banding raw keypoint coordinates against the described regions on
such a capture showed one detector spending roughly three quarters of its budget on
the subject and the other closer to three fifths, while the second scored higher on
coverage. Even-spreading is what the metric rewards and it is not always what you
want.

*What to do.* Before comparing coverage across detectors, or against its healthy
floor, ask what fraction of the frame could hold a repeatable keypoint at all. The
scene description is where that lives — it names the blown backdrop, the empty sky,
the glass. If a large part of the frame is in that state, the number you want is
*occupied cells over cells with content*, and you have to compute it yourself; the
module reports the raw ratio and has no mask parameter. Two consequences worth
knowing without doing any of that work:

- **A coverage number that will not move under any parameter is a ceiling, not a
  failure to tune.** Several independent moves each shifting it by a rounding error
  is the signature, and it means the unreached cells hold nothing to reach.
- **A large coverage gap between a classical and a learned detector on a capture
  with a dead region is evidence about the dead region, not about the detectors.**
  Check where the winner's keypoints landed before believing it.

`keypoints_min` matters for the same reason `min_frame_observations` does later:
the weakest frame is the one that fails to register, and an average cannot see it.
It is published against an absolute floor, which is worth reading as a smoke test
rather than a target — what actually signals trouble is one or two frames sitting
far below the rest of their own set, which the floor does not see and a per-frame
reading does.

### 4. CPU or GPU

Classical detectors are CPU. Learned ones need a GPU and a multi-gigabyte image.
On a large set this is often the deciding constraint rather than a quality
judgement.

### 5. A cap is not a result

Every detector in this family caps detections per image, and every one of them
ships a default low enough that an ordinary capture reaches it. Across a set of
captures each analysed from a standing start, **every single one came back partly
or fully saturated at the module default** — so the first reading of
`keypoints_per_image` measured the parameter rather than the capture, on all of
them.

That makes the first move at this stage not a tuning move at all: raise the cap
until `saturation` reaches zero, then read the count. Four out of five of those
captures settled there and changed nothing else, which is worth saying plainly —
**the common case is that removing the parameter from the measurement is the whole
of the tuning.**

Two things this rule protects you from:

- **`cap_binding` fires on "most images"**, so a capture where a minority of frames
  are pinned raises no diagnostic while its mean is still part parameter and part
  measurement. Treat *any* non-zero `saturation` as "not yet a measurement", not
  just the level that trips the warning.
- **Comparing two detectors while either is saturated compares your two parameter
  choices.** Learned detectors ship much lower defaults than classical ones for
  real reasons — their own suppression has already removed the redundant
  candidates — so a default-versus-default comparison is close to meaningless.
  Match them at a cap neither one binds on.

Raising the cap and finding the count barely moves is itself a result: it says the
ceiling is content rather than the parameter. Raising it again and getting a
byte-identical artifact says so conclusively, and costs one run.

---

## Which end to reach for

**Classical** when the pipeline must run on CPU, when the scene resembles nothing a
network was trained on, or when a predictable failure mode is worth more than a
better average.

**Learned** when the VIEW GRAPH is at risk — this is the measured case and it
outranks everything else on this list. A capture that covers ground quickly
between adjacent frames shares proportionally less between non-adjacent ones, and
an exhaustive view graph is built from those. Run to a sparse model across
fourteen captures, the ones reading highest on `overall_magnitude` /
`high_motion_tail` are exactly the ones whose graph fragments under a classical
detector and a ratio-test matcher — dropping between a quarter and three quarters
of their frames — with a clean gap below them. A learned detector and matcher
restored full or near-full registration on every one, **while finding fewer
keypoints**: it recovers the marginal pairs rather than enriching the good ones.

Also learned when illumination or viewpoint change is large — that is what they
are trained for — and when a learned matcher will follow. Choosing a learned
detector and then matching it with a ratio test discards most of the reason to
have chosen it.

**Ask connectivity FIRST and repetition second.** The two questions have an order
and getting it wrong is expensive: on a fast capture whose subject does not
repeat, the repetition question sends you to the classical detector precisely
where the graph cannot afford it. See `skills/scene_to_pipeline.md` §3b.

Applied cold to captures it had not been fitted on, the ordered pair decided the
detector every time and nothing else came close to deciding it — not texture
density, not the repetition score, not any photometric reading. The repetition
question fired loudly on several of them and correctly changed nothing at this
stage. **Read the per-pair series and not only the median when you ask the first
question.** On the one capture that answered it the other way, the series broke
into a fast stretch and a slow stretch with the break landing exactly where the
description said the camera turned a corner — which converts "this reading
resembles the captures that fragmented" into "this capture's non-adjacent pairs
share little, and here is where that starts". The first is a correlation you are
borrowing; the second is the mechanism, observed.

**And know what you are paying.** On a well-connected capture the learned branch
returned the SMALLEST model of the three on ten of fourteen — its keypoint budget
is capped where a classical detector's is not. Buy it for connectivity and
robustness, not for point count.

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
| **Whether coverage predicts registration** | `spatial_coverage` is asserted to matter more than count, and §3 now establishes that the raw ratio is not even measuring coverage on a capture with a dead region. Correlating a content-masked coverage against downstream `registered_fraction` across scenes is what would establish the underlying claim. The raw one should not be correlated against anything until the denominator is fixed. |
| **Whether descriptors survive to a non-adjacent frame** | The question the detector is actually being chosen for, and structurally unanswerable at this stage: survival is a property of *pairs*, and this stage has none. Every reader who reached it said so independently. Nothing here is a proxy for it — the honest position is that the detector choice is made on connectivity evidence from the motion stage, and confirmed or refuted one stage later by `inlier_ratio` and per-pair match counts. |
