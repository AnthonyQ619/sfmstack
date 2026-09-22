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


def component_sizes(nodes, edges) -> list[int]:
    """Sizes of the connected components `edges` induce on `nodes`, largest first.

    Union-find rather than a graph library: the module's only dependencies are numpy
    and OpenCV, and this is twenty lines.
    """
    at = {v: k for k, v in enumerate(nodes)}
    parent = list(range(len(at)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]      # path halving
            a = parent[a]
        return a

    for i, j in edges:
        a, b = at.get(int(i)), at.get(int(j))
        if a is None or b is None:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    sizes: dict[int, int] = {}
    for a in range(len(at)):
        r = find(a)
        sizes[r] = sizes.get(r, 0) + 1
    return sorted(sizes.values(), reverse=True)


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
        # The same test over ALL of the pair's correspondences. This is not
        # independent evidence and is not what the veto reads; it is the
        # well-determined per-pair median, resting on hundreds of correspondences
        # where the held-out one rests on tens. The component reading below needs
        # that: a noisy per-pair median disconnects the agreeing subgraph by
        # chance, and on corpus captures with few held-out pairs it was measured
        # doing exactly that.
        residual_all = float(np.median(sampson(F, block)))
        rows.append((i, j, len(block), n_held, residual, residual_all))

    arr = np.array(rows, dtype=np.float64).reshape(-1, 6)
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
        residual_all_px=arr[:, 5],
    )
    out.metric("heldout_residual_px", None if reading is None else round(reading, 4),
               direction="lower_better", healthy=(None, 3.0))
    out.metric("held_out_share", round(share, 4), direction="neutral")
    out.metric("pairs_verified", int(verified.sum()), direction="neutral")

    # The per-pair residuals read as a graph rather than as an average.
    #
    # A weighted median answers "how far is the evidence from the model". It cannot
    # answer "is the evidence that agrees with the model still connected", and those
    # come apart on exactly the failure this module exists to catch: a model whose
    # every local neighbourhood is solved correctly and whose neighbourhoods are held
    # at wrong relative orientations reads as fully registered, and the pairs that
    # disagree are the ones joining the pieces. Averaging them in hides the seam;
    # counting components over the agreeing pairs alone shows it.
    #
    # Computed on residual_all_px, not on the held-out residual, and the reason is
    # measured rather than aesthetic: over nineteen corpus captures that all
    # delivered, the held-out version fragmented on five of them -- worst where
    # held-out pairs were fewest -- because a median over tens of correspondences is
    # noisy enough to drop a sound pair below the threshold and cut a camera loose.
    # The all-correspondence median rests on hundreds and read one component on
    # eighteen of the nineteen. This reading does not need independence from the
    # solve: a model in pieces is contradicted by the matches it kept as well.
    focal = float(np.median([(K_model[i][0, 0] + K_model[i][1, 1]) / 2.0
                             for i in sorted(pose)])) if pose else float("nan")
    # No healthy band. The veto is the px threshold, and a second band in mrad
    # would contradict it: a corpus capture reading well inside the px ceiling
    # reads 1.76 mrad, because the px threshold is per-capture by construction.
    # This is the comparable number, not a second gate.
    out.metric("heldout_residual_mrad",
               None if reading is None or not np.isfinite(focal)
               else round(1000.0 * reading / focal, 4),
               direction="lower_better")
    supported = np.isfinite(arr[:, 5]) & (arr[:, 5] <= p.inlier_threshold_px)
    agreeing = arr[supported]
    sizes = component_sizes(sorted(pose), agreeing[:, :2].astype(np.int64))
    largest = (sizes[0] / len(pose)) if sizes and pose else 0.0
    out.metric("supported_components", len(sizes),
               direction="lower_better", healthy=(None, 1))
    # No band on the share: it is camera-count dependent and so cannot carry one.
    # A single stray camera reads 0.968 on a 31-image capture and 0.933 on a
    # 15-image one -- the same physical situation, on opposite sides of any fixed
    # floor. supported_components carries the band; this is how to read it.
    out.metric("supported_largest_share", round(largest, 4),
               direction="higher_better")
    out.metric("supported_second_size", sizes[1] if len(sizes) > 1 else 0,
               direction="lower_better", healthy=(None, 1))
    out.metric("agreeing_pair_share",
               round(float(supported.sum() / len(arr)), 4) if len(arr) else None,
               direction="higher_better")

    # Gate on the SECOND component's size, not on the largest's share, for the
    # reason above: one camera whose agreeing pairs do not reach the rest is a
    # stray and occurs in the reference corpus on a capture that delivered. Two or
    # more cameras forming their own island is a split model. Scale-free, and on
    # the twenty-four models this was checked against it agrees exactly with the
    # share rule it replaces while not punishing a small capture for its size.
    if len(sizes) > 1 and sizes[1] >= 2:
        out.diagnostic(
            "model_not_supported_by_its_own_evidence",
            severity="error",
            message=(
                f"The pairs whose held-out correspondences agree with this model do "
                f"not connect it: they leave {len(sizes)} pieces, the largest holding "
                f"{largest:.0%} of the {len(pose)} registered cameras "
                f"(sizes {', '.join(str(s) for s in sizes[:6])}"
                f"{', ...' if len(sizes) > 6 else ''}). Every piece is internally "
                f"consistent and they are joined across pairs the model contradicts, "
                f"so registration and reprojection error cannot see this."
            ),
            suggested_actions=[
                "Read the per-pair array: the pairs bridging two pieces are where the "
                "model and its evidence part company, and they are candidates for "
                "wrong correspondences that verified anyway.",
                "On a scene with repeated or instanced structure this is the expected "
                "shape of a self-matching failure. Averaging distributes one wrong "
                "relative pose over the whole graph, so the remedy is upstream in the "
                "matcher, not in a threshold here.",
                "Compare against another matcher's pairwise_matches of the same scene. "
                "If the pieces persist across matchers the capture is at fault; if "
                "they move, the matcher is.",
            ],
            see_also="limitations.md#a-model-can-be-in-pieces-and-the-residual-will-not-say-so",
        )

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
                "If the pose stage reported escaped points, the service has already "
                "re-solved this chain at a wider window: read `second_solve` on the "
                "same result before doing anything else. Otherwise solve again from "
                "the same inputs before changing anything. A capture can have more "
                "than one stable answer, and a second solve that reads clean here "
                "is the model to keep.",
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
