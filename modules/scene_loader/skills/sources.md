# Sources — SceneLoader

In-house infrastructure, so there is no paper. The claims that need backing are
about real dataset behaviour and about the predecessor's failure modes, both of
which are checkable.

| Tag | Source | Where | Claims it supports |
| --- | --- | --- | --- |
| S1 | Direct measurement, this repository | pilot run 2026-08-08 over `/home/anthonyq/datasets/ETH/courtyard/images/dslr_images_undistorted` | ETH3D courtyard mixes 6205×4135, 6208×4134 and 6198×4129 within one scene; per-image scales differ in the fourth decimal |
| S2 | Predecessor source, `scene_agent/breadth_agent/src/sfmcore/cameramanager.py` | `_read_images`, lines ~199–201 and ~203 | Scale and both shape tuples were assigned after the loop from the last image's locals in the uncalibrated path, and derived from image 0 alone in the calibrated path — so a mixed-resolution set got one wrong scalar applied to every image |

## Dataset layouts

Recorded in [limitations.md](limitations.md#empty-or-near-empty-sets) and
verified against the datasets on this machine as of 2026-08-08:

```
DTU              <root>/scan<N>/                                  flat, .png
Tanks & Temples  <root>/<scene>_<start>_<end>/                    flat, .jpg
ETH3D            <root>/<scene>/images/dslr_images_undistorted/   nested, .JPG
CO3D             <root>/<category>/<sequence>/<subset>/           nested
```

Calibration sits at a different depth in each:

```
DTU              <root>/calibration_DTU_new.npz                   one for all scans
Tanks & Temples  <root>/calibration_new_{1920,2048}.npz           chosen by resolution
ETH3D            <root>/<scene>/dslr_calibration_undistorted/calibration_ETH_new.npz
CO3D             <root>/<category>/calibration_new_<sequence>.npz
```

## Review triggers

- **A new dataset is onboarded.** Add its layout above; the list is the thing
  people actually need and it is only useful if it is complete.
- **The `.npz` calibration convention changes.** `k_mats (N,3,3)`,
  `dists (N,1,5)` and `baseline_ext` are assumed by `read_calibration`; the
  reader tolerates `(N,5)` for dists but nothing else.
- **A dataset appears with per-image intrinsics.** The median-scale
  approximation documented in [limitations.md](limitations.md#mixed-source-resolutions)
  stops being adequate and `camera_index` should carry real per-camera entries.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Numeric tuning advice with no citation in this file.** `image_dir` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 20 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.1.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.
