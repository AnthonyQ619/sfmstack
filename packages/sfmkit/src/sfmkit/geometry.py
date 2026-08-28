"""Three-view transfer error over a `tracks/v1` table.

The one measurement of tracker POSITIONAL ACCURACY that is available at the
tracker stage, and the reason it is here rather than in each module is the same as
for `split_rate`: it is meant to be compared across trackers.

Why not the obvious thing. A two-view epipolar residual measures nothing useful
here, because a chaining tracker's observations ARE the matcher's verified
inliers -- they satisfy the epipolar constraint by construction, so the number
would read zero for one family and meaningfully for the other. That is a metric of
one family, not a comparison.

Three views is different, and the difference is the whole point. A matcher
verifies pairs (i,j), (j,k) and (i,k) INDEPENDENTLY. Two-view geometry constrains
a correspondence to a line, and three lines meeting pairwise need not meet at a
point -- so a track can satisfy every pairwise check and still not correspond to a
single 3D point. That is exactly the error that makes a track wrong while every
pair in it is verified, and exactly what triangulation later rejects.

The measurement is HELD OUT, which is what stops it being circular:

    1. tracks common to frames (i, j, k), split in half
    2. relative pose (i, j) from the FIT half
    3. every common track triangulated from its OWN (i, j) observations
    4. camera k solved from the FIT half's 3D points and their k observations
    5. the TEST half's 3D points projected into k, measured against their k
       observations

Nothing about a test track's k observation took part in placing anything. It is a
prediction, and the residual is the error of that prediction.

What it still cannot see: an error consistent across ALL views of a track, which
the fitted geometry absorbs. Three views absorb far less than two, which is the
gain, but it is not immunity.

`cv2` is imported lazily. sfmkit is installed in every image including the
dependency-free one, and the contract layer does not get to require OpenCV; a
module that calls this must provide it.
"""

from __future__ import annotations

import numpy as np

__all__ = ["trifocal_transfer", "scene_intrinsics"]


def scene_intrinsics(scene, n_images: int) -> np.ndarray | None:
    """Per-image K from a scene/v1 artifact, or None when it carries none.

    Here rather than in each tracker so the three of them cannot disagree about
    what "the intrinsics" means for a metric they are compared on.
    """
    if not scene.has("calibration"):
        return None
    data = scene.load("calibration")
    K = np.asarray(data["intrinsics"], dtype=np.float64)
    index = data.get("camera_index")
    if index is None:
        index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    return K[np.asarray(index, dtype=int)]


def _normalise(xy: np.ndarray, K: np.ndarray) -> np.ndarray:
    """Pixels -> normalised camera coordinates, so per-image K is handled."""
    return np.stack([(xy[:, 0] - K[0, 2]) / K[0, 0],
                     (xy[:, 1] - K[1, 2]) / K[1, 1]], axis=1)


def _triangulate(P1: np.ndarray, P2: np.ndarray,
                 x1: np.ndarray, x2: np.ndarray) -> np.ndarray:
    """DLT over normalised coordinates. (N, 3) world points.

    Batched rather than looped: numpy's SVD takes a stack, and this runs once per
    sampled triple over every track common to it. The loop version dominated the
    metric's cost on a real track table.
    """
    A = np.empty((len(x1), 4, 4), dtype=np.float64)
    A[:, 0] = x1[:, 0, None] * P1[2] - P1[0]
    A[:, 1] = x1[:, 1, None] * P1[2] - P1[1]
    A[:, 2] = x2[:, 0, None] * P2[2] - P2[0]
    A[:, 3] = x2[:, 1, None] * P2[2] - P2[1]
    X = np.linalg.svd(A)[2][:, -1, :]
    w = X[:, 3]
    out = np.full((len(x1), 3), np.nan)
    ok = np.abs(w) > 1e-12
    out[ok] = X[ok, :3] / w[ok, None]
    return out


def trifocal_transfer(
    obs: np.ndarray,
    K_all: np.ndarray,
    *,
    max_triples: int = 12,
    min_common: int = 40,
    max_tracks_per_triple: int = 400,
    ransac_threshold_px: float = 1.5,
    seed: int = 0,
) -> tuple[float | None, int, int]:
    """Median held-out three-view transfer error in pixels.

    `obs` is the (N, 4) tracks/v1 table; `K_all` is (n_images, 3, 3) intrinsics at
    the same working resolution the observations are in.

    Returns `(median_px, mad_px, n_measurements, n_triples)`. The median is None
    when the scene cannot support the measurement -- fewer than three frames, or no
    triple with `min_common` tracks in all three. That null is informative: it says
    the track table has no three-view structure to check.

    Deterministic FOR ONE TRACK TABLE. The triples are drawn with a fixed seed,
    because a metric that moves between two runs of the same recipe is not a
    metric -- and two runs of the same recipe do return byte-identical values.

    IT IS NOT STABLE ACROSS DIFFERENT TRACK TABLES, WHICH IS THE COMPARISON
    READERS ACTUALLY MAKE. The frame triples come off a fixed seed, but a triple is
    SKIPPED unless `min_common` tracks are shared by all three frames, and the
    per-triple sample is drawn from whatever is common. So a sparser table
    disqualifies different triples and samples different tracks: the held-out set
    changes underneath a comparison of two matcher settings. Observed swinging the
    sample count from tens to thousands across one capture's parameter sweep, with
    the median wandering non-monotonically while every other metric moved cleanly.

    That is why the dispersion is returned and not just the median. `mad_px` is the
    median absolute deviation of the residuals -- the scale of the thing the median
    is a middle of. Two medians a small fraction of it apart, measured over
    different sample sets, are not distinguishable; readers who lacked this had to
    establish a noise floor by re-running a sweep and eyeballing which differences
    reproduced.
    """
    try:
        import cv2
    except ImportError as e:  # pragma: no cover - image without opencv
        raise RuntimeError(
            "trifocal_transfer needs OpenCV. sfmkit does not depend on it -- the "
            "contract layer is installed in every image including the "
            "dependency-free one -- so a module calling this must install "
            "opencv-python-headless in its own image."
        ) from e

    obs = np.asarray(obs, dtype=np.float64)
    if len(obs) == 0:
        return None, None, 0, 0
    K_all = np.asarray(K_all, dtype=np.float64)

    ids = obs[:, 0].astype(np.int64)
    frames = obs[:, 1].astype(np.int64)
    xy = obs[:, 2:4]

    present = sorted(np.unique(frames).tolist())
    if len(present) < 3:
        return None, None, 0, 0

    # frame -> {track: row}. One row per (track, frame): a track observed twice in
    # one frame is inconsistent_rate's business, and taking either observation
    # here would silently pick a side.
    by_frame: dict[int, dict[int, int]] = {int(f): {} for f in present}
    for r in range(len(obs)):
        by_frame[int(frames[r])].setdefault(int(ids[r]), r)

    rng = np.random.default_rng(seed)
    residuals: list[float] = []
    used_triples = 0
    attempts = 0

    while used_triples < max_triples and attempts < max_triples * 6:
        attempts += 1
        i, j, k = (int(v) for v in rng.choice(present, size=3, replace=False))
        Ai, Aj, Ak = by_frame[i], by_frame[j], by_frame[k]
        common = sorted(set(Ai) & set(Aj) & set(Ak))
        if len(common) < min_common:
            continue

        # Capped, because the cost of a triple is linear in this and a few
        # hundred correspondences already over-determine both fits several times
        # over. Sampling rather than truncating keeps the spatial spread.
        order = rng.permutation(len(common))[:max_tracks_per_triple]
        common = [common[t] for t in order]
        half = len(common) // 2
        fit, test = common[:half], common[half:]
        if len(fit) < min_common // 2 or not test:
            continue

        Ki, Kj, Kk = K_all[i], K_all[j], K_all[k]
        xi = _normalise(np.array([xy[Ai[t]] for t in common]), Ki)
        xj = _normalise(np.array([xy[Aj[t]] for t in common]), Kj)
        xk_px = np.array([xy[Ak[t]] for t in common])
        xk = _normalise(xk_px, Kk)
        index = {t: n for n, t in enumerate(common)}
        fit_n = np.array([index[t] for t in fit])
        test_n = np.array([index[t] for t in test])

        # Relative pose (i, j) from the fit half only, in normalised coordinates
        # so per-image intrinsics need no common K.
        threshold = ransac_threshold_px / float(Ki[0, 0])
        E, inliers = cv2.findEssentialMat(
            xi[fit_n], xj[fit_n], np.eye(3), method=cv2.RANSAC,
            prob=0.999, threshold=threshold,
        )
        if E is None or E.shape != (3, 3):
            continue
        _, R, t, _ = cv2.recoverPose(E, xi[fit_n], xj[fit_n], np.eye(3), mask=inliers)

        P1 = np.hstack([np.eye(3), np.zeros((3, 1))])
        P2 = np.hstack([R, t.reshape(3, 1)])
        X = _triangulate(P1, P2, xi, xj)

        good = np.isfinite(X).all(axis=1) & (X[:, 2] > 1e-6)
        good &= ((R @ X.T).T + t.reshape(1, 3))[:, 2] > 1e-6
        fit_ok = fit_n[good[fit_n]]
        test_ok = test_n[good[test_n]]
        if len(fit_ok) < 6 or len(test_ok) == 0:
            continue

        # Camera k from the FIT half's structure only.
        ok, rvec, tvec, _ = cv2.solvePnPRansac(
            X[fit_ok].astype(np.float64), xk[fit_ok].astype(np.float64),
            np.eye(3), None, reprojectionError=threshold,
            flags=cv2.SOLVEPNP_ITERATIVE, confidence=0.999,
        )
        if not ok:
            continue

        # The TEST half projected into k. Nothing here touched their k
        # observations, so this is a prediction.
        Rk = cv2.Rodrigues(rvec)[0]
        cam = (Rk @ X[test_ok].T).T + tvec.reshape(1, 3)
        infront = cam[:, 2] > 1e-6
        if not infront.any():
            continue
        cam = cam[infront]
        projected = np.stack([
            cam[:, 0] / cam[:, 2] * Kk[0, 0] + Kk[0, 2],
            cam[:, 1] / cam[:, 2] * Kk[1, 1] + Kk[1, 2],
        ], axis=1)
        residuals.extend(
            np.linalg.norm(projected - xk_px[test_ok][infront], axis=1).tolist()
        )
        used_triples += 1

    if not residuals:
        return None, None, 0, used_triples
    r = np.asarray(residuals)
    median = float(np.median(r))
    # MAD rather than a standard deviation: the residual distribution has a heavy
    # tail (a handful of bad tracks project far), and a moment-based spread would
    # report the tail rather than the scale of the bulk the median sits in.
    mad = float(np.median(np.abs(r - median)))
    return median, mad, len(r), used_triples
