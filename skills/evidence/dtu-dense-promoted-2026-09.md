# Campaign — three studio-rig captures promoted from the holdout, 2026-09

Three captures from the studio-rig dataset's holdout, driven to a dense cloud by one
isolated agent each under the same frozen context as
[dense-batch-2026-09](dense-batch-2026-09.md), then scored against reference surface
geometry. They were **held out at the time and promoted afterwards**, deliberately and
one at a time, because each of them falsifies something the corpus rows could not.

**Why these three and not a random three.** The corpus's studio-rig block was seven
orbits that all agreed, and a block of agreeing rows cannot contradict the rule read off
it. These were chosen from the holdout by looking for captures that sat outside the
corpus range on one axis each — registration, accuracy, and a delivered health reading —
and each turned out to carry a refutation. Promoting them costs what promotion always
costs: they can no longer test whether the context transfers.

## What ran

One agent per capture, context frozen, no interaction, the working resolution every
earlier campaign in this series used. All three delivered a scored cloud and all three
registered every frame **in the end** — which is the point of the first row below, since
one of them could not do it on the pipeline the corpus prescribes.

| capture | shipped pipeline | registered | sparse points | dense completeness |
| --- | --- | --- | --- | --- |
| DTU/scan48 — two glazed striped cups, rig visible in reflection | SIFT+CLAHE → NN → **global** → global BA | 49/49 | 2 876 | 0.227 |
| DTU/scan75 — still-life of fruit and vegetables | SIFT → NN → incremental → global BA | 49/49 | 27 793 | 0.414 |
| DTU/scan77 — faceted metal stovetop coffee pot | SIFT → **LightGlue** → global → global BA | 49/49 | 4 836 | **0.123** |

## Scored against reference geometry — millimetres

| capture | accuracy | completeness | overall | overall, best fit | placement, mm |
| --- | --- | --- | --- | --- | --- |
| DTU/scan48 | 0.939 | **3.513** | 2.226 | 1.651 | 1.67 (5 cameras excluded) |
| DTU/scan75 | **1.760** | 1.085 | 1.423 | 0.745 | 1.08 |
| DTU/scan77 | 1.395 | 1.326 | 1.361 | 0.770 | 0.77 |

For scale: across the seven corpus orbits of this dataset, accuracy reaches 0.79 at
worst, completeness 1.15, and placement 0.57. Each of these three sits outside that range
on the reading shown in bold, by between two and three times.

## What each one falsifies

### scan48 — the cheap chain does not always register a rig orbit

The corpus block says every studio-rig orbit ships a classical detector, a ratio-test
matcher and an incremental reconstructor, and that the alternative branch only changes
density. On this capture the incremental chain reached **38 of 49 frames** with either
matcher, 44 at best; only a global reconstructor registered all 49.

Two conditions distinguish it, both visible before the run: the subject is a smooth
glazed surface whose only texture is a band pattern that repeats around each cup, and the
capture rig appears *in reflection on the subject* and moves with the viewpoint rather
than with the surface. The sparse model that eventually shipped carries **2 876 points**
over 49 frames — an order of magnitude below every corpus orbit.

It also exposes a stage interaction: `SparseGlobalCOLMAP`'s default `min_num_matches`
sits above the matcher's own floor, so pairs the matcher had linked were silently dropped
by the reconstructor, and the frames they carried went with them. Lowering the
reconstructor's floor toward the matcher's is what registered the tail.

### scan75 — a clean capture's track conflict can be thirty times the documented ceiling

`FeatureTrackUnionFind`'s limitations put the conflict rate on clean data at up to about
0.002. This capture — no repeated parts, no coherent reflector, every frame registered —
read **0.056** at the ratio test's default, and 0.028 one step tighter. The diagnostic
fired and nothing in the context explained a clean capture reading thirty times the
stated ceiling.

Three separate captures in this series then found that the prescribed remedy does not
work: raising the learned matcher's threshold moved the cycle terms by up to fifty times
while leaving the conflict rate flat. The rate is measuring something the matcher dial
does not reach.

Its accuracy is the worst of the batch, on a subject class the corpus does not contain:
smooth organic produce, low texture between specular lobes, and a subject occupying a
minority of a frame that is otherwise clipped backdrop.

### scan77 — a named escape route that cannot be reached, and a health band that misreads

The context names the learned densifier as the escape for a specular subject. It cannot
be reached from a refined model: it consumes `poses/v1`, which only the incremental and
learned **pose** stages produce, and every stage after triangulation — triangulation,
the global reconstructor, both bundle adjusters — produces `sparse_model/v1`. On the
global branch no `poses/v1` exists at any point. So on the exact capture kind the escape
is prescribed for, the escape is unreachable, and an agent discovers this only by trying.

Its delivered `depth_map_completeness` is **0.123**, below the module's own band, on a
cloud that was sound. The reading is a whole-frame fraction, and roughly two thirds of
every frame here is clipped backdrop, so the denominator is mostly not surface. Nothing
in the module said the reading dilutes that way.

It is also the second refutation of the cheap-branch rule, and it points the **other
way** from scan48: here the ratio test returned the smaller, weaker model — 5 009 points
against 7 651, and a worst-frame point count of 16 against 170 — and the joint matcher
shipped.

## Runtime, measured

Gathered from every timed stereo run across the corpus captures of both dense campaigns —
123 runs over 19 captures — because the module's published table came from an isolated
eight-view test and nineteen captures recorded that it did not transfer.

| configuration | seconds per view, median | spread |
| --- | --- | --- |
| working resolution, geometric check on | 40.5 | 39–116 |
| working resolution, geometric check off | 16.4 | 11–28 |
| working resolution, check on, `window_step: 2` | 18.1 | 18–22 |
| half resolution, check on | 24.9 | 17–47 |

**The published quadratic scaling in `max_image_size` is wrong.** Paired within captures
that ran both resolutions, doubling the long edge cost **1.75×** (1.36, 1.75 and 2.39 on
the three corpus captures with both), not the 4× a quadratic predicts. The geometric
check costs **2.4×**, close to the documented doubling; `window_step: 2` saves **2.2×**.

## What was derived from these rows

| Claim | Where it is stated | Supported by |
| --- | --- | --- |
| A rig orbit whose subject is a smooth repeating glaze carrying a coherent reflection can defeat the incremental chain; reach for the global reconstructor rather than another matcher | `plan/scene_to_pipeline.md`; `INDEX.md`'s studio-rig note | scan48: 38/49 incremental with either matcher, 49/49 global |
| A reconstructor floor above the matcher's floor silently drops linked pairs | `modules/sparse_global_colmap` tuning | scan48: lowering it registered the tail |
| The conflict rate on clean data reaches far higher than the stated ceiling, and the matcher dial does not move it | `modules/track_union_find/skills/limitations.md` | scan75 at 0.056; three captures on the unresponsive dial |
| The learned densifier is not reachable from a refined model | `plan/dense.md`; `modules/dense_mvs/skills/tuning.md` | scan77, and the modules' own declared input types |
| `depth_map_completeness` is a whole-frame fraction and dilutes on a backdrop-dominated capture | `modules/dense_mvs/skills/artifact.md` | scan77 at 0.123 with a sound cloud |
| Stereo runtime per view, and the scaling that actually holds | `modules/dense_mvs/skills/SKILL.md`, `limitations.md`, `tuning.md` | the runtime table above, 123 runs over 19 captures |

## What these rows do NOT support

- **Nothing about how often any of this happens.** Three captures chosen *because* they
  sat outside the corpus range are not a rate. They say these failures exist and what
  they look like, not that a new rig orbit is likely to show one.
- **Nothing about the tuning ranges.** No dial was swept on any of the three.
- **Nothing that a corpus row now confirms.** These three were the holdout's evidence
  that the context does not transfer; having been promoted, they cannot also be the
  evidence that it does. The remaining holdout is what that question needs.
