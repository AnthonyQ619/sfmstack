# Runtime against quality, and when the expensive option is worth it

Cost in this stack is not a single quantity. It is wall-clock, GPU memory, and
the risk that a run dies partway — and those three do not move together, which is
why "expensive" is not a useful word on its own.

---

## What actually costs time

**Matching dominates, and it is quadratic in frames.** Exhaustive classical
matching on a capture of a few dozen frames at tens of thousands of keypoints per
image runs in the tens of minutes for the full pair set. Doubling the frame count
roughly quadruples it. Nothing else in a sparse pipeline is in that range.

**A joint learned matcher trades CPU for GPU and adds a second axis.** Its cost
grows with keypoints *per pair* as well as with pairs, so raising a detector's cap
raises its cost faster than it raises the classical matcher's. The two do not
trade off the same way and cannot be compared per-pair.

**Bundle adjustment is cheap until the model is large, and then it is not.** On a
model of tens of thousands of points a global solve is minutes, and raising the
iteration cap is the standard advice — see the warning below before taking it.

**Detection is nearly free** relative to both. This is the half of "the A/B is
nearly free" that is true: a joint matcher can consume a classical detector's
`features/v1` directly, so a matcher swap costs no re-detection.

---

## When to spend

**Spend on the A/B, not on the prediction.** The corpus's predictive claims about
which branch wins have failed repeatedly ([priors.md](priors.md)), and the
comparison has been right every time it was carried to a model. An hour of
matching is cheap against shipping the wrong branch.

**Buy the cheaper form of the A/B first.** Both branches on a restricted pairing,
compared on `min_image_degree` and on how match count decays with frame
separation, answers the branch question at a fraction of the cost. Buy the full
pair set only when those disagree.

**Spend on frames before spending on modules.** Loading the whole capture is free
and increases graph density quadratically. Fragmentation that motivates an
expensive branch swap has been measured disappearing when every frame was loaded.

**Do not spend on a metric at its ceiling.** If a reading will not move across a
real sweep, the next run will not move it either ([smells.md](smells.md)).

---

## GPU

Several modules fall back to CPU rather than failing. That is deliberate and it
is why measurements exist at all, but the factor is large — one matcher is
roughly 50× slower without a device, and a semi-dense matcher is the heaviest
computation in the repository. Treat CPU fallback as a way to get *an* answer, not
as a configuration to plan around.

Where a module holds a multi-billion-parameter model, give it a device to itself.
Sharing one between concurrent captures is how a sweep loses runs to
out-of-memory failures that have nothing to do with either module.

---

## The cost of a run that dies

This is the axis usually left out. A long CPU-bound solve used to be killed by its
own orchestrator when a status poll timed out — reported as "lost contact with the
module server", which reads as a crash. It fired at default parameters and made a
documented action, raising the iteration cap, fatal to follow.

That specific defect is fixed. The general point stands: **before spending a long
run, know what happens if it does not finish.** A cheap run that completes tells
you more than an expensive one that is killed at 90%, and the corpus's open
question about the cost curve of global bundle adjustment went unanswered for
months precisely because the runs that would have answered it were the ones dying.
