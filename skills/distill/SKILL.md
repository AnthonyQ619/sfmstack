# Writing context an agent can actually decide from

What to record after a session, and — more importantly — **what shape to record it
in** so that an agent reading it cold, with no memory of the session that produced
it, reaches the same decision for the same reason.

This file is about the *shape*. The routing (which file a lesson lands in) is at
the bottom.

---

## 1. Two different jobs, two different shapes

A driving agent hits two kinds of decision at every stage, and they are not served
by the same kind of writing.

| | **Selection** — which module | **Tuning** — where to set its knobs |
| --- | --- | --- |
| asked | once, before anything runs | repeatedly, after each run |
| answered by | a scalar reading of the whole capture | a claim about a *region or a frame* |
| best carried as | an **ordered question with a mechanism** | a **branch indexed by observed metric state, with a prediction attached** |
| fails by | ties, or a rule applied out of order | moving a number that was not the constraint |

Getting the shape wrong is the most common way good knowledge fails to transfer.
A mechanism written as a threshold does not survive a new capture. A tuning branch
written as a general principle gives no way to tell whether it applied.

---

## 2. Selection context: order the questions, and carry the mechanism

**The finding this file is built on.** Five captures were driven from a standing
start by readers with no prior exposure to them. Every one chose its detector on a
single ordered pair of questions, and *nothing else came close to deciding it* —
not texture density, not repetition scores, not any photometric reading, though
all of those were available and several were loud. Four of the five went one way
and one the other, and each said plainly which reading drove it.

Three properties made that possible, and they are worth copying deliberately.

**It was ordered, not weighted.** Two questions both fire on a real capture, and
"weigh them against each other" is not a procedure an agent can execute — it stalls
or it invents a tiebreak. *Ask A first; if A fires, it decides; only if A is quiet
does B decide.* The file also says what it costs to get the order backwards, which
is what makes a reader keep the order under pressure.

**It carried the mechanism, not just the correlation.** The rule was fitted on a
corpus, but the file explains *why* the reading implies the outcome — what the
number is a proxy for, and through what causal chain. That is what let a reader
apply it to a capture outside the corpus and, better, **check the mechanism
directly instead of trusting the proxy**: one reader re-ran the upstream module at
a wider spacing to observe the thing the metric only stands in for, another read
the per-pair series and found the break landing exactly where the description said
the camera turned a corner. Both replaced a borrowed correlation with an observed
mechanism. **A correlation tells a reader whether to believe you; a mechanism tells
them how to check.**

**It said what the evidence looks like, not where the cut point is.** See §4.

---

## 3. Tuning context: index by what was observed, and make it predict

Tuning knowledge is only usable if a reader can tell whether it applies *before*
spending a run. Two rules do most of the work.

**Index by observed metric state, not by parameter.** A section headed with a
parameter name is found only by someone who already suspects that parameter. A
section headed with a symptom — this number is high while that one is low — is
found by someone who has the symptom, which is the only person who needs it.

**Attach a prediction, and make the reader commit to it.** The single most
productive discipline observed was: *change one thing, state what should move and
why, then run.* Its value is almost entirely in the runs where the prediction was
**wrong**, because a violated prediction localises the error to a specific belief
about the capture rather than leaving a number that merely "did not help".

- A move that lifted every reported metric was **rejected** because the prediction
  said the gain would land on a region the description called unwanted, and pulling
  the raw coordinates showed most of it had.
- A move predicted to do nothing did nothing, which promoted "the empty region is
  destroyed detail" from a description's claim to a measured fact — at the cost of
  one run.

Write the prediction into the context too. A tuning branch that says *raise this
and expect the count to roughly double while coverage stays flat* is checkable. One
that says *raise this to improve results* is not.

**And state what a metric is a function of.** The single most common wasted first
run in this stack was reading a number that was mostly a default. Where a metric
can be pinned by a parameter, the context must say so at the top of the section
rather than in a branch — otherwise the reader compares two settings, or two
modules, and is really comparing their defaults.

---

## 4. Never write the threshold

A cut point derived from N captures is a property of those N captures. State the
**direction** and the **shape of the evidence** — unanimous, a clean gap, one
exception and why — and let the reader locate their own reading in it.

"The failing captures were the highest readings with a clean gap below them"
transfers to a new corpus. "Above 0.155" does not, and is worse than useless
because it reads as authority.

**Do not print the number even as an example of what not to write.** A reader in a
hurry lifts it straight out of the counter-example, which has already happened here.

The same applies to names. Describe the *capture* — a subject on a lit backdrop, a
walked site whose halves barely overlap, a facade with a band of loose aggregate
below it — never the dataset and scene it came from. A reader cannot check whether
their capture is scene 15; they can check whether it is a facade with gravel.

Scene names belong in exactly two places: the run index and the sources files,
which exist so a claim can be traced back and re-run. Those are citation records,
and they are the reason the prose does not need names.

**But de-naming does not buy independence, and it is worth being clear about what
it does and does not do.** It protects a reader planning a capture the corpus has
never seen. It does nothing at all when the capture in front of them *is* one of the
corpus captures — and that case is common, because a corpus is built from whatever
was to hand. A range table's extremes are specific captures' readings printed
verbatim, so a planner whose number matches one to several digits has looked up
their own answer without either party intending it.

Worse, the traceability link is the leak. The evidence record exists to be followed;
it is indexed by name and carries downstream results; so a reader sent there to
locate a threshold meets their own capture's outcome. Anonymising the record would
destroy the one thing it is for.

The honest resolutions are structural, not editorial: **declare corpus membership
where the reading is served**, so a planner knows before they start whether they are
reasoning or recalling; and **prefer evidence stated as a shape** — a gap between
groups, a unanimous direction — since a shape is much harder to look yourself up in
than a level is. When neither is available, the fallback is disclosure: a plan that
says "this capture is in the corpus and here is what I did about it" is worth far
more than one that quietly presents recall as derivation.

---

## 5. Every metric claim owes a denominator

The sharpest failure found in this stack was a metric that meant the opposite of
what the context said, on exactly the capture type the context spent the most words
on. It was a ratio over a fixed grid across the whole frame — so on a capture where
a large part of the frame holds destroyed detail, the module that detected on
nothing scored higher than the module that stayed on the subject, and the guide's
own advice pointed at the higher number.

**Five of five readers found this independently.** That is the signal that it was a
context failure and not a reader failure: they were all following the file
correctly.

The general form: **an area-weighted or frame-wide statistic silently assumes the
whole frame is eligible.** Before writing that a metric predicts an outcome, ask
what its denominator is and whether every capture supplies the same one. If not,
the context must say what to subtract, where the reader finds out how much to
subtract (usually the scene description), and — critically — **whether the number
is still comparable across modules**, because two modules computing the same
formula over the same grid look comparable and need not be.

That question generalises past coverage. Applied afterwards to this stack's own
headline connectivity metric, it landed: that one is a percentile over a dense
field, also frame-wide, also diluted by a dead backdrop. The reading survived, but
only because the evidence was a *gap between groups* rather than a level — a gap is
robust to a bias that shifts a subset of readings the same way, and a threshold
would not have been. **Writing the evidence as a shape rather than a cut point is
what let the claim survive the discovery of its own bias.**

---

## 6. What selects, and what tunes — they are not the same source

Across five captures driven cold, the split was total and neither side crossed
over:

> **The metrics chose the module. The scene description chose the parameters.**
> Where the two disagreed, the description was right — four times out of four.

Every non-cap parameter adopted or rejected was decided by a claim in the
description, not by a number: exposure normalisation adopted because the
description nominated it for a specific dark region and validated on the specific
frames it named; the same normalisation rejected on a different capture *despite
every metric improving*, because the description labelled the regions the gain
landed in as unwanted; rejected on a third because the description said the empty
region was destroyed rather than dark, which the run then confirmed.

**The reason is structural, not incidental.** A scalar over the frame has no
region. A parameter acts on a region. So a scalar can rank two branches but can
never say *where* a change will land — and "where" is the whole question at tuning
time. This is why the descriptive pass earns its cost, and why its fields should be
written as claims that a later run can confirm or refute rather than as prose.

Two direct consequences for writing context:

- **A stage that tunes needs per-frame and per-region series, not just medians.**
  Where a stage publishes only summaries, readers rebuild the series by hand — three
  of five did, for the same missing array. Either publish it or expect the decision
  to be made worse.
- **Description fields should be phrased so they can be wrong.** "The flat regions
  are exposure-recoverable, not clipped" is worth four times what "the lighting is
  uneven" is worth, because a single run settles it.

---

## 7. Say what the stage cannot answer

Every reader independently identified the same thing as unknowable at the detection
stage: whether descriptors survive to a *non-adjacent* frame — because survival is
a property of pairs and that stage has none.

That agreement is a result, and it belongs in the file. Context that only says what
*can* be concluded invites a reader to manufacture a conclusion for the rest. Naming
the boundary explicitly — *this is decided one stage later, by these metrics* — is
what stops a plausible chain of reasoning from being built across a gap where no
evidence exists.

Distinguish three states and use the words consistently:

| | meaning |
| --- | --- |
| **measured** | both branches were run and compared on the outcome that matters |
| **observed** | a reading supported the claim; no swap was performed |
| **structural** | an argument from how the algorithm works; no data |
| **unknowable here** | the evidence does not exist at this stage — say where it does |

A file that marks its own structural claims as structural is trusted on its
measured ones. One that states everything flatly is trusted on none of it.

---

## 8. Routing

| The lesson is about… | It goes in |
| --- | --- |
| choosing between modules of one stage | `skills/families/<stage>.md` |
| how to move one module's numbers | `modules/<name>/skills/tuning.md`, indexed by symptom |
| where a module stops being the answer | `modules/<name>/skills/limitations.md`, with the escape as a capability query |
| what a metric means and what it is a function of | the module's `module.yaml` and `artifact.md` |
| what to do the moment a diagnostic fires | the diagnostic's own `suggested_actions` — it is the only context guaranteed to be read |
| reading a whole capture before running anything | `skills/scene_to_pipeline.md` |
| a rule spanning two stages | `skills/workflow/`, not either module |
| the raw numbers behind any of the above | `skills/runs/INDEX.md`, with scene names |
| taste — when a result is good enough | `skills/judgment/`, and **propose it, never write it** |

**Two placement rules learned the hard way.**

*Put the correction where the reader is standing.* A caveat about a metric, written
in the guide that introduces it, does not reach the reader who meets that metric two
stages later in a diagnostic's suggested action. The correction has to be repeated
at every point the claim is acted on, or it will be right and useless.

*A diagnostic's `suggested_actions` are load-bearing context, not a UI string.* They
are read at the moment of action by a reader who may consult nothing else. One that
said certain frames were "candidates for exclusion" was, on every capture where it
ever fired, naming sharply-focused frames aimed at a flat surface — the metric
reports content, not focus. Write them as the whole instruction, including what to
check before acting.
