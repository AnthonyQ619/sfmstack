# Tuning — SceneTriage

This module measures; it does not produce anything downstream consumes. So
"tuning" here means two different things, and they are worth keeping apart:

- **Changing what is measured** — `pairing`, `patch_size`, `texture_floor`. These
  change the question, and a number produced under a changed question is not
  comparable with one produced under the default.
- **Reacting to what was measured** — the sections below, which are about the
  pipeline you build next, not about this module.

Sourced claims resolve in [sources.md](sources.md).

---

## `combined_change` above 0.28

**Read it as:** appearance is not stable across the set at the scale that costs
descriptor repeatability. Threshold from the predecessor's HIGH label [S1].

**First, decompose it.** The total is `0.45·illumination + 0.35·colour +
0.20·exposure`, and the three have different fixes:

| Dominant component | What happened | Where the fix is |
| --- | --- | --- |
| `illumination_change` | brightness, contrast or the luminance histogram moved | detection — normalise exposure before describing |
| `color_shift` | white balance or colour cast drifted | detection — a descriptor computed on grayscale is unaffected |
| `exposure_shift` | shadow or highlight clipping changed | the capture — clipped regions have lost their detail permanently |

**Gradient:**

1. If `illumination_change` dominates, enable exposure normalisation at
   detection (`grayscale_clahe` on the SIFT module) and re-read `inlier_ratio`
   from the matcher.
   *Expect:* more keypoints in the shadowed regions; no change to the geometry.
2. If `color_shift` dominates and the chosen detector consumes colour, prefer a
   grayscale one. This is a real difference between detector families, not a
   parameter.
3. If `exposure_shift` dominates, the fix is upstream of everything here: those
   frames are candidates for exclusion, because normalisation cannot recover a
   region that is uniformly 0 or 255.
4. Only if `inlier_ratio` then confirms the problem, change matcher family:
   `sfm_find_alternatives(produces='pairwise_matches/v1',
   not_consuming='features/v1')`.

**Do not** treat a high total as a matcher decision on its own. Across the
benchmark corpus this metric has never left a narrow band and has never fired, so
it has no demonstrated discriminating power — the number that decides a family
change is `inlier_ratio`, and this one tells you *why* it fell. (An earlier
version of this note added "and all of them reconstruct" as supporting evidence.
That was an assumption rather than an observation; run to a sparse model, several
captures in that corpus do not fully reconstruct on a classical branch. It does
not change this metric's verdict — `combined_change` is quiet on the failures too
— but the phrase was doing unearned work and is gone.)

**`pairing: all` is the check worth running** when the capture spans time. A set
shot over two hours can have small consecutive deltas and a large
first-to-last one, and the default `consecutive` cannot see it.

---

## `sharpness_ratio` below 0.4

**Read it as:** at least one frame is under 40% of the set's median Laplacian
variance. Relative, not absolute — absolute sharpness depends on content, so the
comparison is against this capture's own frames.

**Gradient:**

1. The diagnostic names the softest frames. Decide whether they are worth
   keeping: a soft frame usually fails to register rather than corrupting the
   model, so the cost is coverage, not correctness.
2. If they are, re-run `SceneLoader` over the subset without them. There is no
   frame-exclusion parameter here on purpose — the scene is the thing that
   defines the image set, and forking it keeps both versions comparable.
3. If nearly every frame is soft, the ratio will look *healthy* while the whole
   set is blurred. Read the per-image `texture/sharpness` array, not the ratio,
   and read `sharpness_median` beside it — that is the number the ratio divides
   by, and it spans roughly eighteen-fold across the corpus. A ratio of 0.7 means
   something different at a low-contrast subject than at a high-contrast one.

**This metric reports content, not focus, on every capture where it has fired.**
Five of five, confirmed by opening the frames at full resolution: the low frames
were aimed at a smooth roof plane, a blank painted wall, or shaded timber, and
were sharply in focus. **Open the frame
before dropping it.** `texture/sharpness` and `sharpness_median` are in the
artifact and in `sfm_plan_brief` for exactly that; the diagnostic names the
frames, and the array says by how much.

**Do not** raise `analysis_max_side` to make sharpness look better. Laplacian
variance rises with resolution; the ratio is designed to be immune to that, and
the absolute values are not comparable across settings.

---

## `textureless_fraction` above 0.35

**Read it as:** more than a third of the median frame has local standard
deviation under `texture_floor`. Detection cannot happen there at any threshold.

**Gradient:**

1. Check what the region is. Sky and water are harmless — they carry no structure
   worth reconstructing. A textureless *wall* is not harmless, because it is
   geometry you wanted. This metric counts area and is blind to which; pair it
   with `empty_regions` from `SceneDescription`.
2. **Check whether the region is burnt or merely flat**, because they have
   opposite gradients. `highlight_clipped_fraction` and
   `shadow_clipped_fraction` answer it, added in 1.1.0 for this. High textureless
   *and* high clipped means detail is destroyed and no exposure normalisation
   recovers it; high textureless with clipping near zero means the detail is
   there at another exposure or scale, and normalising at detection is a real
   move. Measured across sixteen scenes, the three worst-textured split exactly
   that way: two controlled-rig captures reading ~0.60 empty alongside ~0.6
   clipped are blown backdrop and harmless, where a blank-wall interior reading
   0.80 empty against essentially zero clipped is the surface being reconstructed
   — flat, not burnt, and therefore recoverable at higher working resolution or
   with exposure normalisation at detection.

   **When the deliverable is a dense cloud, this pair predicts the dense result
   itself.** Across a batch of studio orbits scored against reference geometry,
   `highlight_clipped_fraction` tracked the MVS stage's own coverage more strongly
   than any dense parameter moved it, and negatively: a burnt region is one a
   photometric densifier cannot correlate, so it comes back as a hole. A capture
   reading high here will lose dense completeness whatever the dense stage is set
   to, and the recovery — if there is one — is exposure at capture or at detection,
   not a looser filter downstream. See
   [plan/dense.md](../../../skills/plan/dense.md).
3. Watch `spatial_coverage` on `features/v1` rather than keypoint count. A
   detector can hit its cap entirely inside the textured third, and a thousand
   keypoints in one corner give a degenerate two-view geometry.
4. Consider a detector-free matcher, which produces correspondences without
   needing a keypoint to exist first:
   `sfm_find_alternatives(produces='pairwise_matches/v1', not_consuming='features/v1')`.

**`texture_floor` is the knob**, and moving it changes the definition. Raise
toward 8 to count faintly-textured surfaces as textureless too; lower toward 3
only when the images are known to be low-contrast overall and the fraction reads
implausibly high.

---

## `repetitiveness` above 0.75

There is no tuning section for this. It is a capability decision, not a
parameter one — [limitations.md](limitations.md#repetitive-structure).

The one thing worth varying is `patch_size`, and it changes the *scale* the
question is asked at rather than the answer: 32px at a 512px long edge is roughly
one brick or one window pane; 64px asks whether whole architectural bays repeat.
A building frontage can score low at one and high at the other, and which one
matters depends on the scale your detector's descriptors cover.

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. The `texture_density`,
`repetitiveness` and `textureless_fraction` bands have no diagnostic reading
them — descriptions of the captures measured so far, not judgements on yours.
The numbers in the `texture_floor`, `patch_size` and `source_dir` advice are
settings that worked here, not published results — and no run here has yet
paired a high `repetitiveness` with a measured `inlier_ratio` collapse, which
is the experiment that metric is waiting on (see the `sources` skill).
