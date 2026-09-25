"""PoseFill -- sparse_model/v1 + poses/v1 -> poses/v1.

One pose table out of two, so the cameras a geometric solve could not support are
carried by a correspondence-free estimator instead of being left out.

**Why this is a pose module and not a model merge.** The obvious shape is to merge
two `sparse_model/v1`s, and that shape is a trap: it means reconciling two point
sets, two track tables and two observation tables built in different frames at
different scales, and the scale question becomes genuinely hard. Merging the POSES
is a seven-parameter problem with a closed-form answer, and once it is done
`SparseTriangulation` builds the structure from the scene's own tracks in ONE
frame. The filled cameras then carry real observations wherever correspondences
reach them, rather than being pose-only stubs bolted onto someone else's cloud.

**The similarity is what removes the scale difference, and it is the whole reason
this is well posed.** A feed-forward estimator returns poses in its own frame at
its own scale. Fitting scale, rotation and translation on the cameras the two
tables SHARE puts the estimator's answer into the core's frame; after that there is
one frame and one scale and nothing downstream can tell a filled camera from a
registered one by its coordinates. It also means this cannot be used as a swap:
with no shared cameras there is nothing to fit on, and the module refuses.

**What the fit cannot absorb, and why the residual is published.** One similarity
assumes the estimator's scale is consistent along the whole capture. A learned
model that DRIFTS -- scale varying as the trajectory runs -- cannot be corrected by
seven parameters, and the filled cameras then land wrong by whatever the drift is
at their position. The residual on the shared cameras is exactly the reading that
sees this: if the cameras both tables agree on do not line up after the fit, the
fit has not found a common frame and the fill is not trustworthy. That is what
`shared_residual` measures and what the `fit_does_not_agree` diagnostic fires on.

**The output marks which cameras are which, and downstream depends on it.** A
filled camera rests on no correspondences, so every reading built on
correspondences will find it unsupported -- correctly, and misleadingly, because it
was never claimed to be supported. `SparseVerification` reads the `filled` array to
keep those cameras out of its stray count, and the producers of `sparse_model/v1`
carry it through so `filled_images` can be read beside `registered_images`. Without
the mark a correctly-filled model is vetoed by construction.
"""
from __future__ import annotations

import numpy as np
from sfmkit import Ctx, module


def centres(cam_from_world: np.ndarray, valid: np.ndarray, image_index: np.ndarray):
    """Camera centres by image index, for the rows that carry a pose."""
    out = {}
    for r, (im, ok) in enumerate(zip(image_index, valid)):
        if ok:
            P = np.asarray(cam_from_world[r], dtype=np.float64)
            out[int(im)] = -P[:, :3].T @ P[:, 3]
    return out


def umeyama(src: np.ndarray, dst: np.ndarray):
    """The least-squares similarity taking `src` onto `dst`: scale, rotation, offset."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(xd.T @ xs / len(src))
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    var = (xs ** 2).sum(1).mean()
    s = float(np.trace(np.diag(S) @ D) / var) if var > 1e-18 else 1.0
    return s, R, mu_d - s * R @ mu_s


def trimmed_fit(src: np.ndarray, dst: np.ndarray, trim: float, rounds: int = 3):
    """Umeyama, then refit on the closest share of the cameras, twice.

    A plain least-squares similarity is pulled by its worst correspondence, and the
    worst shared camera is exactly the one most likely to be misplaced in one of the
    two tables. Trimming makes the fit describe the cameras that agree, which is the
    population the residual is then meaningful over.
    """
    keep = np.ones(len(src), dtype=bool)
    s, R, t = umeyama(src, dst)
    for _ in range(rounds):
        res = np.linalg.norm((s * (R @ src.T)).T + t - dst, axis=1)
        if trim <= 0:
            break
        cut = np.quantile(res, 1.0 - trim)
        cand = res <= max(cut, 1e-12)
        # never trim below the four cameras a similarity needs to stay determined
        if cand.sum() < max(4, int(0.5 * len(src))):
            break
        keep = cand
        s, R, t = umeyama(src[keep], dst[keep])
    res = np.linalg.norm((s * (R @ src.T)).T + t - dst, axis=1)
    return s, R, t, res, keep


@module
def run(ctx: Ctx):
    core = ctx.inputs["sparse"]
    ff = ctx.inputs["poses"]
    p = ctx.params

    scene = ctx.inputs["scene"]
    n_images = len(scene.load("images", "names"))

    core_pose = core.load("poses")
    c_cfw = np.asarray(core_pose["cam_from_world"], dtype=np.float64)
    c_valid = np.asarray(core_pose["valid"], dtype=bool)
    c_idx = np.asarray(core_pose["image_index"], dtype=int)

    ff_pose = ff.load("poses")
    f_cfw = np.asarray(ff_pose["cam_from_world"], dtype=np.float64)
    f_valid = np.asarray(ff_pose["valid"], dtype=bool)
    f_idx = np.asarray(ff_pose["image_index"], dtype=int)

    C = centres(c_cfw, c_valid, c_idx)
    F = centres(f_cfw, f_valid, f_idx)
    shared = sorted(set(C) & set(F))
    missing = sorted(set(F) - set(C))

    ctx.progress(0.3, f"{len(C)} core, {len(F)} feed-forward, {len(shared)} shared")

    if len(shared) < p.min_shared_cameras:
        raise ValueError(
            f"only {len(shared)} camera(s) carry a pose in BOTH tables; the "
            f"similarity needs at least {p.min_shared_cameras}. With too few shared "
            f"cameras there is nothing to fit the estimator's frame and scale onto, "
            f"and this module is not a swap: if the core registered almost nothing, "
            f"deliver the feed-forward model on its own and say so, rather than "
            f"filling a core that is not there."
        )

    src = np.array([F[i] for i in shared])
    dst = np.array([C[i] for i in shared])
    s, R, t, res, keep = trimmed_fit(src, dst, p.trim)

    # Scale-free, so the number means the same thing on a studio rig and a city
    # block: the residual against how far apart the core's own cameras are.
    span = float(np.linalg.norm(np.ptp(dst, axis=0)))
    rel = res / max(span, 1e-12)
    shared_residual = float(np.median(rel))

    cam_from_world = np.zeros((n_images, 3, 4), dtype=np.float64)
    valid = np.zeros(n_images, dtype=bool)
    filled = np.zeros(n_images, dtype=bool)

    # the core, untouched: its frame IS the output frame
    for r, (im, ok) in enumerate(zip(c_idx, c_valid)):
        if ok:
            cam_from_world[int(im)] = c_cfw[r]
            valid[int(im)] = True

    # the rest, carried across by the similarity. A pose is transformed by the
    # INVERSE map on the world side: a point that was X in the estimator's frame is
    # sR X + t here, so the camera that saw it reads R_c (sR)^-1 on the rotation
    # block and must have the offset taken out of the translation.
    Rt, want = R.T, set(missing)
    for r, (im, ok) in enumerate(zip(f_idx, f_valid)):
        i = int(im)
        if not ok or i not in want:
            continue
        P = f_cfw[r]
        Rc, tc = P[:, :3], P[:, 3]
        Rn = Rc @ Rt
        cam_from_world[i, :, :3] = Rn
        cam_from_world[i, :, 3] = s * tc - Rn @ t
        valid[i] = True
        filled[i] = True

    ctx.progress(0.8, f"filled {int(filled.sum())} camera(s)")

    out = ctx.output("poses")
    out.save("poses", cam_from_world=cam_from_world, valid=valid,
             image_index=np.arange(n_images, dtype=np.int32))
    # A sidecar array under the poses slot, which the additive-extension rule
    # allows -- the same place PoseVGGT and PoseMapAnything put their intrinsics.
    # Everything downstream that has to tell a filled camera from a registered one
    # reads this, so it is written even when nothing was filled.
    out.save("fill", filled=filled, shared_cameras=np.array(shared, dtype=np.int32))

    out.metric("registered_images", int(valid.sum()),
               direction="higher_better", healthy=(3, None))
    out.metric("registered_fraction", round(float(valid.sum() / max(n_images, 1)), 3),
               direction="higher_better")
    # Required by poses/v1 and null for the reason PoseVGGT's are null: there is
    # no correspondence in this module, and a number carried over from the core
    # would describe the core rather than the table that came out.
    out.metric("mean_reprojection_error", None, direction="lower_better")
    out.metric("median_reprojection_error", None, direction="lower_better")
    out.metric("filled_images", int(filled.sum()), direction="neutral")
    # No healthy band on either of these, and for the same reason the verifier's
    # mrad reading carries none: the gate IS a parameter, so a fixed band beside it
    # states a second threshold that disagrees with the real one the moment anybody
    # changes it. `min_shared_cameras` is the floor for the first and the module
    # raises below it; `max_shared_residual` is the gate for the second and the
    # diagnostic below is what fires. Read shared_residual against what a capture of
    # this kind reads, which is what the corpus asks of every other residual.
    out.metric("shared_cameras", len(shared), direction="higher_better")
    out.metric("shared_residual", round(shared_residual, 5), direction="lower_better")
    out.metric("fitted_scale", round(float(s), 5), direction="neutral")
    out.metric("shared_cameras_kept", int(keep.sum()), direction="higher_better")

    if shared_residual > p.max_shared_residual:
        out.diagnostic(
            "fit_does_not_agree",
            severity="error",
            message=(
                f"After the similarity, the cameras BOTH tables placed still sit "
                f"{shared_residual:.1%} of the model's span apart (median over "
                f"{len(shared)} shared cameras). The two tables have not been put "
                f"into a common frame, so the {int(filled.sum())} filled camera(s) "
                f"are not trustworthy and neither is anything built on them."
            ),
            suggested_actions=[
                "Do not deliver this fill. Deliver the core and say in the report "
                "which frames are missing and that the capture was not fully solved.",
                "This is what a drifting estimator looks like: one similarity cannot "
                "correct a scale that varies along the capture. It is expected on a "
                "long handheld walk and unexpected on a subsampled orbit.",
                "Read sfm_compare's pose_agreement between the core and the estimator "
                "before spending another run here: if they disagree on the cameras "
                "they share, no fill of them will agree either.",
            ],
            see_also="limitations.md#what-one-similarity-cannot-absorb")

    if not len(missing):
        out.diagnostic(
            "nothing_to_fill",
            severity="warn",
            message=(
                "The feed-forward table carries no camera the core does not already "
                "have, so this module changed nothing."),
            suggested_actions=[
                "The output is the core's poses. Use the core model directly.",
                "If cameras are missing from BOTH tables, the estimator was run on a "
                "reduced set; run it on the whole scene.",
            ],
            see_also="SKILL.md#when-to-run-it")
