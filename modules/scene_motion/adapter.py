"""SceneMotion -- scene/v1 -> scene_analysis/v1. GPU.

The flow and motion-summary blocks are a port of the predecessor's
`optical_flow.py`. Three things changed on the way, all of them flagged in
docs/design/scene-analysis.md as defects of the original:

1. **The model no longer loads at import time.** The predecessor built RAFT as a
   module-level global, so importing the file for any reason -- a docstring, a
   helper function -- allocated a GPU. It loads in `warmup()` here, which is the
   hook the warm server calls once.
2. **Nothing is formatted into English.** The predecessor returned a paragraph
   with thresholds interpolated into it. Numbers go into the artifact; the prose
   lives in `artifact.md` and the skills, where it can be revised without a
   re-run.
3. **The degeneracy tests are new.** Both were listed as missing and both come
   nearly free once flow exists, because the expensive part is the flow field and
   these are two model fits over correspondences sampled from it.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from sfmkit import Ctx, module, scene_intrinsics
from torchvision.models.optical_flow import raft_large

CHECKPOINT = os.environ.get("RAFT_CHECKPOINT", "/opt/weights/raft_large.pt")

# GRIC constants (Torr, "An assessment of information criteria for motion model
# selection", 1997). r is the dimension of one datum -- a correspondence is two
# 2-vectors, so 4. lambda3 caps the influence of a single outlier at the cost of
# admitting it, which is what makes the criterion usable on real correspondences.
GRIC_R = 4
GRIC_LAMBDA3 = 2.0

MIN_CORRESPONDENCES = 30

_MODEL = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model():
    global _MODEL
    if _MODEL is None:
        model = raft_large(weights=None)
        model.load_state_dict(torch.load(CHECKPOINT, map_location="cpu"))
        _MODEL = model.to(device()).eval()
    return _MODEL


def warmup() -> None:
    get_model()


# --------------------------------------------------------------------------- #
# Flow
# --------------------------------------------------------------------------- #


def load_frame(path, max_side: int) -> tuple[np.ndarray, float]:
    """RGB uint8 at the analysis resolution, plus the scale applied.

    The scale is returned because the intrinsics have to follow it: every
    geometric test below runs in flow-resolution pixels, and a K left at the
    scene's resolution would be wrong by exactly this factor.
    """
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(
            f"could not read image {path}. If the scene was built with "
            f"resize: none it references the dataset directly, which must then "
            f"be reachable from here too."
        )
    h, w = bgr.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        bgr = cv2.resize(bgr, (max(1, round(w * scale)), max(1, round(h * scale))),
                         interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), scale


def to_tensor(rgb: np.ndarray) -> torch.Tensor:
    """(1, 3, H, W) in [-1, 1] -- what RAFT's own transform produces."""
    t = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    return (t * 2.0 - 1.0).unsqueeze(0)


def estimate_flow(rgb1: np.ndarray, rgb2: np.ndarray) -> np.ndarray:
    """(H, W, 2) dense flow from the final RAFT iteration."""
    a, b = to_tensor(rgb1), to_tensor(rgb2)
    h, w = a.shape[-2:]

    # RAFT downsamples by 8 internally and its correlation volume needs both
    # dimensions to be multiples of 8. Pad rather than resize: padding leaves the
    # flow in the original pixel units, where a resize would need it scaled back.
    pad_h, pad_w = (-h) % 8, (-w) % 8
    if pad_h or pad_w:
        a = F.pad(a, (0, pad_w, 0, pad_h))
        b = F.pad(b, (0, pad_w, 0, pad_h))

    dev = device()
    with torch.no_grad():
        flow = get_model()(a.to(dev), b.to(dev))[-1][0]

    return flow[:, :h, :w].permute(1, 2, 0).cpu().numpy().astype(np.float64)


def flow_to_correspondences(flow: np.ndarray, step: int) -> tuple[np.ndarray, np.ndarray]:
    """Sample the dense field onto a grid and keep the correspondences that land
    inside the second image."""
    h, w = flow.shape[:2]
    ys, xs = np.mgrid[0:h:step, 0:w:step]
    xs, ys = xs.reshape(-1), ys.reshape(-1)

    d = flow[ys, xs]
    x2, y2 = xs + d[:, 0], ys + d[:, 1]

    inside = (x2 >= 0) & (x2 < w) & (y2 >= 0) & (y2 < h)
    return (np.stack([xs[inside], ys[inside]], axis=1).astype(np.float64),
            np.stack([x2[inside], y2[inside]], axis=1).astype(np.float64))


# --------------------------------------------------------------------------- #
# Model selection
# --------------------------------------------------------------------------- #


def gric(errors_sq: np.ndarray, sigma: float, d: int, k: int) -> float:
    """Torr's GRIC. Lower is the preferred model.

    The point of GRIC over a plain inlier count is that it charges a model for
    its dimension AND its parameter count, so a fundamental matrix -- which can
    fit anything a homography can, plus more -- does not win by default. That is
    exactly the comparison needed here: on a plane both models fit, and the
    question is which one is doing real work.
    """
    n = len(errors_sq)
    rho = np.minimum(errors_sq / (sigma**2), GRIC_LAMBDA3 * (GRIC_R - d))
    return float(rho.sum() + np.log(GRIC_R) * d * n + np.log(GRIC_R * n) * k)


def homography_errors_sq(H: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """Symmetric transfer error, squared."""

    def transfer(M, pts):
        h = np.concatenate([pts, np.ones((len(pts), 1))], axis=1) @ M.T
        w = np.where(np.abs(h[:, 2:3]) < 1e-12, 1e-12, h[:, 2:3])
        return h[:, :2] / w

    forward = np.sum((transfer(H, p1) - p2) ** 2, axis=1)
    back = np.sum((transfer(np.linalg.inv(H), p2) - p1) ** 2, axis=1)
    return forward + back


def fundamental_errors_sq(Fm: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """Sampson distance, squared -- the first-order approximation to the
    geometric error, which is what makes it comparable with the transfer error
    above rather than being an algebraic residual on a different scale."""
    x1 = np.concatenate([p1, np.ones((len(p1), 1))], axis=1)
    x2 = np.concatenate([p2, np.ones((len(p2), 1))], axis=1)

    Fx1 = x1 @ Fm.T
    Ftx2 = x2 @ Fm
    num = np.sum(x2 * Fx1, axis=1) ** 2
    den = Fx1[:, 0] ** 2 + Fx1[:, 1] ** 2 + Ftx2[:, 0] ** 2 + Ftx2[:, 1] ** 2
    return num / np.maximum(den, 1e-12)


def rotation_residual(H: np.ndarray, K1: np.ndarray, K2: np.ndarray) -> float:
    """How far `K2^-1 H K1` is from being a rotation matrix.

    Under pure rotation the inter-image homography is exactly `K2 R K1^-1`, so
    conjugating it back gives R and the residual is zero. Viewing a PLANE from two
    positions gives `K2 (R + t n^T / d) K1^-1` instead, and the rank-one term is
    not orthogonal for any nonzero baseline. This is the whole discrimination
    between the two degeneracies, and it is why the cue needs intrinsics.
    """
    M = np.linalg.inv(K2) @ H @ K1
    det = np.linalg.det(M)
    if abs(det) < 1e-12:
        return np.inf
    M = M / np.sign(det) / (abs(det) ** (1.0 / 3.0))
    return float(np.linalg.norm(M @ M.T - np.eye(3), ord="fro"))


def rotation_angle_deg(R: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0))))


def scale_K(K: np.ndarray, s: float) -> np.ndarray:
    out = K.copy()
    out[0, 0] *= s
    out[1, 1] *= s
    out[0, 2] *= s
    out[1, 2] *= s
    return out


def pair_geometry(p1, p2, K1, K2, thresh: float, rot_tol: float) -> dict:
    """Model selection and, when calibrated, the angular cues. One pair."""
    out: dict = {}

    H, _ = cv2.findHomography(p1, p2, cv2.USAC_MAGSAC, thresh)
    Fm, _ = cv2.findFundamentalMat(p1, p2, cv2.USAC_MAGSAC, thresh, 0.999)
    if H is None or Fm is None or Fm.shape != (3, 3):
        return out

    gric_h = gric(homography_errors_sq(H, p1, p2), thresh, d=2, k=8)
    gric_f = gric(fundamental_errors_sq(Fm, p1, p2), thresh, d=3, k=7)
    out["planar"] = bool(gric_h < gric_f)

    if K1 is None:
        return out

    # Pure rotation only makes sense as a claim when the homography is the model
    # doing the work; on a general scene H is a bad fit and its conjugate is
    # meaningless.
    out["rotation_only"] = bool(
        out["planar"] and rotation_residual(H, K1, K2) < rot_tol
    )

    # Normalised coordinates rather than passing one K to findEssentialMat: the
    # two images may carry different intrinsics, and a single-K call would
    # silently apply the first one to both.
    n1 = np.stack([(p1[:, 0] - K1[0, 2]) / K1[0, 0], (p1[:, 1] - K1[1, 2]) / K1[1, 1]], 1)
    n2 = np.stack([(p2[:, 0] - K2[0, 2]) / K2[0, 0], (p2[:, 1] - K2[1, 2]) / K2[1, 1]], 1)
    focal = float(np.mean([K1[0, 0], K1[1, 1], K2[0, 0], K2[1, 1]]))

    E, mask = cv2.findEssentialMat(
        n1, n2, np.eye(3), method=cv2.USAC_MAGSAC, prob=0.999, threshold=thresh / focal
    )
    if E is None or E.shape != (3, 3):
        return out

    _, R, _, _ = cv2.recoverPose(E, n1, n2, np.eye(3), mask=mask)
    out["rotation_deg"] = rotation_angle_deg(R)
    return out


# --------------------------------------------------------------------------- #


def choose_pairs(n: int, stride: int, cap: int) -> list[tuple[int, int]]:
    pairs = [(i, i + stride) for i in range(n - stride)]
    if len(pairs) <= cap:
        return pairs
    idx = np.linspace(0, len(pairs) - 1, cap, dtype=int)
    return [pairs[i] for i in idx]


NOTE_PAIRS = 6


def flagged(label: str, pairs, flags, names) -> str:
    """Name the pairs a boolean series is true on, for the artifact note.

    Truncated: a scene where most pairs are degenerate produces a diagnostic and
    a plan to abandon the capture, and does not need sixty names in prose. The
    full series is in the artifact for anyone who does.
    """
    hits = [(i, j) for (i, j), flag in zip(pairs, flags) if flag]
    if not hits:
        return ""
    shown = ", ".join(f"{names[i]}/{names[j]}" for i, j in hits[:NOTE_PAIRS])
    rest = len(hits) - NOTE_PAIRS
    return f" {label}: {shown}" + (f", and {rest} more." if rest > 0 else ".")


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    p = ctx.params

    paths = scene.load("images", "paths")
    names = [str(x) for x in scene.load("images", "names")]
    n = len(paths)

    pairs = choose_pairs(n, p.stride, p.max_pairs)
    if not pairs:
        raise ValueError(
            f"stride={p.stride} leaves no pairs in a {n}-image scene. "
            f"stride must be smaller than the image count."
        )

    K_scene = scene_intrinsics(scene, n)
    calibrated = K_scene is not None

    p75_flow, p90_flow = [], []
    planar, rotation_only, rotations = [], [], []
    # Which pair each of the three lists above is talking about. Three separate
    # index lists rather than one, because they are three different subsets: a
    # pair can admit a homography fit and no rotation estimate, and an
    # uncalibrated scene fills the first and neither of the others. Reducing them
    # to a mean hid that; carrying the mean plus one shared index would have made
    # a false claim about alignment.
    planar_pairs, rotation_only_pairs, rotation_pairs = [], [], []
    fit_failures = 0

    cache: dict[int, tuple[np.ndarray, float]] = {}

    def frame(i: int):
        # Consecutive pairs share an image; with stride 1 this halves the decode
        # and resize cost. Only the previous pair's frames are ever needed again.
        if i not in cache:
            cache[i] = load_frame(scene.resolve(str(paths[i])), p.max_side)
        return cache[i]

    for step, (i, j) in enumerate(pairs):
        ctx.progress(step / len(pairs), f"flow {step + 1}/{len(pairs)}")

        rgb1, s1 = frame(i)
        rgb2, s2 = frame(j)
        for key in [k for k in cache if k < i]:
            del cache[key]

        if rgb1.shape != rgb2.shape:
            # A mixed-resolution scene. RAFT needs one grid, so the second frame
            # is brought onto the first's; its intrinsics follow the same factor.
            h, w = rgb1.shape[:2]
            s2 *= min(h / rgb2.shape[0], w / rgb2.shape[1])
            rgb2 = cv2.resize(rgb2, (w, h), interpolation=cv2.INTER_AREA)

        flow = estimate_flow(rgb1, rgb2)

        h, w = flow.shape[:2]
        diag = float(np.hypot(h, w))
        magnitude = np.linalg.norm(flow, axis=2)
        p75_flow.append(float(np.percentile(magnitude, 75)) / diag)
        p90_flow.append(float(np.percentile(magnitude, 90)) / diag)

        pts1, pts2 = flow_to_correspondences(flow, p.flow_step)
        if len(pts1) < MIN_CORRESPONDENCES:
            fit_failures += 1
            continue

        geom = pair_geometry(
            pts1, pts2,
            scale_K(K_scene[i], s1) if calibrated else None,
            scale_K(K_scene[j], s2) if calibrated else None,
            p.ransac_threshold_px, p.rotation_only_tol,
        )
        if "planar" not in geom:
            fit_failures += 1
            continue

        planar.append(geom["planar"])
        planar_pairs.append((i, j))
        if "rotation_only" in geom:
            rotation_only.append(geom["rotation_only"])
            rotation_only_pairs.append((i, j))
        if "rotation_deg" in geom:
            rotations.append(geom["rotation_deg"])
            rotation_pairs.append((i, j))

    # ----------------------------------------------------------------- summary
    p75 = np.asarray(p75_flow)
    p90 = np.asarray(p90_flow)

    overall = float(np.median(p75))
    tail = float(np.median(p90))
    variability = float(np.percentile(p75, 75) - np.percentile(p75, 25))
    low_baseline = float(np.mean(p75 < p.low_motion_thresh))

    planar_dominance = float(np.mean(planar)) if planar else None
    rotation_risk = float(np.mean(rotation_only)) if rotation_only else None
    rotation_median = float(np.median(rotations)) if rotations else None
    large_rotation = (
        float(np.mean(np.asarray(rotations) > p.rotation_risk_deg)) if rotations else None
    )

    # ------------------------------------------------------------------- write
    out = ctx.output("analysis")

    motion = {
        "overall_magnitude": overall,
        "high_motion_tail": tail,
        "variability": variability,
        "low_baseline_risk": low_baseline,
        # Extra, recorded as such: the per-pair series, so "which part of the
        # capture is the problem" is answerable without re-running flow.
        #
        # `pair_p90` is also what replaced `large_motion_risk`, which was
        # `mean(pair_p90 > high_motion_thresh)` -- a thresholded restatement of
        # `high_motion_tail` with the cut welded in. A consumer that wants the
        # fraction computes it here, at whatever cut it likes.
        "pair_index": np.asarray(pairs, dtype=np.int32),
        "pair_p75": p75,
        "pair_p90": p90,
    }
    if rotation_median is not None:
        motion["rotation_median_deg"] = rotation_median
        motion["large_rotation_risk"] = large_rotation
        motion["pair_rotation_deg"] = np.asarray(rotations, dtype=np.float64)
        # Its OWN index. `pair_rotation_deg` used to be written against `pairs`
        # implicitly, which is only correct when every pair fitted -- one
        # `flow_fit_failed` and the array silently misaligns with the labels.
        motion["rotation_pair_index"] = np.asarray(rotation_pairs, dtype=np.int32)
    out.save("motion", **motion)

    if planar_dominance is not None:
        # `planar_dominance` is a fraction of pairs, and the action attached to it
        # -- watch the seed, raise `init_min_angle_deg`, drop the offending views
        # -- needs to know WHICH pairs. One in eleven and eleven in eleven are the
        # same metric and different plans. The flags are what the fractions are a
        # mean of, so a caller can also recompute the fraction over a subset.
        degeneracy = {
            "planar_dominance": planar_dominance,
            "pair_index": np.asarray(planar_pairs, dtype=np.int32),
            "pair_planar": np.asarray(planar, dtype=np.bool_),
        }
        if rotation_risk is not None:
            degeneracy["pure_rotation_risk"] = rotation_risk
            degeneracy["rotation_pair_index"] = np.asarray(
                rotation_only_pairs, dtype=np.int32
            )
            degeneracy["pair_pure_rotation"] = np.asarray(rotation_only, dtype=np.bool_)
        out.save("degeneracy", **degeneracy)

    out.metric("n_pairs", len(pairs), direction="neutral")
    out.metric("overall_magnitude", round(overall, 5), direction="neutral")
    out.metric("high_motion_tail", round(tail, 5), direction="neutral")
    out.metric("variability", round(variability, 5),
               direction="lower_better", healthy=(None, 0.035))
    out.metric("low_baseline_risk", round(low_baseline, 4),
               direction="lower_better", healthy=(None, 0.35))
    out.metric("rotation_median_deg",
               None if rotation_median is None else round(rotation_median, 3),
               direction="neutral")
    out.metric("large_rotation_risk",
               None if large_rotation is None else round(large_rotation, 4),
               direction="lower_better", healthy=(None, 0.33))
    out.metric("planar_dominance",
               None if planar_dominance is None else round(planar_dominance, 4),
               direction="lower_better", healthy=(None, 0.5))
    out.metric("pure_rotation_risk",
               None if rotation_risk is None else round(rotation_risk, 4),
               direction="lower_better", healthy=(None, 0.1))

    # ------------------------------------------------------------ diagnostics
    if low_baseline > 0.35:
        out.diagnostic(
            "low_baseline",
            severity="warn",
            message=(
                f"{low_baseline:.0%} of {len(pairs)} pairs move less than "
                f"{p.low_motion_thresh:.3f} of the image diagonal at stride "
                f"{p.stride}."
            ),
            suggested_actions=[
                "If the capture is dense video, raise `stride` and re-read before concluding.",
                "Otherwise expect high reprojection error at low triangulation angle.",
                "Consider a learned-prior structure capability - sfm_find_alternatives("
                "produces='sparse_model/v1', not_consuming='poses/v1').",
            ],
            see_also="tuning.md#low_baseline_risk-above-035",
        )

    # There is deliberately no large-motion diagnostic. The metric it would have
    # keyed on was cut: it fired on all ten benchmark scenes measured, every one
    # of which reconstructs, so it was reporting the threshold rather than the
    # capture. `high_motion_tail` carries the measurement and
    # `rotation_median_deg` carries the thing that actually costs a matcher its
    # correspondences -- see limitations.md.

    if planar_dominance is not None and planar_dominance > 0.5:
        out.diagnostic(
            "planar_scene",
            severity="warn",
            message=(
                f"GRIC prefers a homography on {planar_dominance:.0%} of fitted pairs."
                + (f" pure_rotation_risk is {rotation_risk:.0%}."
                   if rotation_risk is not None
                   else " Intrinsics are absent, so the cause cannot be separated.")
            ),
            suggested_actions=[
                "Read pure_rotation_risk: a plane and a pure rotation look identical here.",
                "For a genuine plane, essential-matrix pose is ill-conditioned.",
                "Expect `planarity` on pairwise_matches/v1 to agree once a matcher runs.",
            ],
            see_also="limitations.md#planar-and-rotational-degeneracy-are-the-same-measurement",
        )

    if rotation_risk is not None and rotation_risk > 0.1:
        out.diagnostic(
            "pure_rotation",
            severity="error",
            message=(
                f"{rotation_risk:.0%} of fitted pairs have a homography that "
                f"conjugates to a rotation: the camera turned without translating."
            ),
            suggested_actions=[
                "No matcher or triangulator recovers structure without parallax.",
                "If only part of the capture is rotational, re-run SceneLoader over the translating subset.",
            ],
            see_also="limitations.md#pure-rotation-is-terminal",
        )

    if not calibrated:
        out.diagnostic(
            "uncalibrated_scene",
            severity="info",
            message="Scene carries no intrinsics; rotation and pure-rotation cues omitted.",
            suggested_actions=[
                "Motion magnitudes and planar_dominance are unaffected - none of them need K.",
                "Supply calibration_path to SceneLoader to recover the angular cues.",
            ],
            see_also="limitations.md#what-needs-intrinsics",
        )

    if fit_failures:
        out.diagnostic(
            "flow_fit_failed",
            severity="info",
            message=f"{fit_failures} of {len(pairs)} pairs produced no usable model fit.",
            suggested_actions=[
                "Lower `flow_step` to sample the field more densely.",
                "Expected on pairs that are almost entirely textureless or static.",
            ],
            see_also="limitations.md#what-needs-intrinsics",
        )

    out.note(
        f"RAFT flow over {len(pairs)} pairs at stride {p.stride}, {p.max_side}px. "
        f"Motion: overall {overall:.4f}, tail {tail:.4f}, variability {variability:.4f}; "
        f"low-baseline risk {low_baseline:.0%}. "
        + (f"Rotation: median {rotation_median:.1f} deg, "
           f"{large_rotation:.0%} past {p.rotation_risk_deg:.0f} deg. "
           if rotation_median is not None else "Uncalibrated: no angular cues. ")
        + (f"Degeneracy: planar on {planar_dominance:.0%} of pairs"
           + (f", pure-rotation on {rotation_risk:.0%}." if rotation_risk is not None
              else " (cause not separable without intrinsics).")
           if planar_dominance is not None else "No pair admitted a model fit.")
        # Named even when no diagnostic fires. Every non-zero reading measured so
        # far has been one or two pairs of eleven, well under the 0.5 band, and
        # the fraction alone does not say which views to keep out of the seed.
        + flagged("Planar pairs", planar_pairs, planar, names)
        + flagged("Pure-rotation pairs", rotation_only_pairs, rotation_only, names)
    )
