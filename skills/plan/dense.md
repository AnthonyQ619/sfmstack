# Dense reconstruction — choosing a densifier

Everything that produces `dense_model/v1`. Two densifiers, and the difference between
them is not degree. A third module, `DenseFusion`, also produces the type, but it is a
tuning tool rather than a densifier: it re-fuses a `DenseMVS` stereo pass at other
settings — see "Delivering the verified cloud" below.

---

## The axis

**Verification against prediction.**

**`DenseMVS`** searches, for every pixel, the depth and normal that best correlate
its neighbourhood with the same neighbourhood seen from other views — then keeps
only the pixels several views agree on. Where the evidence is absent it returns
**nothing**.

**`DenseVGGT`** predicts a depth for every pixel from a learned monocular prior
refined across views. Where the evidence is absent it predicts anyway.

**A cloud with no holes is not more complete. It is less willing to say it does not
know.** The holes in an MVS cloud are the honest part: they sit on specular
highlights, shadow, uniform paint, glass, anything that moved.

**A hole is a refusal, not an absence.** Measured against reference geometry on a
studio orbit of a compact subject, with occlusion accounted for, nearly all of the
surface the verified densifier missed was visible and unoccluded in several of that
capture's own views. The pixels were there and the module declined to certify them.
None of the obvious levers reaches them. Changing the sparse model's density,
normalising exposure, loosening the filters and widening the set of views compared all
left the holes where they were. What recovered some was the dense stage's own fusion
policy — see "Delivering the verified cloud". Expect the remainder, and use a learned
densifier if it has to be filled.

**What does not follow is that a learned prior fills those holes.** Measured on the
same captures, most of its points land on the backdrop, the support surface and in
empty space rather than in the holes; see the table at the end of this file.

Two things follow:

- **Point count does not measure coverage across the two.** A predictive
  densifier can return more points *and* cover the verified structure less tightly,
  in a larger bounding box, because a share of its cloud is in space nothing
  confirms. Comparing them by point count compares willingness to guess.
- **Neither reports which case it is in.** MVS expresses uncertainty by deleting
  pixels, so it has no confidence channel at all — what stands in for one is the
  fraction of pixels that survived filtering. A learned densifier's confidence is
  its own unbounded self-report, comparable within the module and across settings
  and to nothing else.

---

## The secondary axes

### Runtime, and it is not a detail

MVS cost is roughly `views × pixels × source_views × samples × iterations`, and it
is measured in minutes per view at real resolution. Feed-forward depth is one
forward pass over the set. **This is often the deciding constraint**, and a pipeline
that spends its budget upstream will not get to run MVS at a resolution worth
having. Plan the dense stage first and the sparse stage around it.

### A learned prior carries a scale, again

The same ambiguity as in [sparse.md](sparse.md), with a sharper failure. Unprojection
places each pixel along a ray from **its own** camera, so a wrong scale shrinks each
view's cloud about a *different* centre — the views stop agreeing, and the result is
a smeared or multiplied surface rather than a small one. It looks like bad depth and
is not. Nothing in the metrics moves, because the filters are scale-invariant.

The scale must be measured against correspondences and reported. Assuming it is 1.0
is correct only when the poses came from the same model.

### What each one needs

MVS needs a `sparse_model/v1` — not just poses. It derives each view's depth search
range and its choice of source views from *which images see which points*, so a
thin or partial sparse model produces empty depth maps and looks like an MVS
failure.

**That condition is readable before spending an hour on it, and not from the
headline metrics.** The input here is normally a refined model, and every producer
of the type — refiners included — publishes the readings that see it:

- **`min_frame_points`** is the direct one. MVS chooses source views per image; an
  image holding almost no structure has nothing to choose from, and that is the
  view whose depth map comes back empty. `registered_images` counts it as
  registered, and `point_count` is a whole-model total that a single starved view
  cannot move.
- **`p05_triangulation_angle`** says whether the depth search range is being
  derived from points whose depth was well determined in the first place. Points
  on near-parallel rays reproject perfectly at badly wrong distances, so a clean
  `mean_reprojection_error` is not evidence against this.

Neither is a threshold — what a densifier needs from them has not been measured
here, and is one of the open questions below. They are the readings to take before
the run so that an empty depth map can be attributed rather than guessed at.

A learned densifier needs only poses, and optionally tracks for the scale.

---

## Which end to reach for

**MVS** when the cloud has to be right, the scene has texture, and there is time.
Everything it emits was correlated across views and agreed on.

**A learned prior** when coverage matters more than verification, when the scene is
textureless or reflective — where MVS has nothing to correlate and no parameter
invents evidence — or when the answer is needed in seconds rather than an hour.

**Both**, when the question is which parts of the learned cloud to trust: the MVS
cloud is then a mask over it.

---

## Planning the sparse stage for a dense deliverable

When the deliverable is a dense cloud, it is tempting to treat the sparse stage as
the supply and tune it for what the densifier will consume. That has been tested, and
it is mostly the wrong place to spend effort.

**Measured end to end, there is very little to plan here.** Four sparse-side changes
were run through to a scored dense cloud on a corpus of studio orbits: the detector's
budget, its contrast threshold, exposure normalisation at detection, and the refiner's
minimum track length. Three of them changed the sparse model substantially — between
three fifths smaller and half again larger — and **none moved dense completeness by as
much as a thousandth of a millimetre.** The fourth changed nothing at all, for a reason
worth knowing: the detector's `saturation` was 0.000 on every capture, so its budget
was never the binding constraint and doubling it returned an identical model.

**So do not spend runs tuning the sparse stage for dense coverage.** The association
across captures is real — captures with thin models do have worse dense completeness —
but it does not survive as a lever: change the density *within* a capture and the dense
result does not move. Both fit one confound, that hard captures produce thin models and
poor coverage without either causing the other.

**What decides the dense result is the dense stage's own policy**, not its input:
`fusion_min_num_pixels` and `geom_consistency` moved completeness by two orders of
magnitude more than any of the above. See "Delivering the verified cloud" below.

**Thin models and poor dense coverage go together across captures — but do not
assume the mechanism is per-view starvation.** Captures whose sparse models are thin
overall do have worse dense completeness, and `min_frame_points` can sit near zero
while `point_count` looks healthy, so it is still worth reading. What has been tested
and did *not* hold is the causal story: measured inside a capture, a view's own sparse
structure does not predict where that view's depth map comes back empty — the
correlation is near zero and its sign flips between captures. So treat the association
as a property of hard captures rather than as a lever, and **do not spend a run
raising the keypoint budget to lift one starved view** in the belief that it will fill
that view's holes.

**What does track the holes is how many views see the surface *well*.** Surface the
densifier missed was exposed and textured in far fewer views than surface it covered
— single figures against twenty or thirty on the same capture. This describes why a
region stays a hole; it is not a setting. Comparing each image against every other view
— which gives any well-exposed view the chance to be used — recovered nothing and cost
accuracy. Neither the keypoint budget nor the choice of source views reaches it.

**Matching and tracking: choose for whether the capture solves, not for the
densifier.** An earlier version of this page leaned towards keeping weak
correspondences on the grounds that broad track tables fed MVS better than clean thin
ones. That rested on the same cross-capture correlation as everything above, and adding
a tenth to a half again more structure through the detector did not move dense
completeness. So let [matching.md](matching.md) decide the matcher on its own terms —
registration and whether the capture holds together — and do not loosen it in the hope
of a better dense cloud.

**Triangulation and refinement: `min_track_len` is NOT a dense decision.** This
page said the opposite, on the strength of a cross-capture correlation, and the direct
test refutes it: raising it to 3 deleted between a third and three fifths of every
model's points and changed dense completeness by **+0.0000 mm**. Decide it on the error
rung and on composition, which is where its effects are real — not on the dense
deliverable.

**Do not refine intrinsics on a calibrated capture.** This one does reach the dense
cloud, through placement rather than coverage. An orbit lets
focal length trade against depth, so the optimiser can buy a lower reprojection
error by resizing the scene; measured on this batch, freeing the focal improved the
error and moved the cloud several times further out of place. See
[optimization.md](optimization.md).

**Two readings to take before spending an hour on MVS:** the model's overall
density, and the capture's clipped-highlight reading from `SceneTriage`. The second
predicted the dense stage's own coverage more strongly than any parameter moved it
— a capture reading high on blown highlights loses dense coverage before the dense
stage starts, and the honest response is to expect the loss, not to loosen filters
afterwards. **Neither is a lever you can pull to fill a specific hole**: blown
highlights are a property of the capture, and per-view density does not predict which
views come back empty.

---

## Delivering the verified cloud

**Plan one `DenseMVS` run at the measured operating region, not at the defaults.** On
a well-posed capture that is the geometric check off and fusion one step below its
default: markedly more complete, accuracy still at the level classical MVS is
published at, and about half the runtime. The region, and when to stay out of it —
doubtful poses, and never the check off with the loosest fusion — are in
[DenseMVS tuning, "Delivering a dense cloud"](../../modules/dense_mvs/skills/tuning.md#delivering-a-dense-cloud).

**Decide what the cloud is for before you fuse it, and record the answer.** Every
dense delivery is a trade between accuracy and coverage, and a task that does not name
one still gets one. Absent an instruction, deliver for accuracy: a looser fusion admits
points a later stage cannot distinguish from real surface, which misplaces whatever is
fitted to the cloud, while a tighter one only leaves holes. Where the two densifier
families sit on that same trade is the axis above.

**Plan a `DenseFusion` exploration only when the capture is unlike the ones
measured.** It needs the stereo pass kept (`keep_workspace: true`), which is large on
disk; after that each fusion setting costs seconds, and point counts alone say where
to stop. The route from an output you already have is one replay:
[DenseFusion SKILL, "Before you run it"](../../modules/dense_fusion/skills/SKILL.md#before-you-run-it).

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **How far a dense stage's runtime model transfers** | Wall clock on shared hardware. The MVS scaling rule under-predicted by between about one-and-a-half and six times across a batch on a contended machine. |
| **What a learned prior buys where MVS genuinely has nothing** | A capture whose target surface is textureless or reflective, with reference geometry. Both families have now been measured, but only on captures where MVS works well — which is the case MVS is best at and the case the prior is least needed in. |
| **The runtime curve** | Wall clock against view count and resolution, on sets spanning both. "Minutes per view" is an order of magnitude, not a model. |

## What HAS now been measured, against reference geometry

A batch of studio orbits of compact subjects, each solved from raw frames to a
dense cloud and scored against reference surface geometry.

| Question | Answer |
| --- | --- |
| **Accuracy against reference geometry** | The verified densifier is accurate at the fine tolerance the reference geometry can resolve; what it loses is completeness, by a factor of roughly one and a half to two on the same captures. |
| **Whether MVS holes are where the prior is wrong** | **No, and this was the argument for the family split.** Union of the two clouds was several times *worse* than MVS alone at fine tolerance, and filling only the verified holes was worse still: most predicted points sit far from any verified surface — on the backdrop, the support surface, in empty space — not in the holes. A predicted cloud is a coverage instrument, not a repair kit for a verified one. |
| **How the verified densifier behaves away from the bench** | A second campaign took the delivered region onto built frontages and enclosures, vegetated sites and built interiors, scored against site laser scans. Accuracy holds; completeness is the axis that falls, and it recovers quickly as the tolerance relaxes — the reading of a cloud that is coarse for the site rather than missing it. Question the working resolution before the scene. |
| **What the two families cost each other on a capture MVS can solve** | Mirror images: the prior is several times less accurate on the surface it covers and meaningfully more complete. Choose on which error the deliverable can afford, not on which is better. |
