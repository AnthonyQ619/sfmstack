---
module: FeatureTrackUnionFind
module_version: 1.4.0
curated_at: 2026-08-07
---

# When to stop tuning FeatureTrackUnionFind and switch

This module is nearly unfailable in its own right — it is a disjoint-set pass over
a table — so "switching away from it" almost always means switching away from the
*matcher-then-tracker* architecture rather than away from this implementation.

## Contradictory tracks come from the matcher

*Symptom:* `inconsistent_rate` above 0.05, which is where the diagnostic fires.

*Why no parameter here helps:* union-find has no basis on which to reject a match.
Two correspondences sharing an endpoint are, as far as this module can know, the
same scene point. When the matcher says A-B and B-C and A'-C with A and A' both
in image 0, the contradiction is already in the input; all this module can do is
notice it and choose how much of the damage to keep.

`on_conflict` is damage control, not a fix. If you find yourself choosing `first`
to keep `track_count` viable, the matcher is what needs attention.

*What to do:* tighten the matcher's acceptance, then read the matcher's own
limitations.md. **Which knob that is depends on the matcher's family, and naming
the wrong one sends you looking for a parameter that does not exist.** A learned
matcher scores an assignment globally and exposes a single acceptance threshold;
a classical one searches descriptors and exposes a ratio test and a
mutual-consistency check, neither of which a learned matcher has an analogue for
— there is no second-best distance to take a ratio against, and one-to-one is
structural rather than checked. Read the matcher's own parameter list before
choosing the dial.

Repeated structure is the usual underlying cause, and it defeats a ratio test by
construction — which is why the classical route needs the geometric filters
behind it and the learned route does not.

---

## Transitive over-merging

*Symptom:* `max_track_length` exceeding what the view graph could support — a track
observed in more frames than any connected chain of pairs could reach — or
`inconsistent_rate` rising while `track_count` falls.

*Why it happens:* union-find is transitive and unweighted. One false match merges
two entire tracks, and there is no confidence threshold at which the merge is
reconsidered. A single bad correspondence can fuse two long tracks into one wrong
one, and nothing in the algorithm resists it.

This is the structural weakness of union-find track building. It is fast, simple,
and has no notion of evidence.

*What to do:* the practical mitigation is upstream match quality. The principled
fix is a track builder that scores merges rather than performing them
unconditionally — see "what would replace this" below.

---

## Proximity merging is approximate

*Symptom:* on detector-free input, `track_count` and `avg_track_length` are both
sensitive to `merge_eps_px` in a range where you expected them to be stable.

*Why:* with no keypoint table to cite, endpoints are merged by a grid. Four offset
grids guarantee that points within `merge_eps_px / 2` on each axis merge, but
points up to about `1.4 x merge_eps_px` apart *may* also merge, depending on where
the cell boundaries fall. There is no exact radius, and a nearest-neighbour
structure would be needed to provide one.

The bound is deliberately one-sided in the safe direction, but it is a real
approximation. On the measured rig sweep the module was stable between 0.5 and
1.5px and degraded visibly at 4.0.

*What to do:* stay in the 1-2px range for a ~1600px working resolution and treat
a rising `inconsistent_rate` as the over-merge signal. If a dense matcher ever
needs sub-pixel exactness here, that is a reason to add a KD-tree-backed variant,
not to widen the tolerance.

---

## When the whole matcher-then-tracker route is wrong

*Symptom:* the matcher is healthy by its own metrics, this module reports no
conflicts, and `long_track_fraction` still cannot be pushed past ~0.3 even at
exhaustive pairing.

*Why no parameter helps:* pairwise matching discards multi-view information by
construction. Each pair is solved independently, and a keypoint visible in eight
views has to survive seven independent binary decisions to produce an eight-view
track. Learned trackers estimate the whole trajectory jointly and do not pay that
compounding cost.

*Switch to:* a direct tracker — something that produces `tracks/v1` without
consuming `pairwise_matches/v1` at all:

```
sfm_find_modules(produces="tracks/v1", not_consuming="pairwise_matches/v1")
```

**That query returns two modules: `FeatureTrackVGGSfM` and `FeatureTrackTapir`.**
This paragraph used to say it returned nothing, and four readers found the modules
anyway — a reader who trusts the old wording loses the alternative the family file
tells them to compare against.

Either replaces both the matcher and this module in one step, which is why the
query is phrased against the *type* rather than against this module's name. That is
also the reason to reach for one: not more reach, but a different dependency. On a
capture whose matcher is detector-free, this module's precision advantage does not
exist (see the family file), and a predictive tracker has beaten it on BOTH axes.

---

## What would replace this implementation specifically

If the architecture is right and only the merging is weak, the upgrade is a
scored track builder rather than a different pipeline:

- Merge in order of match confidence rather than in input order, so strong
  evidence commits first.
- Refuse a merge that would create a same-frame conflict, instead of performing
  it and cleaning up afterward. This turns `on_conflict` from a post-hoc policy
  into a constraint, and is roughly what COLMAP's incremental mapper does.
- Split a contradictory group into consistent sub-tracks rather than dropping or
  truncating it.

None of these change the artifact type, so such a module would be a drop-in
alternative discoverable through:

```
sfm_find_modules(produces="tracks/v1", excluding="FeatureTrackUnionFind")
```

Recorded here because the measured `inconsistent_rate` values on clean data
(0.0000-0.0018) say this is not yet the binding constraint. Revisit when a
matcher shows up whose conflicts cannot be tuned away.
