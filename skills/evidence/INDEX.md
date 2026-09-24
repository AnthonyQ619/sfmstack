# Worked Runs — Index

**Has a capture like mine been solved before, and what solved it?** That is the
only question this file answers. One row per worked capture, keyed on what the
capture *is* rather than on what it measured, with a link to the evidence for
each.

**There are no measurements in this file, by design.** Not one point count, not
one error, not one threshold. Every row's numbers are one hop away in
[EVIDENCE.md](EVIDENCE.md)'s campaign files, and the split is deliberate — see
[Where the raw numbers live](#where-the-raw-numbers-live). A row tells you what
shape of pipeline solved a capture like yours and what the decisive move was; it
does not tell you what reading to expect, because a reading that transfers by
value is exactly the thing this corpus has been wrong about before.

---

## Read this before matching a row

**A row is a precedent to follow, never a plan to copy.** Two captures that match
on every trait below can still need different pipelines: the traits describe what
a reader can see, and a reconstruction is decided by things no one can see until
they run it.

**Check whether your capture is one of these rows first.** Every row here is a
member of [CORPUS.txt](CORPUS.txt), and `sfm_plan_brief` reports
`in_planning_corpus` for exactly this reason. If it says your capture is a member,
then finding "the row like mine" is not retrieval — you have been handed your own
answer key, including the pipeline that was chosen for it and the branches that
were rejected. That is worth strictly less than a row matched from outside the
corpus, and a plan built on it should say so. This caution is stronger here than
the one on the range tables in `plan/`: there, a corpus member recognises its own
*reading*; here, it recognises its own *answer*.

**A capture from the same source as a row is not a cold match either.** Another
scan off the same rig, or another walk around the same campus, will match a row on
nearly every trait and will do so legitimately — that is within-family
generalisation and it is a real result. It is still not evidence that the traits
transfer to a capture from somewhere else, which has been tested on very little.

---

## The trait vocabulary

**Fixed and closed.** Traits are recorded from the reading a
[`SceneDescription`](../../modules/scene_description/skills/SKILL.md) produces —
what someone looked at and graded — and never from thresholding a measured
number. That is a deliberate choice and the reason this file was empty for so
long: the original design derived traits by cutting `scene_analysis/v1` numbers
at thresholds held in the global tier, and those thresholds do not exist because
the evidence does not support naming them. The one connectivity cut point that
was published was withdrawn after it failed a refit on full captures. A category
someone can see can be wrong, but it cannot drift as the corpus grows, which is
what makes it usable as a retrieval key.

To place your own capture in this vocabulary, run `SceneDescription` and read its
report — the same two-call flow that produced every row here.

| Group | Values | Read from |
| --- | --- | --- |
| **Setting** | `studio-rig` · `built-interior` · `built-exterior` · `vegetated-exterior` | `environment`, plus what the frames show |
| **Capture shape** | `orbit-of-an-object` · `walk-along-a-frontage` · `loop-inside-an-enclosure` · `traverse-along-an-axis` · `wander-around-a-site` | the browse set end to end |
| **Subject** | `single-object` · `no-single-subject` · `subject-cropped` | `main_subject`, `subject_completeness` |
| **Target surface** | `target-textured` · `target-low-texture` · `target-repeats-in-one-direction` | `empty_regions`, and whether the flat area is wanted |
| **Repetition** | `repeated-pattern` · `repeated-parts` | the two halves of `repetition_notes` |
| **Hazards** | `coherent-reflector` · `diffuse-reflector` · `movers` · `flare` · `backdrop-clipped` · `target-underexposed` | `material_hazards`, `hazard_position`, `dynamic_content`, `notes` |

Two of these carry more weight than their length suggests. **`target-low-texture`
is not the same as a low texture reading**: it says the flat region is the thing
being reconstructed rather than a backdrop, and that distinction changes what to
do without changing any number. **`repeated-pattern` and `repeated-parts` have
opposite escapes** — scale and a wider descriptor support separate a pattern and
can never separate two castings of one mould — which is why they are two traits
and not one.

---

## The outcome vocabulary

**Fixed and closed**, and chosen so that the outcome column *routes the reader*
rather than merely recording what happened. Each value names the move that
separated the kept model from the best alternative that failed.

| Outcome | What it means | What it tells you to do |
| --- | --- | --- |
| `density-decided` | Every branch tried registered the whole capture. The choice between them was about how much structure came back, not whether the capture was solved. | Your capture is probably not at risk. Compare finished models by the procedure in [ladder](../health/ladder.md#comparing-two-finished-models) and stop; do not go looking for a rescue you do not need. |
| `matcher-decided` | Registration was rescued by changing the matching stage — a ratio test to a joint matcher, or either to a detector-free one. | If a capture of this kind is fragmenting, change the matcher before the detector. On repeated parts especially, a better detector makes the wrong match *more* confident. See [matching](../plan/matching.md). |
| `reconstructor-decided` | Registration was rescued by changing which module produced the poses — seed-and-grow to a global reconstructor. | Stop tuning seed-and-grow. If `graph_components` is 1 and registration is still short, the failure may be the growth strategy itself. `sfm_find_alternatives(produces='sparse_model/v1', consumes='pairwise_matches/v1')`. See [pose](../plan/pose.md). |
| `resolution-decided` | Registration was rescued by working resolution or by detection preprocessing, with the module set unchanged. | Before swapping modules, check what the loader is feeding them. More failures trace to loader parameters than to any module — see [swap_or_build](../judge/swap_or_build.md#when-to-build). |
| `profile-misled` | A branch registered the whole capture, the health profile selected it, and reference geometry says a rejected branch was far better. | **Read this row before trusting a profile-based choice on a capture like yours.** The profile is an ordering over models, not a measurement of correctness, and this is where it is known to fail. |
| `unsolved` | No branch registered the capture. | Rule out the three cheaper answers, then check whether the registry has the shape the problem needs at all: a capability query coming back empty is the signal to build. See [swap_or_build](../judge/swap_or_build.md#when-to-build). |

**Two of these six have no rows**, which is worth saying plainly because an
empty category is easy to mistake for an impossible one.

`unsolved` is empty because every capture here was solved by something already in
the registry. Nothing here has yet demanded a
module that does not exist, so this file cannot show you what that looks like —
only `swap_or_build.md` can, and it says the signal is an empty capability query
and not a run of bad results.

`resolution-decided` is empty for a different and less satisfying reason: the
outcome column holds one value, and on the one capture where working resolution
*did* decide registration, something more consequential happened afterwards and
took the column. That capture is the `profile-misled` row, and raising its
working resolution is what got it fully registered in the first place. So the
absence of this value is an artefact of one row having two stories, not evidence
that resolution never decides anything — `judge/swap_or_build.md` records that
more failures trace to loader parameters than to any module.

---

## The rows

Shipped pipeline per capture, with the branches that were tried and rejected.
`→` reads as the stage order. Link each row to its measurements through the
capture name.

| Capture | Setting · shape | Subject | Surface & repetition | Hazards | Shipped pipeline | Rejected | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [DTU/scan1](agentic-campaign-2026-09.md#cap-dtu-scan1) | `studio-rig` · `orbit-of-an-object` | `single-object` | `target-textured` · `repeated-parts` | `diffuse-reflector` `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan4](agentic-campaign-2026-09.md#cap-dtu-scan4) | `studio-rig` · `orbit-of-an-object` | `single-object` | `target-textured` · `repeated-pattern` `repeated-parts` | `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan9](agentic-campaign-2026-09.md#cap-dtu-scan9) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-textured` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan10](agentic-campaign-2026-09.md#cap-dtu-scan10) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-textured` | `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (short of the full capture) | `matcher-decided` |
| [DTU/scan15](agentic-campaign-2026-09.md#cap-dtu-scan15) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-textured` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan23](agentic-campaign-2026-09.md#cap-dtu-scan23) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-textured` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan33](agentic-campaign-2026-09.md#cap-dtu-scan33) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-textured` · `repeated-parts` | `coherent-reflector` `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan48](dtu-dense-promoted-2026-09.md#scan48--the-cheap-chain-does-not-always-register-a-rig-orbit) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-flat` · `repeated-pattern` | `coherent-reflector` `backdrop-clipped` | SIFT+CLAHE → NN → **global** → BA | incremental, on either matcher (short of the capture) | `reconstructor-decided` |
| [DTU/scan75](dtu-dense-promoted-2026-09.md#scan75--a-clean-captures-track-conflict-can-be-thirty-times-the-documented-ceiling) | `studio-rig` · `orbit-of-an-object` | `multi-object` `subject-cropped` | `target-flat` · `no-repetition` | `diffuse-reflector` `backdrop-clipped` | SIFT → NN → union-find → incremental → triangulate → BA | SIFT → LightGlue (same shape) | `density-decided` |
| [DTU/scan77](dtu-dense-promoted-2026-09.md#scan77--a-named-escape-route-that-cannot-be-reached-and-a-health-band-that-misreads) | `studio-rig` · `orbit-of-an-object` | `single-object` `subject-cropped` | `target-flat` · `repeated-parts` | `specular-metal` `backdrop-clipped` | SIFT → **LightGlue** → global → BA | SIFT → NN (weaker model, both registered) | `density-decided` |
| [ETH/courtyard](agentic-campaign-2026-09.md#cap-eth-courtyard) | `built-exterior` · `loop-inside-an-enclosure` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `coherent-reflector` `movers` | SIFT → LightGlue → union-find → incremental → triangulate → BA | SIFT → NN (same registration, far worse against truth) | `density-decided` |
| [ETH/delivery_area](agentic-campaign-2026-09.md#cap-eth-delivery-area) | `built-interior` · `traverse-along-an-axis` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` `movers` | SIFT+CLAHE → LightGlue → union-find → incremental → n-view triangulation → BA | the same chain at lower resolution; SIFT into pairwise triangulation with a ratio-test matcher and with a joint one | `density-decided` |
| [ETH/electro](agentic-campaign-2026-09.md#cap-eth-electro) | `built-exterior` · `wander-around-a-site` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `coherent-reflector` `movers` | RoMa (detector-free, outdoor weights) → union-find → incremental → triangulate → BA, re-solved at a wider window | SIFT → LightGlue and SIFT → NN, both far short; LoFTR and SuperPoint+SuperGlue short | `matcher-decided` |
| [ETH/facade](agentic-campaign-2026-09.md#cap-eth-facade) | `built-exterior` · `walk-along-a-frontage` | `single-object` `subject-cropped` | `target-textured` · `repeated-pattern` `repeated-parts` | `coherent-reflector` `movers` | SIFT → LightGlue → global reconstructor → BA | the same detector and matcher into seed-and-grow; and SIFT with a ratio-test matcher into seed-and-grow at both resolutions | `reconstructor-decided` |
| [ETH/kicker](agentic-campaign-2026-09.md#cap-eth-kicker) | `built-interior` · `traverse-along-an-axis` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` | SIFT+CLAHE → LightGlue → global reconstructor → BA | seed-and-grow with and without CLAHE, at both resolutions; SuperPoint+SuperGlue | `reconstructor-decided` |
| [ETH/meadow](agentic-campaign-2026-09.md#cap-eth-meadow) | `vegetated-exterior` · `walk-along-a-frontage` | `single-object` `subject-cropped` | `target-repeats-in-one-direction` · `repeated-pattern` `repeated-parts` | `coherent-reflector` `movers` | RoMa (detector-free, outdoor weights) → union-find → incremental → triangulate → BA | SIFT → NN and SIFT → LightGlue, both nearly total failures; two other learned matchers also registered fully and returned less structure | `matcher-decided` |
| [ETH/office](agentic-campaign-2026-09.md#cap-eth-office) | `built-interior` · `wander-around-a-site` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `coherent-reflector` `target-underexposed` | SuperPoint → LightGlue → global reconstructor → BA | every seed-and-grow branch tried, classical and learned and detector-free alike | `reconstructor-decided` |
| [ETH/playground](agentic-campaign-2026-09.md#cap-eth-playground) | `vegetated-exterior` · `wander-around-a-site` | `no-single-subject` | `target-textured` · `repeated-pattern` `repeated-parts` | `coherent-reflector` `movers` `flare` | SIFT+CLAHE → LightGlue → global reconstructor → BA | five seed-and-grow branches, none past half the capture | `reconstructor-decided` |
| [ETH/relief](agentic-campaign-2026-09.md#cap-eth-relief) | `built-interior` · `traverse-along-an-axis` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` | SIFT → NN → union-find → incremental → triangulate → BA, at higher resolution, re-solved at a wider window | the same chain at lower resolution with a ratio-test and a joint matcher; **and a global reconstructor that also registered every frame and that truth ranked far above this chain's first solve** | `profile-misled` |
| [EUROC/V2_01_easy](sparse-pose-2026-09.md#the-thirteen-wrong-models) | `built-interior` · `wander-around-a-site` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `backdrop-clipped` | SuperPoint (dense threshold) → LightGlue → global reconstructor → BA | the same chain at the detector's default (half the capture); seed-and-grow on the same matches (two and three frames) | `reconstructor-decided` |
| [TUM_VI/room4](sparse-pose-2026-09.md#what-to-do-when-the-reading-fires) | `built-interior` · `wander-around-a-site` | `no-single-subject` | `target-low-texture` · `repeated-pattern` `repeated-parts` | `diffuse-reflector` `backdrop-clipped` | RoMa (detector-free, indoor weights) → union-find → incremental → triangulate → BA | SuperPoint → LightGlue into seed-and-grow, short of half the capture; the same into a global reconstructor, short by two frames and **cleaner on pose agreement**; a tighter RoMa re-run, vetoed | `matcher-decided` |

---

## What the rows say when you read down the columns

These are observations about this handful of captures, not rules. They are here
because they are the reason to open the file at all.

**The four `reconstructor-decided` rows have no surface trait in common, and
that is the finding.** Two of them read `target-low-texture` and two read
`target-textured`; they span an interior, an exterior frontage, and a vegetated
site. Whatever makes a capture need a global reconstructor rather than
seed-and-grow, **it is not visible in the traits recorded here**, and a planner
should not expect these columns to predict it. What the four do share is the
shape of the failure rather than the look of the scene: a seed-and-grow chain
that stalls partway through a capture its correspondences can otherwise support.
That is a symptom you read off a finished run, not a trait you read off the
images — which is why `health/ladder.md` and `plan/pose.md` are where that
decision lives, and this file only records that it was the decision.

**`matcher-decided` and `reconstructor-decided` are not separated by how badly
the classical path did.** It is tempting to read one as a collapse and the other
as a near miss, and the rows do not support it: the worst
`reconstructor-decided` capture left a smaller fraction registered than the
better of the two `matcher-decided` ones. The distinction is what the failing
stage was, not how far it got, and a registered fraction alone will not tell you
which you are looking at.

**The `studio-rig` rows were unanimous, and that turned out to be the sampling and
not the rig.** Seven orbits of an object on a controlled backdrop all shipped the
same pipeline, with the alternative branch changing only density. A block of
identical rows is weak evidence, not strong — it is one capture kind sampled seven
times — and when three more orbits were added from the holdout, two of them broke
the block, in opposite directions.

One could not be registered by the prescribed chain at all: a smooth glaze whose
only texture repeats around the subject, carrying the rig in reflection, left the
incremental reconstructor short of the full capture on either matcher, and only the
global one recovered it. On another the ratio test returned the *weaker* model and
the joint matcher shipped. So a `studio-rig` row tells you what usually works on
this capture kind, and the two traits that predict it will not are visible before
the run — `coherent-reflector` on a subject whose texture is a repeating band, and
a sparse model that comes out an order of magnitude thinner than the block's. Both
are in [dtu-dense-promoted-2026-09](dtu-dense-promoted-2026-09.md).

**The two interior-room rows are a matched pair, and the `reconstructor-decided`
one carries a warning its outcome value does not.** Both are small rooms shot with
large rotations between neighbouring views, both read `target-low-texture` with
repetition on both axes, and both were rescued off a stalled seed-and-grow. They
part company on what the rescue was worth. On the `matcher-decided` row the
detector-free matcher carried the capture and the delivered model is accurate. On
the `reconstructor-decided` row the global reconstructor registered every frame,
every health rung read healthy, the verifier said consistent — and reference
geometry says the model is wrong by more than a right angle. **So a rescue that
restores registration is not thereby a rescue that produced a good model**, and on
a capture of this kind the outcome column is telling you what unstuck the run, not
that the run ended well. Read the delivered model's own evidence before delivering
it — [pose](../plan/pose.md) says which reading and what to do when it fires — and
note that on the losing branch of the `matcher-decided` row the *rejected* model was
the cleaner one on pose agreement while being short two frames, which is rung 1
working as designed and is the reason these two are both here.

**The one `profile-misled` row is the most valuable row in the file.** A capture
whose target is dim, nearly featureless polished plaster, and whose viewpoints
fall into disconnected clusters, produced two models that both registered every
frame. The profile preferred the one with more points; reference geometry says the
other is better by a wide margin. Both facts are true at once, and the rung that
would have separated them cannot be computed on the branch that won against truth.

---

## Where the raw numbers live

**The per-capture measurement tables are not in this file.** They are in the
per-campaign files indexed by [EVIDENCE.md](EVIDENCE.md), and they were moved
there because the two things were sharing a file and are not the same kind of
thing:

| | INDEX.md (this file) | EVIDENCE.md |
| --- | --- | --- |
| Answers | "has a scene like this been solved before?" | "where does this claim come from?" |
| Keyed on | observed capture kind | the claim being cited |
| Read | while planning, before running anything | when checking a claim, or re-running one |
| A row is | a precedent to follow | a measurement to trace, **never** a plan |
| Scene names | a retrieval key | a provenance record |

Sharing one file meant a reader who fetched it to plan got a page of scene-named
measurement tables under a heading promising precedent, and the invitation to plan
from a row is exactly the misuse both files warn against. Fetch the one whose
question you are actually asking.

**The routes out of this file**, and what each is for:

| You want | Go to |
| --- | --- |
| The numbers behind a row — its profile, its rejected branches, its error against reference geometry | the capture link in the row, which lands on that capture's row in [agentic-campaign-2026-09](agentic-campaign-2026-09.md) |
| What a healthy model of this kind looks like, and how to compare two finished ones | [health/ladder.md](../health/ladder.md), whose reference distribution is [reference_profile.yaml](reference_profile.yaml) |
| Whether to stop, or to keep turning a dial | [ladder — when to stop turning a dial](../health/ladder.md#when-to-stop-turning-a-dial) |
| Whether the answer is a different module, or a module that does not exist yet | [judge/swap_or_build.md](../judge/swap_or_build.md) |
| What a trait implies for a pipeline, before any of this | [plan/scene_to_pipeline.md](../plan/scene_to_pipeline.md) |

**Read the outcome column before the pipeline column.** The pipeline that shipped
for a capture like yours is the least transferable thing in the row — it was
chosen against one capture's particulars at one working resolution. The decisive
*move* is what carries, and the outcome column is where it is written down.
