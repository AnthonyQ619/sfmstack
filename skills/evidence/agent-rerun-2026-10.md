# Campaign: agent-rerun-2026-10 — the sparse and dense agent batches run again on the revised context

**This is a raw evidence table. Cite it; do not plan from it.** The rules these rows
support live in [`health/ladder.md`](../health/ladder.md), in the procedure for comparing
two finished models, and in [`plan/pose.md`](../plan/pose.md), in the section on readings
built on the model's own evidence.

## The question

The ten-view sparse batch and the full-capture dense batch behind
[agent-controls-2026-10](agent-controls-2026-10.md) and
[estimator-outvote-2026-10](estimator-outvote-2026-10.md) were run again, same
captures, same protocol, on the context those campaigns had revised: does an agent that
meets the situation an edit addresses read the edited page and act on it? Two corpus
captures answered a question the edits had left open.

## What was run

The whole tool loop, strict context, one isolated agent per capture; fourteen ten-view
sparse sessions and fourteen full-capture dense sessions. Scored afterwards against
reference poses (AUC@30 for sparse; for dense, the share of camera pairs whose relative
rotation is within 5° of the reference, a pair touching an unregistered camera counted
as a failure, and the benchmark's own cloud metric). One capture ran twice on the same
context: its first dense session ran out of disk during stereo, after its sparse model
had been chosen, and was run again from an empty store.

## Finding 1 — the reading caught a fold when it was taken, and nothing else did

`/tanks_and_temples/Caterpillar`, 90 views, twice on the same context.

| session | read `plan/pose.md` | estimators run | delivered model, median rotation error | pairs within 5° | verifier |
| --- | --- | --- | --- | --- | --- |
| first | no | neither | 163° | 0.50 | consistent, one supported component |
| second | yes | both | 0.95° | 1.00 | consistent |

The first session compared two global models built on different matchers. They agreed
with each other to 0.8° and were folded the same way, so every comparison it ran —
registration, the verifier, per-bucket error, agreement between its own models — read
level or clean. It had read [`health/ladder.md`](../health/ladder.md) and chosen by its
procedure, which had no step that asks anything outside the model's own correspondences.

The second session ran both estimators. They agreed with each other to 1.6° and with its
global model to 1.1–1.5°, while its incremental model sat at a 90th-percentile
disagreement of 162° from all three; the rotation form fired on that model only and it
was not delivered. The cloud on the delivered model scored 30.5 mm overall as placed;
the earlier batch's delivery on this capture, 72% of pairs within 5°, scored 77.1.

Across the fourteen dense sessions of the batch, four ran no estimator; all four had
delivered models with every pair within 5°. Skipping the reading cost nothing on those
four and a fold on this one.

## Finding 2 — on the centre form alone, a rebuilt geometric model was the right one

`/ETH/meadow`, ten views, sparse deliverable.

| model | LightGlue `filter_threshold` | centre disagreement with each estimator, of span | estimators with each other | rotations | AUC@30 |
| --- | --- | --- | --- | --- | --- |
| first built | 0.3 | 0.27 | 0.03 | inside the estimators' spread | 0.529 |
| delivered | 0.5 | 0.031 / 0.006 | 0.03 | inside | **0.977** |

Only the centre form fired on the first model: its rotations sat inside the estimators'
own spread, the verifier passed it (0.67 px, one component), and the two estimators
agreed with each other. The agent kept a geometric delivery and rebuilt it, bracketing
the threshold: 0.4 was still misplaced, 0.5 and 0.6 agreed with both estimators and with
each other to 0.002 of span. The best any registry module has reached on this staging is
0.981. The step between 0.4 and 0.5 is the one the
[meadow isolation](agent-controls-2026-10.md#the-meadow-isolation) found offline; here
the centre form found it, where no reading of the matcher's graph had.

## What this does not establish

One capture for each finding, one draw each. Finding 1 does not show how often a fold
goes unnoticed without the reading, only that one did, and that four sessions without it
lost nothing. Finding 2 rests on the two estimators agreeing with each other; where they
do not, the centre form carries no signal and this finding says nothing. Neither finding
bears on the vegetated site walk in
[estimator-outvote-2026-10](estimator-outvote-2026-10.md), where the centre form fired
and the geometric cloud was still the better one: a rebuild keeps the geometric delivery
there too.
