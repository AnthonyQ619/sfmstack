"""`sfmx run` wires a required slot from the chain when it is not named, and an optional
slot only when it is named (harness/slots.py)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from slots import wire_inputs  # noqa: E402

DENSE_VGGT = {
    "scene": {"type": "scene/v1", "required": True},
    "poses": {"type": "poses/v1", "required": False},
    "sparse": {"type": "sparse_model/v1", "required": False},
    "tracks": {"type": "tracks/v1", "required": False},
}
CHAIN = {"scene": "art_scene", "poses": "art_first_solve", "sparse": "art_second_solve",
         "tracks": "art_tracks"}


def test_named_sparse_alone_gets_no_chain_poses():
    # The failure this guards: the first solve's poses unprojecting the kept second solve.
    assert wire_inputs(DENSE_VGGT, {"sparse": "art_refined"}, CHAIN) == {
        "scene": "art_scene", "sparse": "art_refined"}


def test_optional_slots_left_out_stay_empty():
    assert wire_inputs(DENSE_VGGT, {}, CHAIN) == {"scene": "art_scene"}


def test_named_poses_and_tracks_get_no_chain_sparse():
    got = wire_inputs(DENSE_VGGT, {"poses": "art_posevggt", "tracks": "art_t"}, CHAIN)
    assert got == {"scene": "art_scene", "poses": "art_posevggt", "tracks": "art_t"}


def test_required_slots_still_come_from_the_chain():
    consumes = {"scene": {"type": "scene/v1"}, "sparse": {"type": "sparse_model/v1", "required": True}}
    assert wire_inputs(consumes, {}, CHAIN) == {"scene": "art_scene", "sparse": "art_second_solve"}


def test_a_bare_type_string_is_required():
    assert wire_inputs({"scene": "scene/v1"}, {}, CHAIN) == {"scene": "art_scene"}


def test_a_required_slot_the_chain_lacks_is_left_for_the_caller_to_report():
    consumes = {"scene": {"type": "scene/v1"}, "matches": {"type": "matches/v1"}}
    assert wire_inputs(consumes, {}, CHAIN) == {"scene": "art_scene"}
