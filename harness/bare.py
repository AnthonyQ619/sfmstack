"""Bare service mode for the context-ablation arms (A1-A3; plan in the experiment record).

Unset, nothing changes, and that is the only way an ordinary run executes. With SFM_BARE=1 (`launch.py --bare`):

  - every answer `sfmx` gives the agent keeps its measurements and loses its advice: metric values and directions,
    diagnostic codes and severities, the health profile's values and percentiles, the verifier's verdict and the
    two-estimator reading's numbers stay; summaries, descriptions, tuning notes, suggested actions, pointers into
    the skills, healthy bands and reading guides are removed;
  - `sfmx skills`, `sfmx brief` and `sfmx skill` are refused (sfmx.py);
  - the service's two automatic tuning moves are off: the second solve and the building of the estimators' own
    models (sfmx.py, `service()`).

The measurements are the tools' outputs and every arm gets them; the advice is the context the arms do without.
"""
from __future__ import annotations

# Keys whose value is advice or explanation, never a measurement.
DROP_KEYS = {
    "summary", "description", "param_tuning", "skill", "available_skills", "type_contracts", "contract",
    "suggested_actions", "see_also", "note", "notes", "how_to_read", "meaning", "healthy", "corpus_range",
    "artifact_md", "body", "message", "provenance_describes", "read", "fire_level", "fires", "fired_forms",
    "trade_off", "reference", "first_solve_health_profile", "second_solve", "estimator_models",
}
REFUSED = {"skills", "brief", "skill"}
REFUSAL = ("`sfmx {cmd}` is not available in this experiment: the written context is withheld. "
           "Use list, find, describe and the step results.")


def scrub(obj):
    """The same structure with every advice field removed (recursively)."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj
