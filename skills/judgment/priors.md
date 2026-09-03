# Which parts of this corpus to trust, and where

Not "which module families are good" — that question is answered per capture by
[`families/`](../families/). This file answers a different one: **when two pieces
of this corpus disagree with each other, or with your reading, which should you
believe?**

It exists because a seventeen-capture sweep falsified six claims that were
written down as measured, and the ones that survived and the ones that failed
form a pattern worth stating.

---

## The reliability ladder

**1. A diagnostic that fired on your run.** It was computed from your artifact by
the module that made it. It can be badly *worded* — several were — but it is not
describing someone else's capture.

**2. A metric's `meaning`, and the type contract.** Definitional. `two_view_fraction`
is the share of points seen in exactly two views whatever your scene is. These
have been wrong here only when a producer's *implementation* disagreed with the
definition, which is a code defect and now has a cross-check.

**3. Mechanism claims — "why" rather than "how much".** "A two-view point is
exactly determined, so its residual is near zero by construction." "A homography
and a fundamental matrix agree on a plane, so triangulation is degenerate."
These survived the sweep intact. They are geometry, not statistics on fourteen
scenes.

**4. Bands and ranges.** Trustworthy as *descriptions of what has been seen*,
unreliable as thresholds. See below.

**5. Predictive claims about which branch wins.** The least reliable category in
this corpus, by a wide margin. See below.

---

## Where the corpus has actually failed

**Predictive branch claims failed six times in one sweep.** The joint-matcher
swap rule — tagged as measured across fourteen captures — has counter-examples in
four different currencies, at least two on captures the original fourteen
included. A detector-recovery claim was contradicted on eight. A remedy ladder
for a divergence error failed on seven, with one reader exhausting every rung.

**The common shape:** each was fitted by comparing two configurations on a small
corpus, and at least one of them appears to have been compared at a *default*
setting of the dial that decides the comparison. A prediction produced that way
is a statement about the experiment, not about the modules.

**So: treat any "X beats Y when the scene is Z" claim as a reason to run the
comparison, never as a substitute for running it.** The A/B is cheap relative to
being wrong, and it has disagreed with the prediction every time it was carried
to a model.

**Bands did not survive leaving the corpus's protocol.** Every range here was
fitted on twelve-frame head samples at a fixed working resolution. Per-frame
appearance readings transfer to a full capture; adjacent-motion readings do not,
because "adjacent" means something different; anything denominated in *pairs*
does not at all, because pairs grow quadratically with frames.

---

## Where it held up

The claims that survived contact with seventeen full captures were **mechanism
claims and definitional ones**, and the corrections made after measurement:

- "Bundle adjustment erases the accuracy half of a triangulator difference" —
  reproduced, with the ranking flipping post-BA exactly as described.
- The yield ceiling on an all-view triangulator — predicted 1.4% headroom,
  delivered 0.2%.
- `converged` being bookkeeping — reproduced to four decimal places.
- A producer's published mean matching a bundle adjuster's independent reading of
  the same artifact — matched twice.
- "Registration is a precondition, not a tiebreak" — the single sentence that
  prevented the worst decision of the sweep.

**The pattern to carry:** this corpus is reliable about *what a number means* and
*why a mechanism behaves as it does*, and unreliable about *what will happen if
you swap a module*. Weight it accordingly.

---

## A standing caution about recall

`sfm_plan_brief` reports `in_planning_corpus`. If it says your capture is a
member, then locating your readings inside these ranges is **recall, not
confirmation** — the ranges were fitted partly on this capture. Several readers
disclosed this correctly and it changed how much their agreement was worth.
