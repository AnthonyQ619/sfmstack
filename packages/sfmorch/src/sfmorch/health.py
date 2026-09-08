"""The seven-rung health profile of a finished sparse model.

Defined and argued in `skills/health/ladder.md`. Every component here is
computed from the model and its lineage alone -- no ground truth -- and is
scene-size invariant, so a percentile against a reference corpus is a fair
comparison rather than a measure of which scene you are on.

**This is the single implementation.** The reference campaign that produces the
corpus distribution and the run-summary digest that scores a new model against
it both call `components()` here. Two implementations of one rung would make
every percentile meaningless in a way nothing would detect: the reading and the
distribution it is scored against have to be the same measurement.

Read the rungs ONLY after the sparse reconstruction step. Nothing here applies
to an upstream stage, even where a component sounds computable early -- judging
a model from upstream readings is the first entry in `health/smells.md`.
"""
from __future__ import annotations

import numpy as np

# The grid the coverage rung counts cells of. 8x8 matches the coverage
# denominator the detection-phase campaign settled, so the two read on one scale.
COVERAGE_GRID = 8

# How many image pairs the pose-agreement rung re-estimates. Bounded because
# this runs inline in a run payload: a 50-image capture matched exhaustively has
# over a thousand pairs, and a digest that costs minutes is a digest that gets
# turned off. The pairs are taken in order of match count, so the cap keeps the
# best-supported edges rather than an arbitrary slice.
POSE_PAIR_CAP = 200

# The support a point needs before its reprojection error is allowed to speak.
# A two-view point is exactly determined, so its residual is near zero whatever
# the model is worth; the error rung is about the rest of the cloud.
MIN_SUPPORT = 3


def _load(art, group: str, name: str, default=None):
    try:
        return art.load(group, name)
    except Exception:
        return default


def track_lengths(obs: np.ndarray, n_points: int) -> np.ndarray:
    """Observations per 3D point. `obs` columns: frame_idx, point_index, x, y."""
    return np.bincount(obs[:, 1].astype(np.int64), minlength=n_points)


def triangulation_angles(xyz, obs, cams, valid, image_index) -> np.ndarray:
    """Per-point WIDEST angle between any two observing rays, in degrees.

    The widest rather than the mean, because a point triangulated from a
    mediocre pair can still be well conditioned by a third view -- the same
    reading SparseTriangulation's own filter uses.
    """
    centres = {}
    for row, (im, ok) in enumerate(zip(image_index, valid)):
        if ok:
            R, t = cams[row][:, :3], cams[row][:, 3]
            centres[int(im)] = -R.T @ t

    by_point: dict[int, list] = {}
    for frame_idx, pi, _x, _y in obs:
        c = centres.get(int(frame_idx))
        if c is not None:
            by_point.setdefault(int(pi), []).append(c)

    out = []
    for pi, cs in by_point.items():
        if len(cs) < 2 or pi >= len(xyz):
            continue
        rays = np.asarray(cs) - xyz[pi]
        n = np.linalg.norm(rays, axis=1)
        keep = n > 1e-12
        if keep.sum() < 2:
            continue
        rays = rays[keep] / n[keep, None]
        cos = np.clip(rays @ rays.T, -1.0, 1.0)
        np.fill_diagonal(cos, 1.0)
        out.append(np.degrees(np.arccos(cos.min())))
    return np.asarray(out, dtype=float)


def coverage(obs, sizes, registered, grid: int = COVERAGE_GRID) -> float:
    """Median over registered frames of the fraction of grid cells holding at
    least one observation.

    Evenness, never totals: a camera can be registered and carry almost no
    structure, and a whole-model point count cannot be moved by one starved
    view -- that view is where the next stage fails.
    """
    per_frame = []
    frames = obs[:, 0].astype(np.int64)
    for f in sorted(registered):
        rows = obs[frames == f]
        if len(rows) == 0:
            per_frame.append(0.0)
            continue
        w, h = sizes[f] if f < len(sizes) else sizes[0]
        gx = np.clip((rows[:, 2] / max(float(w), 1.0) * grid).astype(int), 0, grid - 1)
        gy = np.clip((rows[:, 3] / max(float(h), 1.0) * grid).astype(int), 0, grid - 1)
        per_frame.append(len(set(zip(gx.tolist(), gy.tolist()))) / (grid * grid))
    return float(np.median(per_frame)) if per_frame else 0.0


def two_view_relatives(matches, scene, *, cap: int = POSE_PAIR_CAP) -> dict:
    """Relative pose per image pair, re-estimated from the stored matches.

    Recomputed rather than read off the artifact: a matcher publishes inlier
    counts and match geometry, never a relative pose. Reads `matches/xy`
    directly so a detector-free matcher -- which carries no `feature_index` --
    is measured the same way.
    """
    try:
        import cv2
    except ImportError:
        return {}
    pairs = _load(matches, "pairs", "image_pair")
    xy = _load(matches, "matches", "xy")
    pair_index = _load(matches, "matches", "pair_index")
    K = _load(scene, "calibration", "intrinsics") if scene is not None else None
    if pairs is None or xy is None or pair_index is None or K is None:
        return {}

    pairs = pairs.astype(int)
    pair_index = pair_index.astype(int)
    counts = np.bincount(pair_index, minlength=len(pairs))
    out = {}
    for pi in np.argsort(-counts)[:cap]:
        rows = xy[pair_index == pi]
        if len(rows) < 8:
            continue
        a, b = pairs[pi]
        Ka = K[a] if len(K) > a else K[0]
        Kb = K[b] if len(K) > b else K[0]
        na = cv2.undistortPoints(
            np.ascontiguousarray(rows[:, :2]).reshape(-1, 1, 2).astype(np.float64),
            Ka, None)
        nb = cv2.undistortPoints(
            np.ascontiguousarray(rows[:, 2:]).reshape(-1, 1, 2).astype(np.float64),
            Kb, None)
        E, mask = cv2.findEssentialMat(na, nb, np.eye(3), method=cv2.USAC_MAGSAC,
                                       prob=0.999, threshold=1e-3)
        if E is None or E.shape != (3, 3):
            continue
        _, R, t, _ = cv2.recoverPose(E, na, nb, np.eye(3), mask=mask)
        out[(int(a), int(b))] = (R, t.ravel())
    return out


def pose_agreement(cams, valid, image_index, pair_rel) -> tuple[float, float, int]:
    """Median discrepancy between the final relative poses and the two-view
    estimates, as (rotation degrees, translation-direction degrees, edges).

    Never touches the points, so it sees the drift reprojection error cannot: a
    pose set that is self-consistently wrong produces structure that reprojects
    cleanly. Translation is compared as a DIRECTION only, so scale never enters.

    A consistency reading, not an error against truth -- the two-view estimates
    are themselves noisy, and the discrepancy blends both errors.
    """
    pose = {int(im): cams[row] for row, (im, ok)
            in enumerate(zip(image_index, valid)) if ok}
    rot, trn = [], []
    for (a, b), (R_ab, t_ab) in pair_rel.items():
        if a not in pose or b not in pose:
            continue
        Ra, ta = pose[a][:, :3], pose[a][:, 3]
        Rb, tb = pose[b][:, :3], pose[b][:, 3]
        R_model = Rb @ Ra.T
        t_model = tb - R_model @ ta

        c = (np.trace(R_model @ R_ab.T) - 1.0) / 2.0
        rot.append(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))
        n1, n2 = np.linalg.norm(t_model), np.linalg.norm(t_ab)
        if n1 > 1e-9 and n2 > 1e-9:
            cd = np.clip(abs(float((t_model / n1) @ (t_ab / n2))), -1.0, 1.0)
            trn.append(np.degrees(np.arccos(cd)))
    if not rot:
        return float("nan"), float("nan"), 0
    return (float(np.median(rot)),
            float(np.median(trn)) if trn else float("nan"), len(rot))


def components(model, *, scene=None, tracks=None, matches=None,
               support_floor: float | None = None) -> dict:
    """Every rung as a raw component.

    Percentiles come later, against a reference corpus. A raw value on its own
    is not a verdict and must not be read as one.
    """
    xyz = model.load("points", "xyz")
    obs = model.load("observations", "obs")
    cams = model.load("poses", "cam_from_world")
    valid = np.asarray(model.load("poses", "valid"), dtype=bool)
    image_index = model.load("poses", "image_index")
    point_error = _load(model, "points", "error")

    n_valid = int(valid.sum())
    registered = {int(i) for i, ok in zip(image_index, valid) if ok}

    sizes = (_load(scene, "images", "size_current")
             if scene is not None else None)
    n_images = (len(sizes) if sizes is not None
                else max(len(valid), len(registered)))

    lengths = track_lengths(obs, len(xyz))
    seen = lengths[lengths > 0]
    angles = triangulation_angles(xyz, obs, cams, valid, image_index)

    # Rung 5 is measured among WELL-SUPPORTED points only, so that discarding
    # long tracks cannot flatter it, and "well-supported" means MORE THAN TWO
    # VIEWS.
    #
    # It was the corpus-median support until the reference campaign measured
    # that median: it is 2 on every capture, so the filter admitted every point
    # and the qualifier was doing nothing. Three is not a tuned cut point, it is
    # the arithmetic one -- a two-view point is exactly determined (four
    # residuals, three unknowns), so its residual is near zero by construction
    # however bad the model is, and averaging it in measures the algebra rather
    # than the reconstruction.
    floor = support_floor if support_floor is not None else MIN_SUPPORT
    err_med = float("nan")
    if point_error is not None and len(point_error) == len(xyz):
        vals = np.asarray(point_error)[lengths >= floor]
        vals = vals[np.isfinite(vals)]
        if len(vals):
            err_med = float(np.median(vals))

    t_obs = _load(tracks, "observations", "obs") if tracks is not None else None
    t_count = _load(tracks, "observations", "track_count") if tracks is not None else None

    rel = (two_view_relatives(matches, scene)
           if matches is not None and scene is not None else {})
    rot_deg, trn_deg, edges = pose_agreement(cams, valid, image_index, rel)

    # The composition rung is the share of points seen in MORE than two views.
    #
    # It was median observations-per-point until the reference campaign measured
    # it: the median read exactly 2 on every capture in the corpus, healthy and
    # broken alike, because a sparse cloud is two-view-dominated by construction.
    # A rung with no variance across the reference corpus has a meaningless
    # percentile, which is worse than no rung -- it still reports a number.
    #
    # The replacement is the reading the ladder's own rung 3 argues from: a
    # two-view point is exactly determined -- four residuals, three unknowns --
    # so its residual is near zero however bad the model is. What separates a
    # model whose error means something from one whose error is arithmetic is
    # how much of the cloud is over-determined.
    over_determined = (float((seen >= 3).mean()) if len(seen) else 0.0)

    return {
        "registration": (n_valid / n_images) if n_images else 0.0,
        "conditioning": float(np.median(angles)) if len(angles) else None,
        "composition": over_determined,
        "composition_median_support": float(np.median(seen)) if len(seen) else 0.0,
        "composition_points_per_frame": (len(xyz) / n_valid) if n_valid else 0.0,
        "coverage": (coverage(obs, sizes, registered)
                     if sizes is not None else None),
        "error": err_med if err_med == err_med else None,
        "error_support_floor": floor,
        # Both yield forms, until the corpus decides between them.
        # Observation-yield is the stricter: it also punishes truncating long
        # tracks into short ones.
        "yield_obs": (len(obs) / len(t_obs)) if t_obs is not None and len(t_obs) else None,
        "yield_track": (len(xyz) / int(t_count)) if t_count else None,
        "pose_agreement": rot_deg if rot_deg == rot_deg else None,
        "pose_agreement_translation": trn_deg if trn_deg == trn_deg else None,
        "pose_agreement_edges": edges,
        # Header context. A raw count is comparable WITHIN a capture -- model A
        # against model B of the same scene -- and never across scenes, where it
        # is confounded with texture, resolution and scale before the pipeline
        # does anything.
        "point_count": int(len(xyz)),
        "observation_count": int(len(obs)),
        "registered_images": n_valid,
        "n_images": int(n_images),
    }
