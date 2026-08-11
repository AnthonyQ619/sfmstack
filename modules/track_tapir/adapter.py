"""FeatureTrackTapir -- scene/v1 + features/v1 -> tracks/v1.

Point tracking with BootsTAPIR. Keypoints from a few query frames are followed
through the set as though it were video.

The model comes from a different field than everything else here, and that shows
up in three places.

**Image order is input.** TAPIR reasons about a point's trajectory over time. The
set is fed in scene order, so that order is a real parameter of the problem in a
way it is not for a matcher or for VGGSfM's tracker.

**It tracks bidirectionally from each query frame**, which is why the default
`query_frame_num` is 3 here against VGGSfM's 5 -- one central query frame reaches
both ends of a sequence.

**Occlusion is a first-class output.** TAPIR returns an occlusion logit and an
expected-distance logit separately, and the confidence used here is the product
`(1 - sigma(occlusion)) * (1 - sigma(expected_dist))`. A point behind an object
scores low for being occluded; a point the model can see but cannot pin down
scores low for being uncertain. Both are reported, because the fix differs: the
first is a capture property and the second is a resolution or texture one.

On the resize. TAPIR runs at a fixed square resolution and the images are squeezed
into it anisotropically, which for a 4:3 scene distorts the picture. That is a
QUALITY question here and not a correctness one, unlike the same operation in the
VGGT modules: TAPIR predicts positions, not intrinsics, so the inverse map is
exact and the round trip is lossless. The VGGT bug was that a model predicting
`fx == fy` cannot express what an anisotropic squeeze does to a camera. There is
no camera here.
"""

from __future__ import annotations

import os

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from sfmkit import Ctx, module
from tapnet.torch import tapir_model

CHECKPOINT = os.environ.get("TAPIR_CHECKPOINT", "/opt/weights/bootstapir_v2.pt")

_MODEL = None
_MODEL_LEVEL = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model(pyramid_level: int):
    """BootsTAPIR is TAPIR with `extra_convs=True`; nothing else distinguishes it."""
    global _MODEL, _MODEL_LEVEL
    if _MODEL is None or _MODEL_LEVEL != pyramid_level:
        model = tapir_model.TAPIR(pyramid_level=pyramid_level, extra_convs=True)
        state = torch.load(CHECKPOINT, map_location="cpu")
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        # strict=False because a non-default pyramid_level changes the
        # architecture. At the default it loads exactly -- 0 missing, 0
        # unexpected -- which the image's build step asserts.
        model.load_state_dict(state, strict=False)
        _MODEL, _MODEL_LEVEL = model.to(device()).eval(), pyramid_level
    return _MODEL


def warmup() -> None:
    get_model(1)


def load_video(scene, n_images, size, dev) -> torch.Tensor:
    """(1, T, S, S, 3) in [-1, 1] -- TAPIR's channel-last video convention."""
    paths = scene.load("images", "paths")
    frames = []
    for f in range(n_images):
        array = np.asarray(
            Image.open(scene.resolve(str(paths[f]))).convert("RGB"), dtype=np.float32
        ) / 255.0
        frames.append(torch.from_numpy(array).permute(2, 0, 1))
    video = torch.stack(frames).to(dev)
    video = F.interpolate(video, size=(size, size), mode="bilinear", align_corners=False)
    return (video.permute(0, 2, 3, 1) * 2.0 - 1.0)[None].contiguous()


def select_query_frames(n_images: int, p) -> list[int]:
    """Which frames' keypoints get tracked.

    Never anchored at frame 0. TAPIR runs both temporal directions from a query
    frame, so a central one reaches twice as much of a sequence as an endpoint
    does -- the same finding FeatureTrackVGGSfM records, with a stronger reason.
    """
    wanted = min(p.query_frame_num, n_images)
    if p.query_selection == "interval":
        step = n_images / wanted
        ranking = [min(n_images - 1, int(round(step * (i + 0.5))))
                   for i in range(wanted)]
    else:  # midpoint -- outwards from the centre
        centre = (n_images - 1) / 2
        ranking = sorted(range(n_images), key=lambda f: (abs(f - centre), f))
    # Truncate the ranking, then sort. The other way round would return the
    # numerically smallest frame indices whatever the selection decided.
    return sorted(list(dict.fromkeys(int(f) for f in ranking))[:wanted])


def dedupe(observations, n_tracks, eps):
    """Union-find over tracks whose observations coincide within `eps` in a frame.

    Identical in purpose and implementation to FeatureTrackVGGSfM's: tracking from
    several query frames finds the same physical point several times, once per
    query frame that saw it, and left alone that point enters everything downstream
    once per copy.
    """
    parent = list(range(n_tracks))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for frame in np.unique(observations[:, 1].astype(int)):
        rows = np.flatnonzero(observations[:, 1].astype(int) == frame)
        cells: dict[tuple[int, int], list[int]] = {}
        for r in rows:
            key = (int(observations[r, 2] // eps), int(observations[r, 3] // eps))
            cells.setdefault(key, []).append(r)
        for (cx, cy), members in cells.items():
            neighbours = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbours.extend(cells.get((cx + dx, cy + dy), ()))
            for a in members:
                for b in neighbours:
                    if b <= a:
                        continue
                    if (abs(observations[a, 2] - observations[b, 2]) <= eps
                            and abs(observations[a, 3] - observations[b, 3]) <= eps):
                        union(int(observations[a, 0]), int(observations[b, 0]))

    return np.array([find(t) for t in range(n_tracks)], dtype=np.int64)


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    features = ctx.inputs["features"]
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    n_images = len(names)
    width, height = int(sizes[0, 0]), int(sizes[0, 1])

    if n_images < 2:
        raise ValueError(
            f"FeatureTrackTapir needs at least 2 images and the scene has "
            f"{n_images}. There is nowhere to track to."
        )
    if len(np.unique(np.asarray(sizes), axis=0)) > 1:
        raise ValueError(
            "FeatureTrackTapir needs every image at the same resolution -- it "
            "stacks them into one video tensor. Re-run SceneLoader with a fixed "
            "resize."
        )

    keypoints = features.load("keypoints")
    xy_all = np.asarray(keypoints["xy"], dtype=np.float32)
    image_index = np.asarray(keypoints["image_index"], dtype=int)
    scores = keypoints.get("scores")

    dev = device()
    model = get_model(p.pyramid_level)
    size = int(p.input_size)

    ctx.progress(0.05, f"loading {n_images} images at {size}x{size}")
    video = load_video(scene, n_images, size, dev)

    # Scene pixels <-> TAPIR pixels. Anisotropic, and exactly invertible -- see the
    # module docstring on why that is fine here and was not for VGGT.
    scale_x = size / width
    scale_y = size / height

    query_frames = select_query_frames(n_images, p)
    ctx.progress(0.1, f"query frames {query_frames}")

    rows, confidences, next_track = [], [], 0
    outside = 0
    conf_sum, conf_n, occ_sum = 0.0, 0, 0.0

    with torch.inference_mode():
        for step, q in enumerate(query_frames):
            ctx.progress(
                0.15 + 0.7 * step / len(query_frames),
                f"tracking from frame {q} ({step + 1}/{len(query_frames)})",
            )
            in_frame = np.flatnonzero(image_index == q)
            if len(in_frame) == 0:
                continue
            if scores is not None and len(in_frame) > p.max_query_points_per_frame:
                order = np.argsort(-np.asarray(scores)[in_frame])
                in_frame = in_frame[order[: p.max_query_points_per_frame]]
            else:
                in_frame = in_frame[: p.max_query_points_per_frame]

            points = xy_all[in_frame]
            # TAPIR's query format is (t, y, x), not (x, y). Getting this the wrong
            # way round on a non-square image does not crash; it tracks the
            # transpose of the scene.
            query = np.stack([
                np.full(len(points), float(q), dtype=np.float32),
                points[:, 1] * scale_y,
                points[:, 0] * scale_x,
            ], axis=1)
            query_t = torch.from_numpy(query).to(dev)

            tracks_all, conf_all, occ_all = [], [], []
            for start in range(0, len(query_t), p.query_chunk_size):
                chunk = query_t[start : start + p.query_chunk_size][None]
                out = model(
                    video=video,
                    query_points=chunk,
                    is_training=False,
                    query_chunk_size=p.query_chunk_size,
                )
                occluded = torch.sigmoid(out["occlusion"])
                uncertain = torch.sigmoid(out["expected_dist"])
                tracks_all.append(out["tracks"][0].float().cpu().numpy())
                conf_all.append(((1.0 - occluded) * (1.0 - uncertain))[0]
                                .float().cpu().numpy())
                occ_all.append(occluded[0].float().cpu().numpy())

            # (N, T, 2) and (N, T) -- points first, then time. The opposite order
            # to VGGSfM's tracker, whose output is (T, N, 2).
            tracks = np.concatenate(tracks_all, axis=0)
            confidence = np.concatenate(conf_all, axis=0)
            occlusion = np.concatenate(occ_all, axis=0)

            conf_sum += float(confidence.sum())
            occ_sum += float(occlusion.sum())
            conf_n += confidence.size

            # Back to scene pixels. Exactly the inverse of the squeeze above.
            xs = tracks[..., 0] / scale_x
            ys = tracks[..., 1] / scale_y

            visible = confidence >= p.min_confidence
            inside = (xs >= 0) & (xs <= width - 1) & (ys >= 0) & (ys <= height - 1)
            outside += int((visible & ~inside).sum())
            keep = visible & inside

            for n in range(tracks.shape[0]):
                frames = np.flatnonzero(keep[n])
                if len(frames) < p.min_track_len:
                    continue
                for f in frames:
                    rows.append([next_track, int(f), xs[n, f], ys[n, f]])
                    confidences.append(confidence[n, f])
                next_track += 1

            del tracks_all, conf_all, occ_all
            if dev.type == "cuda":
                torch.cuda.empty_cache()

    mean_confidence = conf_sum / max(conf_n, 1)
    mean_occlusion = occ_sum / max(conf_n, 1)

    if not rows:
        out = ctx.output("tracks")
        out.diagnostic(
            "no_tracks",
            severity="error",
            message="No track survived.",
            see_also="tuning.md#nothing-survives",
        )
        raise ValueError(
            f"no track survived. Mean confidence was {mean_confidence:.3f} and mean "
            f"predicted occlusion {mean_occlusion:.3f} over query frames "
            f"{query_frames}, against min_confidence {p.min_confidence} and "
            f"min_track_len {p.min_track_len}. "
            + (
                "High occlusion means the points genuinely leave view -- the query "
                "selection is what to change."
                if mean_occlusion > 0.5 else
                "Occlusion is low, so the model can see the points and cannot "
                "localise them: lower min_confidence, or raise input_size."
            )
        )

    observations = np.array(rows, dtype=np.float64)
    confidence = np.array(confidences, dtype=np.float32)
    raw_tracks = next_track

    merged = 0
    if p.dedupe_eps_px > 0 and raw_tracks > 1:
        ctx.progress(0.88, f"deduplicating {raw_tracks} raw tracks")
        root = dedupe(observations, raw_tracks, float(p.dedupe_eps_px))
        merged = raw_tracks - len(np.unique(root))

        best: dict[tuple[int, int], int] = {}
        for r in range(len(observations)):
            key = (int(root[int(observations[r, 0])]), int(observations[r, 1]))
            if key not in best or confidence[r] > confidence[best[key]]:
                best[key] = r
        chosen = np.array(sorted(best.values()), dtype=int)
        observations = observations[chosen]
        confidence = confidence[chosen]
        observations[:, 0] = root[observations[:, 0].astype(int)]

    _, inverse, counts = np.unique(
        observations[:, 0].astype(int), return_inverse=True, return_counts=True
    )
    keep_rows = counts[inverse] >= p.min_track_len
    observations = observations[keep_rows]
    confidence = confidence[keep_rows]

    if len(observations) == 0:
        out = ctx.output("tracks")
        out.diagnostic(
            "no_tracks",
            severity="error",
            message="No track survived deduplication.",
            see_also="tuning.md#nothing-survives",
        )
        raise ValueError(
            f"every one of the {raw_tracks} raw tracks fell below min_track_len "
            f"{p.min_track_len} after deduplication. Lower dedupe_eps_px -- at "
            f"{p.dedupe_eps_px}px it is fusing distinct points."
        )

    unique_ids, dense = np.unique(observations[:, 0].astype(int), return_inverse=True)
    observations[:, 0] = dense
    track_count = len(unique_ids)

    ctx.progress(0.95, f"{track_count} tracks, {len(observations)} observations")

    lengths = np.bincount(dense)
    per_frame = np.bincount(observations[:, 1].astype(int), minlength=n_images)

    out = ctx.output("tracks")
    out.save(
        "observations",
        obs=observations,
        track_count=np.int64(track_count),
        visibility=confidence.astype(np.float64),
    )

    avg_length = float(lengths.mean())
    duplicate_rate = merged / max(raw_tracks, 1)

    out.metric("track_count", int(track_count),
               direction="higher_better", healthy=(200, None))
    out.metric("avg_track_length", round(avg_length, 3),
               direction="higher_better", healthy=(3.0, None))
    out.metric("long_track_fraction", round(float((lengths >= 3).mean()), 4),
               direction="higher_better", healthy=(0.5, None))
    out.metric("min_frame_observations", int(per_frame.min()),
               direction="higher_better", healthy=(50, None))
    out.metric("frames_covered", round(float((per_frame > 0).mean()), 4),
               direction="higher_better", healthy=(1.0, None))
    # Structurally zero, as in FeatureTrackVGGSfM: one query point yields one
    # position per frame, so a track cannot contradict itself.
    out.metric("inconsistent_rate", 0.0, direction="lower_better", healthy=(None, 0.0))
    out.metric("max_track_length", int(lengths.max()), direction="neutral")
    out.metric("median_track_length", float(np.median(lengths)),
               direction="higher_better")
    out.metric("track_survival_5", round(float((lengths >= 5).mean()), 4),
               direction="higher_better")
    out.metric("track_survival_10", round(float((lengths >= 10).mean()), 4),
               direction="higher_better")
    out.metric("duplicate_track_rate", round(duplicate_rate, 4),
               direction="lower_better", healthy=(None, 0.5))
    out.metric("query_frames", len(query_frames), direction="neutral")
    out.metric("mean_confidence", round(mean_confidence, 4),
               direction="higher_better", healthy=(0.3, None))
    out.metric("mean_occlusion", round(mean_occlusion, 4), direction="lower_better")
    out.metric("observations_outside_frame", outside, direction="lower_better")

    if mean_confidence < 0.3:
        out.diagnostic(
            "poor_query_selection",
            severity="warn",
            message=(
                f"Mean confidence is {mean_confidence:.2f} over query frames "
                f"{query_frames}."
            ),
            suggested_actions=[
                "Use midpoint rather than interval on a sequential capture.",
                "Raise query_frame_num.",
                f"Mean predicted occlusion is {mean_occlusion:.2f} -- above 0.5 the "
                f"points are leaving view, below it the model cannot localise them.",
            ],
            see_also="tuning.md#query-frames-and-image-order",
        )

    if per_frame.min() < 50:
        out.diagnostic(
            "thin_frame",
            severity="warn",
            message=(
                f"Frame {int(per_frame.argmin())} carries {int(per_frame.min())} "
                f"observations."
            ),
            suggested_actions=[
                "That frame will fail to register whatever the totals say.",
                "Add a query frame near it rather than lowering thresholds.",
            ],
            see_also="limitations.md#coverage-follows-the-query-frames",
        )

    if duplicate_rate > 0.5:
        out.diagnostic(
            "heavy_duplication",
            severity="info",
            message=(
                f"Deduplication merged {duplicate_rate:.0%} of the {raw_tracks} "
                f"raw tracks."
            ),
            suggested_actions=[
                "Expected with several query frames viewing the same structure.",
                "Lower query_frame_num, or raise max_query_points_per_frame instead.",
            ],
            see_also="artifact.md#duplicate_track_rate-is-redundancy-not-error",
        )

    if mean_occlusion > 0.5:
        out.diagnostic(
            "mostly_occluded",
            severity="info",
            message=(
                f"Mean predicted occlusion is {mean_occlusion:.2f}: the model thinks "
                f"most points are out of view in most frames."
            ),
            suggested_actions=[
                "Normal on a capture orbiting an object -- half the surface is behind it.",
                "Unexpected on a forward walk-through, where it suggests the image "
                "order does not match the capture order.",
            ],
            see_also="limitations.md#image-order-is-input",
        )

    out.note(
        f"BootsTAPIR over {n_images} images at {size}x{size} (scene "
        f"{width}x{height}), query frames {query_frames} chosen by "
        f"{p.query_selection}. {raw_tracks} raw tracks, {merged} merged as "
        f"duplicates ({duplicate_rate:.0%}), {track_count} kept with "
        f"{len(observations)} observations, mean length {avg_length:.2f}. Mean "
        f"confidence {mean_confidence:.3f} = (1-occlusion)*(1-uncertainty), with "
        f"mean occlusion {mean_occlusion:.3f} on its own; {outside} predicted "
        f"positions landed outside the image and were dropped. Image ORDER is input "
        f"to this tracker in a way it is not for the others -- it follows points "
        f"through the set as video."
    )
