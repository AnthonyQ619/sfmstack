---
module: FeatureTrackTapir
module_version: 1.5.0
upstream: BootsTAPIR v2 (torch), google-deepmind/tapnet @ c2cbab8
curated_at: 2026-08-11
sources: 3
---

Point tracking with BootsTAPIR. Keypoints from a few query frames are followed
through the set **as though it were video**. GPU required.

**It consumes `features/v1`, not `pairwise_matches/v1`** — no matcher in the chain.

## Reach for it when tracks are breaking, not when precision matters

8 DTU views, SIFT keypoints, everything else identical:

| | tracks | `avg_track_length` | `long_track_fraction` | `track_survival_5` |
|---|---:|---:|---:|---:|
| `FeatureTrackUnionFind` | 4702 | 2.85 | 0.431 | 0.116 |
| `FeatureTrackVGGSfM` | 4033 | 3.85 | 0.712 | 0.345 |
| **`FeatureTrackTapir`** | 2736 | **5.98** | **0.927** | **0.754** |

**Six times as many tracks reach five views as union-find manages**, and nearly
all of them reach three. Nothing else here produces connectivity like that.

Through the same triangulator, though:

| tracker | points | mean error | `yield` |
|---|---:|---:|---:|
| `FeatureTrackUnionFind` | 4671 | **0.280 px** | 0.993 |
| `FeatureTrackVGGSfM` | 3982 | 0.502 px | 0.987 |
| `FeatureTrackTapir` | 1548 | 1.581 px | 0.566 |

**The longest tracks and the least accurate positions.** This is a connectivity
tool. On a scene where the matcher works it is the wrong choice; on one where the
view graph fragments and tracks die at every missing edge, it is the only module
here that will chain them anyway.

## `input_size` decides whether it is usable at all

BootsTAPIR was trained at 256 square and the default here is **384**, because
track statistics and reconstruction quality disagree about it:

| `input_size` | tracks | `track_survival_5` | tri points | tri error | `yield` |
|---:|---:|---:|---:|---:|---:|
| 256 | 2629 | 0.738 | 887 | 1.715 | 0.337 |
| **384** | 2736 | **0.754** | **1548** | 1.581 | **0.566** |
| 512 | 2683 | 0.739 | 1445 | **1.434** | 0.539 |
| 768 | 2728 | 0.692 | 1433 | 1.470 | 0.525 |

At 256 one model pixel is four scene pixels across, and the positional error that
carries is what the reprojection filter then rejects — the track metrics barely
notice while the yield halves. Past 384 it plateaus and then regresses: the model
is being taken away from its training distribution.

## Occlusion is a separate output

TAPIR predicts occlusion and localisation uncertainty independently. The
confidence written here is their product, and both are reported:

- **`mean_occlusion` high** → the points genuinely leave view. A capture property;
  the query selection is what to change.
- **`mean_occlusion` low but `mean_confidence` low** → the model sees the points
  and cannot pin them down. Raise `input_size`.

No other tracker here separates those two.

## Image order is input

TAPIR reasons about trajectories over time, so the order the scene stores images
in is a real parameter. A shuffled set is a different and harder problem than the
one the model was trained on. `FeatureTrackUnionFind` and `FeatureTrackVGGSfM` do
not care about order at all.

## `dedupe_eps_px` is the one knob here worth sweeping — and it has a hard ceiling

**Bounded at 2.0 by the schema.** `tracks/v1` fixes its duplicate test at 2.0 px, so
above that the merge is fusing tracks the type itself calls **distinct**. Nine scenes
say what that costs: by 6.0 px the median run has lost 74% of its tracks and 81% of
its bundle-adjusted points at unchanged registration, and the errors that look
better up there are smaller models, not better ones.

**Inside 0–2 it moves the reconstruction and cannot be predicted.** The best value
landed at every point on that range across nine scenes, and the direction flips —
on one scene more merging helped monotonically, on another any merging cost ~60% of
the pose accuracy. Worth a sweep when the scene matters; worth leaving at 1.5 when
it does not.

**Never compare sweep rows that registered different numbers of images.** Raising
this deletes tracks, which removes the 2D–3D links PnP needs to register an image
at all. A smaller model wins every aggregate metric it is scored on.

Full numbers and the failure at 0: [tuning.md](tuning.md#dedupe_eps_px--worth-tuning-inside-a-hard-ceiling).

**Reading the output:** [artifact.md](artifact.md) ·
**Tuning:** [tuning.md](tuning.md) · **Limits:** [limitations.md](limitations.md)
