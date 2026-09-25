"""PoseMapAnything -- scene/v1 -> poses/v1.

Feed-forward camera poses and intrinsics, read off MapAnything's camera head. The
sibling of `PoseVGGT`, and it exists for one reason that has nothing to do with
being better than PoseVGGT: it is a SECOND estimator that consumes the scene and
nothing else.

**Why that matters, and it is the whole design note.** Every other producer of
poses in this registry is downstream of correspondences. `PoseEssentialToPnP`
needs tracks. `SparseGlobalCOLMAP` needs pairwise matches. `SparseVGGT` and
`SparseMapAnything` both take the poses as INPUT and are therefore conditioned on
the geometry one might want to check. That leaves exactly one module whose answer
is independent of the matcher -- `PoseVGGT` -- and one opinion cannot break a tie.
A capture whose correspondences are wrong in a globally consistent way (repeated
or near-symmetric structure) produces a model that agrees with its own evidence at
every baseline, and every reading built on that evidence agrees with it. Measured
on such a capture: two different matchers produced models agreeing to 3.8%, the
held-out residual was the LOWEST of its batch, and the delivered cloud was metres
wrong. Two correspondence-free estimators can disagree with the matcher together,
which is a reading the pipeline cannot otherwise produce.

**It runs UNCONDITIONED.** MapAnything will accept poses and intrinsics and
predict the rest, which is what `SparseMapAnything` uses and why that module is
not a second opinion. Here nothing is supplied: no intrinsics, no poses, no
metric-scale assertion. Conditioning it on the very geometry it is being asked to
check independently would defeat the only purpose this module has.

**Frame and scale are its own.** `camera_poses` comes back camera-to-world in
MapAnything's world frame at MapAnything's scale, exactly as VGGT's do, and is
inverted here to the cam-from-world the type declares. Nothing about the output is
metric and `is_metric_scale` is never asserted.

Intrinsics are recovered per view and mapped from the model's preprocessed frame
back to the scene's working resolution. `preprocess_inputs` resizes uniformly and
centre-crops, which is affine, so the model's own returned K and the scene's K
give the scale and offset directly -- the same derivation `SparseMapAnything`
uses, and for the same reason: it stays correct if the upstream resolution table
changes.
"""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image
from sfmkit import Ctx, module
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs

MODEL_ID = "facebook/map-anything"
_MODEL: MapAnything | None = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model() -> MapAnything:
    global _MODEL
    if _MODEL is None:
        _MODEL = MapAnything.from_pretrained(MODEL_ID).to(device()).eval()
    return _MODEL


def camera_centers(cam_from_world: np.ndarray) -> np.ndarray:
    return np.array([-P[:, :3].T @ P[:, 3] for P in cam_from_world])


@module
def run(ctx: Ctx) -> None:
    p = ctx.params
    scene = ctx.input("scene")
    paths = scene.load("images", "paths")
    n_images = len(paths)
    sizes = np.asarray(scene.load("images", "size_current"))

    model = get_model()
    dev = device()

    cam_from_world = np.zeros((n_images, 3, 4), np.float64)
    K_all = np.zeros((n_images, 3, 3), np.float64)
    valid = np.zeros(n_images, bool)

    chunk = p.max_images_per_pass or n_images
    groups = [list(range(i, min(i + chunk, n_images)))
              for i in range(0, n_images, chunk)]

    for gi, frames in enumerate(groups):
        ctx.progress(0.1 + 0.8 * gi / len(groups),
                     f"pass {gi + 1} of {len(groups)}")
        views = [{"img": np.asarray(
            Image.open(scene.resolve(str(paths[f]))).convert("RGB"))}
            for f in frames]
        processed = preprocess_inputs(views, norm_type=model.encoder.data_norm_type)
        with torch.no_grad():
            predictions = model.infer(
                processed,
                memory_efficient_inference=p.memory_efficient_inference,
                amp_dtype=p.amp_dtype,
            )
        for k, f in enumerate(frames):
            pred = predictions[k]
            # camera-to-world 4x4 -> cam-from-world 3x4, the type's convention.
            c2w = pred["camera_poses"][0].float().cpu().numpy().astype(np.float64)
            R, t = c2w[:3, :3], c2w[:3, 3]
            cam_from_world[f, :, :3] = R.T
            cam_from_world[f, :, 3] = -R.T @ t
            # Model-frame K -> scene working resolution. Uniform resize plus a
            # centre crop is affine, so one scale per axis and an offset invert it.
            K_model = pred["intrinsics"][0].float().cpu().numpy().astype(np.float64)
            w, h = int(sizes[f, 0]), int(sizes[f, 1])
            th, tw = processed[k]["img"].shape[-2:]
            sx, sy = tw / w, th / h
            s = min(sx, sy) if p.assume_uniform_scale else sx
            K = K_model.copy()
            K[0, 2] += (s * w - tw) / 2.0
            K[1, 2] += (s * h - th) / 2.0
            K[:2, :] /= s
            K_all[f] = K
            valid[f] = True
        del predictions, processed
        if dev.type == "cuda":
            torch.cuda.empty_cache()

    ctx.progress(0.9, "writing poses")

    centers = camera_centers(cam_from_world[valid])
    if len(centers) > 1:
        a, b = np.triu_indices(len(centers), k=1)
        sep = np.linalg.norm(centers[a] - centers[b], axis=1)
        median_separation = float(np.median(sep))
        span = float(median_separation / sep.max()) if sep.max() > 0 else 0.0
    else:
        median_separation, span = 0.0, 0.0

    focal_ratio = None
    if scene.has("calibration"):
        calib = scene.load("calibration")
        given = np.asarray(calib["intrinsics"], dtype=np.float64)
        cam_index = calib.get("camera_index")
        if cam_index is None:
            cam_index = (np.arange(n_images) if len(given) == n_images
                         else np.zeros(n_images, int))
        given = given[np.asarray(cam_index, dtype=int)]
        ratios = K_all[valid, 0, 0] / np.maximum(given[valid, 0, 0], 1e-9)
        focal_ratio = float(np.mean(ratios))

    out = ctx.output("poses")
    out.save("poses", cam_from_world=cam_from_world, valid=valid,
             image_index=np.arange(n_images, dtype=np.int32))
    # As in PoseVGGT: poses/v1 carries no intrinsics file, so the estimate goes in
    # a sidecar array under the same slot, which the additive-extension rule allows.
    out.save("intrinsics", K=K_all, camera_index=np.arange(n_images, dtype=np.int32))

    out.metric("registered_fraction", round(float(valid.mean()), 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("registered_images", int(valid.sum()),
               direction="higher_better", healthy=(3, None))
    # Null for the same reason PoseVGGT's are null: a reprojection error computed
    # from the model's own point maps reports how self-consistent the network is,
    # not whether it is right.
    out.metric("mean_reprojection_error", None, direction="lower_better")
    out.metric("median_reprojection_error", None, direction="lower_better")
    out.metric("median_camera_separation", round(median_separation, 6),
               direction="neutral")
    out.metric("baseline_span", round(span, 4),
               direction="higher_better", healthy=(0.1, None))
    out.metric("estimated_focal_ratio",
               round(focal_ratio, 4) if focal_ratio is not None else None,
               direction="neutral")
    out.metric("chunks", len(groups), direction="lower_better", healthy=(None, 1))

    if len(groups) > 1:
        out.diagnostic(
            "chunked", severity="error",
            message=(
                f"The set was run in {len(groups)} passes. Each pass has its own "
                f"world frame and its own scale and this module does not stitch "
                f"them, so poses across passes are not comparable."),
            suggested_actions=[
                "Sample fewer images rather than chunking.",
                "If the poses are wanted as a second opinion, a chunked answer "
                "cannot serve: the comparison needs one frame."])
