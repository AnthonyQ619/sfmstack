"""Swapping two inputs of one type must not return the other run.

The recipe sorted input ids and dropped their slots, so `PoseFill(poses=A, poses_b=B)`
and `PoseFill(poses=B, poses_b=A)` had one id, and the second call was handed the
first call's output, marked cached. An agent found it on a real capture.
"""
from __future__ import annotations

from dataclasses import dataclass

from sfmkit import artifact_id, recipe_inputs


@dataclass
class A:
    id: str
    type: str


def _id(inputs):
    return artifact_id(type="poses/v1", module="PoseFill", module_version="1.1.0",
                       slot="poses", params={}, inputs=recipe_inputs(inputs))


def test_swapping_two_same_typed_inputs_changes_the_id():
    scene, sparse = A("art_s", "scene/v1"), A("art_m", "sparse_model/v1")
    vggt, mapa = A("art_v", "poses/v1"), A("art_a", "poses/v1")
    one = _id({"scene": scene, "sparse": sparse, "poses": vggt, "poses_b": mapa})
    two = _id({"scene": scene, "sparse": sparse, "poses": mapa, "poses_b": vggt})
    assert one != two


def test_the_old_recipe_could_not_tell_them_apart():
    """Negative control: with the bare ids the old way, the two orders collide."""
    ids = lambda d: [a.id for a in d.values()]  # noqa: E731
    vggt, mapa = A("art_v", "poses/v1"), A("art_a", "poses/v1")
    kw = dict(type="poses/v1", module="PoseFill", module_version="1.1.0", slot="poses", params={})
    assert artifact_id(**kw, inputs=ids({"poses": vggt, "poses_b": mapa})) == \
        artifact_id(**kw, inputs=ids({"poses": mapa, "poses_b": vggt}))


def test_a_recipe_without_a_repeated_type_hashes_exactly_as_before():
    """No existing cache entry is invalidated: only repeated types change form."""
    ins = {"scene": A("art_s", "scene/v1"), "features": A("art_f", "features/v1")}
    assert recipe_inputs(ins) == ["art_s", "art_f"]
    kw = dict(type="pairwise_matches/v1", module="M", module_version="1.0.0", slot="matches", params={})
    assert artifact_id(**kw, inputs=recipe_inputs(ins)) == artifact_id(**kw, inputs=["art_s", "art_f"])
