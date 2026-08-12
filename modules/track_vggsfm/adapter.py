"""FeatureTrackVGGSfM -- scene/v1 + features/v1 -> tracks/v1.

Learned multi-view tracking. Keypoints from a handful of selected query frames are
propagated to every other frame in one pass, so there is no matcher and no view
graph anywhere in the chain.

The tracker is VGGSfM v2's, reached through VGGT's vendored copy at
`vggt.dependency` rather than through the vggsfm repository. Same weights, same
architecture, and it avoids a second research-licensed clone plus its pytorch3d
dependency. What that copy does NOT compute is the per-observation score --
`refine_track` is called with `compute_score=False` and returns None -- so there
is no score threshold here, only the visibility one, which is a genuine 0-1
probability.

Two design points, both measured.

**Query frame choice dominates everything.** On 8 DTU views, 2048 SIFT keypoints:
tracking from frame 0 leaves each point visible in a mean of 1.77 frames, and from
frame 4, 4.40. An endpoint of a sequential capture sees the least of the scene.
The predecessor always forced frame 0 into the query set; here it gets no special
treatment and the default selection is DINOv2 coverage ranking.

**Tracking from several query frames produces the same point several times.** Each
query point becomes its own track, so a well-seen point enters bundle adjustment
once per query frame that found it, quietly overweighted. The predecessor did not
deduplicate. Here tracks whose observations coincide are merged, and the merge rate
is reported -- it is a measure of redundancy rather than of error, and it rises
with `query_frame_num` by construction.

That merge is also the mirror image of `FeatureTrackUnionFind`'s conflict
handling. Union-find can fuse two scene points into one track and detects it with
`inconsistent_rate`; this tracker cannot, because each query point yields at most
one position per frame, so that metric is structurally zero here. What it can do
is SPLIT one point across tracks -- the failure union-find's metric is blind to --
and that is what `duplicate_track_rate` measures.
"""

from __future__ import annotations

import time

import os

import numpy as np
import torch
from PIL import Image
from sfmkit import Ctx, module, scene_intrinsics, split_rate, trifocal_transfer
from vggt.dependency.vggsfm_utils import (
    build_vggsfm_tracker,
    calculate_index_mappings,
    generate_rank_by_dino,
    predict_tracks_in_chunks,
    switch_tensor_order,
)

TRACKER_WEIGHTS = os.environ.get("VGGSFM_TRACKER", "/opt/weights/vggsfm_v2_tracker.pt")

_TRACKER = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_tracker():
    global _TRACKER
    if _TRACKER is None:
        # From the baked path, never the URL. build_vggsfm_tracker(None) would
        # reach for HuggingFace on first use, which is a network call in the middle
        # of a job on a host that may not have one.
        _TRACKER = build_vggsfm_tracker(TRACKER_WEIGHTS).to(device()).eval()
    return _TRACKER


def warmup() -> None:
    get_tracker()


def load_images(scene, n_images, dev) -> torch.Tensor:
    """(1, T, 3, H, W) in [0, 1] at the scene's working resolution.

    No resizing: the tracker is fully convolutional and the query points are in
    scene pixels, so working in that frame means no coordinate mapping exists to
    get wrong. It also means memory scales with the scene's resolution, which is
    what `max_query_points_per_frame` is there to trade against.
    """
    paths = scene.load("images", "paths")
    sizes = scene.load("images", "size_current")
    if len(np.unique(np.asarray(sizes), axis=0)) > 1:
        raise ValueError(
            "FeatureTrackVGGSfM needs every image at the same resolution -- it "
            "stacks them into one tensor and tracks across the stack. This scene "
            "has mixed resolutions; re-run SceneLoader with a fixed resize."
        )
    frames = []
    for f in range(n_images):
        array = np.asarray(
            Image.open(scene.resolve(str(paths[f]))).convert("RGB"), dtype=np.float32
        ) / 255.0
        frames.append(torch.from_numpy(array).permute(2, 0, 1))
    return torch.stack(frames)[None].to(dev)


def select_query_frames(images, n_images, p, dev) -> list[int]:
    """Which frames' keypoints get tracked.

    Frame 0 is deliberately NOT forced into the set. The predecessor did that
    "matching the VGGT demo behavior", and on a sequential capture an endpoint is
    the worst available choice -- measured, 1.77 visible frames per point against
    4.40 from the middle of the same 8-frame set.
    """
    wanted = min(p.query_frame_num, n_images)

    if p.query_selection == "dino":
        ranking = list(generate_rank_by_dino(
            images[0], query_frame_num=wanted, device=str(dev)
        ))
    elif p.query_selection == "interval":
        # Evenly spaced and CENTRED: the i-th of `wanted` bins, sampled at its
        # midpoint. Anchoring at frame 0 instead would guarantee an endpoint,
        # which is the choice the docstring above says to avoid.
        step = n_images / wanted
        ranking = [min(n_images - 1, int(round(step * (i + 0.5))))
                   for i in range(wanted)]
    else:  # midpoint -- outwards from the centre
        centre = (n_images - 1) / 2
        ranking = sorted(range(n_images), key=lambda f: (abs(f - centre), f))

    # Truncate the RANKING and then sort, not the other way round: these lists are
    # ordered best-first, so sorting before truncating would silently return the
    # numerically smallest frame indices whatever the selection method decided.
    return sorted(list(dict.fromkeys(int(f) for f in ranking))[:wanted])


def dedupe(observations, n_tracks, eps):
    """Union-find over tracks whose observations coincide within `eps` in a frame.

    Tracking from several query frames finds the same physical point several
    times, once per query frame that saw it. Left alone, that point enters
    everything downstream once per copy.

    Grid-hashed rather than pairwise: cells of side `eps` mean two observations
    within eps are always in the same or an adjacent cell, so each is compared
    against a bounded neighbourhood instead of against every other observation in
    the frame.
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
            f"FeatureTrackVGGSfM needs at least 2 images and the scene has "
            f"{n_images}. There is nowhere to track to."
        )

    keypoints = features.load("keypoints")
    xy_all = np.asarray(keypoints["xy"], dtype=np.float32)
    image_index = np.asarray(keypoints["image_index"], dtype=int)
    scores = keypoints.get("scores")

    dev = device()
    tracker = get_tracker()

    ctx.progress(0.05, f"loading {n_images} images at {width}x{height}")
    images = load_images(scene, n_images, dev)

    ctx.progress(0.1, f"selecting query frames by {p.query_selection}")
    query_frames = select_query_frames(images, n_images, p, dev)

    with torch.inference_mode():
        ctx.progress(0.15, "feature maps")
        fmaps = tracker.process_images_to_fmaps(images[0])[None]

        rows, visibilities, next_track = [], [], 0
        outside = 0
        visibility_sum, visibility_n = 0.0, 0

        for step, q in enumerate(query_frames):
            ctx.progress(
                0.2 + 0.65 * step / len(query_frames),
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

            points = torch.from_numpy(xy_all[in_frame]).to(dev)[None]

            # The tracker assumes the query points belong to frame 0, so the
            # stack is permuted to put the query frame there and permuted back
            # afterwards. Both directions use the same index map.
            order = calculate_index_mappings(q, n_images, device=dev)
            fed_images, fed_fmaps = switch_tensor_order([images, fmaps], order, dim=1)

            per_chunk = max(1, p.max_points_num // n_images)
            chunks = list(torch.split(points, per_chunk, dim=1))

            track, vis, score = predict_tracks_in_chunks(
                tracker, fed_images, chunks, fed_fmaps, fine_tracking=p.fine_tracking
            )
            track, vis = switch_tensor_order([track, vis], order, dim=1)

            track = track[0].float().cpu().numpy()   # (T, N, 2)
            vis = vis[0].float().cpu().numpy()       # (T, N)
            visibility_sum += float(vis.sum())
            visibility_n += vis.size

            visible = vis >= p.visibility_threshold
            # The tracker extrapolates rather than refusing, so predicted
            # positions land outside the image. Those are not observations.
            inside = (
                (track[..., 0] >= 0) & (track[..., 0] <= width - 1)
                & (track[..., 1] >= 0) & (track[..., 1] <= height - 1)
            )
            outside += int((visible & ~inside).sum())
            keep = visible & inside

            for n in range(track.shape[1]):
                frames = np.flatnonzero(keep[:, n])
                if len(frames) < p.min_track_len:
                    continue
                for f in frames:
                    rows.append([next_track, int(f), track[f, n, 0], track[f, n, 1]])
                    visibilities.append(vis[f, n])
                next_track += 1

            del track, vis, fed_images, fed_fmaps
            if dev.type == "cuda":
                torch.cuda.empty_cache()

    mean_visibility = visibility_sum / max(visibility_n, 1)

    if not rows:
        out = ctx.output("tracks")
        out.diagnostic(
            "no_tracks",
            severity="error",
            message="No track survived.",
            see_also="tuning.md#nothing-survives",
        )
        raise ValueError(
            f"no track survived. Mean predicted visibility was "
            f"{mean_visibility:.3f} over {len(query_frames)} query frames "
            f"{query_frames}, and visibility_threshold is {p.visibility_threshold} "
            f"with min_track_len {p.min_track_len}. A low mean visibility is a "
            f"query-selection problem, not a threshold one -- the chosen frames "
            f"see little of the scene."
        )

    observations = np.array(rows, dtype=np.float64)
    visibility = np.array(visibilities, dtype=np.float32)
    raw_tracks = next_track

    # ---------------------------------------------------------------- dedupe
    merged = 0
    if p.dedupe_eps_px > 0 and raw_tracks > 1:
        ctx.progress(0.88, f"deduplicating {raw_tracks} raw tracks")
        root = dedupe(observations, raw_tracks, float(p.dedupe_eps_px))
        merged = raw_tracks - len(np.unique(root))

        # One observation per (merged track, frame): the most visible one, which
        # is the same rule used to pick between duplicate observations elsewhere.
        best: dict[tuple[int, int], int] = {}
        for r in range(len(observations)):
            key = (int(root[int(observations[r, 0])]), int(observations[r, 1]))
            if key not in best or visibility[r] > visibility[best[key]]:
                best[key] = r
        chosen = np.array(sorted(best.values()), dtype=int)
        observations = observations[chosen]
        visibility = visibility[chosen]
        observations[:, 0] = root[observations[:, 0].astype(int)]

    # Re-apply the length filter: merging cannot shorten a track, but dropping the
    # duplicate observations within one frame can.
    _, inverse, counts = np.unique(
        observations[:, 0].astype(int), return_inverse=True, return_counts=True
    )
    keep_rows = counts[inverse] >= p.min_track_len
    observations = observations[keep_rows]
    visibility = visibility[keep_rows]

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

    # track_id must be dense in [0, track_count), which the type checks.
    unique_ids, dense = np.unique(observations[:, 0].astype(int), return_inverse=True)
    observations[:, 0] = dense
    track_count = len(unique_ids)

    ctx.progress(0.95, f"{track_count} tracks, {len(observations)} observations")

    lengths = np.bincount(dense)
    per_frame = np.bincount(
        observations[:, 1].astype(int), minlength=n_images
    )

    out = ctx.output("tracks")
    out.save(
        "observations",
        obs=observations,
        track_count=np.int64(track_count),
        visibility=visibility.astype(np.float64),
    )

    avg_length = float(lengths.mean())
    duplicate_rate = merged / max(raw_tracks, 1)
    frames_covered = float((per_frame > 0).mean())

    out.metric("track_count", int(track_count),
               direction="higher_better", healthy=(200, None))
    out.metric("avg_track_length", round(avg_length, 3),
               direction="higher_better", healthy=(3.0, None))
    out.metric("long_track_fraction", round(float((lengths >= 3).mean()), 4),
               direction="higher_better", healthy=(0.5, None))
    out.metric("min_frame_observations", int(per_frame.min()),
               direction="higher_better", healthy=(50, None))
    out.metric("frames_covered", round(frames_covered, 4),
               direction="higher_better", healthy=(1.0, None))
    # Structurally zero: one query point yields at most one position per frame, so
    # a track cannot contradict itself. Reported because the type requires it, and
    # documented as uninformative HERE rather than quietly emitted as a success.
    # Positional accuracy -- the one axis no other metric here touches. Timed and
    # reported, because it is the only part of this module that could grow with the
    # scene in a way the rest does not.
    transfer_started = time.monotonic()
    K_all = scene_intrinsics(scene, n_images)
    transfer, transfer_n, transfer_triples = (
        trifocal_transfer(observations, K_all) if K_all is not None else (None, 0, 0)
    )
    transfer_seconds = time.monotonic() - transfer_started

    out.metric("inconsistent_rate", 0.0, direction="lower_better", healthy=(None, 0.0))
    # What deduplication did NOT catch, at the tolerance tracks/v1 fixes rather
    # than at dedupe_eps_px. duplicate_track_rate says what was merged; this says
    # what is still split in the table as written, comparably with every other
    # tracker.
    out.metric(
        "trifocal_transfer_px",
        round(transfer, 4) if transfer is not None else None,
        direction="lower_better", healthy=(None, 3.0),
    )
    out.metric("trifocal_samples", transfer_n, direction="higher_better")
    out.metric("trifocal_seconds", round(transfer_seconds, 2), direction="lower_better")
    out.metric("split_rate", round(split_rate(observations, track_count), 4),
               direction="lower_better", healthy=(None, 0.1))
    out.metric("median_track_length", float(np.median(lengths)),
               direction="higher_better")
    out.metric("track_survival_5", round(float((lengths >= 5).mean()), 4),
               direction="higher_better")
    out.metric("duplicate_track_rate", round(duplicate_rate, 4),
               direction="lower_better", healthy=(None, 0.5))
    out.metric("query_frames", len(query_frames), direction="neutral")
    out.metric("mean_visibility", round(mean_visibility, 4),
               direction="higher_better", healthy=(0.3, None))
    out.metric("observations_outside_frame", outside, direction="lower_better")

    if mean_visibility < 0.3:
        out.diagnostic(
            "poor_query_selection",
            severity="warn",
            message=(
                f"Mean predicted visibility is {mean_visibility:.2f} over query "
                f"frames {query_frames}; they see little of the scene."
            ),
            suggested_actions=[
                "Switch query_selection to dino, which ranks frames by coverage.",
                "Raise query_frame_num.",
                "On a sequential capture, avoid the endpoints -- measured, an "
                "endpoint gave 0.22 against 0.54 from the middle of the same set.",
            ],
            see_also="tuning.md#query-frames-are-the-whole-game",
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
                f"Deduplication merged {duplicate_rate:.0%} of the "
                f"{raw_tracks} raw tracks."
            ),
            suggested_actions=[
                "Expected with several query frames viewing the same structure.",
                "Lower query_frame_num if runtime matters more than coverage.",
            ],
            see_also="artifact.md#duplicate_track_rate-is-redundancy-not-error",
        )

    out.note(
        f"VGGSfM v2 tracker over {n_images} images at {width}x{height}, query "
        f"frames {query_frames} chosen by {p.query_selection}. {raw_tracks} raw "
        f"tracks, {merged} merged as duplicates ({duplicate_rate:.0%}), "
        f"{track_count} kept with {len(observations)} observations, mean length "
        f"{avg_length:.2f}. Mean predicted visibility {mean_visibility:.3f}; "
        f"{outside} predicted positions landed outside the image and were dropped. "
        f"No matcher and no view graph took part -- these tracks come straight "
        f"from the detector's keypoints. inconsistent_rate is structurally zero "
        f"here and carries no information; duplicate_track_rate is the metric that "
        f"does."
    )
