# Campaign: sparse-pose-2026-09 — does a delivered model's own evidence say whether its poses are right?

**This is a raw evidence table. Cite it; do not plan from it.** The rules these rows
support live in [`plan/pose.md`](../plan/pose.md) on reading a finished model before
delivering it, in [`health/ladder.md`](../health/ladder.md) on what the registration
rung's denominator does on a subsampled capture, and in `SparseVerification`'s
[sources](../../modules/sparse_verification/skills/sources.md) on which of its two
residual readings survives a change of camera.

## The question

[view-graph-support-2026-09](view-graph-support-2026-09.md) fixed the healthy end of
the verifier's reading on nineteen models that were all known to be good, and said
so plainly: *"It is a description of 19 successes, not a discrimination experiment."*
Nothing in this corpus had ever put a **wrong** model in front of it.

This campaign does. Seventy-five captures were driven to a refined sparse model with
no ground truth available to the agent, and the delivered models were then scored
against reference extrinsics. Thirteen came back badly wrong. So for the first time
the verifier's readings can be priced — not "what does a good model read", but "does
any reading separate the good models from the wrong ones, and at what cost in false
alarms".

## Protocol

- **Captures.** Ten views sampled from each of 75 captures across five families —
  three hand-carried visual-inertial datasets (a phone walk, a micro-aerial flight, a
  wide-FOV room rig) and the two benchmark families already in this corpus. All 45
  unordered pairs of each capture are scored. Nineteen of the 75 are corpus members;
  the other 56 were cold.
- **The agent loop.** `harness/PROCEDURE.md`, unchanged, one capture per agent, no
  ground truth reachable. Frozen context at `a955521`.
- **Pose error, pair-wise and gauge-free.** Relative rotation is gauge-free; relative
  translation is gauge-free in direction only. `pose_error = max(rotation error,
  translation direction error)` in degrees, and `AUC@t` is the normalised area under
  the cumulative curve to `t` degrees. A pair touching a camera the model never
  registered is charged as a miss over all 45 pairs, because the feed-forward arms
  compared against always answer all 45.
- **Frames.** One family ships body-frame ground truth; its metric composes the
  camera-to-body rotation only and drops the lever arm, which is unrecoverable from
  scale-free estimates. Rotation error is exactly identical in either frame; only
  translation moves. The other four are camera-frame and take the ordinary path.
  Each family's pose convention was **measured** from its own pixels rather than read
  off its metadata, because a constant body-to-camera offset preserves a relative
  rotation's angle exactly and moves only its axis — no angle-based check can catch
  it. See [lmdata's under-declared conventions](EVIDENCE.md) for the same hazard
  caught the other way.
- **The verifier readings.** `SparseVerification` was then run over all 75 delivered
  models at uniform defaults, from the stored artifacts. Nothing was re-solved. No
  ground truth enters that reading; reference extrinsics enter only as the label.

## What the five families delivered

Pooled over every pair, with three feed-forward pose estimators run over the
identical frames as reference arms.

| family | n | mean reg /10 | arm | AUC@3 | AUC@5 | AUC@10 | AUC@30 |
|---|---|---|---|---|---|---|---|
| phone walk | 23 | 4.1 | **agent** | **0.0044** | 0.0090 | 0.0201 | 0.0669 |
| | | 10.0 | best feed-forward | 0.0086 | 0.0208 | 0.0473 | 0.1349 |
| aerial flight | 11 | 8.8 | **agent** | **0.2165** | **0.3121** | 0.4241 | 0.5194 |
| | | 10.0 | best feed-forward | 0.1494 | 0.2899 | 0.5085 | 0.7569 |
| room rig | 6 | 8.7 | **agent** | **0.1201** | 0.2468 | 0.3721 | 0.5153 |
| | | 10.0 | best feed-forward | 0.1046 | 0.3076 | 0.6095 | 0.8661 |
| studio orbits | 22 | 10.0 | **agent** | **0.7310** | **0.8350** | **0.9129** | 0.9649 |
| | | 10.0 | best feed-forward | 0.6914 | 0.8149 | 0.9074 | 0.9691 |
| site walks | 13 | 9.5 | **agent** | **0.6744** | **0.7083** | **0.7380** | 0.7734 |
| | | 10.0 | best feed-forward | 0.3088 | 0.4377 | 0.6010 | 0.7949 |

**The shape to carry: the agent wins at the tight threshold and loses at the loose
one, on four families out of five.** Where the geometry is there, the geometric
chain places cameras more precisely than anything that estimates them in one shot;
where it is not, it declines to place them at all and is charged for every pair it
left unanswered. That is the same trade [`plan/pose.md`](../plan/pose.md) already
records from seven stalled captures, measured here across a much wider set.

**Corpus and holdout.** On the studio orbits the split is trustworthy and the context
generalises: ten corpus scans mean 0.9722 at @30 against twelve holdouts at 0.9589,
identical median rotation error. On the site walks the split is **confounded and
must not be quoted** — the nine corpus members read 0.6773 and the four holdouts
0.9898, because the holdouts are the easier scenes, not because cold captures do
better.

## The headline: the veto is denominated in the wrong unit

`SparseVerification`'s veto is `heldout_residual_px`, banded at the pose estimator's
inlier threshold. Its own [sources](../../modules/sparse_verification/skills/sources.md)
file states the risk and that nothing had tested it: *"Nothing has been swept across
focal lengths."* These 75 captures sweep it, over a **15× range** of median focal
length — from a wide-FOV room camera at the low end to a studio rig at the high end.

Thirteen delivered models are wrong by more than ten degrees of median rotation.

| reading | catches (of 13) | false alarms (of 62) |
|---|---|---|
| the published px veto, at its default | **2** | 0 |
| the same residual as an angle, at 1.5 mrad | 11 | 11 |
| + `supported_second_size ≥ 1` | 12 | 13 |
| + `nothing_held_out` counted as unverified | **13** | 17 |

**The px veto missed eleven of thirteen wrong models, and it missed them in a
pattern.** Every one of the models it missed came from a short-focal camera, where a
fixed pixel tolerance is a much larger angle. At the low end of this range the
default veto is roughly fifteen milliradians of slack; at the high end it is about
one. The two it did catch are the two whose residual was large in *both* units.

This is the second time this corpus has found a scale-dependent statistic behaving
this way, and the first time is the direct precedent:
[view-graph-support-2026-09](view-graph-support-2026-09.md) withdrew
`supported_largest_share` in favour of `supported_second_size` because a share moves
with the camera count and penalises a small capture for its size. A pixel residual
moves with the focal length and forgives a wide-angle capture for its optics. Same
defect, different axis.

**What this does not license.** The angular reading at any ceiling tight enough to
catch these models also fails roughly one good model in five. It is a reason to look
again, not a veto, and the module's existing judgement — that no mrad band belongs on
the metric — is *correct as a band* and is left alone. What changes is that the
reading is now known to carry the signal the px veto loses, which is a different
claim from "it should replace the veto".

**Correlation, for what it is worth.** Across the 70 models with a residual at all,
the angular residual correlates **+0.72** with the log of delivered median rotation
error (+0.77 in log-log). That is the strongest single discriminator found anywhere
in this campaign, and it is still only a correlation over a mixed population.

## The thirteen wrong models

| capture | family | reg /10 | median rot | mrad | 2nd comp | what the module said |
|---|---|---|---|---|---|---|
| advio-02 | phone walk | 3 | 64.3° | 7.34 | 0 | contradicted — the one clean catch |
| advio-04 | phone walk | 3 | 35.1° | 2.94 | 0 | contradicted |
| advio-05 | phone walk | 3 | 86.6° | 2.61 | 0 | silent |
| advio-06 | phone walk | 2 | 153.4° | — | 0 | `nothing_held_out` — unverifiable |
| advio-10 | phone walk | 9 | 68.0° | 2.20 | 1 | silent on the residual; the graph reading fires |
| advio-19 | phone walk | 5 | 11.0° | 1.95 | 1 | silent on the residual; the graph reading fires |
| advio-23 | phone walk | 2 | 69.0° | 2.39 | 0 | silent |
| V1_03_difficult | aerial | 7 | 17.6° | 4.90 | 0 | silent |
| V2_01_easy | aerial | 10 | 106.4° | 1.80 | 1 | silent — **and every other rung passed** |
| V2_03_difficult | aerial | 10 | 79.0° | 1.87 | 1 | silent |
| room2 | room rig | 10 | 14.0° | 1.54 | 1 | silent |
| room3 | room rig | 8 | 34.0° | 1.99 | 0 | silent |
| office | site walk | 10 | 24.3° | 1.37 | 1 | silent on the residual; the graph reading fires |

**Six of the thirteen registered eight cameras or more**, so the registration rung
cleared them. `V2_01_easy` is the sharpest case in the campaign and is now a corpus
member for that reason: a global reconstructor placed all ten cameras, every health
rung read healthy, the module reported *consistent* against its own px band, and the
model is a hundred and six degrees wrong.

**Every one of the thirteen had a verifier reading, and eleven of them read
`consistent`.** The service runs the module itself after the optimization stage, so
a verdict comes back whether the driving agent asks for one or not, and all thirteen
reports quote one. Only thirty of the seventy-five agents additionally invoked it by
hand, but that number describes initiative, not coverage, and nothing rests on it.

Three of those verdicts are worth quoting, because together they show the veto
failing in three different ways:

- a phone-walk capture wrong by 86.6° read **2.91 px against a 3.0 px threshold** —
  inside the band by a margin thinner than any tuning could recover, at 2.61 mrad;
- a site walk wrong by 24.3° read 1.21 px and passed outright;
- the aerial capture wrong by 106.4° read 0.787 px, and **its own agent performed the
  angular conversion in its report** — writing that 0.83 px at a focal length near
  458 px is about 1.8 mrad and that this was "outside a long-lens corpus" — and
  delivered the model anyway.

That last one is the campaign's most useful single observation. The information was
not missing, was not unreachable, and was not even unnoticed. The reading that
carried it had no band to be outside of, the reading that had a band was silent, and
nothing said which to believe. **The problem this evidence supports is a unit and a
missing instruction, not an omitted step.**

## Support as a trigger, and why it was rejected

An earlier form of this rule used the view graph rather than the verifier: take the
largest connected component of pairs carrying at least a floor of geometrically
verified matches, call that `support`, and distrust a model that registered more
cameras than `support` allows.

It fires correctly on the over-registered failures. It also fires on **the two best
captures in the whole campaign** — two interior walks of a shallow relief that read
support 6 and 7 of 10, registered all ten, and delivered 0.997 and 0.998 at @30 with
median rotation error under a tenth of a degree. A trigger whose false alarms are the
two best models in the set is not usable.

The failure is the one this corpus keeps finding: **a match-count floor is an
absolute count**, and across these families the median verified matches per pair
spans from roughly twenty on a subsampled indoor walk to several hundred on a studio
orbit. On the studio family the floor never binds at all, which happens to be correct
behaviour there, and on the site walks it binds on captures that did not need it.

The verifier's angular residual has no such dependence and stays silent on both
relief walks (0.17 and 0.06 mrad). **Support was dropped; the verifier reading
replaced it.** The over-registration correlation that motivated support is real
(0.42 against log rotation error) but it is weaker than the verifier's 0.72 and it
cannot be made scale-free.

## What to do when the reading fires

Seven captures — five over-registered and two deliberate false alarms — were re-run
with the pose stage instructed differently. Prompt-level only; nothing in `skills/`
was touched for these runs.

| arm | AUC@3 | AUC@5 | AUC@10 | AUC@30 |
|---|---|---|---|---|
| as delivered | 0.1258 | 0.2005 | 0.2774 | 0.3674 |
| stop at what the graph supports | 0.1406 | 0.2008 | 0.2709 | 0.3454 |
| fill the rest feed-forward, then refine everything | 0.1263 | 0.1959 | 0.3179 | 0.5123 |
| **fill the rest feed-forward, refine the core only** | **0.1282** | **0.2233** | **0.4007** | **0.6695** |
| the feed-forward estimator alone | 0.1147 | 0.2264 | 0.4038 | 0.6671 |

**Stopping at what the graph supports is not the answer.** It improves accuracy on
every capture it touches and loses overall, because the pairs it declines to answer
are charged. Registering fewer cameras more accurately is a trade, not a fix.

**The hybrid is, and one detail decides it.** All seven agents reached a feed-forward
pose module unprompted, and all seven reached full registration; median rotation
error over the seven fell from 34.0° to 3.7°. But refining the combined model gave
most of it back. Split by which cameras a pair touches:

| pairs touching | after joint refinement | left at the feed-forward estimate |
|---|---|---|
| the geometric core | improved on all seven | — |
| a filled camera | median 12.77°, a third worse than 30° | median 4.73°, a fourteenth worse than 30° |

**Bundle adjustment helps the core and destroys the fill**, and the mechanism is
plain: it drags the filled cameras using exactly the correspondences that were too
thin to register them in the first place. This corrects a claim made when the
experiment was designed — that refinement would leave weakly-supported cameras near
their feed-forward estimate. It does not.

**The alignment is not the expensive part.** Fitting a similarity from the
feed-forward frame into the core's frame and scoring one consistent model costs
1.4% at @30 against scoring each pair from whichever model holds it, and *gains* at
@3 and @5, because a mixed pair then has the accurate core on one side. All seven had
four to nine shared cameras, so the fit was well conditioned throughout.

**And the counter-example matters as much as the rule.** One of the two controls —
a wide-FOV room capture that the verifier flags at 2.87 mrad with a stray second
component — was **already good** at 2.27° and 0.712, and the hybrid made it worse
(0.491). The reading fires there and acting on it costs. That capture is the second
of this campaign's two corpus promotions, and it is there to stop the rule
generalising into "always reach for feed-forward."

## The dense path: tested, and it does not transfer

The dense procedure makes the refined sparse model part of the dense deliverable, and
the cloud is unprojected through exactly those poses, so the mechanism says this
reading should matter there too. It was run over the sparse model behind every
delivered cloud in the two finished dense campaigns whose artifact stores are still
intact — thirty-five captures. The other two dense campaigns had their stores pruned
after they were scored, so their delivered models can no longer be re-read at all.
That is a housekeeping fact about one machine rather than a property of those
captures, and it means the reading below rests on the two benchmark families only.

| batch | n | corr(residual, dense accuracy) | corr(residual, pose AUC@30) |
|---|---|---|---|
| studio orbits, dense | 22 | **+0.07** | +0.07 |
| site walks, dense | 13 | −0.28 | −0.74 |

**No predictive power on the studio orbits, and the wrong sign on the site walks.**
The gate would have fired on two of the thirty-five, both of which delivered good
clouds. The five *worst* dense accuracies in the studio batch all read clean, an
order of magnitude inside any interesting ceiling. The site walks' −0.74 against pose
AUC is on thirteen points and is read here as small-sample noise, not as an inverse
relationship.

**Why, and this is the part that generalises.** Both readable dense batches ran on
families whose captures have dense overlap — the same two families where this
reading was silent on the sparse path as well, correctly, because nothing went wrong
there. A discriminator cannot be measured on a population with no failures in it.
This is the same limitation [view-graph-support-2026-09](view-graph-support-2026-09.md)
recorded about itself, recurring one campaign later.

**The condition under which this must be revisited.** The dense evidence above is
drawn entirely from captures with dense overlap and full registration. It is not
evidence that the reading is uninformative on the dense path; it is evidence that the
dense path has not yet been run anywhere the reading could say anything. **If a dense
reconstruction is ever driven on a thin capture — a subsampled walk, an unordered set
whose pairs mostly share nothing, or any capture where the sparse stage registers
short of the frames it was given — the mechanism argument applies again in full and
this measurement does not cover it.** On such a capture the reading should be taken
and recorded, and this campaign file extended with what it read, before anyone
concludes either way. The three visual-inertial families in this campaign are exactly
that kind of capture and none of them has been driven to a dense cloud.

The module already runs on both paths — it is a fixed step after the final bundle
adjustment, on every model — so nothing here is about whether the reading is
produced. It is about whether to act on it. Until a thin capture is driven to a dense
cloud, **act on it on the sparse path and merely record it on the dense one**, and
the reason is measured rather than assumed.

## What is not established here

- **Precision.** At any ceiling that catches these models the reading also fails
  about one good model in five. It is a reason to look again and never a discard.
  Two of the campaign's most accurate models are among its false alarms.
- **The ceiling itself.** Nothing here fits one. The figures quoted are readings from
  a population that contains thirteen failures, not a threshold with a stopping rule
  behind it, and a different family's optics would move them.
- **Consistency, not accuracy** — the limit the residual has always carried. A model
  wrong in a way every one of its own correspondences allows is invisible to it. The
  shallow-relief captures in this campaign are exactly where that blind spot lives,
  and it is why they read clean while being genuinely excellent: this reading cannot
  tell those two cases apart by itself.
- **The feed-forward arms are not a controlled comparison of estimators.** They ran
  at their own native input handling rather than the pipeline's working resolution,
  and letterboxing against resizing alone moves them by several degrees on these
  captures. They are here as a reference level, not as a ranking of models.
- **One draw each.** Every row is a single agent session. The caution at the foot of
  [EVIDENCE.md](EVIDENCE.md) applies in full, and it applies hardest to the thirteen:
  a capture solved seven times from one recipe has produced models an order of
  magnitude apart.
