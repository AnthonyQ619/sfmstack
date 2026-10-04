# Campaign: short-core-2026-10 — when a geometric core registers only part of a capture, is it the delivery?

**This is a raw evidence table. Cite it; do not plan from it.** The rule these rows
support lives in [`plan/pose.md`](../plan/pose.md), in the delivery table at the foot
of the fill section and in the paragraph on where the swap trade flips.

## The question

[sparse-pose-2026-09](sparse-pose-2026-09.md) established that stopping at what the
view graph supports loses overall, because the pairs a short model declines to answer
are charged against it, and that filling the missing frames from a feed-forward
estimator beats both branches on the captures where the fill's trigger fires. It left
one case unmeasured: what to deliver when the fill is **not** available — the gates
refuse it, or the core shares too few cameras with the estimator to fit a similarity
at all.

The delivery table's answer was "deliver the core, and name the missing frames." This
campaign prices that answer.

## What was measured

The seventy-five-capture pose batch, scored by the frozen pairwise metric
(`scoring/pose_auc.py`, as every batch in this series is). For each capture: the model
the agent actually delivered, against the two feed-forward estimators available as
modules — `PoseVGGT` and `PoseMapAnything` — run over the same frames. **Twenty-four of
the seventy-five are corpus members**; the rest are not and are not named here. Every
table below gives the corpus figure beside the batch figure, and the corpus figure is
the one that may be recalled.

Captures split on `registered_fraction`, which `poses/v1` requires, so the reading
costs nothing new.

| | captures | the estimator's model was better | mean AUC@30 difference |
|---|---|---|---|
| `registered_fraction` ≤ 0.7, whole batch | 26 | **24** | **+0.165** |
| `registered_fraction` ≤ 0.7, corpus only | 5 | **4** | +0.328 |
| `registered_fraction` = 1.0, whole batch | 43 | 19 | −0.004 |
| `registered_fraction` = 1.0, corpus only | 17 | 6 | +0.031, **median −0.004** |

The full-coverage row needs its median read beside its mean: the core wins eleven of
seventeen corpus captures there, and the positive mean comes from two low-texture
outdoor captures (ETH/meadow +0.418, ETH/courtyard +0.227) where full registration did
not make the core the better model. Those two are not what this rule is about and it
does not fire on them, but they say full registration is not by itself a reason to stop
looking.

The crossing is near 0.7 and the choice of threshold is not carrying the result: a
fixed policy of delivering `PoseMapAnything`'s model at ≤ 0.6, ≤ 0.7 and ≤ 0.8 gains
+0.041, +0.048 and +0.047 on the batch mean respectively. 0.7 also bounds the worst
single loss at −0.064; at ≤ 0.8 it is −0.164 and with no threshold at all −0.314,
because the captures the swap damages are the nearly-complete accurate ones.

**The route already existed and was not taken.** The table row for a core too small to
fill already permitted delivering the estimator's model on its own, and every capture
that reached it delivered the core instead. **On the corpus this row is one capture** —
`tum_vi/room3`, a five-camera core, where the estimator's model was better by 0.330
AUC@30. Across the whole batch twenty captures reached the row and the estimator's
model was better on nineteen, by a mean of 0.112, but nineteen of those twenty are not
corpus captures and are not named here. The row offered the two as alternatives joined
by "or" and stated no preference, which is the defect; that a single corpus capture
demonstrates it is why `tum_vi/room3` was promoted to carry it.

## The two promoted captures

### euroc/MH_05_difficult — the rule

`indoor` · `wander-around-a-site` · `no-single-subject` · `low-texture` ·
`reflective-diffuse`. A ten-frame sweep through an industrial machine hall, rotation
heavy — median ten degrees between frames, 22% of pairs past twenty — with one frame
dark and 39% shadow-clipped.

**The run is worth reading in order, because the agent got every step right.** It
built a 10-of-10 model and `health/ladder` rung 1 preferred it. It then asked both
correspondence-free estimators, which agreed with each other and put that model
**111 to 146 degrees** off — so it rejected the full model as unjustified, which is
exactly what the consensus reading is for and exactly the right call. It tried
`PoseFill` on the missing frames; the gate refused it at thirty degrees of estimator
disagreement on precisely those frames, also correct. With the fill unavailable the
delivery table sent it to the verified six-frame core, and it named the missing frames
as unsolved.

Six of ten, accurate on what it held, every reading obeyed. **And it was still the
wrong delivery.** The core scored **0.3141** AUC@30 over all pairs against
`PoseMapAnything`'s **0.8182** on the same frames — the largest such gap in the batch
at that registration level, **+0.504**.

**The lesson is the one step that was missing: the estimators were trusted as a check
and never considered as a candidate.** The agent used them to reject a wrong model —
correctly — and then delivered a quarter-blind core without asking what those same two
tables would have delivered on their own. Nothing in the context told it to ask. Four
unanswered frames out of ten cost more than the estimator's lower per-pair accuracy
did, and this capture is promoted to say so.


### tum_vi/room3 — the row the table left open

`indoor` · `wander-around-a-site` · `no-single-subject` · `low-texture` ·
`reflective-diffuse`. A handheld walk around a small lab room, not an orbit: most of
every frame is flat wall, ceiling or a dark window, and `textureless_fraction` reads
0.82. One frame is almost entirely blank wall.

The agent rejected the only ten-of-ten candidate on a `SparseVerification` veto, and
rejected the global model because both estimators agreed with its five-frame core and
sat about 104 degrees from that global model. Both rejections were correct. It then
could not fill — the core shared too few cameras with the estimator to fit a
similarity — so it reached the table's last row, the one that already permitted
delivering the estimator's model on its own, and delivered the core.

Core **0.2083** against `PoseVGGT`'s **0.5384** on the same frames, **+0.330**.

This capture is promoted because it is the row-5 case rather than the row-4 case, and
the two fail for different reasons: row 4 offered no swap at all, while row 5 offered
it as an alternative joined by "or" and stated no preference. Across the batch, twenty
captures reached row 5 and **all twenty delivered the core**; the estimator's model was
better on nineteen, by a mean of 0.112. A five-frame core of a ten-frame capture is
half the capture missing, and the row read as though the two choices were equal.

### advio/advio-07 — the exception

`indoor` · `along-a-path` · `no-single-subject` · `low-texture` ·
`reflective-coherent` · `movers`. A handheld phone sequence inside a mall, riding a
glass elevator: two frames carry almost no real structure, only a coherent reflection
that moves with the camera, and `SceneMotion` flagged pure rotation with no parallax
on four of nine pairs.

The agent registered seven of ten and chose between two finished models on structure,
per `health/ladder`'s comparison: equal registration, then point count 750 against 344
and `min_frame_points` 78 against 5. The fill was refused by its own gates. And here
the core **won** — 0.0213 against 0.0000 from both estimators. It is the only capture at or below 0.7 where delivering the core
was the better call, and the margin is a contest between two failures rather than a
good delivery lost.

It is promoted because the rule needs its limit in the corpus. **The exception is not
"a hard capture" — it is a capture whose estimators are themselves unusable**, and the
reason is in the scene: a coherent reflector between camera and subject, and no
parallax to estimate from. No estimator-side reading separates it from the captures
the swap helped — its `baseline_span` sits inside their range and no diagnostic fires —
so the rule is a default with a known cost rather than a rule with an escape, and that
is what this capture is here to say.

## What this campaign does not settle

The twenty-six captures at or below 0.7 include two that were already corpus members
(ETH/electro +0.558, ETH/delivery_area +0.271) and, before these promotions,
twenty-four holdouts. The batch figures above therefore rest substantially on captures
the context had not been written against; the two promoted here are what the rule in
`plan/pose.md` cites, and the batch numbers are reported for scale rather than as the
rule's grounding.

Nothing here measures the dense consequence. A swapped pose table changes what the
densifier is handed, and `plan/dense.md`'s routing to this file is the only link
between them; it is untested.
