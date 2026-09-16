# Dense reconstruction — choosing a densifier

Everything that produces `dense_model/v1`. Two modules, and the difference between
them is not degree.

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
So the lever sits upstream — photometry and structure — and not in the filters.

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

When the deliverable is a dense cloud, the sparse stage stops being an end in
itself and becomes the supply. Choose its settings for what the densifier will
consume, which is **coverage** — and accept that this is not the same model you
would ship if the sparse model were the product.

**Coverage is the requirement, not a tie-breaker.** Measured over a batch of
studio orbits of compact subjects at tens of views: the captures whose dense clouds
were most complete are the ones whose sparse models were broad and a little noisy,
and models pruned to long clean tracks produced the sparsest depth maps at equal
registration and equal reprojection error. A model that is clean and thin is worse
input here than one that is broad and slightly self-contradictory.

**The floor that matters is the thinnest view, not the model.** A model thin in
*any* view starves that view's depth map, and a whole-model point count cannot show
it — `min_frame_points` can sit near zero while `point_count` looks healthy. Raise
the keypoint budget and lower the contrast threshold until the *worst* view clears
a floor rather than until the mean looks well, and read
[feature_sift tuning](../../modules/feature_sift/skills/tuning.md) for which knob
moves which case.

**Matching and tracking: lean towards keeping weak correspondences.** A
correspondence only two cameras support still carries surface the densifier needs,
and the batch found broad track tables feeding MVS better than clean thin ones.
**This is a lean, not a licence.** Keeping everything also keeps the mismatches,
the pose stage still has to survive what the matcher hands it, and on repeated
structure a permissive matcher fails in the way [matching.md](matching.md)
describes rather than in a way more points can fix. Where the two pages disagree
about a capture, the matching page is about whether the capture solves at all and
wins; this page is about what the dense stage is fed once it does.

**Triangulation and refinement: treat `min_track_length` as a dense decision.**
Raising it, or tightening a reprojection filter, buys a better-looking error rung
by deleting the two-view structure that covers the parts of the subject only two
cameras see well — which is exactly where the holes appear. Nothing downstream
recovers those points. Decide it against the deliverable, not as hygiene.

**Do not refine intrinsics on a calibrated capture to get there.** An orbit lets
focal length trade against depth, so the optimiser can buy a lower reprojection
error by resizing the scene; measured on this batch, freeing the focal improved the
error and moved the cloud several times further out of place. See
[optimization.md](optimization.md).

**Two readings to take before spending an hour on MVS:** the per-view point floor
above, and the capture's clipped-highlight reading from `SceneTriage`. The second
predicted the dense stage's own coverage more strongly than any parameter moved it
— a capture reading high on blown highlights loses dense coverage before the dense
stage starts, and the honest response is to expect the loss, not to loosen filters
afterwards.

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
| **What the two families cost each other on a capture MVS can solve** | Mirror images: the prior is several times less accurate on the surface it covers and meaningfully more complete. Choose on which error the deliverable can afford, not on which is better. |
