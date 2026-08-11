"""PoseVGGT -- scene/v1 -> poses/v1.

Feed-forward camera poses and intrinsics, read off VGGT's camera head. No
correspondences, no seed pair, no registration order.

The intrinsics VGGT returns are for the 518x518 square it was fed, so they are
mapped back to the scene's working resolution before being written.

That mapping is where the first version of this module was wrong, and the error is
worth stating because it is silent. Squeezing a 1024x768 image anisotropically into
518x518 changes the aspect ratio, and VGGT -- which predicts fx == fy, i.e. square
pixels -- cannot know that. Undoing the squeeze per axis then produced K with
fx/fy = 1.329, exactly 1024/768, and a focal length 1.48x the scene's calibration.
The numbers looked like a model/calibration disagreement and were an input bug.

Images are therefore letterboxed the way VGGT's own `load_and_preprocess_images`
does it: aspect preserved, long side 518, short side padded to square. One scale
factor inverts it, and the pad offset comes out of the principal point.
"""

from __future__ import annotations

import os

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from sfmkit import Ctx, module
from vggt.models.vggt import VGGT
from vggt.utils.pose_enc import pose_encoding_to_extri_intri

# VGGT is trained at a fixed 518x518 input. Nothing about this is tunable.
VGGT_SIZE = 518
CHECKPOINT = os.environ.get("VGGT_CHECKPOINT", "/opt/weights/vggt-1b.pt")

_MODEL: VGGT | None = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model() -> VGGT:
    global _MODEL
    if _MODEL is None:
        model = VGGT()
        model.load_state_dict(torch.load(CHECKPOINT, map_location="cpu"))
        _MODEL = model.eval().to(device())
    return _MODEL


def warmup() -> None:
    get_model()


DTYPES = {
    "bfloat16": torch.bfloat16,
    "float16": torch.float16,
    "float32": torch.float32,
}


def letterbox(width: int, height: int) -> tuple[float, int, int, int, int]:
    """Aspect-preserving fit into VGGT_SIZE, matching upstream's `pad` mode.

    Returns (scale, new_w, new_h, pad_x, pad_y). Padding is centred and the offset
    is what the principal point has to be corrected by on the way back.
    """
    scale = VGGT_SIZE / max(width, height)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    return scale, new_w, new_h, (VGGT_SIZE - new_w) // 2, (VGGT_SIZE - new_h) // 2


def load_batch(scene, frames, dev) -> torch.Tensor:
    """Frames -> (N, 3, 518, 518) in [0, 1], letterboxed on white.

    White padding rather than black, matching upstream: the model was trained with
    it, and a black border reads as scene content the aggregator then attends to.
    """
    paths = scene.load("images", "paths")
    batch = []
    for f in frames:
        image = Image.open(scene.resolve(str(paths[f]))).convert("RGB")
        array = np.asarray(image, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1)[None]

        _, new_w, new_h, pad_x, pad_y = letterbox(image.width, image.height)
        resized = F.interpolate(
            tensor, size=(new_h, new_w), mode="bilinear", align_corners=False
        )[0]

        canvas = torch.ones(3, VGGT_SIZE, VGGT_SIZE, dtype=resized.dtype)
        canvas[:, pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
        batch.append(canvas)
    return torch.stack(batch).to(dev)


def camera_centers(cam_from_world: np.ndarray) -> np.ndarray:
    return np.array([-P[:, :3].T @ P[:, 3] for P in cam_from_world])


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    n_images = len(names)

    if n_images < 2:
        raise ValueError(
            f"PoseVGGT needs at least 2 images and the scene has {n_images}. It "
            f"reasons across the whole set at once; a single image has no relative "
            f"pose to estimate."
        )

    model = get_model()
    dev = device()
    dtype = DTYPES[p.dtype]

    chunk = p.max_images_per_pass or n_images
    groups = [list(range(i, min(i + chunk, n_images))) for i in range(0, n_images, chunk)]

    cam_from_world = np.zeros((n_images, 3, 4), dtype=np.float64)
    K_all = np.zeros((n_images, 3, 3), dtype=np.float64)
    valid = np.zeros(n_images, dtype=bool)

    for step, frames in enumerate(groups):
        ctx.progress(
            0.1 + 0.7 * step / len(groups),
            f"pass {step + 1}/{len(groups)}, {len(frames)} images",
        )
        images = load_batch(scene, frames, dev)

        with torch.no_grad():
            with torch.amp.autocast(dev.type, dtype=dtype):
                tokens, _ = model.aggregator(images[None])
            # The camera head is run OUTSIDE autocast: it decodes a pose encoding
            # into a rotation, and half-precision there costs accuracy in the one
            # place this module has no way to recover it.
            pose_encoding = model.camera_head(tokens)[-1]
            extrinsic, intrinsic = pose_encoding_to_extri_intri(
                pose_encoding, images.shape[-2:]
            )

        extrinsic = extrinsic[0].float().cpu().numpy()
        intrinsic = intrinsic[0].float().cpu().numpy()

        for k, f in enumerate(frames):
            cam_from_world[f] = extrinsic[k]
            # Undo the letterbox: one scale for both axes -- which is what keeps
            # fx == fy, as VGGT predicted it -- and the pad offset out of the
            # principal point.
            scale, _, _, pad_x, pad_y = letterbox(int(sizes[f, 0]), int(sizes[f, 1]))
            K = intrinsic[k].copy()
            K[0, 2] -= pad_x
            K[1, 2] -= pad_y
            K[:2, :] /= scale
            K_all[f] = K
            valid[f] = True

        del images, tokens
        if dev.type == "cuda":
            torch.cuda.empty_cache()

    ctx.progress(0.9, "writing poses")

    centers = camera_centers(cam_from_world[valid])
    if len(centers) > 1:
        a, b = np.triu_indices(len(centers), k=1)
        separations = np.linalg.norm(centers[a] - centers[b], axis=1)
        median_separation = float(np.median(separations))
        span = (
            float(median_separation / separations.max())
            if separations.max() > 0 else 0.0
        )
    else:
        median_separation, span = 0.0, 0.0

    focal_ratio = None
    if scene.has("calibration"):
        calib = scene.load("calibration")
        given = np.asarray(calib["intrinsics"], dtype=np.float64)
        cam_index = calib.get("camera_index")
        if cam_index is None:
            cam_index = (
                np.arange(n_images) if len(given) == n_images
                else np.zeros(n_images, int)
            )
        given = given[np.asarray(cam_index, dtype=int)]
        ratios = K_all[valid, 0, 0] / np.maximum(given[valid, 0, 0], 1e-9)
        focal_ratio = float(np.mean(ratios))

    out = ctx.output("poses")
    out.save(
        "poses",
        cam_from_world=cam_from_world,
        valid=valid,
        image_index=np.arange(n_images, dtype=np.int32),
    )
    # poses/v1 carries no intrinsics file, so the estimate goes in a sidecar array
    # under the same slot. Consumers that prefer a model's own K read it; the
    # additive-extension rule makes this legal without a new type.
    out.save("intrinsics", K=K_all, camera_index=np.arange(n_images, dtype=np.int32))

    out.metric("registered_fraction", round(float(valid.mean()), 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("registered_images", int(valid.sum()),
               direction="higher_better", healthy=(3, None))
    # Null, not zero, and not a number derived from VGGT's own point maps: that
    # would report how self-consistent the network is, not how accurate it is.
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
            "chunked",
            severity="error",
            message=(
                f"The {n_images} images were split across {len(groups)} forward "
                f"passes; each has its own world frame and scale."
            ),
            suggested_actions=[
                "Set max_images_per_pass to 0 and sample fewer images instead.",
                "Or reconstruct each chunk as its own scene.",
            ],
            see_also="limitations.md#chunking-does-not-stitch",
        )

    if focal_ratio is not None and not 0.8 <= focal_ratio <= 1.25:
        out.diagnostic(
            "intrinsics_disagree",
            severity="warn",
            message=(
                f"Estimated focal length is {focal_ratio:.2f}x the scene's "
                f"calibrated value."
            ),
            suggested_actions=[
                "Trust the calibration and use PoseEssentialToPnP instead.",
                "Or trust VGGT, and note downstream modules read ITS intrinsics.",
                "Check the scene's calibration was scaled to the working resolution.",
            ],
            see_also="artifact.md#it-writes-its-own-intrinsics",
        )

    if span < 0.1:
        out.diagnostic(
            "degenerate_baseline",
            severity="warn",
            message=f"Camera separations span a factor of {1 / max(span, 1e-9):.0f}.",
            suggested_actions=[
                "Check the capture has translation and not only rotation.",
                "Nothing triangulated against these poses will condition well.",
            ],
            see_also="limitations.md#what-it-cannot-tell-you",
        )

    out.note(
        f"VGGT-1B camera head, {len(groups)} forward pass(es) over {n_images} "
        f"images at {VGGT_SIZE}x{VGGT_SIZE} in {p.dtype}. Every image is posed; "
        f"there is no registration to fail. Intrinsics were ESTIMATED and written "
        f"beside the poses"
        + (f", at {focal_ratio:.2f}x the scene's calibrated focal length"
           if focal_ratio is not None else " (the scene carries no calibration)")
        + f". Median camera separation {median_separation:.4f} in the model's "
        f"arbitrary scale unit. Reprojection error is null by construction -- this "
        f"module has no correspondences, so triangulate against these poses and "
        f"read the triangulator's error."
    )
