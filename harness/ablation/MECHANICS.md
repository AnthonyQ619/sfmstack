# How the pipeline works: the mechanics

This file explains what the tools do and how the parts connect. It says nothing about which module or setting
works better on which capture; that is yours to decide.

## The shape of a reconstruction

A reconstruction is a chain of steps. Each step runs one **module**, which takes typed **artifacts** in and gives
typed artifacts out. Every artifact is stored, has an id (`art_…`), and is never deleted, so you can go back to any
of them.

| Stage | What it produces | Type |
| --- | --- | --- |
| 1. Scene loading | the frames and the calibration, as one scene | `scene/v1` |
| 2. Analysis | measurements of the scene (no geometry) | `scene_analysis/v1` |
| 3. Detection | keypoints and descriptors per frame | `features/v1` |
| 4. Matching | matched points between pairs of frames | `pairwise_matches/v1` |
| 5. Tracking | matches joined into tracks across many frames | `tracks/v1` |
| 6. Pose | a camera pose per frame | `poses/v1` |
| 7. Sparse | 3D points triangulated from tracks and poses, with the poses | `sparse_model/v1` |
| 8. Optimization | the sparse model, refined | `sparse_model/v1` |
| 9. Dense | a dense point cloud built on a refined sparse model | `dense_model/v1` |

**A chain is valid when every required input of a module is an artifact of the right type.** The service refuses an
incompatible chain. Some modules skip a stage: a module that matches straight from images needs no detection step,
and a module that builds a sparse model straight from matches needs no separate tracking or pose step.

## The modules

Inputs marked `?` are optional. GPU modules run on the capture's GPU.

| Module | Stage | Consumes | Produces | GPU |
| --- | --- | --- | --- | --- |
| SceneLoader | loading | — | scene | |
| SceneTriage | analysis | scene | scene_analysis | |
| SceneMotion | analysis | scene | scene_analysis | ✓ |
| SceneDescription | analysis | scene | scene_analysis | |
| FeatureDetectionSIFT | detection | scene | features | |
| FeatureDetectionORB | detection | scene | features | |
| FeatureDetectionSuperPoint | detection | scene | features | ✓ |
| FeatureDetectionALIKED | detection | scene | features | ✓ |
| FeatureMatchNN | matching | scene, features | pairwise_matches | |
| FeatureMatchFLANN | matching | scene, features | pairwise_matches | |
| FeatureMatchLightGlue | matching | scene, features | pairwise_matches | ✓ |
| FeatureMatchSuperGlue | matching | scene, features | pairwise_matches | ✓ |
| FeatureMatchLoFTR | matching | scene | pairwise_matches | ✓ |
| FeatureMatchRoMa | matching | scene | pairwise_matches | ✓ |
| MatchQuantize | matching | pairwise_matches | pairwise_matches | |
| FeatureTrackUnionFind | tracking | scene, pairwise_matches | tracks | |
| FeatureTrackTapir | tracking | scene, features | tracks | ✓ |
| FeatureTrackVGGSfM | tracking | scene, features | tracks | ✓ |
| PoseEssentialToPnP | pose | scene, tracks | poses | |
| PoseVGGT | pose | scene | poses | ✓ |
| PoseMapAnything | pose | scene | poses | ✓ |
| PoseFill | pose | scene, sparse_model, poses, poses_b? | poses | |
| SparseTriangulation | sparse | scene, tracks, poses | sparse_model | |
| SparseTriangulationGTSAM | sparse | scene, tracks, poses | sparse_model | |
| SparseVGGT | sparse | scene, tracks, poses | sparse_model | ✓ |
| SparseMapAnything | sparse | scene, tracks, poses | sparse_model | ✓ |
| SparseGlobalCOLMAP | sparse | scene, pairwise_matches | sparse_model | |
| BundleAdjustmentGlobal | optimization | scene, sparse_model | sparse_model | |
| BundleAdjustmentLocal | optimization | scene, sparse_model | sparse_model | |
| SparseVerification | analysis | scene, sparse_model, pairwise_matches | verification | |
| DenseMVS | dense | scene, sparse_model | dense_model | ✓ |
| DenseVGGT | dense | scene, poses?, sparse_model?, tracks? | dense_model | ✓ |
| DenseFusion | dense | dense_model | dense_model | |

`sfmx describe <module>` gives a module's parameters (name, type, default, allowed range), its input and output slots,
and the names of the metrics it reports. `sfmx find <type>` lists the modules that produce a type.

## The tool

`sfmx` is on your PATH, and your capture is already set.

    sfmx list [consumes=..|produces=..|kind=..]   # modules, filtered
    sfmx find <produces>                          # modules that produce a type
    sfmx describe <module>                        # parameters, slots, metric names
    sfmx run <module> '<params json>' [slot=artifact_id ...]
    sfmx run <module> --params-file <file> [slot=artifact_id ...]
    sfmx wait [seconds]                           # block until the step in flight ends
    sfmx running                                  # what is running now
    sfmx state                                    # the chain: current artifact per slot, and the history
    sfmx replay <artifact_id> [overrides-json]    # re-run the step that made it, with new parameters,
                                                  # and every step built on it
    sfmx pin <slot> <artifact_id>                 # make an earlier artifact current again
    sfmx artifact <id>                            # an artifact's metrics, inputs and files
    sfmx image <id> [name]                        # a PATH to an image; open it with your image reader
    sfmx compare <id> <id> [...]                  # two or more models side by side
    sfmx summary                                  # every step of this capture
    sfmx series <id> <group>                      # one stored group of an artifact, as JSON
    sfmx cloud <id> [n]                           # a model's extent and a sample of its points

**Wiring.** In `run`, a slot you name takes that artifact. A required slot you leave out is wired from the chain's
*current* artifact of that type (`sfmx state`), and an optional one stays empty. `pin` changes what is current.

**Long steps.** A step runs in its own worker. `run` returns after at most nine minutes; if the step is still going
it says so. Then call `sfmx wait` until nothing is in flight, and read the step from `sfmx state`. Never re-issue a
step that is in flight. One step runs at a time per capture. Give each `sfmx` call a Bash timeout of 600000 ms.

**Calling it.** Call `sfmx` as a bare command: no pipe, no redirect, no `;` or `&&`. Anything that does not begin
with `sfmx` is refused. Every answer is also saved in your `scratch/` directory as `last_<command>.json`; read a long
answer from there with the file reader.

## What comes back from a step

A `run` returns the step's outputs (artifact ids), its parameters, and its **metrics**: named numbers. Each metric's
name and its direction (higher or lower is better) are in `describe`. Where a step reports a problem it gives a
**diagnostic code** and a severity.

After a step that produces a refined sparse model, the service also attaches three readings on its own:

- **Health profile.** Seven rungs, each a percentile (0–100) of this model against a fixed reference set of
  models, computed without ground truth:

  | Rung | Measures |
  | --- | --- |
  | registration | registered frames over capture frames |
  | conditioning | median triangulation angle |
  | composition | share of points seen in more than two views |
  | coverage | median per-frame share of image cells holding an observation |
  | error | reprojection error of points seen in more than two views |
  | yield | observations kept over observations in the tracks |
  | pose agreement | final relative poses against pairwise two-view estimates |

  The profile's summary is the lowest of the rungs. A rung that cannot be computed is reported as unevaluable.
- **Verification.** Matches the solve never used are held out and checked against the model. The verdict is
  *contradicted* (the held-out matches disagree with the model), *consistent*, or *unverified* (nothing could be held
  out).
- **Two-estimator reading.** The model's camera poses are compared with two pose estimators that never saw its
  matches (`PoseVGGT`, `PoseMapAnything`), in rotation and in camera position. Each form is reported as the model's
  disagreement with the estimators, divided by the estimators' disagreement with each other.

## Writing a plan

Before running anything past analysis, write your plan in `scratch/plan.md`, in this shape: one line per stage,
naming the module and its parameters and the reading behind the choice.

    SCENE         what the capture is, from the analysis
    DETECTION     module, params, why
    MATCHING      module, params, why
    TRACKING      module, params, why
    POSE          module, params, why
    SPARSE        module, params, why
    OPTIMIZATION  module, params, why
    DENSE         module, params, why
    WATCH         the reading you will judge the result on
    ESCAPE        what you would change if it fails, and what would tell you
    UNSUPPORTED   what you chose without anything to back it

Every stage gets a line, even when the module needs no separate step (say so).

## What you deliver

A dense model (`dense_artifact`) and the refined sparse model it was built on (`refined_artifact`), reported in
`../agent_report.json` in the shape your procedure gives.
