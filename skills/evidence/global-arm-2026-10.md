# Campaign: global-arm-2026-10 — what a global reconstruction adds to a short model, and what it does not add to a dense one

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports
live in [`plan/pose.md`](../plan/pose.md) §4, on when to reach for
`SparseGlobalCOLMAP` against a model that registered part of a capture, and in
[`plan/dense.md`](../plan/dense.md), on what that arm is and is not worth to a dense
deliverable.

## The question

`SparseGlobalCOLMAP` estimates poses internally, by rotation averaging over the whole
view graph followed by global positioning. It has no registration order, so it has
nothing to stall on, and [`INDEX.md`](INDEX.md)'s `reconstructor-decided` class records
captures whose registration it rescued. Two things were unmeasured:

1. against a model that already registered **part** of a capture, does it place the
   frames that model left behind — and does it keep the ones that model had?
2. where it changes the model's global shape, is that worth anything to the **dense**
   result?

## Part 1 — registration, against the best incremental model on the same matches

Seven corpus captures at their full frame counts, each holding an incremental model
short of its own capture.
The global arm was run on **that model's own `pairwise_matches/v1` artifact**, so the
matcher is held fixed and the reconstructor is the only thing that varies.

**The control is the HIGHEST-registering incremental model built on those same
matches**, not the first one found. This matters: picking the shortest incremental
model in each store instead inflated two of these rows, one of them by a factor of
fourteen, because it compared the global arm against a branch nobody would have
delivered.

Placed-image sets were compared element-wise, so *added* and *lost* are counted and
not inferred from a total.

| capture | images | best incremental | global | added | lost | gap before | gap closed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DTU/scan48 | 49 | 38 | 40 | +2 | **0** | 11 | 2 |
| ETH/electro | 45 | 40 | 43 | +3 | **0** | 5 | 3 |
| ETH/facade | 50 | 45 | 48 | +3 | **0** | 5 | 3 |
| ETH/playground | 38 | 35 | **38** | +3 | **0** | 3 | 3 |
| tanks_and_temples/Meetingroom | 90 | 88 | 89 | +1 | **0** | 2 | 1 |
| ETH/kicker | 31 | 30 | **31** | +1 | **0** | 1 | 1 |
| tanks_and_temples/Barn | 90 | 90 | 90 | 0 | **0** | 0 | — |

- **Added on 6 of 7**; the seventh was already registered whole, so it had nothing to
  add. **13 cameras added across the set and none lost anywhere** — it strictly
  dominated its control on every capture with a shortfall.
- **It closed between one and three frames, whatever the size of the gap.** It
  completed registration on the two captures whose gap was already within that reach,
  and on the widest gap in the set it closed two of eleven. It is a last push, not a
  route from a badly short model to a complete one.
- Three of these captures — scan48, facade and kicker — are the `reconstructor-decided`
  rows in [`INDEX.md`](INDEX.md). All three reproduced.
- Every capture here has `registered_fraction` of **0.776 or above**, so this set lies
  entirely on the side of the 0.7 crossing in [`plan/pose.md`](../plan/pose.md) where
  the geometric core is already the better delivery. It says nothing about the regime
  below that crossing.

## Part 2 — the dense deliverable, and the reading that does not predict it

Ten captures, each with a dense cloud built on the incremental model and a second
built on the global arm from the same matches, reusing the capture's own `DenseMVS`
parameters so the sparse arm is the only variable. Scored under each dataset's
protocol, as-placed and after a best-fit similarity, with the similarity into the
reference frame fitted from camera centres alone.

The hypothesis under test, **pre-registered** with a threshold and a predicted sign:
that the gain follows the capture's **drift penalty** — the gap between the as-placed
and best-fit scores of the incremental cloud.

| capture | drift penalty | dense gain |
| --- | ---: | ---: |
| tanks_and_temples/Barn | 27.4% | **+61.6%** |
| DTU/scan4 | 103.3% | +11.1% |
| DTU/scan15 | 49.4% | +6.3% |
| DTU/scan9 | 42.3% | +4.5% |
| DTU/scan33 | 50.1% | +1.3% |
| tanks_and_temples/Meetingroom | 4.4% | +0.3% |
| DTU/scan10 | 110.8% | −0.9% |
| DTU/scan75 | 90.9% | −2.2% |
| DTU/scan1 | 46.2% | −4.4% |
| DTU/scan23 | 142.1% | −4.7% |

- **Spearman −0.286** within the protocol carrying eight of the ten, against a
  pre-registered threshold of +0.65. Not met, **and the sign is inverted.** Pooled over
  all ten, −0.406. The arm was better on 4 of 8 and on 6 of 10.
- **The capture with much the largest gain carries a lower drift penalty than any of
  the captures that gained nothing**, and the capture with the highest penalty got
  worse. The hypothesis is not merely unsupported.
- One capture gained more than sixty per cent; the next best gained eleven. **Treat
  the large result as an outlier, not a template.**
- A separate search over **every metric the stack reports** — 138 readings, plus 17
  view-graph spectral features including tree-connectivity and effective resistance —
  found nothing predicting the drift penalty that beats a family-wise permutation null:
  the best candidate reached 0.499 where the median best-of-family under shuffled
  labels is 0.686.

## What this settles

- A global reconstruction **places frames an incremental model left behind, without
  dropping any of that model's own**, at full frame count, above the 0.7 crossing.
  The gain is a few frames.
- It is **not** a route to complete registration from a badly short model.
- Its effect on a dense deliverable is **small and of either sign**, does not follow
  the drift penalty, and has **no agent-side trigger** — run both arms and compare the
  clouds.

## What this does not settle

- The regime **below** the 0.7 crossing. No capture here sits there.
- Whether the consensus reading selects this arm. It is not measured here.
- Why the one large dense gain is so much larger than the rest.
