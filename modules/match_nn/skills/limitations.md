---
module: FeatureMatchNN
module_version: 1.6.0
curated_at: 2026-08-07
---

# When to stop tuning FeatureMatchNN and switch

Tuning has a ceiling here, and it is set by the descriptor, not by this module.
Nearest-neighbour matching asks one question — "which descriptor in image B is
closest to this one in image A?" — and when the descriptor cannot answer it, no
parameter here can.

The signal that you have hit the ceiling: `inlier_ratio` stays below ~0.3 after
lowering `ratio_test` to 0.7 and raising `ransac_threshold`, **and** the detector's
`keypoints_per_image` is healthy. Plenty of keypoints, plenty of candidate
matches, and almost none of them agree with any two-view geometry.

## Finding a replacement

The escape is expressed as a capability query, not a module name, so it keeps
working as modules are added:

```
sfm_find_alternatives(produces="pairwise_matches/v1", excluding="FeatureMatchNN")
```

For the detector-free case specifically — where the answer is to stop detecting
keypoints at all — the query is for something that produces matches without
consuming features:

```
sfm_find_alternatives(produces="pairwise_matches/v1", not_consuming="features/v1")
```

That returns nothing today. When it does, the module it returns will need no
detector upstream and will emit matches with no `feature_index`, which the tracker
already handles via its proximity merge path.

---

## Textureless regions

*Symptom:* the detector reports low `spatial_coverage` and keypoints clustered on
a few high-contrast objects; matching is fine on those and the rest of the frame
contributes nothing. The reconstruction covers a fraction of the scene.

*Why no parameter helps:* SIFT found nothing in the flat regions to describe, so
there is nothing here to match. Lowering `contrast_threshold` upstream produces
detections in noise, which match wrongly rather than not at all.

*Switch to:* a detector-free matcher (LoFTR, RoMa). They estimate dense
correspondence fields directly and do not need a repeatable interest point.

---

## Repeated structure

*Symptom:* healthy match counts, `inlier_ratio` between 0.2 and 0.4, and the
tracker reporting a raised `inconsistent_rate`. Lowering `ratio_test` to 0.7
improves the ratio but leaves `matches_per_pair` too thin.

*Why no parameter helps:* the ratio test compares a keypoint's best match to its
second best. On a facade of identical windows those two are equally good by
construction, so the test cannot separate them — it rejects both the right answer
and the wrong one. This is a limitation of the *criterion*, not of its threshold.

The dangerous version is when repetition survives verification: a consistent set
of wrong matches between two repeated units fits a fundamental matrix perfectly
well. High `inlier_ratio` with a high tracker `inconsistent_rate` is that
signature.

*Switch to:* a learned matcher (LightGlue, SuperGlue). They reason about the
match set jointly rather than per-keypoint, which is exactly the information the
ratio test throws away.

---

## Wide baselines and large viewpoint change

*Symptom:* consecutive pairs match well, but the pairs that would close a loop or
link distant views all fall under `min_matches` — so `graph_components` stays above
1 no matter how far `window` is raised, or `exhaustive` finds nothing that
`sequential` did not.

*Why no parameter helps:* SIFT's descriptor is invariant to scale and in-plane
rotation but not to out-of-plane rotation. Past roughly 40-50 degrees of viewpoint
change the descriptors of the same patch stop resembling each other.

The window sweep in [tuning.md](tuning.md) shows the benign version of this:
beyond window 8, that capture stopped producing new pairs entirely. That was a
correctly ordered capture where the far views really do share nothing. The
malignant version is the same reading on a set where you know the views overlap.

*Switch to:* a learned matcher first; if that also fails, the capture needs more
images, not a better matcher.

---

## Photometric instability

*Symptom:* `inlier_ratio` varies wildly between pairs within one scene, and the
weak pairs correlate with exposure or lighting changes rather than with baseline.

*Try first:* the detector's `grayscale_clahe`, which raises repeatability across
exposure changes rather than just raising counts.

*Switch to:* a learned matcher. They are trained across illumination change; SIFT's
gradient-orientation histogram is only invariant to affine intensity change, which
real relighting is not.

---

## Planar and rotation-only captures

*Symptom:* `planarity` above 0.9.

**Not a matcher problem, and not fixable by swapping matchers.** The explanation
and what to do instead are owned by `plan/matching.md` section 5, "`planarity`
is the one metric here whose answer is not a matcher" -- read it there rather than
here, because three matcher files used to restate it and drifted apart in wording
while agreeing in substance.

The one module-local note: widening the baseline here means raising `window`.

Recorded because it is the failure most likely to be misdiagnosed as a matching
problem: every matching metric can look excellent while the reconstruction
collapses.

---

## When NN matching simply fails

`pairs_matched` is 0 and the module raised rather than producing an artifact. In
order of likelihood:

1. **A starved frame.** Check the detector's `keypoints_min`. One frame with
   almost no keypoints breaks every pair it is in.
2. **Wrong ordering.** `pairing: sequential` trusts SceneLoader's order. For an
   unordered collection that order is alphabetical and means nothing — use
   `exhaustive`.
3. **Verification rejecting everything.** Re-run with `geometric_model: none`. If
   matches appear, the correspondences exist but no consistent geometry does,
   which usually means the images are not of the same scene, or the pairs are
   pure rotation about the optical centre.
4. **Descriptors from a different detector than the matcher expects.** Binary
   descriptors (ORB) need Hamming distance; this module reads the `binary` flag
   in the features artifact and switches automatically, but a detector that
   writes uint8 descriptors *without* setting that flag will match under L2 and
   produce garbage.
