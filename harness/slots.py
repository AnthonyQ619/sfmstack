"""Which artifact goes into each slot a module consumes, for `sfmx run`.

A slot named on the command line takes that artifact. A REQUIRED slot left out is wired
from the chain's current artifact for it. An OPTIONAL slot left out stays empty.

Optional slots used to be wired from the chain as well. The only module whose optional
slots name artifacts the chain carries is DenseVGGT (`poses`, `sparse`, `tracks`), and
there the chain's current artifact was routinely from a different solve than the one
the agent passed: the first solve's poses beside the kept second solve's model, or a
folded model beside VGGT's poses. Seven of eight sessions in one test ran DenseVGGT at
least once on inputs they had not named, and one delivered it
(skills/evidence/dense-fixes-2026-10.md, Finding 6).
"""
from __future__ import annotations


def required(spec) -> bool:
    return not isinstance(spec, dict) or spec.get("required", True)


def wire_inputs(consumes: dict, overrides: dict, current: dict) -> dict:
    """slot -> artifact id, for every slot that gets one."""
    inputs = {}
    for slot, spec in consumes.items():
        aid = overrides.get(slot) or (current.get(slot) if required(spec) else None)
        if aid:
            inputs[slot] = aid
    return inputs
