"""Lineage comparison.

Nothing is ever marked "stale". Re-running an upstream module BRANCHES the DAG,
and a newer branch does not supersede an older one -- it may well be worse, and
that is a judgment the orchestrator cannot make. Divergence is a fact;
supersession is an opinion.

So instead of a staleness flag, comparison reports *where two artifacts' ancestry
parted company*. That stops the agent attributing a difference to the parameter it
just changed when it actually came from three stages up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sfmkit import ArtifactStore


@dataclass(frozen=True)
class Divergence:
    """One point where two lineages differ."""

    module: str
    payload_type: str
    left: str | None  # artifact id on the left branch
    right: str | None
    param_diff: dict[str, tuple[Any, Any]]

    def describe(self) -> str:
        if self.left is None or self.right is None:
            side = "left" if self.right is None else "right"
            return (
                f"{self.module} ({self.payload_type}): present only on the {side} branch"
            )
        if not self.param_diff:
            return (
                f"{self.module} ({self.payload_type}): different artifacts "
                f"({self.left} vs {self.right}) with identical parameters -- the "
                f"difference is inherited from further upstream"
            )
        bits = ", ".join(
            f"{k} {a!r} -> {b!r}" for k, (a, b) in sorted(self.param_diff.items())
        )
        return f"{self.module} ({self.payload_type}): {bits}"


def _by_producer(store: ArtifactStore, artifact_id: str) -> dict[tuple[str, str], str]:
    """(module, payload type) -> artifact id, over the whole ancestry."""
    out: dict[tuple[str, str], str] = {}
    for aid in store.ancestry(artifact_id):
        try:
            art = store.open(aid)
        except Exception:
            continue
        prov = art.manifest.produced_by
        module = prov.module if prov else "<unknown>"
        out[(module, art.type)] = aid
    return out


def _params(store: ArtifactStore, artifact_id: str) -> dict[str, Any]:
    try:
        prov = store.open(artifact_id).manifest.produced_by
    except Exception:
        return {}
    return dict(prov.params) if prov else {}


def diverge(store: ArtifactStore, left: str, right: str) -> list[Divergence]:
    """Where two artifacts' lineages differ, keyed by producing module and type."""
    l_map = _by_producer(store, left)
    r_map = _by_producer(store, right)

    out: list[Divergence] = []
    for key in sorted(set(l_map) | set(r_map)):
        module, payload_type = key
        l_id = l_map.get(key)
        r_id = r_map.get(key)
        if l_id == r_id:
            continue

        diff: dict[str, tuple[Any, Any]] = {}
        if l_id and r_id:
            lp, rp = _params(store, l_id), _params(store, r_id)
            for name in sorted(set(lp) | set(rp)):
                if lp.get(name) != rp.get(name):
                    diff[name] = (lp.get(name), rp.get(name))

        out.append(
            Divergence(
                module=module,
                payload_type=payload_type,
                left=l_id,
                right=r_id,
                param_diff=diff,
            )
        )
    return out


def compare(store: ArtifactStore, artifact_ids: list[str]) -> dict[str, Any]:
    """Metrics side by side, plus lineage divergence for each pair.

    The metric table alone invites a false conclusion whenever two results differ
    for a reason further upstream than the knob under test, which is why the
    divergence report travels with it rather than being a separate call.
    """
    rows: dict[str, dict[str, Any]] = {}
    metric_names: set[str] = set()

    for aid in artifact_ids:
        art = store.open(aid)
        prov = art.manifest.produced_by
        rows[aid] = {
            "type": art.type,
            "module": prov.module if prov else None,
            "params": dict(prov.params) if prov else {},
            "metrics": {n: m.value for n, m in art.manifest.metrics.items()},
            "diagnostics": [d.code for d in art.manifest.diagnostics],
        }
        metric_names |= set(art.manifest.metrics)

    divergences = {}
    for i, a in enumerate(artifact_ids):
        for b in artifact_ids[i + 1 :]:
            found = diverge(store, a, b)
            if found:
                divergences[f"{a} vs {b}"] = [d.describe() for d in found]

    out = {
        "artifacts": rows,
        "metrics": sorted(metric_names),
        "lineage_divergence": divergences,
    }
    sparse = [aid for aid in artifact_ids if rows[aid]["type"] == SPARSE_MODEL]
    if len(sparse) >= 2:
        out["sparse_models"] = _sparse_comparison(store, sparse)
    # Rotations do not need points, and `poses/v1` declares the same cam_from_world,
    # valid and image_index arrays `sparse_model/v1` does, so the two read alike. The
    # comparison used to be gated to sparse models, which made health/bounce's "solve
    # the capture with a second pose paradigm and read rotation_agreement" impossible
    # to carry out: every second paradigm reachable from here -- PoseVGGT,
    # PoseMapAnything -- emits poses/v1, so the tool returned nothing for exactly the
    # pair the instruction named. This adds a key; it changes no existing one.
    posed = [aid for aid in artifact_ids if rows[aid]["type"] in POSE_CARRYING]
    if len(posed) >= 2 and not all(rows[aid]["type"] == SPARSE_MODEL for aid in posed):
        out["pose_agreement"] = _pose_comparison(store, posed)
    return out


SPARSE_MODEL = "sparse_model/v1"
POSES = "poses/v1"
POSE_CARRYING = (SPARSE_MODEL, POSES)
TRACKS = "tracks/v1"

POSE_HOW_TO_READ = (
    "rotation_agreement is how far two models' RELATIVE camera rotations disagree "
    "over the cameras both registered, in degrees -- gauge-free, needing no "
    "reference, and defined between any two artifacts carrying poses whatever "
    "produced them. It is the check health/bounce asks for before a stuck "
    "pose-agreement rung is read as a capability gap, and the reading plan/pose "
    "asks for before a model is delivered. Two INDEPENDENT estimators are what "
    "make it readable: one estimator disagreeing with your model cannot tell you "
    "whether the model or the estimator is the outlier, so compare the estimators "
    "with EACH OTHER as well and read your disagreement against their spread. A "
    "disagreement is a reason to measure the alternative, never a reason to "
    "discard a model -- two learned estimators sharing a training distribution can "
    "agree closely and both be wrong. Entries are null where the two share fewer "
    "than two cameras, or were built on different scenes."
)

SPARSE_HOW_TO_READ = (
    "error_by_support splits each model's per-point reprojection error by how "
    "many views see the point; compare bucket medians together with bucket "
    "sizes, never a pooled mean, because a model with more two-view points reads "
    "better by arithmetic. A pair built from ONE track table also gets "
    "paired_error_by_support: the difference on the same tracks (first model "
    "minus second), bucketed by the first model's observation count. Two models "
    "from different track tables (a detector, matcher or tracker changed) have "
    "nothing to join, so there is no paired entry. rotation_agreement is how far "
    "the two models' relative camera rotations disagree over the cameras both "
    "registered -- no reference needed; it is the check health/bounce asks for "
    "before a stuck pose-agreement rung is read as a capability gap."
)


def _ancestor(store: ArtifactStore, art, wanted: str, depth: int = 8):
    """The nearest artifact of type `wanted` upstream of `art`, or None."""
    frontier = [art]
    for _ in range(depth):
        nxt = []
        for a in frontier:
            for pid in a.manifest.inputs:
                try:
                    parent = store.open(pid)
                except Exception:
                    continue
                if parent.type == wanted:
                    return parent
                nxt.append(parent)
        frontier = nxt
    return None


def _sparse_comparison(store: ArtifactStore, ids: list[str]) -> dict[str, Any]:
    from .health import error_by_support, paired_error_by_support, rotation_agreement

    arts = {aid: store.open(aid) for aid in ids}
    tracks = {aid: _ancestor(store, a, TRACKS) for aid, a in arts.items()}
    pairs: dict[str, Any] = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ta, tb = tracks[a], tracks[b]
            same = ta is not None and tb is not None and ta.id == tb.id
            entry: dict[str, Any] = {"same_track_table": same}
            if same:
                entry["paired_error_by_support"] = paired_error_by_support(arts[a], arts[b])
            if arts[a].manifest.scene and arts[a].manifest.scene == arts[b].manifest.scene:
                entry["rotation_agreement"] = rotation_agreement(arts[a], arts[b])
            pairs[f"{a} vs {b}"] = entry
    return {
        "error_by_support": {aid: error_by_support(a) for aid, a in arts.items()},
        "pairs": pairs,
        "how_to_read": SPARSE_HOW_TO_READ,
    }


def _pose_comparison(store: ArtifactStore, ids: list[str]) -> dict[str, Any]:
    """Pairwise rotation agreement over anything carrying poses.

    No error_by_support here: that reading needs per-point reprojection error, which
    `poses/v1` does not have -- a feed-forward estimator has no correspondences to
    measure against, which is exactly why it is worth comparing to.
    """
    from .health import rotation_agreement

    arts = {aid: store.open(aid) for aid in ids}
    pairs: dict[str, Any] = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            same_scene = (arts[a].manifest.scene
                          and arts[a].manifest.scene == arts[b].manifest.scene)
            pairs[f"{a} vs {b}"] = (rotation_agreement(arts[a], arts[b])
                                    if same_scene else None)
    return {"pairs": pairs, "how_to_read": POSE_HOW_TO_READ}
