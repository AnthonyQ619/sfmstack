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

**Give `DenseVGGT` the refined model, not the raw poses.** It accepts either a
`poses/v1` or a `sparse_model/v1` and wants exactly one. Pass the sparse model
whenever one exists, for two reasons. It is the only input that reaches the module
from anywhere downstream of the pose stage — triangulation, the global
reconstructor and both bundle adjusters all produce `sparse_model/v1`, and a
globally-reconstructed pipeline never holds a `poses/v1` at all. And it settles the
scale below, which raw poses cannot.

That was learned the hard way: the module once took `poses/v1` alone, which made
this whole paragraph an impossibility rather than a preference. A specular capture
was sent here by this file, arrived with a bundle-adjusted model, and found nothing
the module would accept.

**A cloud with no holes is not more complete. It is less willing to say it does not
know.** The holes in an MVS cloud are the honest part: they sit on specular
highlights, shadow, uniform paint, glass, anything that moved.

**A hole is a refusal, not an absence.** Measured against reference geometry, with
occlusion accounted for, on captures where every view looks at the same subject from a
different angle: most of the surface the verified densifier missed was visible and
unoccluded in several of that capture's own views — nearly all of it on captures that
miss little, and still a clear majority on the worst. The pixels were there and the
module declined to certify them.
None of the obvious levers reaches them. Changing the sparse model's density,
normalising exposure, loosening the filters and widening the set of views compared all
left the holes where they were. What recovered some was the dense stage's own fusion
policy — see "Delivering the verified cloud". Expect the remainder, and use a learned
densifier if it has to be filled.

**What does not follow is that a learned prior fills those holes.** Tested on every
capture it has been tried on, across both kinds of capture: adding predicted points
*only where the verified cloud is empty* — the repair the family split most invites —
was **never** the best of the four options, not once. Most predicted points do not land
in the holes; they land on the backdrop, the support surface and in empty space. What
*is* capture-dependent is a different question — whether to reach for the prior instead
of the verified cloud — and that is decided by the verified cloud's own completeness;
see [Which end to reach for](#which-end-to-reach-for) and the table at the end.

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

MVS costs tens of seconds per view at the working resolution — measured, not
extrapolated — so a full capture is a half-hour to an hour with the geometric check
on, and up to three times that on a contended device. Feed-forward depth is one
forward pass over the set. **This is often the deciding constraint**, and a pipeline
that spends its budget upstream will not get to run MVS at a resolution worth
having. Plan the dense stage first and the sparse stage around it.

**If you need to buy time, the geometric check and `window_step` are the levers, not
the resolution** — halving `max_image_size` saves under half the time while costing
point count in proportion. The measured costs are in
[DenseMVS tuning](../../modules/dense_mvs/skills/tuning.md#the-runtime-knobs-in-the-order-to-reach-for-them).

### A learned prior carries a scale, again

The same ambiguity as in [sparse.md](sparse.md), with a sharper failure. Unprojection
places each pixel along a ray from **its own** camera, so a wrong scale shrinks each
view's cloud about a *different* centre — the views stop agreeing, and the result is
a smeared or multiplied surface rather than a small one. It looks like bad depth and
is not. Nothing in the metrics moves, because the filters are scale-invariant.

The scale must be measured against correspondences and reported. Assuming it is 1.0
is correct only when the poses came from the same model. Passing the refined model as
`sparse` measures it with no extra input and no re-triangulation, because its points
already sit in the poses' frame; `depth_scale_source` on the output says which of the
three routes the run actually took, and `parameter` means it was never measured.

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

A learned densifier needs only poses — but should be given the refined model
anyway, as its `sparse` input: it is what reaches the module after the pose stage, and
its points are what fix the scale. Tracks are the fallback when there is no model.

---

## Which end to reach for

**MVS** when the cloud has to be right, the scene has texture, and there is time.
Everything it emits was correlated across views and agreed on.

**A learned prior** when coverage matters more than verification, when the scene is
textureless or reflective — where MVS has nothing to correlate and no parameter
invents evidence — or when the answer is needed in seconds rather than an hour.

**And there is one reading that decides between them after the fact: the verified
cloud's own completeness.** Scored both ways on the same captures, the verified cloud
wins wherever its completeness is respectable, and the prior overtakes it — by a wide
margin — on the captures where that completeness has collapsed. It overtakes by being
complete, not by being right: on those same captures it is still the less accurate of
the two. So this is a choice about which error the deliverable can afford, made on a
number you can read, and not a sign that the prior became correct.

**Beware the averaged score here.** Where the verified cloud's completeness has fallen
far enough, a single accuracy-and-completeness average stops separating a tight cloud
from a loose one — a cloud several times worse on accuracy can tie or win on the mean.
Read the two numbers separately whenever coverage is the thing that went wrong.

**Both**, when the question is which parts of the learned cloud to trust: the MVS
cloud is then a mask over it. **Not** as a patch — see above; filling only the
verified cloud's holes was never the best option on any capture tried.

---

## Planning the sparse stage for a dense deliverable

When the deliverable is a dense cloud, it is tempting to treat the sparse stage as
the supply and tune it for what the densifier will consume. That has been tested, and
it is mostly the wrong place to spend effort.

**Measured end to end, there is very little to plan here.** Four sparse-side changes
were run through to a scored dense cloud, on close-range orbits of a compact subject
and not yet anywhere else: the detector's budget, its contrast threshold, exposure
normalisation at detection, and the refiner's minimum track length. Three of them
changed the sparse model substantially — between
three fifths smaller and half again larger — and **none moved dense completeness by as
much as a thousandth of a millimetre.** The fourth changed nothing at all, for a reason
worth knowing: the detector's `saturation` was 0.000 on every capture, so its budget
was never the binding constraint and doubling it returned an identical model.

**So do not spend runs tuning the sparse stage for dense coverage.** There is an
association across captures, but it holds on one kind of capture only: where a compact
subject is orbited at close range it is strong, and where the capture is a site — a
frontage, an enclosure, a vegetated area — it is absent. And on neither kind does it
survive as a lever: change the density *within* a capture and the dense result does not
move. What fits both halves is one confound — captures that are hard for the detector
also tend to be hard for the densifier, without either causing the other — and on a site
the two difficulties are set by different things, so even the association goes away.

**What decides the dense result is the dense stage's own policy**, not its input:
`fusion_min_num_pixels` and `geom_consistency` moved completeness by two orders of
magnitude more than any of the above. See "Delivering the verified cloud" below.

**Where thin models and poor dense coverage do go together, do not assume the
mechanism is per-view starvation.** On close-range orbits of a compact subject the two
track each other across captures, and `min_frame_points` can sit near zero while
`point_count` looks healthy, so it is still worth reading. Two things qualify it.
The association is **absent on site captures**, so a thin model there says nothing
about the dense result. And on neither kind does the causal story hold: measured
inside a capture, a view's own sparse structure does not predict where that view's
depth map comes back empty — the correlation is near zero and its sign flips between
captures. So read a thin model as a sign the capture is hard, and only where the
subject's own surface is what limits it; **do not spend a run raising the keypoint
budget to lift one starved view** in the belief that it will fill that view's holes.

**What does track the holes is how many views see the surface *well*.** Surface the
densifier missed was exposed and textured in fewer views than surface it covered, on
every capture measured. **How much fewer is what varies, and it varies with how much
the capture misses.** Where a capture loses only a few percent of the reference
surface, missed and covered surface are seen about equally well and the reading tells
you little; where it loses a tenth or more, missed surface drops to single figures
against the twenties. So the reading earns its keep on the captures that are already
going badly, and is near-silent on the ones that are not. This describes why a region
stays a hole; it is not a setting. Comparing each image against every other view —
which gives any well-exposed view the chance to be used — recovered nothing and cost
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
cloud, through placement rather than coverage. Focal length trades against depth, so
the optimiser can buy a lower reprojection error by resizing the scene. Tested
directly — the same models refined twice, once with the focal fixed and once free —
it came out the same way **every time, on both a close-range orbit and a site**:
the reprojection error improved and the model moved between one and a half and five
times further out of place. It is the one sparse-side decision on this page that has
been shown to reach the dense result, and the only one measured on both kinds of
capture. See [optimization.md](optimization.md).

**Two readings to take before spending an hour on MVS:** the model's overall
density, and the capture's clipped-highlight reading from `SceneTriage`. The second
predicted the dense stage's own coverage more strongly than any parameter moved it
— a capture reading high on blown highlights loses dense coverage before the dense
stage starts, and the honest response is to expect the loss, not to loosen filters
afterwards. **That was measured on lit close-range orbits and has not been confirmed
anywhere else**: on site captures the per-view coverage metric it was read against is
usually not produced at all, and the highlight readings there span a couple of percent
where the orbits spanned most of the range. Treat it as a strong reading on a lit
bench and an untested one outdoors. **Neither is a lever you can pull to fill a
specific hole**: blown
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

**That default is the safe choice under ignorance, not the better cloud.** It is right
when something downstream will fit geometry to the cloud, because a stray point there
costs more than a hole. It is the wrong end of the trade when the cloud itself is the
deliverable and will be judged as a whole — a balanced accuracy-and-coverage score
charges the hole and the stray equally, and a tightly fused cloud gives up more on the
one than it gains on the other, particularly where coverage is already the weaker half.
**So depart from the default only when the task names a use that says to**; do not
guess at how the result will be judged, and do not loosen fusion in the hope of a
better score.

**Look at the cloud before you accept it.** Every densifier's published readings are
scalars, and none of them separates a clean surface from a clean surface wrapped in
strays — a cloud can carry a healthy point count, a healthy view count and a plausible
confidence while a support surface has been fused into the subject, or a face has been
reconstructed twice at slightly different depths. Each dense module writes
`browse/cloud_views.png`: three orthographic views, two from the plane the cameras
occupy and one down its axis. Fetch it with `sfm_artifact_image`. The off-ring panel is
the one that earns its place, because everything listed above sits behind the surface
from every camera and is invisible until you leave the ring. Treat it as a check on the
numbers, not as a measurement — it is framed on the bulk of the cloud and quantifies
nothing.

**Plan a `DenseFusion` exploration only when the capture is unlike the ones
measured.** It needs the stereo pass kept (`keep_workspace: true`), which is large on
disk; after that each fusion setting costs seconds, and point counts alone say where
to stop. The route from an output you already have is one replay:
[DenseFusion SKILL, "Before you run it"](../../modules/dense_fusion/skills/SKILL.md#before-you-run-it).

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **What a learned prior buys where MVS genuinely has nothing** | A capture whose target surface is textureless or reflective, with reference geometry. Both families have now been measured, but only on captures where MVS works well — which is the case MVS is best at and the case the prior is least needed in. Until recently the module could not be reached from a refined model at all, so this question has never actually been asked on the captures that motivate it. |
| **The runtime curve against view count** | Cost per view is now measured across two campaigns and the resolution and check scalings with it (below). What is still unmeasured is whether cost per view is flat in the size of the set — every capture measured sat near fifty views. |

**Runtime is no longer one of them.** Over a hundred timed stereo runs across two
campaigns put the working resolution with the geometric check on at around forty
seconds per view, so a fifty-view capture is about half an hour and up to three times
that on a contended device. The scalings that hold and the one that does not — halving
the resolution buys far less than the old quadratic rule promised — are in
[DenseMVS tuning](../../modules/dense_mvs/skills/tuning.md#the-runtime-knobs-in-the-order-to-reach-for-them).

## What HAS now been measured, against reference geometry

Two campaigns, each capture solved from raw frames to a dense cloud and scored against
reference surface geometry: close-range orbits of compact subjects against a laboratory
reference, and site captures — built frontages and enclosures, vegetated areas, built
interiors — against site laser scans. **Where a row below is true of only one of the
two, it says so.** A row that names neither was measured on both.

| Question | Answer |
| --- | --- |
| **Accuracy against reference geometry** | The verified densifier is accurate at the fine tolerance the reference geometry can resolve; what it loses is completeness, by a factor of roughly one and a half to two on the same captures. |
| **Whether MVS holes are where the prior is wrong** | **No, on both kinds of capture, and this was the argument for the family split.** Four clouds were scored on every capture tried — verified alone, predicted alone, their union, and the union filtered to predicted points where the verified cloud is empty. **That last one, the repair, was never the best of the four on any capture.** Most predicted points sit far from any verified surface — on the backdrop, the support surface, in empty space — not in the holes. A predicted cloud is a coverage instrument, not a repair kit for a verified one. |
| **Whether the verified cloud is always the one to deliver** | **No — and which one wins is readable in advance.** On captures where the verified cloud's completeness holds up it wins comfortably; where that completeness has collapsed the prior, and the plain union, overtake it by a wide margin. The prior is the less accurate cloud in both cases, so this is the accuracy-against-coverage trade being resolved by how much coverage was lost, not the prior becoming correct. Read the two components rather than their average, which stops discriminating exactly in the cases where this question arises. |
| **How the verified densifier behaves away from the bench** | A second campaign took the delivered region onto built frontages and enclosures, vegetated sites and built interiors, scored against site laser scans. Accuracy holds; completeness is the axis that falls, and it recovers quickly as the tolerance relaxes — the reading of a cloud that is coarse for the site rather than missing it. Question the working resolution before the scene. |
| **What the two families cost each other on a capture MVS can solve** | Mirror images: the prior is several times less accurate on the surface it covers and meaningfully more complete. Choose on which error the deliverable can afford, not on which is better. |
