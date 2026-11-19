#!/usr/bin/env python3
"""Audit sealed sessions for withheld scene information (P11). Also the checker the seal tests use.

    audit_seal.py <capture_dir> [<capture_dir> ...] [--signals visual,illumination,motion] [--out audit.json]

Signals default to the session's own `context_roots.json`. Per session it reports, from the
transcript(s) under ~/.claude/projects and the store:

  values        withheld readings, as the store holds them and as modules print them, found in any
                tool result (illumination: triage's photometric metrics and clipping; motion: every
                SceneMotion metric, triage's `ordered` / `capture_interval_s`)
  keys          withheld reading names in tool results of the commands that return measurements
                (run, artifact, series, state, summary, compare, wait, brief) -- not in context pages,
                which name every metric by design
  colour        `rgb` arrays in tool results under visual or illumination
  frames        Read calls on image files outside scratch/views, and every frame or sheet the views
                layer served (its log) under a signal that refuses it
  refused       calls to a withheld module, and refusals the agent hit (expected: counted, not leaks)
  denied        reads the permission layer refused (expected: attempts, not leaks)
  channels      any tool beyond Bash/Read/Edit/Write (messaging, connectors, ToolSearch, ...) and any
                message from another session: on a sealed run each is a FAIL, used or not
  scene_words   scene-type words in the agent's OWN text (underwater, orchard, rover, ...): not proof of
                a leak -- the agent may infer them -- but each is listed for review

A session passes when values, keys, colour, frames and channels are all empty. Results too large for the
transcript are saved under the session's tool-results/ folder; those files are scanned as well.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import withhold  # noqa: E402

PHOTO_METRICS = ("illumination_change", "color_shift", "exposure_shift", "combined_change",
                 "highlight_clipped_fraction", "shadow_clipped_fraction")
SEALED_TOOLS = {"Bash", "Read", "Edit", "Write"}
MEASURING = re.compile(r"^sfmx (run|artifact|series|state|summary|compare|wait|brief|replay)\b")
SCENE_WORDS = re.compile(r"underwater|under water|seafloor|sea floor|seabed|marine|diver|\bcoral|ocean|"
                         r"subsea|aquatic|turbid|backscatter|caustic|\brover\b|\bmars\b|martian|orchard|"
                         r"vineyard|apple tree|fruit tree|canopy|hedge|\bFLSea\b|MADMAX|\bFuji", re.I)


def _manifests(store: Path):
    import yaml
    for md in sorted((store / "artifacts").glob("*/artifact.md")):
        text = md.read_text()
        try:
            front = yaml.safe_load(text.split("---", 2)[1])
        except Exception:
            continue
        yield md.parent, front, text


def _num_forms(v: float) -> set[str]:
    """How a reading can appear: as stored (4 dp) and as notes print it (3 dp, percent)."""
    out = set()
    if v is None or not isinstance(v, (int, float)) or isinstance(v, bool):
        return out
    s4 = f"{round(v, 4)}"
    digits = s4.lstrip("-").replace(".", "").lstrip("0").rstrip("0")
    if len(digits) >= 3:                      # distinctive enough to mean this reading
        out.add(s4)
    return out


def withheld_readings(store: Path, signals: set[str]) -> dict:
    """{'values': {string: why}, 'keys': [...]} for this store under these signals."""
    vals: dict[str, str] = {}
    keys: list[str] = []
    for adir, front, text in _manifests(store):
        mod = ((front.get("produced_by") or {}).get("module")) or ""
        metrics = front.get("metrics") or {}
        val = {k: (m.get("value") if isinstance(m, dict) else m) for k, m in metrics.items()}
        if "illumination" in signals and mod == "SceneTriage":
            for k in PHOTO_METRICS:
                for f in _num_forms(val.get(k)):
                    vals[f] = f"SceneTriage.{k}"
            for label, k in (("combined", "combined_change"), ("illumination", "illumination_change"),
                             ("colour", "color_shift"), ("exposure", "exposure_shift")):
                if isinstance(val.get(k), (int, float)):
                    vals[f"{label} {val[k]:.3f}"] = f"SceneTriage note {k}"
            h, sh = val.get("highlight_clipped_fraction"), val.get("shadow_clipped_fraction")
            if isinstance(h, (int, float)):
                vals[f"{h:.2%} highlight"] = "SceneTriage note clipping"
            if isinstance(sh, (int, float)):
                vals[f"{sh:.2%} shadow"] = "SceneTriage note clipping"
        if "motion" in signals and mod == "SceneMotion":
            for k, v in val.items():
                for f in _num_forms(v):
                    vals[f] = f"SceneMotion.{k}"
                keys.append(k)
        if "motion" in signals and mod == "SceneTriage":
            if "ordered" in val:
                vals[f'"ordered": {val["ordered"]}'] = "SceneTriage.ordered"
            vals["Ordered capture"] = "SceneTriage note"
            vals["UNORDERED capture"] = "SceneTriage note"
    if "illumination" in signals:
        keys += list(PHOTO_METRICS) + ["photometric", "pair_combined", "highlight_clipped",
                                       "shadow_clipped", "illumination_unstable"]
    if "motion" in signals:
        keys += ["ordered", "capture_interval_s", "unordered_capture"]
    keys = sorted(set(k for k in keys if k not in ("stride", "n_pairs")))
    return {"values": vals, "keys": keys}


def find_leaks(text: str, readings: dict, signals: set[str], measuring: bool = True) -> dict:
    # Bounded, so a reading of 0.1333 does not match inside an unrelated 0.133391.
    hits = {"values": sorted({f"{v} ({why})" for v, why in readings["values"].items()
                              if re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", text)})}
    # A reading NAME is a leak only where it carries a reading: as a key (JSON or YAML) or as a
    # diagnostic code. Advice that names a metric ("read overall_magnitude") carries nothing.
    hits["keys"] = sorted(k for k in readings["keys"] if measuring and re.search(
        rf'"{re.escape(k)}"\s*:|^\s*{re.escape(k)}:|code["\']?\s*[:=]\s*["\']?{re.escape(k)}\b', text, re.M))
    for pat, why in ((r"Photometric:", "photometric sentence"), (r"Clipping:", "clipping sentence")):
        if "illumination" in signals and measuring and pat in text:
            hits["keys"].append(why)
    hits["colour"] = (['"rgb"'] if {"visual", "illumination"} & signals and re.search(r'"rgb"\s*:', text) else [])
    return hits


def transcripts(capture_dir: Path) -> list[Path]:
    sys.path.insert(0, str(HERE))
    from launch import transcript_dir
    found = sorted(transcript_dir(capture_dir / "scratch").glob("*.jsonl"))
    # The transcript folder is keyed by the scratch path, so an earlier run at the same path shares it.
    # Audit this run's own sessions (agent_log.json) when it names them.
    log = capture_dir / "agent_log.json"
    ids = {a.get("session_id") for a in (json.loads(log.read_text()).get("attempts") or [])} - {None} \
        if log.exists() else set()
    return [t for t in found if t.stem in ids] if ids else found


def audit(capture_dir: Path, signals: set[str] | None = None) -> dict:
    roots = json.loads((capture_dir / "context_roots.json").read_text()) if (capture_dir / "context_roots.json").exists() else {}
    if signals is None:
        signals = set(roots.get("withheld") or [])
    readings = withheld_readings(capture_dir / "store", signals)
    rep = {"capture_dir": str(capture_dir), "signals": sorted(signals), "sealed": bool(roots.get("sealed")),
           "values": [], "keys": [], "colour": [], "frames": [], "channels": [], "refused": [], "denied": [],
           "scene_words": [],
           "tool_calls": 0}
    calls = {}
    for tr in transcripts(capture_dir):
        for line in tr.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            for p in ((e.get("message") or {}).get("content") or []):
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "tool_use":
                    rep["tool_calls"] += 1
                    if p.get("name") not in SEALED_TOOLS:
                        rep["channels"].append(f"tool {p.get('name')} {json.dumps(p.get('input'))[:120]}")
                    inp = p.get("input") or {}
                    calls[p["id"]] = (p.get("name"), inp)
                    cmd = str(inp.get("command", ""))
                    for m in withhold.modules(signals):
                        if re.search(rf"sfmx (run|describe|skill) {m}\b", cmd):
                            rep["refused"].append(cmd[:160])
                    f = str(inp.get("file_path", ""))
                    if p.get("name") == "Read" and re.search(r"\.(png|jpe?g)$", f, re.I) and "/scratch/views/" not in f:
                        rep["frames"].append(f"Read {f}")
                elif p.get("type") == "tool_result":
                    c = p.get("content")
                    text = c if isinstance(c, str) else json.dumps(c)
                    name, inp = calls.get(p.get("tool_use_id"), ("", {}))
                    cmd = str(inp.get("command", ""))
                    if "denied" in text.lower() and "permission" in text.lower():
                        rep["denied"].append(f"{name} {cmd or inp.get('file_path', '')}"[:200])
                    measuring = bool(MEASURING.match(cmd)) or (name == "Read" and "/scratch/last_" in str(inp.get("file_path", "")))
                    h = find_leaks(text, readings, signals, measuring)
                    for k in ("values", "keys", "colour"):
                        rep[k] += [f"{x} <- {name} {cmd[:80] or inp.get('file_path', '')}" for x in h[k]]
                    # a failed Read of an image is an attempt, not a view
                    if name == "Read" and rep["frames"] and rep["frames"][-1].endswith(str(inp.get("file_path", ""))) \
                            and ("denied" in text.lower() or "not allowed" in text.lower()):
                        rep["denied"].append(rep["frames"].pop())
                elif p.get("type") == "text" and e.get("type") == "user" and "cross-session-message" in (p.get("text") or ""):
                    rep["channels"].append("incoming cross-session message: " + p["text"][:160])
                elif p.get("type") in ("text", "thinking") and e.get("type") == "assistant":
                    t = p.get("text") or p.get("thinking") or ""
                    for m in SCENE_WORDS.finditer(t):
                        rep["scene_words"].append(t[max(0, m.start() - 80):m.end() + 80].replace("\n", " "))
            if isinstance(e.get("message", {}).get("content"), str) and e.get("type") == "user" \
                    and "cross-session-message" in e["message"]["content"]:
                rep["channels"].append("incoming cross-session message: " + e["message"]["content"][:160])
    # Results too large for the transcript are persisted whole next to it; the transcript holds a preview.
    for tr in transcripts(capture_dir):
        for f in sorted((tr.parent / tr.stem / "tool-results").glob("*")):
            h = find_leaks(f.read_text(errors="replace"), readings, signals, True)
            for k in ("values", "keys", "colour"):
                rep[k] += [f"{x} <- tool-results/{f.name}" for x in h[k]]
    log = capture_dir / ".views_log.jsonl"
    for line in (log.read_text().splitlines() if log.exists() else []):
        v = json.loads(line)
        if "visual" in signals and v["kind"] in ("frame", "sheet"):
            rep["frames"].append(f"served {v}")
        if {"visual", "illumination"} & signals and v["kind"] == "render" and v["transform"] != "uncoloured":
            rep["frames"].append(f"served coloured render {v}")
        if "illumination" in signals and v["kind"] in ("frame", "sheet") and "normalised" not in v["transform"]:
            rep["frames"].append(f"served un-normalised {v}")
    for k in ("values", "keys", "colour", "frames", "channels", "refused", "denied"):
        rep[k] = sorted(set(rep[k]))
    # Nothing to read is not a clean session: a moved directory or a wrong transcript path would pass.
    rep["transcripts"] = [t.name for t in transcripts(capture_dir)]
    rep["pass"] = bool(rep["transcripts"]) and rep["tool_calls"] > 0 and not (
        rep["values"] or rep["keys"] or rep["colour"] or rep["frames"] or rep["channels"])
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--signals")
    ap.add_argument("--out")
    a = ap.parse_args()
    sig = withhold.parse(a.signals) if a.signals else None
    reps = [audit(Path(d).resolve(), sig) for d in a.dirs]
    for r in reps:
        print(f"{'PASS' if r['pass'] else 'FAIL'}{'' if r['transcripts'] else ' (no transcript)'} {r['capture_dir']} signals={r['signals']} calls={r['tool_calls']} "
              f"values={len(r['values'])} keys={len(r['keys'])} colour={len(r['colour'])} frames={len(r['frames'])} channels={len(r['channels'])} "
              f"refused={len(r['refused'])} denied={len(r['denied'])} scene_words={len(r['scene_words'])}")
    if a.out:
        Path(a.out).write_text(json.dumps(reps, indent=1))
    return 0 if all(r["pass"] for r in reps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
