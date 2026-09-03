---
module: FeatureMatchNN
module_version: 1.6.0
curated_at: 2026-08-07
---

# Tuning FeatureMatchNN

Order matters. Fix the view graph first, then the ratio test, then the RANSAC
threshold. Tuning the ratio test on a disconnected graph is wasted work.

## The order to work in

1. `graph_components` == 1? If not, raise `window`. Nothing else matters yet.
2. `inlier_ratio` above 0.5? If not, lower `ratio_test` or raise
   `ransac_threshold` — see below for which.
3. `matches_per_pair` and `min_matches_per_pair` healthy? If not, the fix is
   usually **upstream** in the detector, not here.
4. `planarity` below ~0.9? If not, the capture geometry is the problem and no
   matcher parameter helps.

---

## `graph_components` above 1

The view graph is disconnected. Raise `window` until it reaches 1, then stop —
past that point the extra pairs cost time and find almost nothing.

**Measured on a turntable capture of a compact object, sampled UNIFORMLY so that
index distance tracks viewpoint distance, 12 images, SIFT at defaults.** That
sampling property is not a footnote — it is the precondition for everything below,
and the next section is what happens without it. Only `window` changes:

| window | pairs kept | matches/pair | inlier_ratio | components | tracks | long_track_fraction | min_frame_obs |
|-------:|-----------:|-------------:|-------------:|-----------:|-------:|--------------------:|--------------:|
| 1 | 10 | 259 | 0.907 | **2** | 2404 | 0.062 | 19 |
| 2 | 16 | 237 | 0.905 | **2** | 2987 | 0.164 | 19 |
| 4 | 30 | 217 | 0.905 | 1 | 3716 | 0.320 | 79 |
| 8 | 39 | 175 | 0.894 | 1 | 3744 | 0.325 | 94 |
| exhaustive | 39 | 175 | 0.894 | 1 | 3744 | 0.325 | 94 |

Three things to take from this.

**Window 4 is where this capture connects.** Below it the set is two halves with
no link between them, and `long_track_fraction` is stuck near zero because tracks
cannot cross a gap that was never matched.

**Window 8 and exhaustive were identical HERE, and that does not generalise.**
Every pair beyond window 8 fell under `min_matches`, because on this capture the
camera goes around once and never comes back, so far-in-index really is
far-in-viewpoint and those views share nothing.

**The property that makes that true is that the trajectory never revisits.** When
it does, the same reasoning inverts, and it inverts hard: on a capture whose path
folds back on itself, the single strongest pair in the whole set was a far-index
one, and non-adjacent pairs carried the majority of all verified correspondences —
around a third of them at separations of six or more. A window sweep on that
capture stops improving long before it reaches the fold, so "raising `window` has
stopped changing `pairs_matched`" reads as convergence when it is a plateau
between two humps. Sequential pairing would have discarded the loop closure and
reported a healthy `graph_components` while doing it.

Two cheap ways to know which kind of capture you have, before spending the sweep:

- **Ask whether the ordering means anything.** A capture with a `sampling` that
  subsamples an ordered rig is not the same shape as one that took the first N
  frames, and the brief does not say which you got — the scene artifact's own
  provenance does.
- **Read the per-pair rotations for a reversal.** One adjacent pair rotating far
  less than its neighbours is the trajectory turning around; the fold centre sits
  there, and the match counts will show a second hump across it.

So: check whether raising `window` has stopped changing `pairs_matched` before
reaching for `exhaustive` — and on any capture that might revisit, confirm it
against one exhaustive run rather than against the plateau. At a dozen images the
exhaustive run costs seconds and settles it.

**`matches_per_pair` falls as the graph improves** (259 → 175). Newly admitted
pairs are wider-baseline and thinner, which drags the mean down while making the
reconstruction strictly better. This metric is a mean over surviving pairs and
moves in the wrong direction under exactly the change you want. Judge it beside
`pairs_matched`, never alone.

**When to use `exhaustive` instead of a large window:** unordered photo
collections, and any capture where the images are not in trajectory order at all.
`sequential` assumes SceneLoader's ordering is meaningful; for a folder of
holiday photos it is alphabetical, which is nothing.

### When `exhaustive` does not fix it either, look two stages upstream

**Measured on one ordered rig capture, 6 images, SIFT at 2048 keypoints,
`pairing: exhaustive` in both cases.** Only SceneLoader's `sampling` changes:

| SceneLoader sampling | pairs kept (of 15) | components | tracks | long_track_fraction |
|---|---:|---:|---:|---:|
| `uniform` | 3 | **3** | 678 | **0.000** |
| `head` | 15 | 1 | 1704 | 0.349 |

Uniform sampling of a long ordered capture takes every Nth frame — here every
eighth. Exhaustive pairing tried all 15 pairs and 12 of them shared nothing —
the viewpoint change between eighth frames is past what SIFT's descriptor
survives. Not one track reached a third view.

This is worth internalising because every metric points at the matcher and the
fix is in the *scene loader*. When `exhaustive` finds nothing that `sequential`
did not, the matcher has already told you everything it can: the images do not
overlap. Check `sampling` and `max_images` before concluding the matcher is weak.
`head` keeps a contiguous run with real overlap; `uniform` spans the trajectory
and is for getting a quick look at a whole capture, not for reconstructing one.

---

## `inlier_ratio` below 0.3

Two different causes with opposite fixes. Distinguish before acting.

**Run once with `geometric_model: none`.** If `matches_per_pair` barely rises,
the matcher was not producing candidates to begin with and this is a detector
problem — go raise `max_keypoints` or lower `contrast_threshold`. If it rises a
lot, verification is doing the rejecting, and the question is whether it is right
to.

- **Repeated structure** (facades, tiling, foliage): the ratio test is what
  repetition defeats — a keypoint's true match and its repeat look equally good,
  so the ratio approaches 1 and the test admits whichever is nearer. Lower
  `ratio_test` to 0.7.
- **Heavy downscaling or soft optics**: real correspondences sit further off the
  epipolar line than 3px allows. Raise `ransac_threshold` to 4-6. Scale it with
  the scene's actual `downscale_factor` — 3px at max_edge 1600 is roughly 1px at
  max_edge 500.

### `ratio_test`: measured, same scene, window 4

| ratio_test | matches/pair | inlier_ratio | tracks | avg_track_length | long_track_fraction | tracker inconsistent_rate |
|-----------:|-------------:|-------------:|-------:|-----------------:|--------------------:|--------------------------:|
| 0.7 | 191 | 0.973 | 2763 | 2.42 | 0.265 | 0.0000 |
| 0.8 | 217 | 0.905 | 3716 | 2.54 | 0.320 | 0.0003 |
| 0.9 | 251 | 0.559 | 4700 | 2.59 | 0.339 | 0.0034 |
| 1.0 (off) | 320 | 0.220 | 5662 | 2.68 | 0.368 | 0.0175 |

**Read this table carefully, because it is a trap.** Every downstream count
improves monotonically as the ratio test is loosened: more matches, more tracks,
longer tracks, a higher long-track fraction. Taken alone they say "turn the ratio
test off".

They are lying. `inlier_ratio` collapses from 0.97 to 0.22, and the tracker's
`inconsistent_rate` rises 58x. The extra track length is coming from *wrong*
merges — two distinct scene points fused because a false match linked them. Those
tracks reach further precisely because they are wrong.

The rule: **`avg_track_length` is only meaningful at constant `inlier_ratio`.** If
a change raises track length and lowers inlier ratio, it made things worse. 0.8 is
Lowe's value and the right default; 0.7 when repetition is the problem; above 0.9
essentially never with geometric verification as the only thing standing between
you and garbage.

---

## `matches_per_pair` below 100

Almost always upstream. Check the detector's `keypoints_per_image` and
`keypoints_min` first — a matcher cannot match what was never detected, and one
starved frame breaks every pair it appears in.

If detection is healthy and matches are still thin: raise `ratio_test` toward 0.9
(keeping `geometric_model: fundamental`, so the false positives it admits get
rejected), or turn `mutual` off to see how much the mutual check is costing. If
turning `mutual` off is what fixes it, that is a signal the descriptors are weak
and a learned matcher is the real answer — do not just leave the mutual check off.

---

## `min_matches_per_pair` well below the mean

One weak link in an otherwise healthy graph. Tracks can only cross the graph
through its thinnest edge, so a single 16-match pair caps what the whole set
achieves regardless of a 237 mean. In the window-2 row above, `min_frame_obs` was
19 while the mean was 237.

Raise `window` so the weak frame links to more neighbours rather than depending on
one bad pair. Raising `min_matches` to *drop* the weak pair is usually wrong — it
often disconnects the graph, which is worse than a thin link.

---

## `planarity` near 1.0

A homography explains these pairs as well as epipolar geometry does. The pair is
planar or pure rotation, and triangulating it gives a confident wrong answer.

No matcher parameter fixes this; the capture geometry is what it is. What helps:

- Raise `window` so pairs are further apart — a wider baseline breaks the
  degeneracy if there is any depth in the scene at all.
- If the target genuinely is planar, this is not an SfM problem.

A turntable capture of a compact object has been measured across 0.70-0.78 —
substantial depth, but a dominant background plane. Treat above 0.9 as the warning
line, not above 0.7.

**Do not read that range as a property of a capture, because it is not one.** The
same scene and the same detection artifact moved 0.72 to 0.88 under two different
matchers, and moved with `ransac_threshold` alone on identical inputs — a looser
threshold admits more of the homography's inliers than the fundamental matrix's,
so the ratio climbs while nothing about the geometry changed. A reading is
comparable only against another at the same matcher, the same threshold and the
same confidence filtering. If a value near the warning line moves when you sweep
the threshold, you are measuring slack; `scene_analysis`'s degeneracy group is the
authority on the capture itself.

---

## Cost

Matching cost is (pairs x keypoints²). On a 12-image capture at 4096
keypoints: window 1 took 0.3s, window 4 took 0.85s, exhaustive 1.1s. Doubling the
detector's `max_keypoints` roughly quadruples all of these. `exhaustive` on 40
images is 780 pairs against 30 for sequential window 1 — a real cost at full
resolution, which is why the window sweep is the right thing to try first.

## Metrics that mislead

`matches_per_pair` is a mean over surviving pairs. Loosening any filter admits
thin pairs that were previously dropped, which lowers the mean while improving
the result. See the window sweep in [tuning.md](tuning.md), where it falls from
259 to 175 across a change that fixes a disconnected graph.

`inlier_ratio` is 1.0 by construction when `geometric_model: none`. That is not a
perfect score; it means nothing was checked.

`planarity` is `None` when it could not be measured — fewer than 4 inliers on
every pair, or `geometric_model: homography` (where the comparison would be
against itself).
