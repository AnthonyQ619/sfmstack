# Campaign: consensus-2026-09 — can two correspondence-free estimators catch a model its own evidence cannot?

**This is a raw evidence table. Cite it; do not plan from it.** The rule these rows
support lives in [`plan/pose.md`](../plan/pose.md), in the section on readings built
on the model's own evidence, and in [`health/bounce.md`](../health/bounce.md) on
ruling out the reference before a stuck pose-agreement rung is read as a defect.

## The question

[sparse-pose-2026-09](sparse-pose-2026-09.md) priced the verifier's readings against
thirteen known-wrong models and found the angular residual carried most of the
signal. It also recorded what none of those readings reach: a model whose
correspondences are wrong in a globally consistent way satisfies every one of them.
Registration is full, held-out correspondences verify, two different matchers agree
with each other — and the delivery is metres out. Every reading in that campaign is
computed from correspondences, so none of them can see this.

This campaign asks whether something that never saw the correspondences can.

## What was run

Thirty-five captures across three families, each already delivered by the agentic
pipeline and scored against reference geometry. For each, two correspondence-free
estimators were run from the scene alone — `PoseVGGT` and `PoseMapAnything`, neither
conditioned on any pose, intrinsic or depth — and camera centres were compared by
similarity fit, so each estimator's own frame and scale drop out.

Three numbers per capture: how far the two estimators sit from **each other**
(`spread`), how far the delivered model sits from them (`ours`, the median of the
two), and the **ratio** of the second to the first.

Nothing outside the agent's reach enters the reading. The evaluation arms that score
these batches were deliberately *not* used: the agent cannot run them, and they are
the baselines it is measured against, so a delivery decision taken on them would be
circular. An earlier version of this check did use them and was discarded for that
reason.

## The result

"True" below means the feed-forward branch, run through to a cloud, actually
improved the delivered result when measured.

| configuration | fires | true | false | missed |
| --- | --- | --- | --- | --- |
| one estimator (VGGT), raw disagreement | 6 | 4 | **2** | 1 |
| one estimator (MapAnything), raw disagreement | 7 | 4 | **3** | 1 |
| **both, disagreement over spread** | 6 | **5** | **1** | **0** |

The single-estimator rows are shown at the threshold most favourable to them; the
counts do not improve at any other.

**Two mechanisms, and the second is the one that is easy to miss.**

The first is that a single estimator condemns captures where the *estimator* is the
outlier. On one capture the delivered model sat far from VGGT and very close to
MapAnything; a VGGT-only check condemns it, and it is the most accurate
reconstruction in its batch. Two captures in another family show the same shape with
the estimators exchanged. In all three the two estimators sit about as far from each
other as either sits from the model, so the ratio reads low and nothing fires.

The second is that a single estimator **misses** captures whose disagreement is
small in absolute terms. On the capture promoted below, the model sits only a few
per cent from each estimator — too little to trip any absolute threshold — while the
two estimators sit a fraction of that from each other. Against their own agreement
the model is the outlier by a wide margin, and only the ratio expresses it.

The fire set is unchanged anywhere across a wide band of thresholds: the weakest
capture that fires and the strongest that stays quiet are separated by more than a
factor of three, so nothing here rests on where a cut was placed.

## The false positive, which is not a false reading

One capture fires and should not be acted on: a vegetated exterior where the two
estimators agree tightly and both disagree with the delivered model by a wide margin.

**The reading is correct.** Those poses are the worst in their batch against
reference extrinsics, by a clear margin over the next worst. What is wrong is the
step from there to a swap: the delivered cloud beats the feed-forward branch on both
accuracy and completeness, because dense vegetation is outside the training
distribution of the learned dense path as well. The two estimators are independent of
the matcher; they are not independent of each other.

**Four candidate cautions were tested against this capture and all four fail**, each
because a capture where the swap genuinely helps looks the same or more extreme:

| candidate | behaviour |
| --- | --- |
| how concentrated the disagreement is across cameras | the flattest true positive is flatter |
| camera spread over scene depth | a true positive sits highest, a quiet capture just below it |
| how much of the gap one anisotropic scale absorbs | the true positive absorbs the most |
| the two estimators' disagreement about focal length | a quiet, accurate capture reads higher |

This is recorded as a negative result rather than resolved. The rule in
`plan/pose.md` handles it structurally instead: the fire opens a measurement, not a
swap, so this capture costs one run and loses nothing.

## The capture promoted to the corpus

`/TT/Barn` — an outdoor structure, ninety images, fully registered, delivered by the
pipeline without any reading firing.

It is promoted because it is the capture that **neither estimator catches alone at
any threshold**, and only the ratio finds. That makes it the worked example of why
the reading is built the way it is, rather than a capture that any formulation would
have caught. The feed-forward branch, measured, is the better delivery on it.

The remaining six captures in its family stay holdout and are not listed here.

## What this does not establish

- **Nothing about the sparse path.** The same check was run there and is not carried
  into guidance: it is unavailable on captures registering too few cameras, and on
  two of the captures it could read, the estimators disagreed with each other enough
  that no ratio was meaningful. It caught two bad models and raised one false alarm
  among the good. That is not a strong enough showing to cite.
- **Nothing about a third estimator.** Two is what was measured. Whether a third
  reduces the correlated-failure case above is untested, and the vegetated capture is
  a reason to doubt that more models from the same family would help.
- **Nothing about where to cut.** The band is quoted as a separation, not a
  threshold, and deliberately: three families is not enough to fit one.
