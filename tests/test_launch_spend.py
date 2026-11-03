"""The launcher keeps what each agent attempt cost, as the CLI reported it.

`claude -p --output-format json` returns tokens by kind, dollars overall and per model, turns
and timings. The launcher used to keep only the session id and the reply, so no batch could say
what a session cost.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "harness"


def _launch():
    spec = importlib.util.spec_from_file_location("launch_mod", HARNESS / "launch.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["launch_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


CLI_OUT = {"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
           "result": "done", "num_turns": 41, "duration_ms": 3_600_000, "duration_api_ms": 2_900_000,
           "total_cost_usd": 12.5, "stop_reason": "end_turn",
           "usage": {"input_tokens": 98, "cache_creation_input_tokens": 356_560,
                     "cache_read_input_tokens": 11_467_066, "output_tokens": 31_691},
           "modelUsage": {"claude-opus-5-5": {"inputTokens": 98, "outputTokens": 31_691, "costUSD": 12.5}},
           "uuid": "not-kept", "ttft_ms": 900}


def test_an_attempt_keeps_the_cost_tokens_turns_and_timings():
    rec = _launch().attempt_record(0, "", CLI_OUT)
    assert rec["total_cost_usd"] == 12.5
    assert rec["usage"]["cache_read_input_tokens"] == 11_467_066
    assert rec["modelUsage"]["claude-opus-5-5"]["costUSD"] == 12.5
    assert (rec["num_turns"], rec["duration_ms"], rec["duration_api_ms"]) == (41, 3_600_000, 2_900_000)
    assert (rec["session_id"], rec["result"], rec["exit"]) == ("s-1", "done", 0)


def test_only_the_spend_fields_are_added():
    rec = _launch().attempt_record(0, "", CLI_OUT)
    assert "uuid" not in rec and "ttft_ms" not in rec


def test_a_missing_cost_stays_missing_rather_than_zero():
    # Negative control: output that is not JSON (the launcher wraps it as {"raw": ...}) carries no
    # spend, and the record must not invent one.
    rec = _launch().attempt_record(1, "boom", {"raw": "Traceback ..."})
    assert not any(k in rec for k in ("total_cost_usd", "usage", "modelUsage", "num_turns"))
    assert rec["session_id"] is None and rec["exit"] == 1
