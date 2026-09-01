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
know.** The holes in an MVS cloud are the honest part, and they sit exactly where a
learned prior's output is least trustworthy — specular highlights, shadow, uniform
paint, glass, anything that moved.

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

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **Accuracy against reference geometry** | A dataset with ground-truth surface. Everything measured so far compares one cloud against the triangulated points from the same pipeline, which is a consistency check and not an accuracy one. |
| **What a learned prior buys where MVS fails** | A textureless or reflective scene. Measured so far only where MVS works well, which is the case it is best at. |
| **Whether MVS holes are where the prior is wrong** | The two clouds and a reference surface. The claim that holes mark untrustworthy prediction is the argument for this whole family split, and it is an argument. |
| **The runtime curve** | Wall clock against view count and resolution, on sets spanning both. "Minutes per view" is an order of magnitude, not a model. |
