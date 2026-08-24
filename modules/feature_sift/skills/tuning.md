# Tuning — FeatureDetectionSIFT

Indexed by what you observe, not by parameter. Sourced claims carry a tag
resolved in [sources.md](sources.md). **Observed** sections come from real runs
and carry their scene context, because a DTU number need not transfer to ETH3D.

---

## `saturation` near 1.0

**Read it as:** every image is hitting `max_keypoints`. The cap is what limits
detection, not the image content — SIFT found more and OpenCV discarded the
weakest by contrast score [S1].

**Gradient:**

1. `max_keypoints` ×2. This is the whole answer when saturation is 1.0.
   *Expect:* keypoint count roughly doubles, runtime and descriptor memory scale
   linearly, `spatial_coverage` rises as detections reach flatter regions.
2. Repeat while saturation stays near 1.0 **and** downstream track survival is
   still the binding constraint.

**Stop when** saturation reaches **zero**, not when it drops below a half. Any
non-zero saturation means some frames returned your parameter and others returned
the capture, so `keypoints_per_image` is a blend of a measurement and a setting and
cannot be compared to anything — not to another parameter setting, and certainly
not to another detector. The `cap_binding` diagnostic will not help you here: it
fires only when *most* images are pinned, so the entire partial band is silent.

**Do not** raise the cap to fix low counts when saturation is already zero. That
is the contrast filter binding, not the cap; see the next section.

**The most useful thing this section does is come first.** Across a set of captures
each analysed cold, every one came back partly or fully saturated at the module
default, and most of them then settled on nothing more than the raised cap. Treat
"raise the cap until saturation is zero, then read the numbers" as the entry
condition for reading this file at all, rather than as one of its branches.

### Observed

> **L-0001 · Doubling from 1024 to 8192 on DTU scan1**
> **Run:** first real pilot, 2026-08-08 · **Seen in:** 1 run · **Confidence:** low
> **Context:** DTU scan1, 8 images, 1600×1200, calibrated, well-lit turntable object.
> **Observed:** 1024 → mean 1024/image, saturation 1.00, coverage 0.65.
> 8192 → mean 7672/image (min 4677), saturation 0.75, coverage 0.80.
> **Takeaway:** at 8192 the cap is no longer fully binding on this kind of scene,
> and coverage gained more than count did. The coverage move is the part that
> matters for geometry.
> **Untested:** whether the extra keypoints survive matching; no downstream
> module existed at the time of measurement.

> **L-0002 · The coverage half of L-0001 does not transfer**
> **Run:** detection phase, five captures analysed cold · **Seen in:** 4 captures
> **Confidence:** medium — consistent across four, and the mechanism is understood.
> **Context:** DTU scan10/scan15/scan33 and ETH3D facade, 12 images each at ~0.7-0.8 MP.
> **Observed:** raising the cap to clear saturation reliably did what L-0001 says
> for *count*, and reliably did not for *coverage* — the coverage move was an order
> of magnitude smaller than L-0001's on every one, and on one capture raising the cap
> a second time returned a byte-identical artifact.
> **Takeaway:** the count gain is a property of the cap; the coverage gain in L-0001
> was a property of that particular scene having reachable flat regions left. Where
> the uncovered cells are **destroyed detail** rather than merely flat — a blown-out
> backdrop, clipped sky — no cap reaches them, and neither does lowering
> `contrast_threshold` or enabling CLAHE.
> **Scope — read this before applying the above.** All four captures behind L-0002
> had *destroyed* empty regions. The rule does not extend to captures whose empty
> regions are merely flat; see [L-0003](#l-0003). Check
> `highlight_clipped_fraction` / `shadow_clipped_fraction` and the description's
> `empty_regions` before predicting a ceiling.
> **Untested:** whether the extra keypoints survive matching. Still true two
> observations later, and it is the question this stage cannot answer.

> <a id="l-0003"></a>
> **L-0003 · Where the empty region is FLAT, coverage moves — and it is the cheapest
> test of which kind you have**
> **Run:** detection phase, twelve further captures analysed cold · **Seen in:** 3
> captures moving, 8 not · **Confidence:** medium-high — the two groups separate on
> a reading available before the run.
> **Context:** ETH3D delivery_area, office, courtyard, 12 images each at ~0.7 MP.
> **Observed:** on a loading-bay capture whose large empty region is a flat panel
> door at a heavy downscale — unclipped, `highlight_clipped_fraction` effectively
> zero, and graded *merely flat* by the description — halving `contrast_threshold`
> moved `spatial_coverage` **0.910 → 0.987** in one step. That is an order of
> magnitude more than L-0002's captures moved under any parameter. A dim interior
> behaved the same way: two levers together took coverage from 0.352 to 0.725.
> **Takeaway:** predict the coverage move before the run, and let the *prediction*
> be the instrument. Destroyed cells cannot be reached by any parameter, so a
> coverage number that will not move is a ceiling. Flat-but-unclipped cells can be
> reached, so a coverage number that *does* move tells you the detail is genuinely
> present at this working resolution — which is a positive result about the capture,
> not merely a tuning success, and it is the confirmation the description's
> flat-versus-burnt call was right. **The two cases are distinguishable before you
> run anything**: the clipping fractions and `empty_regions` separate them.
> **Also observed:** a coverage number can be *exhausted* rather than capped. Past
> roughly 0.99 on an 8×8 grid the metric is inside its own quantisation — under a
> cell per image — and stops discriminating between runs or between detectors. Stop
> reading it there rather than chasing the last cells.
> **Untested:** whether keypoints recovered from a flat region match as well as
> keypoints from a textured one. They are lower-contrast by construction, so this is
> the obvious place for the stage's standing unknown to bite.

---

## `keypoints_per_image` low while `saturation` is low

**Read it as:** SIFT is rejecting candidates before the cap applies. The image is
dim, flat, or soft.

**Gradient:**

1. `contrast_threshold` 0.04 → 0.02 → 0.01. This is the dominant knob here: it
   is the low-contrast rejection test, applied per octave layer [S1].
   *Expect:* counts rise substantially on dim scenes; below ~0.01 the added
   detections are noise and repeatability falls.
2. `grayscale_clahe: true` — for either of **two** indications, and this file used
   to name only the first.
   *Across-set:* strong shadow/highlight variation between frames. The point there
   is not the extra keypoints in dark regions but that equalisation makes detection
   more *repeatable* across frames of different exposure.
   *Within-frame:* a dim or low-contrast capture whose **wanted** surface is flat
   but unclipped. CLAHE equalises over local windows, so it works on within-frame
   contrast regardless of whether the set varies — and this is where its largest
   measured gains have come from, on captures whose across-set photometric readings
   were at the bottom of the observed range. Written the old way, the file
   contraindicated the parameter on the very captures it then won on, and several
   readers noticed the collision between the module's stated rationale and the
   description's recommendation for their capture.
   **The count is not the test.** CLAHE lifts every low-contrast region, and where a
   large unwanted one exists — loose aggregate, lawn, sky — most of the gain lands
   there: counts up by tens of percent while the subject's *share* of the budget
   falls. Two cheap checks: does `keypoints_min` rise faster than the mean (a
   targeted gain on the starved frames looks like that), and do the extra keypoints
   land in the region `empty_regions` calls wanted. Where neither can be answered,
   prefer the knob whose effect you can predict.
3. `sigma` 1.6 → 1.0 if the inputs are soft or slightly out of focus. The default
   assumes the image already carries ~0.5 of blur [S1]; over-smoothing a soft
   image destroys the extrema.

**Check the scene first — but check the right flag.** `heavy_downscale` is a ratio
and fires on every large-sensor source regardless of whether anything is starved;
`low_working_resolution` is keyed on the megapixels that survived and is the one that
means something. If *that* fired, the keypoints were thrown away before SIFT ever
ran, and the fix is a new scene at a larger working resolution rather than looser
thresholds here — `max_edge` under `resize: auto`, `target_resolution` under
`resize: fixed` or `square`. A scene cannot be resized in place, so this rebuilds
every id downstream, which is why it is worth confirming the detector is actually
starved first: read `keypoints_min` against `keypoints_per_image` and see whether the
counts are near the floor or merely uneven.

That is a pointer, not an ordering rule; loosen here first if you prefer, but where
the resolution really is the constraint the scene fix is much the larger effect.

---

## `keypoints_min` below 200 while the mean is healthy

**Read it as:** the set is uneven. One or a few frames are starved, and the mean
is hiding them.

**Why it matters more than the mean:** tracks chain through consecutive frames. A
single frame with 150 keypoints breaks every track passing through it, so the
worst frame bounds multi-view support for the whole sequence — not the average.

**Gradient:**

1. Look at *which* frame. The diagnostic names it. If it is motion-blurred or
   points at a blank wall, no parameter fixes it; drop the frame at the scene
   level instead.
2. `contrast_threshold` down, as above — helps the dim frames without hurting the
   good ones, since the good ones are cap-limited anyway.
3. `grayscale_clahe: true` if the starved frames are the dark ones specifically.

---

## `spatial_coverage` below 0.35

**Read it as:** detections are clustered. A thousand keypoints in one corner give
a degenerate two-view geometry no matter how many there are — the estimated
essential matrix is poorly conditioned when correspondences do not span the frame.

**Gradient:**

1. `contrast_threshold` down, to reach the flatter regions that are currently
   filtered out.
2. `max_keypoints` up, but only if `saturation` is high — otherwise the extra
   budget goes unused.

**If coverage stays low after both**, the uncovered regions are genuinely
textureless and no detector setting will populate them. That is a
[limitations](limitations.md#textureless-regions) case, not a tuning one.

---

## Parameters that are rarely the answer

- **`n_octave_layers`** — 3 is the value from the original paper's own
  evaluation [S1]. Raising it finds more scale-intermediate keypoints at roughly
  linear cost, but it is not the lever when counts are low.
- **`edge_threshold`** — note its sense is *opposite* to `contrast_threshold`:
  higher keeps **more** edge-like keypoints. It is a principal-curvature ratio
  limit [S1]. Raise it only when the scene's real structure is linear (girders,
  window frames) and you accept keypoints that localise poorly along the edge.
- **`root_sift`** — leave on. It is two vector operations and strictly better for
  L2 matching [S2]; there is no scenario in this pipeline where turning it off is
  correct.
