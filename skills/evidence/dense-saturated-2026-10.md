# Campaign: dense-saturated-2026-10 — a capture whose sparse model is sound and whose dense result still fails

**This is a raw evidence table. Cite it; do not plan from it.** The rule it supports
lives in [`plan/dense.md`](../plan/dense.md), on reading coverage as the requirement
rather than as a tie-breaker.

## The question

Every dense failure investigated in this series so far traced back to the sparse stage:
drifted poses, a displaced camera, a model the view graph could not justify. The
routing in `plan/dense.md` follows from that — it sends the reader to
[`plan/pose.md`](../plan/pose.md) before choosing a model to densify.

This asks whether that is always where the answer is.

## The capture

**tanks_and_temples/Meetingroom** — `indoor` · `loop-inside-an-enclosure` ·
`no-single-subject` · `low-texture` · `reflective-coherent` · `movers`. A banquet room
photographed from inside it: rows of identical chairs and tables, large flat white
walls and cove-lit ceiling panels that are *wanted structure*, bright window bands, a
few small mirrors and chrome at the room boundary. The camera rotates about fifteen
degrees between frames and coverage means covering a volume rather than orbiting a
subject.

## Three deliveries placed the cloud alike

Across three consecutive batches on three different contexts, the agent delivered
**three different sparse models** — distinct artifact ids, distinct lineages — and
Protocol A read:

| batch | delivered sparse artifact | cameras aligned | Protocol A |
|---|---|---|---|
| first | `art_068a92a7e81a` | 85 of 90 | **101.188 mm** |
| second | `art_c8f852da4a9a` | 85 of 90 | **101.187 mm** |
| third | `art_f3fbba500ec5` | 85 of 90 | **101.189 mm** |

Three independently produced models agreeing to two parts in a hundred thousand. The
reading is not responding to the sparse model at all, because **the capture's dense
result is determined by something the sparse model does not control**. Eighty-five of
ninety cameras align; nothing in the pose stage is failing.

Those three placed the cloud alike; they do not show that no sparse model could do better.
Two later sessions on one context delivered other models of this capture: one gave 91.6 mm,
and one whose cameras sat 2.8% of the span from the reference, with every rotation right,
gave 135.8 ([dense-variance-2026-10](dense-variance-2026-10.md#finding-3--the-spread-follows-which-sparse-model-is-densified-through-its-placement)).
Coverage stayed the dominant failure in both: completeness 122 and 176 mm against accuracy
60 and 96.

## Where it actually fails: coverage, and only coverage

Protocol B on the same capture, our MVS cloud against the three feed-forward evaluation baselines:

| cloud | accuracy (median) | completeness (median) | normal consistency | **coverage** |
|---|---|---|---|---|
| **our MVS cloud** | **0.203** | 0.158 | 0.546 | **0.319** |
| mapanything | 0.331 | 0.284 | 0.565 | 0.990 |
| pi3 | 0.045 | 0.029 | 0.762 | 1.000 |
| vggt | 0.041 | 0.025 | 0.758 | 1.000 |

**Under the dataset's own protocol our cloud is the most accurate of the four; under
this one it is not; under both it covers a third of the surface.** On Protocol A (the
dataset's evaluator, figures in the section below) its accuracy term leads the three
networks by a third. On Protocol B above, which scores every rendered reference pixel,
its median accuracy sits behind two of them, because the stray points in its tail count
here and are cut off there. Where it exists it is not wrong by the dataset's measure; it
does not exist across two thirds of what the reference holds. The flat wanted wall and ceiling panels the description flagged are exactly the
surface MVS declines to reconstruct — a photometric refusal, not a geometric error, and
the coherent reflectors at the room boundary add phantom structure in the background
rather than removing real structure.

## What this capture is promoted to say

**A sound sparse model does not make the dense result the sparse model's fault, and a
reading that does not move when the model changes is not measuring the model.** Before
spending runs on the pose stage for a dense deliverable, check whether the dense
reading responds to the sparse model at all: deliver twice, see whether the number
moves, and read the centre form of the two-estimator reading on both models beside it.
Two numbers that agree say the two models placed the cameras alike, not that no model
could place them better — on this capture a later model placed further out moved the
number by a third, and a better-placed one improved it
([dense-variance-2026-10](dense-variance-2026-10.md#finding-3--the-spread-follows-which-sparse-model-is-densified-through-its-placement)).
When the two deliveries also read alike on the centre form, the sparse stage is not the
constraint. Here they did, and three batches were spent improving a sparse stage that
was never the constraint.

Accuracy beside coverage is the only honest reading of a cloud like this one, and the
protocol has to be named with the accuracy: on the dataset's own term our delivery is
the best of four, on a protocol that scores every reference pixel it is third of four,
and ranked on what it covers it is last by a factor of three either way.

## Beside the networks under both protocols, and what the dense settings move

Added 2026-10-18. The delivered cloud of a later session on this capture (its sparse
model read 1.23 on the centre form, the lowest of that session's candidates), scored
beside the three networks' predictions on the same frames with no agent. The networks
are similarity-aligned to the reference; ours is scored as placed.

| cloud | Protocol A overall (accuracy / completeness), mm | Protocol B robust accuracy / completeness, m | coverage |
| --- | --- | --- | --- |
| our stereo cloud, fusion at 4 | 92.0 (60.5 / 123.6) | 0.099 / 0.099 | 0.37 |
| VGGT | 87.2 (87.5 / 86.8) | 0.064 / 0.037 | 1.00 |
| pi3 | 92.7 (95.5 / 89.9) | 0.059 / 0.033 | 1.00 |
| MapAnything | 217.0 (228.0 / 206.0) | 0.301 / 0.071 | 0.99 |

The protocol decides who is "most accurate": on the dataset's own accuracy term our cloud
leads by a third; on every rendered reference pixel it trails two networks, because the
stray points in its tail count there. On the overall figure the three are inside this
capture's two-session floor of one another
([dense-variance-2026-10](dense-variance-2026-10.md#finding-2--two-sessions-on-one-context-differ-by-a-third-to-double)).

The same sparse model, re-fused and re-run at other dense settings with the stereo
workspace kept, so the sparse model is not a variable:

| setting | Protocol A overall (accuracy / completeness), mm | Protocol B completeness, m | coverage |
| --- | --- | --- | --- |
| fusion at 2 | 78.2 (72.9 / 83.6) | 0.060 | 0.70 |
| fusion at 3 | 86.2 (64.1 / 108.2) | 0.079 | 0.49 |
| fusion at 4, as delivered | 92.0 (60.5 / 123.6) | 0.099 | 0.37 |
| fusion at 5 | 97.7 (58.1 / 137.3) | 0.122 | 0.30 |
| geometric check on, fusion at 4 | 94.8 (53.3 / 136.2) | 0.129 | 0.36 |
| the learned densifier on the same model | 64.8 (79.7 / 50.0) | 0.030 | 0.91 |

Each step down in the fusion threshold buys completeness with accuracy, monotonically,
and no stereo setting reaches the networks' coverage: at 2 the cloud covers 0.70 of the
reference where they cover all of it. The learned densifier on the same sparse model is
a third better overall than the verified cloud at the delivered setting and level with
the networks — the delivery rule's case in `plan/dense.md`, measured on a fixed input
where the dense module's own repeat noise is nil (finding 1 of dense-variance). Fusion
at 2 is not proposed from this: on one of the two rig orbits it was tried on it made the
cloud worse by a fifth, and a rule scoped by capture kind would be post hoc.

## The alignment count is self-referential and must not be compared between models

`tanks_and_temples/Barn`, the other corpus member of this dataset, was going to be
recorded here as a capture whose low alignment count cannot be repaired by dropping
cameras. Re-measuring it found something that matters more: **the count is not a
measure of accuracy at all, and a worse model scores higher on it.**

The robust aligner keeps a camera unless its residual exceeds **both** three times the
kept median **and** an absolute floor. The floor is the only fixed part. So the
effective cutoff is `max(3 × kept median, floor)`, which each model sets for itself —
and a model with a poor kept median is judged against a looser cutoff than a good one.

Three models on the same 90 cameras of this capture, same aligner, same floor:

| model | cameras kept | kept median | the cutoff that produced it | within the floor | within 0.5 m | median | worst |
|---|---:|---:|---:|---:|---:|---:|---:|
| delivered (incremental + global BA) | **36** | 0.032 m | 0.100 m | **36** | 60 | 0.212 m | 1.229 m |
| a feed-forward estimator | **83** | 0.214 m | **0.641 m** | **7** | 80 | 0.227 m | 0.944 m |
| a second feed-forward estimator | 63 | 0.195 m | 0.586 m | 13 | 61 | 0.282 m | 1.526 m |

The estimator "aligns" 83 cameras of 90 against the delivered model's 36, and has **7**
cameras within the floor where the delivered model has 36. Its count is high because
its own residuals are uniformly larger, which widens the cutoff it is then judged
against. **Any plan that targets a number of aligned cameras can be satisfied by making
the model worse.**

Read instead, at one distance you fix yourself: how many cameras fall inside it, the
median, and the worst. Those three say what the count cannot.

**A second place the same trap is set.** The batch's stored `align.residual_m`
describes the **kept** cameras only — median 0.032 m, max 0.080 m for the delivered
model here, every value inside the floor by construction. Read as though it described
the model it says the alignment is excellent while 54 of 90 cameras sit outside the
floor. Neither that field nor `align.cameras` can show the distribution; the fit has to
be re-run for the per-camera residuals, which is why the batch now stores them.

## What the two error shapes are, and why neither is a repair for the other

At a fixed distance the models above do not order each other — they differ in **shape**:

- The delivered incremental model has a **tight core and a long tail**: 36 cameras
  inside the floor, and a worst camera at 1.229 m. That is accumulated drift, and
  `plan/optimization.md` is right that a window which never spans the sequence cannot
  correct it — this model had already had a global solve.
- The feed-forward model is **uniform**: almost nothing inside the floor, 80 of 90
  inside half a metre, and the shortest tail of the three. That is exactly what
  [`plan/pose.md`](../plan/pose.md) already says about this family — no registration
  order, so no drift, but *"whatever the model gets wrong, it gets wrong everywhere at
  once."* The measurement is a confirmation of that sentence, not a new finding.

**So a feed-forward swap is not a repair for drift.** It trades a few very accurate
cameras for many mediocre ones. Which you want depends on the deliverable: a dense
stage scoring completeness wants the uniform model, and one scoring accuracy wants the
tight core. On this capture the delivered cloud read 106.7 mm as placed against
83.7 mm under a best-fit alignment, so most of its placement error is the drift the
similarity could not absorb.

**What was detectable before scoring, and did fire.** Reference geometry is not
reachable from inside the pipeline, so none of the above is a reading an agent has.
The reading it does have is the two-estimator consensus of
[`consensus-2026-09`](consensus-2026-09.md): on this capture the two independent
estimators agreed with each other **4.8× more closely than the delivered model agreed
with either**. That is the shape that file calls the delivered model being the
outlier, and it was already in hand. What no rule then said was what to do about it on
a capture that had registered every camera — the hybrid rule in `plan/pose.md` keys on
a short core, and this core was complete.

## What this campaign does not settle

Why MVS refuses that surface is not measured here — the DTU dense campaign
([dtu-dense-promoted-2026-09](dtu-dense-promoted-2026-09.md)) attributes holes on flat
wanted surfaces to clipped highlights and photometric cost rather than visibility, and
that mechanism is consistent with this capture but was not tested on it.

Nothing here says the sparse stage never matters for dense. Two captures in the same
batch failed squarely on the sparse side. It says only that this capture does not, and
that the question is answerable cheaply before the runs are spent.
