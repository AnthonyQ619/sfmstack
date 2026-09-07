# Limitations — SceneTriage

What this module cannot tell you, and where its numbers stop meaning what they
look like they mean.

---

## Repetitive structure

**The failure signature:** `repetitiveness` high, `texture_density` high,
`textureless_fraction` low — a scene rich in detail where the detail repeats.
Downstream this looks like plenty of keypoints, plenty of matches, and an
`inlier_ratio` that collapses under geometric verification. It is the case where
every number before the verification step looks excellent.

**But do not trust this metric to tell you the signature is present.** It
template-matches a patch against elsewhere in its **own image**, and
`matchTemplate` is not scale invariant. Two consequences, both observed:

- **A subject whose repeating elements recede in perspective reads LOW** — a long
  frontage of bays, a colonnade, a receding row of windows. A near element does
  not correlate with a far one, so the most repetitive subject in a corpus can
  produce the lowest reading in it.
- **A fronto-parallel grid of identical panels reads HIGH** for a purely geometric
  reason, whether or not its ambiguity is actually hard to resolve.

**The reading is dominated by viewing geometry, not by ambiguity**, and the
ordering across a corpus is therefore not trustworthy. Worse, the hazard that
breaks reconstructions is *between-image* ambiguity — element `n` in one frame
matching element `n+1` in the next — and this measurement is within-image only.
See "What this cannot see" below.

**Use `repetition_notes` from `SceneDescription` as the primary reading** and this
number as weak corroboration. A viewer can see that two windows are the same
window; no within-image correlation can.

**Why no parameter recovers it.** Descriptor matching decides correspondence by
appearance. When two different scene points have the same appearance, the ratio
test — which compares the best match to the second-best — sees two equally good
candidates and rejects both, or sees one marginally better and accepts the wrong
one. Lowering the ratio threshold trades the second failure for the first. There
is no setting where a locally-computed descriptor distinguishes two identical
windows, because the information needed is not local.

**The capability escape:** something that reasons about more than a patch —
global context, or the whole image pair jointly.

```
sfm_find_alternatives(produces='pairwise_matches/v1')
```

and read [`skills/plan/matching.md`](../../../skills/plan/matching.md)
before choosing. This module cannot tell you *which* alternative; it tells you
that the choice is a family one.

**What the measurement actually is:** the median patch's best correlation with a
*different* location in its own image. It is within-image self-similarity, not
between-image ambiguity. A scene of forty photographs of forty different
identical-looking buildings would score low here and defeat matching just as
thoroughly. That case is not measured.

---

## Textureless scenes

**The failure signature:** `textureless_fraction` high, `texture_density` low.
Downstream: low `keypoints_per_image`, and more importantly low
`spatial_coverage` — the keypoints that exist are clustered.

**The limit of the measurement:** it counts area below a contrast floor and says
nothing about *where* that area is. A frame that is 40% sky and a frame with a
40% blank wall across its middle score identically, and only the second is a
problem, because the sky carries no structure anyone wanted. Read the images, or
read `spatial_coverage` once a detector has run.

---

## The bands here are provisional

Every `healthy` band on this module was set from ten ETH3D and DTU scenes at 12
images each [S4]. That is enough to see the range and not enough to place a
boundary in it.

Specifically:

- **`repetitiveness` measured 0.62–0.81** across those ten, ordered plausibly —
  natural terrain lowest, brick facades highest — **with no gap to cut at.** The
  band sits at 0.75 because that is where the two known-repetitive facades fall,
  which is a description of the sample, not a validated threshold. The warn fires
  at 0.80 so that it stays rare.
- **`combined_change` measured 0.055–0.116**, and the band's 0.12 ceiling comes
  from the predecessor's LOW/MEDIUM cut [S1] rather than from these scenes. Nothing
  in the sample exceeded it, so the ceiling is untested in the direction that
  matters.

Treat all of them as a reading rather than a verdict, and expect them to be
revised from the agent-driven runs.

---

## Order is inferred from filenames

`ordered` is a heuristic when EXIF is absent, and EXIF is usually absent — see
below. The test is: every filename ends in digits, the digits increase across the
set in filename order, and their span is under four times the image count.

**It passes things it should not.** `0001.jpg … 0040.jpg` and `DSC_0287.JPG …
DSC_0326.JPG` are genuine capture sequences and pass. But so does an unordered
collection that someone renamed `img_001 … img_040` — the numbering is real and
the order it implies is not. The images are also *already* sorted by filename by
`SceneLoader`, so "increasing" is nearly free and the span test is what carries
the discrimination.

**When it matters:** `ordered = 0` is trustworthy — no digits means no sequence.
`ordered = 1` is a weak claim. If a video-trained tracker or sequential pairing
is being chosen on the strength of it, supply `source_dir` and get the answer from
timestamps instead.

---

## EXIF does not survive the scene artifact

`SceneLoader` with any resize policy other than `none` decodes each image and
re-encodes it as PNG into the artifact. That is deliberate and it is what makes
downstream containers independent of the dataset — but it discards every EXIF
tag, so `capture_interval_s` and `focal_35mm` cannot be recovered from the scene.

**The workaround** is the `source_dir` parameter, which reads the original files
by the names the scene recorded, for metadata only. Pixels still come from the
artifact.

**The real fix** is for `SceneLoader` to carry the EXIF it read into `scene/v1`,
which would make this module's metadata block work unconditionally and would let
the loader sanity-check a supplied calibration against the lens that took the
photographs. That is a change to `scene/v1` and has not been made.

---

## What is not measured at all

Named because their absence is easy to mistake for a clean result:

- **Dynamic content.** People and vehicles corrupt tracks silently. Detecting them
  needs the flow residual after fitting a global motion model, which lives on the
  `SceneMotion` side and is not implemented there either.
- **View-graph shape.** Whether the capture is a chain, a loop, or an unordered
  set — cheap from global descriptors, and it decides whether loop closure is
  even available. Not implemented.
- **Between-image ambiguity**, as distinct from within-image self-similarity. See
  the note under [repetitive structure](#repetitive-structure).
