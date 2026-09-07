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
| Pose agreement | the global solve cannot reconcile the local evidence — an optimizer or pose paradigm mismatch for this motion |

These are directions, not verdicts; each one still owes the three-part signal
above before it justifies a build.

---

## Not yet operational — what this skeleton is waiting on

**The reference corpus does not exist yet**, so no percentile can be computed and
no rung can be called "in the bottom tail". Until the reference campaign lands in
[`evidence/`](../evidence/EVIDENCE.md), the run-summary digest reports every rung
as *cannot evaluate: no reference yet* — and the bounce call falls back to the
qualitative ladder plus [`judge/swap_or_build.md`](../judge/swap_or_build.md)'s
per-family signals, which is what it was before this file existed.

The frontier bookkeeping (rung 3 of the signal: which swaps and sweeps this run
already tried) is readable from the run record today; nothing summarises it yet.
That summary belongs in the same digest and is part of the reference-campaign
work.
