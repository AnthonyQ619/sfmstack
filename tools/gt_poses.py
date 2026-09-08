#!/usr/bin/env python3
"""Ground-truth camera poses for the two benchmark families, and the error of a
reconstruction against them.

Used ONCE, by the reference campaign, to check whether the internal readings of
the health profile actually track true error. GT can never be a rung: the
profile has to work on captures that have none.

DTU. `pose_info/pos_NNN.txt` is a 3x4 projection matrix P = K[R|t] per robot-arm
position, shared across every scan because the arm hits the same physical stops.
Only the EXTRINSICS are taken from it. Its embedded K is the rectified camera
(fx ~2892), while our images are the cleaned/distorted set whose calibration is
`calibration_DTU_new.npz` (fx ~2900, with distortion) -- that npz reproduces
`Calib_Results_left.m` digit for digit, so the pipeline keeps using it and only
R|t comes from here.

ETH3D. `dslr_calibration_undistorted/images.txt` is COLMAP text: one line per
image with a world-from-camera quaternion and translation in COLMAP's
cam_from_world convention, keyed by image NAME rather than index.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

DATASETS = Path("/home/anthonyq/datasets")
DTU_POSE_INFO = DATASETS / "DTU" / "pose_info"


def _rq3(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """RQ decomposition of a 3x3, returning (K, R) with K's diagonal positive."""
    P = np.flipud(np.eye(3))
    Q, R = np.linalg.qr((P @ M).T)
    K = P @ R.T @ P
    Rot = P @ Q.T
    S = np.diag(np.sign(np.diag(K)))
    K, Rot = K @ S, S @ Rot
    if np.linalg.det(Rot) < 0:
        K, Rot = -K, -Rot
    return K / K[2, 2], Rot


def dtu_extrinsics(pose_dir: Path = DTU_POSE_INFO) -> dict[int, np.ndarray]:
    """1-based position index -> cam_from_world 3x4.

    `pos_NNN.txt` matches image `clean_NNN_max.png` one to one, so the key is
    the image's own number.
    """
    out = {}
    for f in sorted(pose_dir.glob("pos_*.txt")):
        n = int(re.search(r"pos_(\d+)", f.name).group(1))
        P = np.loadtxt(f)
        K, R = _rq3(P[:, :3])
        t = np.linalg.inv(K) @ P[:, 3]
        out[n] = np.hstack([R, t.reshape(3, 1)])
    return out


def eth_extrinsics(scene_dir: Path) -> dict[str, np.ndarray]:
    """Image basename -> cam_from_world 3x4, from COLMAP images.txt."""
    path = scene_dir / "dslr_calibration_undistorted" / "images.txt"
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = line.split()
        if len(f) < 10:
            continue          # the POINTS2D continuation line
        try:
            qw, qx, qy, qz = (float(x) for x in f[1:5])
            tx, ty, tz = (float(x) for x in f[5:8])
        except ValueError:
            continue
        n = np.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
        qw, qx, qy, qz = qw / n, qx / n, qy / n, qz / n
        R = np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
        ])
        out[Path(f[9]).name] = np.hstack([R, np.array([tx, ty, tz]).reshape(3, 1)])
    return out


def gt_for_scene(image_names: list[str], image_dir: str
                 ) -> dict[int, np.ndarray] | None:
    """cam_from_world per scene image index, or None when no GT is available.

    Keyed on the loader's `image_dir` rather than the scene's stored paths:
    those are artifact-relative (`data/images/000000.png`) because the loader
    copies pixels into the artifact, so the dataset of origin survives only in
    provenance. The same field `_corpus_membership` reads.
    """
    if "/DTU/" in image_dir:
        ext = dtu_extrinsics()
        out = {}
        for i, name in enumerate(image_names):
            m = re.search(r"(\d+)", Path(name).stem)
            if m and int(m.group(1)) in ext:
                out[i] = ext[int(m.group(1))]
        return out or None
    if "/ETH/" in image_dir:
        scene_dir = Path(image_dir).parents[1]
        try:
            ext = eth_extrinsics(scene_dir)
        except FileNotFoundError:
            return None
        out = {i: ext[Path(n).name] for i, n in enumerate(image_names)
               if Path(n).name in ext}
        return out or None
    return None


def relative_pose_error(est: dict[int, np.ndarray], gt: dict[int, np.ndarray]
                        ) -> dict[str, float]:
    """Pose error against ground truth, as medians over image PAIRS.

    Pairwise relatives rather than absolutes because a reconstruction is
    determined only up to a similarity: comparing absolute poses would need a
    gauge alignment whose residual is itself a free parameter. A relative
    rotation is gauge-free, and a relative translation is gauge-free in
    DIRECTION, which is what is compared here.
    """
    shared = sorted(set(est) & set(gt))
    rot, trn = [], []
    for ai in range(len(shared)):
        for bi in range(ai + 1, len(shared)):
            a, b = shared[ai], shared[bi]
            Ra, ta = est[a][:, :3], est[a][:, 3]
            Rb, tb = est[b][:, :3], est[b][:, 3]
            R_est = Rb @ Ra.T
            t_est = tb - R_est @ ta

            Ra, ta = gt[a][:, :3], gt[a][:, 3]
            Rb, tb = gt[b][:, :3], gt[b][:, 3]
            R_gt = Rb @ Ra.T
            t_gt = tb - R_gt @ ta

            c = (np.trace(R_est @ R_gt.T) - 1.0) / 2.0
            rot.append(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))
            n1, n2 = np.linalg.norm(t_est), np.linalg.norm(t_gt)
            if n1 > 1e-9 and n2 > 1e-9:
                cd = np.clip(abs(float((t_est / n1) @ (t_gt / n2))), -1.0, 1.0)
                trn.append(np.degrees(np.arccos(cd)))
    if not rot:
        return {"gt_pairs": 0, "gt_rotation_deg": float("nan"),
                "gt_translation_deg": float("nan")}
    return {
        "gt_pairs": len(rot),
        "gt_rotation_deg": float(np.median(rot)),
        "gt_translation_deg": float(np.median(trn)) if trn else float("nan"),
        "gt_images_matched": len(shared),
    }
