# Decisions log

Design choices made while porting the 23 modules, written down because they are
the ones worth arguing with. Newest section last.

Each entry: what was decided, what the alternatives were, and what would make me
change my mind. Anything marked **NEEDS A DECISION** is something I picked a
default for so work could continue, and which you should overrule if you disagree.

---

## 2026-08-07 — Session context

Starting point: `SceneLoader`, `FeatureDetectionSIFT`, `FeatureMatchNN`,
`FeatureTrackUnionFind` built and tested. 226 tests. The chain runs
scene → features → pairs → tracks across four containers.

Goal for this session: the remaining 20 of the 23 legacy modules, and a real
end-to-end reconstruction with numbers.

Priority order chosen, and why:

1. **The classical critical path first** — pose, sparse, bundle adjustment. It is
   the only thing that turns the existing four modules into an actual SfM
   pipeline, it needs no model weights, and it is what produces the end-to-end
   result you asked for. Breadth is worth nothing if nothing completes.
2. **Cheap OpenCV breadth next** — ORB, FLANN. Minutes each, and they give the
   registry real alternatives so the module-swapping machinery is exercised
   against something other than fixtures.
3. **The torch stack** — SuperPoint, ALIKED, LightGlue, SuperGlue. One shared
   base image, four modules.
4. **Detector-free** — LoFTR, RoMa.
5. **Learned reconstruction** — VGGT (pose/sparse/dense), MapAnything.
6. **Direct trackers** — VGGSfM, Tapir.

Groups 5 and 6 carry the most risk: vendored repositories, large weights, and no
guarantee the upstream code still imports against a current torch. They are last
deliberately, so a failure there costs breadth rather than the pipeline.

---
## The pose estimator consumes tracks, not pairs

`CamPoseEstimatorEssentialToPnP` in the predecessor walked `pairwise_matches` in
file order, maintaining its own track structure by chaining consecutive pairs.
Ours consumes `tracks/v1` instead.

Consequences, all of which I consider improvements:

- **Registration order is driven by evidence, not by filename.** Each round picks
  whichever unregistered image has the most 2D-3D correspondences. The
  predecessor's order was fixed, so a single unregisterable frame truncated
  everything after it.
- **The seed pair is chosen, not assumed.** The predecessor hardcoded
  `init_pair_idx = 0` (with dead code above it that pretended to search, and an
  unreachable `if init_pair_idx is None` branch below). We score every candidate
  pair by inlier count *gated on median parallax*, because the pair with the most
  matches is usually the pair with the least baseline -- seeding there is the
  classic way to produce a confident wrong model.
- **A frame that will not register is skipped, not fatal.** It gets `valid=False`
  in the artifact, which `poses/v1` makes mandatory precisely so consumers cannot
  ignore it.

**Worth your attention:** this means the module cannot be run without a tracker,
whereas the predecessor went straight from matches. If you want a pose estimator
that consumes pairs directly, say so -- it is a different module, not a parameter.

## A new module the 23 did not have: SparseTriangulation

Triangulation lived inside each pose estimator *and* inside each sparse
reconstructor in the predecessor -- four implementations, four sets of
thresholds, and point clouds that could not be compared across them because the
filtering differed.

I split it into its own module: `scene + tracks + poses -> sparse_model`. Any
pose source feeds it, including VGGT and MapAnything, because it consumes
`poses/v1` and knows nothing about how the poses were obtained.

This makes 24 modules rather than 23. The alternative was to have the pose
estimator emit `sparse_model` as a second output slot, which the module contract
supports. I did not, because then swapping the pose estimator would also swap the
triangulation policy, which is exactly the coupling that made the predecessor's
clouds incomparable.

## Geometry is done in normalised camera coordinates

Every classical geometry module undistorts and applies K^-1 once, up front, then
works with plain `[R|t]` projection matrices.

This is why per-image intrinsics need no special case anywhere. A
mixed-resolution capture (ETH3D courtyard) or a multi-camera rig just works. The
predecessor carried a single `self.K_mat` and a single `self.dist` through every
routine, which is one of the reasons its mixed-resolution handling was wrong.

The cost is that reprojection error must be converted back to pixels for
reporting, which is a few lines in each module. Worth it.

**Consequence worth knowing:** `sparse_model/v1` observations are UNDISTORTED
pixels. Everything downstream, including the COLMAP export, assumes this -- the
COLMAP cameras written by the BA module are PINHOLE with no distortion terms, not
as an approximation but because the distortion was already removed.

## sparse_model/v1 gained an optional `intrinsics` file

Bundle adjustment with `refine_focal_length` had nowhere to write the refined K.
Added additively, as the type system's rules require: optional file, consumers
that do not know about it are unaffected.

The rule I applied: a consumer that finds it should PREFER it over `scene/v1`
calibration, because a BA that refined K did so jointly with the poses in the
same artifact and the two cannot be mixed with an older K. `SparseTriangulation`
and `BundleAdjustmentGlobal` both implement that precedence.

## Two pycolmap traps, both of which silently produced wrong numbers

Recording these because they are the kind of thing that produces a plausible
metric rather than an error.

**`compute_mean_reprojection_error()` returns 0.0 on a freshly built
reconstruction.** It averages a per-point `error` field that COLMAP leaves unset
until `update_point_3d_errors()` is called. The first working version of the BA
module therefore reported `reprojection_error_before: 0.0` and
`error_reduction: 0.0` -- i.e. it claimed the input was already perfect and BA
had achieved nothing, when in fact it went 0.376px -> 0.253px. With the fix, the
"before" reads 0.3763 against our own triangulator's independently computed
0.376, which is a nice cross-check between two implementations.

**`pycolmap.bundle_adjustment(rec, options)` returns `None`.** Iteration count
and convergence were being invented from a summary that did not exist. Building
the adjuster explicitly via `create_default_bundle_adjuster` costs three lines
and returns a real summary. `read_summary` now reports `converged=False` when it
cannot tell, rather than defaulting to True -- the metric exists to be trusted
when a solve goes wrong, which is exactly when a cheerful default misleads.

---

## 2026-08-08 — The host cannot pass GPUs into containers

**This needs your attention; I did not fix it because the fix needs sudo and
changes the Docker daemon.**

The box has 8x RTX A6000 and `nvidia-smi` sees all of them. Docker cannot:

```
docker: Error response from daemon: could not select device driver ""
        with capabilities: [[gpu]]
```

The NVIDIA container toolkit is not installed and the daemon has no `nvidia`
runtime (`docker info` lists only `runc`; there is no `/etc/docker/daemon.json`).
Having GPUs on the host is not the same as being able to pass one into a
container.

The fix, when you want it:

```bash
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus device=0 sfmstack/runtime:1.0 -c "print('ok')"
```

What I did instead: `DockerBackend` now probes GPU support once, caches the
answer, and falls back to CPU with a loud one-time warning that prints the above.
`cpu_fallback=False` turns it back into an error.

I chose fallback over failure because a host merely missing a driver package
should not look like a host that cannot run the pipeline, and because it let me
verify every GPU module end to end today. The cost is that GPU modules are running
1-2 orders of magnitude slower than they should, so every `expected_duration_s` on
a `gpu: true` module is calibrated for hardware that is not currently reachable.
The GPU broker itself is therefore still only exercised by tests.

**Consequence for the numbers below:** all learned-module timings in this session
are CPU timings. The *metrics* are unaffected — inference runs under
`inference_mode` and is device-independent — but do not read the timings as
representative.

## The classical stack beat the learned stack on DTU

Same scene, same everything downstream, four detector/matcher combinations, each
run all the way to a bundle-adjusted model. DTU scan1, 10 contiguous images,
1024px, exhaustive pairing.

| stack | secs | kp/img | matches/pair | inlier | tracks | long% | conflict | points | err_pre | err_post |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIFT + NN | 17.7 | 4096 | 494.9 | 0.966 | 6091 | 0.491 | **0.004** | 6040 | 0.373 | **0.246** |
| ORB + NN | **8.6** | 4096 | 217.6 | 0.856 | 4386 | 0.368 | 0.020 | 4274 | 0.521 | 0.411 |
| SuperPoint + LightGlue | 55.8 | 2030 | 649.2 | 0.835 | 2131 | **0.607** | 0.206 | 1834 | 1.007 | 0.645 |
| ALIKED + LightGlue | 57.3 | 2048 | **688.4** | 0.886 | 2840 | 0.605 | 0.172 | 2324 | 0.824 | 0.451 |

All four registered 10/10 images.

The learned stacks win every intermediate metric that looks like it should
matter — most matches per pair, longest tracks, highest `long_track_fraction` —
and lose on the only metric that is the actual output. SIFT ends at 0.246px with
6040 points; SuperPoint ends at 0.645px with 1834.

The column that explains it is `conflict` (the tracker's `inconsistent_rate`):
0.004 for SIFT against 0.206 for SuperPoint, a factor of fifty. One in five merged
groups from the LightGlue run was observed twice in the same image, meaning at
least one of the matches that built it is wrong.

This is precisely the trap already documented in the tracker's tuning file from
the `ratio_test` sweep — more and longer tracks arriving together with a rising
conflict rate is what *degradation* looks like, not improvement. I did not expect
to see it again this cleanly, from a completely different cause.

**How I read this, and where I could be wrong.** DTU scan1 is a well-lit,
high-texture, turntable capture — squarely inside SIFT's comfort zone and outside
the regime learned matchers were built for (illumination change, low texture, wide
baselines). It would be wrong to conclude "SIFT is better"; the honest conclusion
is "on an easy scene the classical stack wins, and this scene is easy". Confounds I
have not controlled: the learned runs used 2048 keypoints against SIFT's 4096, and
LightGlue ran at its permissive default `filter_threshold` of 0.1. A follow-up
sweep on both is running.

**What I think this says about the design**, which is the part worth your
disagreement: it is evidence that the per-stage metrics are doing their job. The
pipeline reported a problem (`high_conflict_rate` fired on both learned runs) two
stages before the accuracy loss appeared, and pointed upstream at the matcher. That
is the behaviour the whole metric/diagnostic scheme exists to produce.

It also says the agent should not pick a matcher by reputation. Establishing which
stack is right for a capture takes one comparison run, and the comparison is cheap.

## LightGlue must be told which weights match its input

LightGlue is trained per descriptor type. Running `superpoint` weights over ALIKED
descriptors does not error — it returns confident, meaningless matches.

`FeatureMatchLightGlue` infers the weight set from the features artifact's
**provenance** (which module produced it) and cross-checks the descriptor width.
Width alone is not enough: aliked, sift and disk are all 128-d.

`weights: auto` fails loudly on an unknown producer rather than guessing. The
metric that catches a wrong choice after the fact is `mean_match_score` — a low
value alongside a healthy `inlier_ratio` is the signature, because the geometry is
consistent (the matches came from one rigid scene) while the model is unsure (the
descriptors are not what it was trained on).

**Worth your attention:** this couples the matcher to a table of known detector
names. A custom detector emitting 128-d descriptors is not inferable and needs
`weights` set by hand. The alternative — recording the descriptor type in
`features/v1` as an additive optional array — is cleaner and I did not do it,
because it would mean every detector module has to declare something the type
system does not currently require. Say the word and I will add it.

## Two build-system traps worth recording

**Dockerfile heredocs need BuildKit.** This daemon uses the legacy builder, where
`RUN python - <<'PY'` is not a heredoc: the parser takes the first line as the
whole `RUN` and treats the script body as further Dockerfile instructions. `python -`
then reads an empty stdin, exits 0, and you get an image with no weights in it and
no error. Weight-caching scripts are now real files that get `COPY`ed.

**`git` is not in `python:3.11-slim`.** `pip install git+https://...` — which is
how essentially all of this research code ships — fails with "Cannot find command
'git'". Added to `runtime-torch` rather than to the base `runtime`, and
deliberately *after* the torch layer so adding it does not invalidate a 2.5 GB
download. The dependency-free tracker image should not grow 50 MB to support
modules it has nothing to do with.

## Follow-up: the LightGlue gap is localisation, not matching

I suspected the DTU result above was an artefact of LightGlue's permissive default
`filter_threshold` (0.1) and its lower keypoint budget. Swept both. Neither
explains it.

SuperPoint + LightGlue, DTU scan1, 10 images, exhaustive, everything downstream fixed:

| setting | matches/pair | inlier | match score | tracks | conflict | points | final error |
|---|---:|---:|---:|---:|---:|---:|---:|
| `filter_threshold: 0.1` | 649.2 | 0.835 | 0.650 | 2131 | 0.206 | 1834 | 0.645 |
| `filter_threshold: 0.3` | 671.4 | 0.939 | 0.778 | 2446 | 0.175 | 2283 | 0.663 |
| `filter_threshold: 0.5` | 695.0 | **0.989** | 0.882 | 2710 | 0.131 | 2561 | 0.655 |
| 4096 keypoints, `0.3` | 770.9 | 0.952 | 0.786 | 2633 | 0.181 | 2408 | 0.657 |

Raising the threshold does everything it should to the *matching* metrics —
`inlier_ratio` goes 0.835 to 0.989, conflicts fall by a third, and the verified
match count actually **rises** (cleaner input lets MAGSAC find a better model and
keep more true inliers). Doubling the keypoint budget adds matches too.

And the final reprojection error does not move: 0.645, 0.663, 0.655, 0.657. It is
pinned at roughly 0.65px regardless.

So the gap against SIFT's 0.246px is not a matching-quality problem. A better
hypothesis, which the three-way ordering supports:

| detector | subpixel mechanism | final error |
|---|---|---:|
| SIFT | quadratic fit to the DoG extremum | **0.246 px** |
| ALIKED | learned deformable sampling, localisation is its stated contribution | 0.451 px |
| SuperPoint | soft-argmax over an 8x8 cell heatmap | 0.645 px |

That ordering is exactly what keypoint **localisation precision** predicts, and it
is a different axis from matching. It also explains why ALIKED — the weaker
descriptor, with fewer matches than SuperPoint at equal budget — produced the
better reconstruction of the two learned stacks. ALIKED's whole claim is
localisation, and this is what that claim looks like when it is true.

**This is a hypothesis, not a measurement.** I have not isolated it. The clean test
is to run all three detectors through the *same* matcher, which is possible today
for SIFT vs SuperPoint vs ALIKED through LightGlue (all three have weight sets) and
would separate detector localisation from matcher behaviour completely. I have not
run it.

**Why it matters for how the agent should reason:** if this holds, the choice of
detector and the choice of matcher optimise different things, and the metrics that
expose them are in different artifacts. Match count and inlier ratio live in the
matcher's artifact; localisation only becomes visible in the bundle adjuster's
`reprojection_error_after`, four stages later. An agent tuning on the matcher's own
metrics would have driven `filter_threshold` to 0.5, seen `inlier_ratio` reach
0.989, and concluded it had solved a problem it had not touched.

That is an argument for the judgment tier you wanted to write yourself: "which
metric actually answers the question I am asking" is exactly the tacit knowledge
that does not belong in any single module's tuning file.

## A synthetic test confirmed a wrong default, and real data caught it

The tracker's `merge_eps_px` governs the detector-free path: with no
`feature_index` to merge on, endpoints are merged by proximity.

I tuned it early, before any detector-free matcher existed, by taking SIFT matches
and stripping `feature_index` to force the proximity path. That experiment said
0.5px and 1.5px were indistinguishable and 4px over-merged — a clean curve
endorsing the 1.5px default inherited from the predecessor's
`pseudo_merge_eps_px`.

It was wrong. On real LoFTR output (DTU scan1, 5 images, 640px):

| `merge_eps_px` | long_track_fraction | conflict | registered |
|---:|---:|---:|---:|
| 1.5 | 0.078 | 0.002 | **3/5** |
| 3.0 | 0.195 | 0.007 | 4/5 |
| 6.0 | 0.286 | 0.059 | 4/5 |
| 12.0 | reconstruction fails | | |

At the endorsed value, tracks barely chain past a single pair and two of five
images cannot be registered at all.

The proxy was not measuring the quantity that matters. With a detector, the same
keypoint is *reused* in every pair it appears in, so its coordinates recur
**exactly** and any nonzero tolerance merges them — the experiment was measuring
numerical noise. With a detector-free matcher every pair is estimated
independently, so one physical point lands at different sub-pixel positions per
pair, and the tolerance has to cover that estimation spread instead.

Both measurements are now in the tracker's tuning file, the wrong one included,
because the failure mode is worth being able to recognise: a synthetic test that
exercises the right *code path* while not exercising the right *phenomenon*, and
which therefore confirms whatever default it was given.

**Worth your attention:** this is a case where the metrics did NOT catch the
problem on their own. `inconsistent_rate` looked excellent at 1.5px (0.002) — it
is a measure of over-merging and says nothing about under-merging. The signal was
`long_track_fraction` at 0.078 and `registered_fraction` at 0.6, two artifacts
apart. If you want a rule for the judgment tier, this is a candidate: *a metric
that only detects one direction of an error is not a health check for that
parameter.*

## Module count and what is left

Fourteen modules, covering eleven of the twenty-three legacy ones plus three that
did not exist there (`SceneLoader`, `SparseTriangulation`, and `FeatureMatchNN`
which merges the predecessor's BF and cross-check paths).

Built and measured end to end: SIFT, ORB, SuperPoint, ALIKED, NN, FLANN,
LightGlue, LoFTR, UnionFind, EssentialToPnP, Triangulation, BA global, BA local.

Not yet ported: SuperGlue, RoMa, VGGT (pose/sparse/dense), MapAnything, VGGSfM,
Tapir, COLMAP global mapper, gtsam incremental sparse, PatchMatch MVS.

The remaining nine split into two groups. The COLMAP mapper and the gtsam sparse
module need no weights and are straightforward ports — they are the next ones I
would do. The learned reconstruction modules (VGGT, MapAnything, VGGSfM, Tapir,
RoMa) need vendored repositories and multi-gigabyte weights, and are the ones most
likely to need real integration work rather than a port; they are also the ones
that benefit most from the GPU passthrough being fixed first, since nothing about
them can be meaningfully validated on CPU.

---

## 2026-08-08 — GPU passthrough: it does not work, and I cannot fix it

Tested, as asked. It fails.

```
$ nvidia-smi --query-gpu=index,name,driver_version --format=csv,noheader
0, NVIDIA RTX A6000, 580.159.03      (x8)

$ docker info | grep Runtimes
 Runtimes: io.containerd.runc.v2 runc          <- no `nvidia` runtime

$ ls /usr/bin/nvidia-container-runtime /usr/bin/nvidia-ctk
ls: cannot access ...: No such file or directory

$ cat /etc/docker/daemon.json
cat: /etc/docker/daemon.json: No such file or directory

$ docker run --rm --gpus device=0 sfmstack/runtime:1.0 -c "print('ok')"
docker: Error response from daemon: could not select device driver ""
        with capabilities: [[gpu]]

$ sudo -n true
sudo: a password is required
```

Driver 580.159.03 is fine and the host sees all eight cards. What is missing is
the **NVIDIA container toolkit**, which is a separate package that installs a
runtime shim and registers it with the Docker daemon. Installing it needs root,
and sudo here needs a password, so this one is yours:

```bash
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus device=0 sfmstack/runtime:1.0 -c "print('ok')"
```

### The workaround, and what it bought

`SubprocessBackend` runs the module server as a local process rather than in a
container, and a local process on this host sees the GPUs normally. Installing
torch 2.6.0+cu124, lightglue and kornia into the venv makes every GPU module
runnable that way — `torch.cuda.device_count()` returns 8.

This is not equivalent to the container path and should not be mistaken for it:
it gives up the dependency isolation that is the entire point of the
architecture, and it only works because those three stacks happen not to
conflict *today*. It is a development convenience, exactly as the README says.

What it did buy is real:

- **The GPU broker is exercised for the first time against actual devices.** The
  full run below shows SuperPoint leasing GPU 0 and LightGlue leasing GPU 1 —
  distinct exclusive leases, visible as badges in the report.
- **Honest timings.** LoFTR: 4.8s for 9 pairs on GPU against ~90s in a CPU
  container. LightGlue: 3.2s for 120 exhaustive pairs on 16 images.
- **A complete run to build the visualiser against.**

Full pipeline, DTU scan1, 16 contiguous images at 1024px, all on real GPUs:

| module | seconds | device |
|---|---:|---|
| SceneLoader | 0.9 | cpu |
| FeatureDetectionSuperPoint | 1.2 | GPU 0 |
| FeatureMatchLightGlue | 3.2 | GPU 1 |
| FeatureTrackUnionFind | 0.1 | cpu |
| PoseEssentialToPnP | 1.3 | cpu |
| SparseTriangulation | 1.3 | cpu |
| BundleAdjustmentGlobal | 4.6 | cpu |

16/16 cameras registered, 2365 points, tracks spanning all 16 frames,
0.839px → 0.681px through bundle adjustment.

Two things in that run are worth noticing. `inconsistent_rate` is **0.228** —
the LightGlue conflict-rate finding from the previous session reproducing on a
larger set and on real hardware, so it was not a CPU or scale artefact. And
`converged` is **0** at 301 iterations against the new cap of 300, so the cap
wants raising again for problems this size; the previous session's fix is
working, it just moved the boundary rather than removing it.

## The report is generated from lineage, not from a recipe

`tools/sfm_report.py <store> <final-artifact-id>` walks an artifact's `inputs`
backwards and renders the whole run as one self-contained HTML file.

It is not told what the pipeline was. Artifacts already record their own inputs,
parameters, metrics with `healthy` bands, and diagnostics, so the report is
arrangement rather than instrumentation — and it works unchanged on the
classical chain, the learned chain, and the detector-free chain.

That is the strongest argument I have for the manifest design so far: the
visualiser needed no per-module knowledge at all, and the "is this metric
healthy" colouring reads the band out of the artifact rather than out of a table
in the report.

No CDN, no external fonts, no runtime fetch — the point cloud is base64 inside
the page. A report that needs the network is a blank page exactly when you most
want to look at a result.

