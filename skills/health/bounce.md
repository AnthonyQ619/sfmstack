# When an unhealthy reconstruction means BUILD, not more tuning

[`ladder.md`](ladder.md) says whether a model is healthy. This file answers the
question that comes after a *no*: **is this a reconstruction that better use of
the registry can fix, or a signal that no tool in the registry addresses this
capture — so the right next act is building one?**

The two answers cost very differently. Bouncing to build when a swap would have
worked wastes days; tuning when nothing in the registry can work is how a run
spends its whole budget in a decision tree whose branches all end in the same
place. This file exists so that call is made from readings, not from fatigue.

For *module-level* doubt mid-pipeline — "this matcher isn't working, swap it or
build a replacement?" — the file is [`judge/swap_or_build.md`](../judge/swap_or_build.md).
This file is whole-model doubt at the end of the pipeline, and it hands off to
that one's BUILD section once the verdict lands.

---

## The bounce signal

The reading is the health profile's **weakest rung, watched across the frontier
of attempts** — every configuration this run has already tried, which the run
record holds.

**Low says unhealthy. Low and immobile says bounce.** Precisely:

1. The same rung is the minimum-percentile rung across the frontier — the
   failure has an identity, not just a magnitude.
2. It sits in the corpus's bottom tail while other rungs do not — the model is
   not uniformly bad (uniformly bad usually means an upstream defect, which is a
   backtracking question, not a build question — check the stage-local
   diagnostics first).
3. It has not moved across attempts that *should* have moved it: at least one
   swap of the module that owns the failing rung's stage, and a bracketed sweep
   of that module's primary dial. An untried registry is not evidence about the
   registry.

When all three hold, the registry has been given its chance at this capture and
declined it. Take the failing rung's *capability* — not a module name — to
`judge/swap_or_build.md` §BUILD, which says how a build is scoped from a
capability gap.

## What each rung's persistent failure points at

A rung names the stage that owns it, which is what scopes the build:

| Persistently weakest rung | The capability gap it indicates |
| --- | --- |
| Registration | nothing in the registry connects these views — a different matching or pose paradigm, not a better setting |
| Conditioning | the capture's geometry starves triangulation — something that constrains depth without wide parallax |
| Composition | tracks die young everywhere — a tracker that survives this capture's appearance changes |
| Coverage | structure concentrates where the tools can see — a detector/matcher for the surfaces being skipped |
| Error | residuals stay high on well-supported points — usually upstream, rule out calibration before building anything |
| Yield | structure is found and then lost wholesale — the hand-off between stages is the defect, not either stage |
| Pose agreement | the global solve cannot reconcile the local evidence — an optimizer or pose paradigm mismatch for this motion. **Rule out the reference first:** solve the capture with a second pose paradigm and read `sfm_compare`'s `rotation_agreement` between the two models — under `sparse_models` when the second solve is a sparse model, under `pose_agreement` when it is a correspondence-free estimator emitting `poses/v1`. If they agree far more closely than this rung reports, the rung is measuring noise in the pairwise two-view estimates it compares against — common on near-planar subjects and narrow baselines — not a defect, and it is no bounce signal |

**Use two references, not one, when the second paradigm is a feed-forward
estimator.** Both `PoseVGGT` and `PoseMapAnything` consume the scene alone, and
passing your model and both of them to `sfm_compare` in one call costs one extra run
and answers a question one reference cannot: whether a wide disagreement is your
model or the reference wandering. If the two estimators disagree with *each other*
about as much as they disagree with you, you have ruled nothing out. The reading and
what it is worth are in [`plan/pose.md`](../plan/pose.md); this rung only needs the
part about not trusting a single reference.

These are directions, not verdicts; each one still owes the three-part signal
above before it justifies a build.

**Two of the rows carry a health warning.** Composition and conditioning were
scored against ground truth across every pair of comparable models the corpus
holds, and composition ranked *below chance* while conditioning ranked at it —
because both rise when a stage merely discards its weak points
([`ladder.md`](ladder.md)). A build scoped from either of those rows alone would
be scoped from a reading that moves for reasons unrelated to the capability it
is supposed to name. Read yield beside them before scoping anything, and treat
coverage and yield — which ranked every comparison correctly — as the rows to
lean on.

---

## What works now, and what this still waits on

**The reference corpus exists**, so rungs 1 and 2 of the signal are live: the
digest reports each rung's percentile against
[`evidence/reference-pipeline-2026-09`](../evidence/reference-pipeline-2026-09.md),
and "in the bottom tail" is a reading rather than a wish. The corpus is coarse —
sixteen draws, so percentiles move in steps of several points — and it is one
fixed pipeline over two benchmark families, so a capture unlike those is being
scored against a distribution that never saw its kind.

**Rung 3 is still manual.** Whether the failing rung has moved across the swaps
and bracketed sweeps already tried is readable from the run record, and nothing
summarises it for you. Until something does, that half of the signal is a
judgement you make by looking, and a bounce call made without it is a call made
on a low reading alone — which the corpus says is not enough, because the worst
model in it reads *high* on two rungs.

**But it has now been tested by hand, and it is the rung that does the work.**
The
reference corpus contains three captures that satisfy rungs 1 and 2 as clearly
as anything could: registration is the minimum-percentile rung, it sits at the
very bottom of the corpus, and the other rungs do not. On a low reading alone,
all three read as bounce candidates. The alternate-leg campaign then gave the
registry its chance at them — a detector-free matcher, a learned
detector/matcher pair, and a feed-forward pose estimator, one stage swapped each
time — and **every one of the three swaps registered between 0.88 and 1.00 of
every one of the three captures.** Not one was a build.

The most instructive of the three changed nothing upstream of pose: it ran off
the *same cached tracks* the reference had already failed on. So the failing
rung was not describing a gap in the registry at all. It was describing one
paradigm's behaviour on data that another paradigm handled without complaint.

**What that calibrates:** a persistently weak registration rung is a strong
signal that this configuration cannot reconstruct this capture, and a weak
signal about the registry. Before a registration bounce, the swaps rung 3
requires must cross **paradigms** and not merely modules — a second incremental
estimator is not a second attempt. And the cost asymmetry favours doing it: the
pose swap that rescued all three captures ran in seconds against artifacts
already on disk, which is nothing against the days a build costs.

**No bounce has been acted on yet**, and this campaign is why: the three
strongest candidates the corpus has produced all turned out to be swaps.
