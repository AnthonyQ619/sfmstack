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

    return {
        "artifacts": rows,
        "metrics": sorted(metric_names),
        "lineage_divergence": divergences,
    }
