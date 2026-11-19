"""Scene-information an experiment withholds from the agent (Phase 6 Wave 3; revised for P11).

Unset, nothing is withheld, and that is the only way an ordinary run executes. An experiment sets
`SFM_WITHHOLD` (through `launch.py --withhold`) to a comma-separated subset of:

  visual        what the frames look like. `SceneDescription` is refused; `sfmx image` serves no
                frame (scene, contact sheet, dense workspace) and replaces every coloured cloud
                render with an uncoloured one (harness/views.py); point colours (`rgb`) are
                removed from every answer.
  illumination  how lighting changes across the frames. `SceneTriage`'s photometric group as
                the module stores it -- illumination, colour, exposure and combined change, the
                per-pair series behind them, the shadow and highlight clipping -- and the
                `illumination_unstable` diagnostic; the triage note is rebuilt sentence by
                sentence without them. Frames the agent may still see are contrast-normalised
                and cloud renders are uncoloured (harness/views.py); point colours are removed.
  motion        how the camera moves. `SceneMotion` is refused; triage's `ordered` reading,
                `capture_interval_s`, the `unordered_capture` diagnostic and the note's
                "Ordered capture." are removed. Frames the agent may still see are served under
                opaque names in shuffled order, so pixels cannot be placed in the sequence
                (harness/views.py).

`motion_illumination` (Wave 3's single switch) is accepted as both of its halves, so Wave 3's
records still parse.

Only scene analysis changes. The pipeline's own outputs -- poses, parallax, registration, and
the per-image arrays every module indexes in scene order -- are not withheld: they are what the
agent builds, and frame order on disk is input the modules consume.

A withheld module is refused by name, in words that name no experiment. Every answer `sfmx`
gives the agent -- printed, written to scratch, the brief and the chain -- passes through
`scrub`.
"""
from __future__ import annotations

import re

import yaml

KNOWN = ("illumination", "motion", "visual")
ALIASES = {"motion_illumination": {"motion", "illumination"}}
MODULES = {"visual": {"SceneDescription"}, "motion": {"SceneMotion"}, "illumination": set()}

PHOTOMETRIC_KEYS = {"illumination_change", "color_shift", "exposure_shift", "combined_change",
                    "pair_combined", "shadow_clipped", "highlight_clipped",
                    "shadow_clipped_fraction", "highlight_clipped_fraction", "photometric"}
PHOTOMETRIC_CODES = {"illumination_unstable"}
MOTION_KEYS = {"ordered", "capture_interval_s"}
MOTION_CODES = {"unordered_capture"}
COLOUR_KEYS = {"rgb", "colors", "colours"}

# SceneTriage's note, one sentence per reading group. Split on a full stop followed by space and a
# capital, which a decimal point never is ("0.017 (illumination" has no space after the point).
_SENTENCE = re.compile(r"(?<=\.)\s+(?=[A-Z])")
PHOTO_SENTENCE = re.compile(r"^(Photometric|Clipping):")
MOTION_SENTENCE = re.compile(r"^(Ordered|UNORDERED) capture\.?$")


def parse(value: str | None) -> set[str]:
    signals: set[str] = set()
    for s in (s.strip() for s in (value or "").split(",")):
        if not s:
            continue
        if s in ALIASES:
            signals |= ALIASES[s]
        elif s in KNOWN:
            signals.add(s)
        else:
            raise SystemExit(f"SFM_WITHHOLD: unknown {s!r}; known {list(KNOWN)} "
                             f"(and {sorted(ALIASES)})")
    return signals


def _expand(signals) -> set[str]:
    out: set[str] = set()
    for s in signals or ():
        out |= ALIASES.get(s, {s})
    return out


def modules(signals: set[str]) -> set[str]:
    signals = _expand(signals)
    return set().union(*(MODULES[s] for s in signals)) if signals else set()


def refusal(module: str, signals: set[str]) -> str | None:
    if module in modules(signals):
        return f"{module} is not available on this run."
    return None


def rebuild_note(text: str, signals: set[str]) -> str:
    """A triage-style note without the sentences that carry a withheld reading."""
    signals = _expand(signals)
    photo, motion = "illumination" in signals, "motion" in signals
    if not (photo and ("Photometric:" in text or "Clipping:" in text)) and not (
            motion and re.search(r"(Ordered|UNORDERED) capture", text)):
        return text
    kept = []
    for s in _SENTENCE.split(text):
        st = s.strip()
        if photo and PHOTO_SENTENCE.match(st):
            continue
        if motion and MOTION_SENTENCE.match(st):
            continue
        kept.append(s)
    out = " ".join(kept)
    return out + ("\n" if text.endswith("\n") and not out.endswith("\n") else "")


def scrub(obj, signals: set[str]):
    """The same structure with every withheld signal removed."""
    signals = _expand(signals)
    if not signals:
        return obj
    gone = modules(signals)
    photo, motion = "illumination" in signals, "motion" in signals
    colour = bool({"visual", "illumination"} & signals)
    drop_keys = (PHOTOMETRIC_KEYS if photo else set()) | (MOTION_KEYS if motion else set()) \
        | (COLOUR_KEYS if colour else set())
    drop_codes = (PHOTOMETRIC_CODES if photo else set()) | (MOTION_CODES if motion else set())
    drop_strings = gone | (drop_keys if drop_keys else set()) | drop_codes

    def walk(x):
        if isinstance(x, dict):
            if x.get("code") in drop_codes:
                return None
            # Any record of a withheld module: its brief entry, its registry row, a chain step.
            if x.get("module") in gone or x.get("name") in gone:
                return None
            out = {}
            for k, v in x.items():
                if k in drop_keys:
                    continue
                w = walk(v)
                if w is not None or v is None:
                    out[k] = w
            return out
        if isinstance(x, list):
            kept = [walk(v) for v in x]
            return [w for v, w in zip(x, kept) if not (w is None and v is not None)
                    and not (isinstance(v, str) and v in drop_strings)]
        if isinstance(x, str):
            if x.startswith("---") and "\nmetrics:" in x:
                return manifest(x)
            return rebuild_note(x, signals)
        return x

    def manifest(text):
        """An artifact manifest as `sfmx artifact` returns it: YAML front matter, then notes."""
        _, front, body = text.split("---", 2)
        return "---\n" + yaml.safe_dump(walk(yaml.safe_load(front)), sort_keys=False) + "---" + walk(body)

    return walk(obj)


def series_refusal(group: str, signals: set[str]) -> str | None:
    """`sfmx series <id> <group>`: a whole stored group that is a withheld reading."""
    signals = _expand(signals)
    if "illumination" in signals and group == "photometric":
        return "That group is not available on this run."
    return None
