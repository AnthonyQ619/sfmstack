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

**That confirmation is conditional, and the condition is the same one that runs
through this whole section.** Repeated on captures whose empty regions are *flat
rather than destroyed*, the same tenfold threshold removed just as many detections —
around half — and coverage barely moved, a few percent. Those detections were low
in score because the signal is low in amplitude, not because there was no signal:
raise the bar and the cell is still held by whatever survives. So the probe
separates the two cases rather than confirming one of them. **Coverage collapsing
under a raised threshold means the cells were held by nothing. Coverage holding
means they were held by something faint.** Both are useful; only the first is the
trap.

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
*occupied cells over cells with content*, and the module reports the raw ratio and
has no mask parameter.

**Before spending effort on that denominator, know what it can and cannot buy you.**
Nothing in this stack consumes a mask, a region, or a frame exclusion — not the
detectors, not the matchers, not the trackers. So a masked coverage figure can tell
you a reading is a ceiling rather than a shortfall, which stops you tuning against
a number that cannot move; it cannot become an instruction to any module. Treat it
as a reason to stop, as a WATCH line, and as input to the next stage's *choice of
module* — never as work you are going to act on here. Every reader who computed it
found it useful for exactly the first thing and had nowhere to put the rest.

**Computing it is a dozen lines, not a research project**, and this file used to
imply otherwise. Everything needed is already published: the artifact ships raw
keypoint `xy` in scene pixels, and **every detector in this family scores coverage
on an 8×8 grid** — a fact recorded until now only in the individual modules'
`artifact.md`, which is why readers assumed the analysis was out of reach. Bin the
coordinates on that grid and you reproduce the module's own number exactly, which is
the control that tells you your mask is aligned; then divide by the cells that carry
content instead of by 64. Readers who did this reproduced the published metric to
three decimals every time.

**Judge "dead" by cells, not by area — they are not the same thing and the
difference has already flipped a reading.** On a capture where sky filled a third to
a half of every *frame*, masking found under a tenth of the *cells* content-free,
because the sky met the horizon inside cells that also held building. The learned
detector's coverage lead survived masking nearly intact, and the rule as it stood
would have had the reader dismiss a true reading as an artefact. So: mask and
recount before you either believe or dismiss a coverage gap. The inversion needs a
large count of content-free **cells**.

**And it does not need a dead region at all.** The failure was found on captures with
blown backdrops, but it reproduces where the wanted region is merely *harder* than
the rest — on a capture with zero clipped pixels anywhere, the even-spreading
detector still scored higher while spending a smaller share of its budget on the
surface the description called the subject. Even-spreading is what the metric
rewards, and that is not always what you want. The general form: **coverage rewards
reaching everywhere, and you usually want spending where the scene is.**

Four consequences worth knowing without doing any of that work:

- **A coverage number that will not move under any parameter is a ceiling, not a
  failure to tune** — *when the unreached cells are destroyed detail.* Several
  independent moves each shifting it by a rounding error is the signature. Where the
  empty region is flat rather than burnt the number does move, sometimes a great
  deal, and that movement is a positive result about the capture.
- **A large coverage gap between a classical and a learned detector is evidence
  about the dead region, not about the detectors — only once you have confirmed the
  dead region is large in cells.** Check where the winner's keypoints landed.
- **Past roughly 0.99 the metric is exhausted, not healthy.** An 8×8 grid has 64
  states, so differences under about 0.016 are less than one cell per image. Two runs
  or two detectors separated by less than that are not separated. On a well-textured
  capture both branches reach that band under mild tuning and coverage stops being
  able to compare anything.
- **Its healthy floor is a smoke test, not a target.** Observed readings sit far
  above it on everything except a genuinely starved capture, and on the captures
  where the metric is inverted the floor is measuring something other than what it
  thinks. Treat a reading *below* the floor as informative and a reading above it as
  saying almost nothing.

`keypoints_min` matters for the same reason `min_frame_observations` does later:
the weakest frame is the one that fails to register, and an average cannot see it.

**Read it as a ratio against the mean, not against its floor.** The published floor
is absolute and sits orders of magnitude below what an ordinary capture returns, so
it is a smoke test that fires only on a genuinely starved capture — useful when it
does, and silent the rest of the time. What actually signals trouble is one or two
frames sitting far below the rest of *their own set*, and the two published scalars
already give you that: `keypoints_min / keypoints_per_image`. Around 0.7–0.9 is an
even capture. Down near a third means one frame is starved while the mean looks
healthy, and that frame is where a track chain will break.

Two things follow that are worth doing rather than reading:

- **Watch the ratio across a tuning move, not just the mean.** A parameter that
  raises the mean while the ratio falls has spent the budget where it was already
  sufficient. A parameter that raises `keypoints_min` faster than the mean is the
  targeted one, and on a capture with a starved frame that is the move to keep even
  if another buys more total keypoints.
- **The ratio names the frame's cause, with the triage per-frame series.** A frame
  low here that was also low on `density_per_image` is short of content; one low
  here but ordinary there is being rejected by a threshold, which is a parameter
  problem rather than a capture problem.

#### What to DO with this, which the section above did not say

Seven readers reached this analysis, agreed with it, and could not act on it —
because it establishes that the reported number is wrong without saying what to
do instead, and no module consumes a mask. So, plainly:

1. **Never rank two detectors by `spatial_coverage` on a capture with a dead
   region.** That is the comparison it inverts. If the frame is mostly subject,
   the number is fine; if a large part of it is blown backdrop, clipped sky or
   bare wall, the number is measuring how willing a detector is to place
   keypoints on nothing.
2. **Treat a coverage figure that will not move as a CEILING, not a failure.**
   If two or three parameter moves each change it by a rounding error, the
   detector is already occupying every cell with content in it, and further
   tuning toward coverage is spending runs on a number that cannot rise. That
   pattern — a metric flat across a real sweep — is the cheap signal, and it
   costs nothing beyond the sweep you were already running.
3. **Read `min_frame_points` on the finished model instead**, when what you
   actually want to know is whether coverage was adequate. It answers the
   downstream question — is any camera starved of structure — with no denominator
   problem, because it counts points that survived rather than cells that were
   occupied.
4. **Do not hand-build the masked figure unless you are settling a specific
   dispute.** It is a genuine measurement and it is expensive to construct, and
   two readers who built it confirmed a ceiling they could have inferred from
   step 2 in one line.

### 4. CPU or GPU

Classical detectors are CPU. Learned ones need a GPU and a multi-gigabyte image.
On a large set this is often the deciding constraint rather than a quality
judgement.

### 5. A cap is not a result

Every detector in this family caps detections per image, and every one of them
ships a default low enough that most captures reach it. Across seventeen captures
each analysed from a standing start, **the great majority came back partly or fully
saturated at the module default** — so the first reading of `keypoints_per_image`
measured the parameter rather than the capture.

That makes the first move at this stage not a tuning move at all: **raise the cap
until `saturation` reaches zero, then read the count.** On most captures that is
also the last move — a large fraction settle there and change nothing else, so
removing the parameter from the measurement is frequently the whole of the tuning.

**The check belongs to a CONFIGURATION, not to a capture, and any later parameter
that changes candidate supply invalidates it.** It is easy to read this as a
one-time gate cleared at the start of tuning; it is not. Enabling contrast
normalisation on a capture that had already reached `saturation` 0.0 took it
straight back to 0.75, because normalisation manufactures candidates — the reader
caught it only because the number happened to print. Anything that changes how many
candidates exist does this: exposure normalisation, a lower contrast or detection
threshold, a smaller suppression radius, a higher working resolution.

So: **re-read `saturation` after every change, not only the first.** A run that is
saturated is not reporting the capture, whatever it reported an hour ago, and a
count compared across one saturated run and one unsaturated run compares two
different things.

**The check is mandatory; its outcome is not.** A minority of captures arrive at
`saturation` 0.0 already, and on those the raised cap changes nothing —
which is still a result worth one run, because it says the ceiling is content. The
kinds of capture that arrive unsaturated are the ones where something *upstream* of
the cap already binds: a dim or low-contrast capture where the contrast filter cuts
candidates first, a heavily downscaled one with little detail left to find, or a
subject shot tight enough that there is simply not much in frame. On those, raising
the cap is not the move and the tuning file's low-count branch is.

Do not read the majority result as a promise. An earlier version of this section
said *every* capture arrives saturated; the first captures analysed outside the set
that produced that claim included several that did not, and a reader who trusts the
universal wastes a run looking for saturation that is not there — or worse, doubts
a correct reading.

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
ceiling is content rather than the parameter. Raising it again and getting
**identical metrics** says so conclusively, and costs one run.

*Compare the metrics, not the artifact.* An earlier version of this line said "a
byte-identical artifact", which is not a check anyone can perform: ids are derived
from the recipe, so a different parameter always mints a new id even when the
content is the same, and nothing in the tool surface exposes a content hash. Three
readers tried and reported it as unperformable. Identical metrics across a doubled
cap is the observable form of the same fact, and it is enough.

---

> **Before choosing on texture: check the capture does not change camera
> orientation part-way through.** A block of portrait frames among landscape ones
> is invisible to every analysis metric and inverts the advice below, because
> upright-trained learned detectors fail across the break where a
> rotation-invariant classical one does not. `families/matching.md` has the
> signature to look for and what to do.

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
returned the SMALLEST model of the three on ten of fourteen — often by a factor of
two. Buy it for connectivity and robustness, not for point count.

*That is the observation. The mechanism once written beside it was wrong and is
worth naming, because it is a mistake this file warns against elsewhere.* It used to
read "its keypoint budget is capped where a classical detector's is not" — which is
an artefact of comparing each module at its own default cap, exactly what §5 exists
to forbid. Measured at caps neither detector binds on, the learned detector has come
back with substantially **more** keypoints than the classical one on more than one
capture, and with fewer on others; which way it goes depends on whether the
classical detector's contrast filter is starving on a dim or heavily downscaled
capture, not on either module's cap. **A smaller final model is not explained by
fewer keypoints.** The likelier account is what §3b.1 records — the learned branch
recovers marginal *pairs* rather than enriching good ones — but that is an argument,
not a measurement, and it is not settled here.

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
