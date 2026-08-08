# Limitations — SceneLoader

---

## Mixed source resolutions

**Signature:** the `mixed_resolution` diagnostic fires; `size_original` rows differ.

**Not an error.** Real datasets do this. ETH3D `courtyard` mixes 6205×4135,
6208×4134 and 6198×4129 within a single scene [S1].

**What it invalidates:** any single scalar scale for the set. The predecessor
computed one scale from one image and applied it to all, so on this scene every
other image's keypoint coordinates were being converted with a factor wrong in
the fourth decimal — small, systematic, and biased rather than noisy, which is
the worst kind of error in triangulated geometry.

**What this module does:** records `size_original`, `size_current` and `scale`
per image. Downstream must index them per image.

**What is still approximated:** intrinsics are scaled by the **median** scale
across the set, because the calibration file supplies one K for the whole scene.
That is exact when resolutions are uniform and the best single answer when they
are not. If you need per-image intrinsics for a mixed-resolution scene, this
module cannot express it — `scene/v1` supports `camera_index`, so the escape is a
loader that emits one camera per distinct resolution.

---

## Uncalibrated scenes

**Signature:** the `uncalibrated` diagnostic; no `calibration` file in the artifact.

**Correct for** VGGT and MapAnything paths, which estimate intrinsics and perform
worse when handed a supplied K.

**A hard stop for** classical pose estimation from the essential matrix, which
needs K by construction. If a downstream module requires intrinsics and the scene
has none, that is a wiring problem the orchestrator cannot catch — `scene/v1` is
the right type either way, since calibration is an optional file within it.

**Escape:** supply `calibration_path`, or route through a module that produces
`poses/v1` with an `intrinsics` file, and use those downstream.

---

## Empty or near-empty sets

**Signature:** `too_few_images`; the module raises rather than producing an artifact.

**Almost always** `image_dir` pointing at a parent rather than the leaf that holds
image files. The layouts differ per dataset and none of them are guessable:

```
DTU              <root>/scan1/                                    flat
Tanks & Temples  <root>/barn_1_40/                                flat
ETH3D            <root>/<scene>/images/dslr_images_undistorted/   nested
CO3D             <root>/<category>/<sequence>/<subset>/           nested
```

**Second most likely:** `pattern` excluding the files present, or the files
having an extension outside the recognised set (`.png .jpg .jpeg .tif .tiff
.bmp .ppm .pgm .webp`). Enumeration is **not** recursive, deliberately — a
recursive default silently pulls in thumbnails, masks, and depth maps from
sibling directories.

---

## `resize: none` makes the dataset a runtime dependency

**Signature:** a downstream module fails to read an image, reporting a path that
exists on the host.

**Why:** with `resize: none` the artifact records absolute paths into the dataset
rather than copying pixels in. Every downstream container then needs the dataset
mounted at that same absolute path.

**Escape:** use any resize policy other than `none`, and the artifact becomes
self-contained. `resize: auto, max_edge: <native long edge>` gets you effectively
unresized pixels while keeping self-containment, at the cost of one re-encode.

---

## Not handled at all

- **Video files.** Input is a directory of stills. Extract frames first.
- **Recursive discovery.** Deliberate, per above.
- **Per-image intrinsics.** One K for the set; see the mixed-resolution section.
- **Masks, depth, or any per-image side channel.** `scene/v1` could carry them as
  optional arrays under the additive-extension rule, but this loader does not
  produce them.
