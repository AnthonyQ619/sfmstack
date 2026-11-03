"""Scene-analysis signals an experiment withholds from the agent (Phase 6 Wave 3).

Unset, nothing is withheld, and that is the only way an ordinary run executes. An experiment sets
`SFM_WITHHOLD` (through `launch.py --withhold`) to a comma-separated list of:

  visual               `SceneDescription` (the contact sheet and the frames the describer is
                       asked to look at), and `sfmx image` on the scene artifact itself. Images of
                       every later artifact stay available.
  motion_illumination  `SceneMotion`, and `SceneTriage`'s photometric group as the module stores
                       it: illumination, colour, exposure and combined change, the per-pair
                       series behind them, and the shadow and highlight clipping, with the
                       `illumination_unstable` diagnostic. Triage's texture, sharpness and
                       ordering readings stay.

Only the scene-analysis step changes. A withheld module is refused by name, and every answer
`sfmx` gives the agent -- printed, written to scratch, the brief and the chain -- is filtered.
"""
from __future__ import annotations

import re

import yaml

SIGNALS = {"visual": {"SceneDescription"}, "motion_illumination": {"SceneMotion"}}
PHOTOMETRIC_KEYS = {"illumination_change", "color_shift", "exposure_shift", "combined_change",
                    "pair_combined", "shadow_clipped", "highlight_clipped",
                    "shadow_clipped_fraction", "highlight_clipped_fraction", "photometric"}
PHOTOMETRIC_CODES = {"illumination_unstable"}
# SceneTriage's notes repeat the group in prose: "Photometric: combined 0.105 (...)." and
# "Clipping: 33.54% highlight, 1.62% shadow in the median frame."
PHOTOMETRIC_PROSE = re.compile(r"\s*(Photometric|Clipping):[^.]*(\([^)]*\))?[^.]*\.")


def parse(value: str | None) -> set[str]:
    signals = {s.strip() for s in (value or "").split(",") if s.strip()}
    unknown = signals - set(SIGNALS)
    if unknown:
        raise SystemExit(f"SFM_WITHHOLD: unknown {sorted(unknown)}; known {sorted(SIGNALS)}")
    return signals


def modules(signals: set[str]) -> set[str]:
    return set().union(*(SIGNALS[s] for s in signals)) if signals else set()


def refusal(module: str, signals: set[str]) -> str | None:
    if module in modules(signals):
        return (f"{module} is withheld in this experiment: the scene-analysis signal it gives is "
                "not available on this run. Plan without it.")
    return None


def scrub(obj, signals: set[str]):
    """The same structure with every withheld signal removed."""
    if not signals:
        return obj
    gone = modules(signals)
    photo = "motion_illumination" in signals

    def walk(x):
        if isinstance(x, dict):
            if photo and x.get("code") in PHOTOMETRIC_CODES:
                return None
            if (x.get("module") in gone or x.get("name") in gone) and set(x) & {"artifact", "version", "kind", "summary", "consumes"}:
                return None
            out = {}
            for k, v in x.items():
                if photo and k in PHOTOMETRIC_KEYS:
                    continue
                w = walk(v)
                if w is not None or v is None:
                    out[k] = w
            return out
        if isinstance(x, list):
            kept = [walk(v) for v in x]
            return [w for v, w in zip(x, kept) if not (w is None and v is not None)
                    and not (isinstance(v, str) and (v in gone or (photo and v in PHOTOMETRIC_KEYS | PHOTOMETRIC_CODES)))]
        if isinstance(x, str) and photo:
            if x.startswith("---") and "\nmetrics:" in x:
                return manifest(x)
            return PHOTOMETRIC_PROSE.sub("", x)
        return x

    def manifest(text):
        """An artifact manifest as `sfmx artifact` returns it: YAML front matter, then notes."""
        _, front, body = text.split("---", 2)
        return "---\n" + yaml.safe_dump(walk(yaml.safe_load(front)), sort_keys=False) + "---" + walk(body)

    return walk(obj)
