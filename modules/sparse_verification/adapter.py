"""SparseVerification -- does a finished sparse model agree with evidence it was not fit on?

Every error reading a sparse model carries is computed over the observations the
model kept, and bundle adjustment minimised exactly those. A model that settled
into a wrong but self-consistent configuration therefore scores well on all of
them. Measured: one capture solved repeatedly from identical correspondences gave
models an order of magnitude apart against reference geometry, and the badly wrong
ones reported LOWER reprojection error, registered every frame, and satisfied every
rung of the health profile better than the correct ones.

The matcher produces more correspondences than any model keeps, and the ones a
model did not keep were never in its objective. That is held-out evidence. For each
matched pair this module takes the correspondences that do NOT coincide with an
observation of one model point in both images, measures their epipolar distance
under the model's own relative pose, and takes the pair's median. The reading is
the median over pairs, each weighted by its count of held-out correspondences.

Three simpler designs were tried and each failed for a reason worth keeping:

  - Choosing "short-baseline" pairs by frame index worked, but assumes the images
    are in capture order, which an unordered collection is not.
  - Weighting pairs by the model's own co-visibility selects exactly the pairs the
    model was fit on, and reads its own residual back: flat across correct and
    badly wrong models alike.
  - Comparing the model against each pair's own best two-view fit fails on a dense
    matcher, whose smooth correspondences between barely-overlapping images give a
    two-view fit a large consensus of nothing.

The pair's median over held-out evidence, weighted by how much of it there is,
needs no ordering and no second fit, and survives a matcher's outliers as long as
they are a minority on the pairs that carry the weight.

What it cannot see: an error that every pair's correspondences allow. Two models of
one shallow subject, one a few degrees wrong and one nearly exact, read the same --
on their own matches and on each other's. This checks agreement with evidence. It
does not measure accuracy, and a clean reading is not a certificate.
"""
from __future__ import annotations

import cv2
import numpy as np
from sfmkit import Ctx, module

# Two correspondences closer than this in BOTH images are one correspondence. The
# widest merge radius any tracker in the stack uses by default, so an observation a
# tracker built from a match is always recognised here as that match.
COINCIDENCE_PX = 2.0
_KEY = 1_000_003  # row stride for the grid-cell key; larger than any cell index


# --------------------------------------------------------------------------- #
# Cameras
# --------------------------------------------------------------------------- #


def cameras(scene, model, n_images: int):
    """(K to undistort with, distortion, K to project with), per image.

    Match coordinates are in the scene's DISTORTED working-resolution pixels;
    sparse_model/v1 lives in undistorted pixels. So matches are undistorted with
    the scene's calibration -- the same one every producer used on its own
    observations -- and projected with the model's intrinsics when it refined
    them, because a model's poses were solved jointly with its own K and the two
    cannot be mixed with an older one.
    """
    K_model = None
    if "intrinsics" in model.manifest.files:
        intr = model.load("intrinsics")
        K = np.asarray(intr["K"], dtype=np.float64)
        ci = intr.get("camera_index")
        ci = np.arange(n_images) if ci is None else np.asarray(ci, dtype=int)
        K_model = K[ci]

    if "calibration" in scene.manifest.files:
        cal = scene.load("calibration")
        Ks = np.asarray(cal["intrinsics"], dtype=np.float64)
        dist = np.asarray(cal["distortions"], dtype=np.float64)
        ci = cal.get("camera_index")
        ci = np.zeros(n_images, dtype=int) if ci is None else np.asarray(ci, dtype=int)
        K_scene, dist = Ks[ci], dist[ci]
    elif K_model is not None:
        # An uncalibrated scene reconstructed by a module that estimated K. There
        # is no distortion model to undo, so the matches are taken as they are.
        K_scene, dist = K_model, np.zeros((n_images, 5))
    else:
        raise ValueError(
            "neither the scene nor the model carries intrinsics, so no relative "
            "pose can be turned into an epipolar constraint. Verify a model from a "
            "calibrated scene, or one whose producer estimated K."
        )
    return K_scene, dist, (K_model if K_model is not None else K_scene)


def undistort(xy, image_pair, pair_index, K_scene, dist):
    """Match coordinates -> undistorted pixels, per image."""
    if not np.any(dist):
        return xy
    out = xy.copy()
    for side, cols in ((0, slice(0, 2)), (1, slice(2, 4))):
        image = image_pair[pair_index, side]
        for f in np.unique(image):
            sel = image == f
            pts = xy[sel, cols].reshape(-1, 1, 2)
            out[sel, cols] = cv2.undistortPoints(
                pts, K_scene[f], dist[f], P=K_scene[f]
            ).reshape(-1, 2)
    return out


def fundamental(Ki, Kj, cam_i, cam_j):
    """F with x_j^T F x_i = 0, from two cam_from_world poses. None at zero baseline."""
    Ri, ti, Rj, tj = cam_i[:, :3], cam_i[:, 3], cam_j[:, :3], cam_j[:, 3]
    R = Rj @ Ri.T
    t = tj - R @ ti
    norm = np.linalg.norm(t)
    if norm < 1e-12:
        return None
    t = t / norm
    tx = np.array([[0.0, -t[2], t[1]], [t[2], 0.0, -t[0]], [-t[1], t[0], 0.0]])
    return np.linalg.inv(Kj).T @ (tx @ R) @ np.linalg.inv(Ki)


def sampson(F, xy):
    """First-order geometric distance to the epipolar constraint, in pixels."""
    x1 = np.c_[xy[:, :2], np.ones(len(xy))]
    x2 = np.c_[xy[:, 2:4], np.ones(len(xy))]
    Fx1, Ftx2 = x1 @ F.T, x2 @ F
    num = np.einsum("ij,ij->i", x2, Fx1) ** 2
    den = Fx1[:, 0] ** 2 + Fx1[:, 1] ** 2 + Ftx2[:, 0] ** 2 + Ftx2[:, 1] ** 2
    return np.sqrt(num / np.maximum(den, 1e-12))


# --------------------------------------------------------------------------- #
# Which matches the model used
# --------------------------------------------------------------------------- #


def observation_index(model) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Per frame: observations bucketed on a COINCIDENCE_PX grid, sorted by cell."""
    obs = np.asarray(model.load("observations", "obs"))
    frame = obs[:, 0].astype(np.int64)
    point = obs[:, 1].astype(np.int64)
    xy = obs[:, 2:4].astype(np.float64)
    index = {}
    for f in np.unique(frame):
        sel = frame == f
        cell = np.floor(xy[sel] / COINCIDENCE_PX).astype(np.int64) + 1
        key = cell[:, 0] * _KEY + cell[:, 1]
        order = np.argsort(key, kind="stable")
        index[int(f)] = (key[order], xy[sel][order], point[sel][order])
    return index


def nearest_point(index_f, q: np.ndarray) -> np.ndarray:
    """The model point observed within COINCIDENCE_PX of each query, or -1."""
    best = np.full(len(q), -1, dtype=np.int64)
    if index_f is None or not len(q):
        return best
    keys, xy, point = index_f
    best_d = np.full(len(q), np.inf)
    cell = np.floor(q / COINCIDENCE_PX).astype(np.int64) + 1
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            k = (cell[:, 0] + dx) * _KEY + (cell[:, 1] + dy)
            lo = np.searchsorted(keys, k, "left")
            hi = np.searchsorted(keys, k, "right")
            for step in range(int((hi - lo).max(initial=0))):
                j = lo + step
                ok = j < hi
                jj = np.where(ok, j, 0)
                d = np.where(ok, np.hypot(xy[jj, 0] - q[:, 0], xy[jj, 1] - q[:, 1]), np.inf)
                closer = d < best_d
                best_d[closer] = d[closer]
                best[closer] = point[jj][closer]
    best[best_d > COINCIDENCE_PX] = -1
    return best


def weighted_median(values, weights) -> float:
    v, w = np.asarray(values, dtype=np.float64), np.asarray(weights, dtype=np.float64)
    order = np.argsort(v)
    c = np.cumsum(w[order])
    return float(v[order][np.searchsorted(c, 0.5 * c[-1])])


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    model = ctx.inputs["sparse"]
    matches = ctx.inputs["matches"]
    p = ctx.params

    # Same capture, or the reading is a number about nothing. Any matches
    # artifact of this scene is legitimate evidence -- the model's own ancestor or
    # another matcher's -- but one from a different scene indexes other images.
    scenes = {scene.id, model.manifest.scene or scene.id, matches.manifest.scene or scene.id}
    if len(scenes) != 1:
        raise ValueError(
            f"scene, model and matches do not belong to one scene: scene {scene.id}, "
            f"model from {model.manifest.scene}, matches from {matches.manifest.scene}. "
            f"Frame indices would refer to different images."
        )

    n_images = len(scene.load("images", "names"))
    K_scene, dist, K_model = cameras(scene, model, n_images)
    cam = np.asarray(model.load("poses", "cam_from_world"), dtype=np.float64)
    valid = np.asarray(model.load("poses", "valid"), dtype=bool)
    image_index = np.asarray(model.load("poses", "image_index"), dtype=np.int64)
    pose = {int(i): cam[r] for r, (i, ok) in enumerate(zip(image_index, valid)) if ok}

    image_pair = np.asarray(matches.load("pairs", "image_pair"), dtype=np.int64)
    xy = np.asarray(matches.load("matches", "xy"), dtype=np.float64)
    pair_index = np.asarray(matches.load("matches", "pair_index"), dtype=np.int64)
    ctx.progress(0.1, f"undistorting {len(xy)} correspondences")
    xy = undistort(xy, image_pair, pair_index, K_scene, dist)
    order = np.argsort(pair_index, kind="stable")
    xy, pair_index = xy[order], pair_index[order]
    bounds = np.searchsorted(pair_index, np.arange(len(image_pair) + 1))

    ctx.progress(0.3, "indexing the model's observations")
    index = observation_index(model)

    rows = []  # (i, j, matches, held_out, residual)
    total = held_total = 0
    for pi, (i, j) in enumerate(image_pair):
        if pi % 200 == 0:
            ctx.progress(0.3 + 0.6 * pi / max(len(image_pair), 1), "scoring pairs")
        i, j = int(i), int(j)
        block = xy[bounds[pi]:bounds[pi + 1]]
        if i not in pose or j not in pose or not len(block):
            continue
        F = fundamental(K_model[i], K_model[j], pose[i], pose[j])
        if F is None:
            continue
        a = nearest_point(index.get(i), block[:, :2])
        b = nearest_point(index.get(j), block[:, 2:4])
        held = ~((a == b) & (a >= 0))
        n_held = int(held.sum())
        total += len(block)
        held_total += n_held
        residual = (
            float(np.median(sampson(F, block[held])))
            if n_held >= p.min_held_out_per_pair else float("nan")
        )
        rows.append((i, j, len(block), n_held, residual))

    arr = np.array(rows, dtype=np.float64).reshape(-1, 5)
    verified = np.isfinite(arr[:, 4])
    reading = (
        weighted_median(arr[verified, 4], arr[verified, 3]) if verified.any() else None
    )
    share = held_total / total if total else 0.0

    out = ctx.output("verification")
    out.save(
        "pairs",
        image_pair=arr[:, :2].astype(np.int64),
        matches=arr[:, 2].astype(np.int64),
        held_out=arr[:, 3].astype(np.int64),
        residual_px=arr[:, 4],
    )
    out.metric("heldout_residual_px", None if reading is None else round(reading, 4),
               direction="lower_better", healthy=(None, 3.0))
    out.metric("held_out_share", round(share, 4), direction="neutral")
    out.metric("pairs_verified", int(verified.sum()), direction="neutral")

    if reading is None:
        out.diagnostic(
            "nothing_held_out",
            severity="warn",
            message=(
                f"No pair had {p.min_held_out_per_pair} correspondences the model did "
                f"not already use, so there is no independent evidence to test it "
                f"against; the model is unverified, not verified."
            ),
            suggested_actions=[
                "Supply another matcher's pairwise_matches of the same scene as "
                "`matches`. Evidence from a different matcher was never in this "
                "model's objective at all.",
                "Lowering min_held_out_per_pair admits pairs whose median rests on a "
                "handful of correspondences; read the per-pair array before trusting it.",
            ],
            see_also="limitations.md#when-nothing-is-held-out",
        )
    elif reading > p.inlier_threshold_px:
        worst = arr[verified][np.argsort(-arr[verified, 4])][:3]
        out.diagnostic(
            "contradicted_by_held_out_evidence",
            severity="error",
            message=(
                f"Correspondences this model was never fit on sit {reading:.2f}px "
                f"from its epipolar lines, against a {p.inlier_threshold_px:.1f}px "
                f"inlier threshold. Worst pairs: "
                + ", ".join(f"{int(r[0])}-{int(r[1])} at {r[4]:.1f}px" for r in worst)
                + ". The model's own reprojection error cannot see this; it was "
                  "minimised on the other evidence."
            ),
            suggested_actions=[
                "Solve again from the same inputs before changing anything. A "
                "capture can have more than one stable answer, and a second solve "
                "that reads clean here is the model to keep.",
                "Do not choose between models on reprojection error or registration: "
                "a wrong model that is self-consistent satisfies both, and has been "
                "measured satisfying them BETTER than the correct one.",
                "Read the per-pair residual_px array: a contradiction confined to "
                "the pairs across one part of the capture locates where the solve "
                "went wrong.",
            ],
            see_also="limitations.md#what-a-contradiction-means",
        )

    verdict = (
        "UNVERIFIED -- nothing held out" if reading is None
        else f"CONTRADICTED ({reading:.3f}px > {p.inlier_threshold_px:.1f}px)"
        if reading > p.inlier_threshold_px
        else f"consistent ({reading:.3f}px <= {p.inlier_threshold_px:.1f}px)"
    )
    out.note(
        f"Held-out verification over {int(verified.sum())} of {len(arr)} registered "
        f"pairs: {verdict}. {share:.1%} of the matcher's correspondences on those "
        f"pairs were not used by the model and served as the test set. Consistency "
        f"with held-out evidence is not accuracy: an error every pair's "
        f"correspondences allow reads clean here."
    )
