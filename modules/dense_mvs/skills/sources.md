---
module: DenseMVS
module_version: 1.0.0
curated_at: 2026-08-11
---

# Sources

## Pixelwise View Selection for Unstructured Multi-View Stereo
Schönberger, Zheng, Pollefeys, Frahm — ECCV 2016.
<https://demuc.de/papers/schoenberger2016mvs.pdf>

The algorithm this module runs. Its contribution is joint estimation of depth,
normal, and *which views to use per pixel* — the reason it degrades gracefully on
an unstructured collection where a fixed reference/source split does not.

The filtering stage is the part worth knowing when reading the parameters:
`filter_min_ncc`, `filter_min_triangulation_angle` and
`filter_min_num_consistent` are three independent gates, and a pixel must pass all
three. `depth_map_completeness` is what is left.

## COLMAP
Schönberger & Frahm — CVPR 2016. <https://colmap.github.io>

`pycolmap.undistort_images`, `patch_match_stereo`, `stereo_fusion`, at pycolmap
4.1.1.

## pycolmap-cuda12
<https://pypi.org/project/pycolmap-cuda12/>

The same package and version as `pycolmap`, with the same import name, built with
CUDA. It exists because `patch_match_stereo` is CUDA-only in COLMAP — there is no
CPU implementation to fall back to — and the PyPI `pycolmap` wheels are built
without it, so this module simply cannot run on them.

Two build notes:

- The CUDA wheel links X11 session management, so the image needs `libsm6`,
  `libxext6` and `libxrender1` on top of the base's `libgl1`. Without them the
  import fails as `libSM.so.6: cannot open shared object file`, which reads like a
  display problem and is not — nothing here opens a window.
- It carries its own CUDA runtime via `nvidia-cuda-runtime-cu12` and
  `nvidia-curand-cu12`, so the image does not build `FROM runtime-torch` and the
  whole module image is 742 MB rather than 6 GB.

## API details this module depends on

- `stereo_fusion(output_path=...)` wants a **directory**, not a `.ply` path, at
  the default `output_type="bin"`. Passing a filename fails inside COLMAP with
  `Check failed: colmap::ExistsDir(path_val)`.
- `PatchMatchOptions.write_consistency_graph` must be on, because fusion walks
  that graph. It defaults to off.
- `gpu_index` is left at `"-1"` — all visible devices. The GPU broker gives this
  container exactly one, so "all visible" and "the leased one" are the same set,
  and naming `ctx.device` here would name a host index the container cannot see.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/scenereconstruction.py`,
`Dense3DReconstructionMVS`.

Differences:

- It required a COLMAP workspace to have been laid down on disk by an earlier
  optimizer stage, so the dense step could not run without that specific
  predecessor. This builds the workspace from a `sparse_model/v1` artifact, so any
  sparse producer feeds it.
- It set `opts.geom_consistency_max_cost` and `opts.min_triangulation_angle`,
  which are the *optimisation* fields. The gates that decide what survives are
  `filter_geom_consistency_max_cost` and `filter_min_triangulation_angle` — the
  intended tuning knobs were the ones next to the ones it set.
- It reported no metrics at all; `DenseSceneEstimation` set `use_base_metrics =
  True` and registered no providers. Everything under `metrics:` here is new.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `point_count`, `views_contributing` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `max_image_size`, `window_radius`, `window_step`, `num_samples`, `num_iterations`, `filter_min_ncc`, and 6 more name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.0.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `point_count`, `views_contributing` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
