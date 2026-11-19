#!/usr/bin/env python3
"""Launch agents as isolated headless Claude Code processes.

    launch.py --gpus 4,5,6,7 --parallel 8 DTU/scan1 ETH/courtyard ...
    launch.py --scope dense --exp ~/sfm_experiments/DTU_dense_exp/runs \
              --controls DTU/scan1,DTU/scan4 DTU/scan1 DTU/scan4 DTU/scan15 ...
    launch.py --smoke                         # isolation check, no reconstruction

**Every capture named in this file is a member of skills/evidence/CORPUS.txt.**
That is deliberate and it is the reason this harness lives in the repository: a
holdout capture named in an example, a smoke test or an error message is a holdout
that has been written into the context, and it stops being able to measure whether
the context generalises. The predecessor at ~/sfm_experiments/harness is frozen with
its own history and still names holdouts; do not copy examples back from it.

Why not subagents: a subagent inherits its parent session's auto-memory and runs
beside every other agent in one shared scratch space, and both leaked into the
first holdout batch. Each agent here is its own `claude -p` process:

  - its working directory is its capture's scratch directory, so its project
    memory is a fresh, empty one, and auto-memory is switched off anyway;
  - no user or project settings are loaded (only the capture's own local ones,
    which do not exist), so no permission rule or hook from this machine applies;
  - in `dontAsk` mode it may use exactly `sfmx` and file reads and writes inside
    its own capture directory, plus the procedure it is told to read -- anything
    else is refused rather than asked about, so "do not read the repository" is
    enforced instead of requested.

A process that exits without writing agent_report.json is resumed once with a
fixed message, the same for every agent, so no resume carries anything else.
"""
import argparse
import json
import os
import re
from datetime import datetime
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
# NOT HARNESS.parent any more. This harness lives in the repository, so the
# parent is the repo root; the experiment record it writes into is elsewhere and
# has to be named. --exp overrides it, as it always did.
EXP = Path(os.environ.get("SFM_EXP_ROOT") or Path.home() / "sfm_experiments")
# Set from --skills / --modules for an ablation batch; None means the repository's
# own trees, which is every ordinary run.
SKILLS: Path | None = None
MODULES: Path | None = None
# Set from --withhold for an experiment that removes scene-analysis signals
# (harness/withhold.py); None on every ordinary run.
WITHHOLD: str | None = None
# Set for a context-ablation arm (harness/bare.py, harness/mcmc.py, harness/ablation/); None on every ordinary run.
PROCEDURE: Path | None = None          # --procedure: the arm's procedure in place of PROCEDURES[scope]
EXTRA_READS: list[Path] = []           # --read: further files the agent may open (the arm's mechanics file)
BARE = False                           # --bare
SEALED = False                         # --sealed: P11 scene-information ablation (harness/views.py)
PROMPT_FILE: Path | None = None        # --prompt-file: a fixed prompt in place of BRIEF (leak tests)
MCMC: dict[str, str] = {}              # --mcmc-n / --mcmc-t / --mcmc-seed
GOALS = {"sparse": "a refined sparse model", "dense": "a dense reconstruction"}
# What a dense deliverable is judged on, as a task would state it. DenseFusion's tuning
# reads a task that names neither as accuracy-first, and every dense session then stopped
# at the delivery anchor; replayed, the families below scored best at the settings their
# objective leads to (skills/evidence/dense-fixes-2026-10.md). Families not listed were
# not measured and get no objective. A batch entry's own "objective" wins.
DENSE_OBJECTIVE = {"DTU": "accuracy", "ETH": "coverage", "TT": "coverage"}
OBJECTIVE_TEXT = {
    "accuracy": ("Deliverable: accuracy-first. Stray points off the surface cost as much "
                 "as holes in it."),
    "coverage": ("Deliverable: coverage-first. How much of the surface is reconstructed "
                 "counts as much as how accurately."),
}
PROCEDURES = {"sparse": HARNESS / "PROCEDURE.md", "dense": HARNESS / "PROCEDURE_dense.md"}
CLAUDE = os.environ.get("CLAUDE_BIN") or max(
    Path.home().glob(".vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
    key=lambda p: p.stat().st_mtime, default="claude")
RESUME = ("Keep going from where you stopped. Stay in the foreground: use `sfmx wait` "
          "for a step in flight, never a background command. Finish the pipeline and "
          "write ../agent_report.json before you reply.")

BRIEF = """You are driving a structure-from-motion pipeline for ONE capture, from raw
frames to {goal}, as a context experiment.

Read {procedure} first, in full, and follow it exactly.

Your capture: {capture}
  image_dir: {image_dir}
  calibration_path: {calibration_path}
{objective}
When finished, write ../agent_report.json in the schema at the end of the
procedure. Then reply with a 10-line summary: final pipeline, the refined artifact
id, key metrics, runs spent, backtracks, the rule that chose the final model, and
the single most important context gap you hit."""

SMOKE = """This is an isolation check; do exactly these four things and nothing else.
Call `sfmx` as a bare command: no pipe, no redirect, no second statement. Only a
command beginning with `sfmx` is permitted, so `sfmx skills | head` is refused where
`sfmx skills` is allowed. Step 1 is testing exactly that, so do not work around it.
1. Run `sfmx skills` and report its first line.
2. Use your Read tool on /home/anthonyq/projects/sfmstack/README.md and report
   whether it was allowed.
3. Run `cat /home/anthonyq/projects/sfmstack/README.md` and report whether it was allowed.
4. Say whether your context contains any auto-memory notes or CLAUDE.md content;
   quote one line if it does.
Reply with four numbered lines."""


def settings(capture_dir: Path, procedure: Path) -> dict:
    here = f"//{str(capture_dir).lstrip('/')}"
    # Bare arms read only their scratch files and the images `sfmx image` points at: the store's manifests in the
    # capture directory carry the advice bare mode withholds (harness/bare.py).
    reads = ([f"Read({here}/scratch/**)", *[f"Read({here}/**/*.{x})" for x in ("png", "jpg", "jpeg")],
              f"Edit({here}/scratch/**)", f"Edit({here}/agent_report.json)"] if BARE
             else [f"Read({here}/**)", f"Edit({here}/**)"])
    writes = [f"Write({here}/**)"]
    deny = ["WebFetch", "WebSearch", "Agent", "Task"]
    if SEALED:
        # Scratch (where `sfmx` leaves a filtered copy of every answer and every image it serves),
        # the brief's Markdown, and the report. Nothing else in the capture directory: the store's
        # manifests and frames, the chain, the run's own records and the alias key are unfiltered.
        reads = [f"Read({here}/scratch/**)", f"Read({here}/brief_*.md)", f"Read({here}/brief.json)",
                 f"Read({here}/agent_report.json)", f"Edit({here}/scratch/**)",
                 f"Edit({here}/agent_report.json)"]
        writes = [f"Write({here}/scratch/**)", f"Write({here}/agent_report.json)"]
        deny += [f"Read({here}/store/**)", f"Read({here}/.views_key.json)", f"Read({here}/.views_log.jsonl)", f"Read({here}/chain.json)",
                 f"Read({here}/context_roots.json)", f"Read({here}/context_reads.jsonl)",
                 f"Read({here}/agent_log.json)", f"Read({here}/running.json)",
                 "Read(//home/anthonyq/datasets/**)", "Read(//home/anthonyq/projects/**)",
                 "Read(//home/anthonyq/sfm_experiments/**/store/**)", "Read(//bigdata/**)",
                 "Read(//home/anthonyq/.claude/projects/**/*.jsonl)", "Glob", "Grep",
                 *[f"Bash({c}:*)" for c in ("cat", "head", "tail", "less", "more", "grep", "rg",
                                             "ls", "find", "sed", "awk", "python", "python3", "strings",
                                             "xxd", "od", "file", "stat", "du", "tree", "wc", "env",
                                             "printenv", "echo", "cd", "cp", "mv", "tar")]]
    return {"permissions": {
        "defaultMode": "dontAsk",
        "allow": ["Bash(sfmx:*)", "Bash(sfmx *)",
                  *reads, *writes,
                  f"Read(//{str(procedure).lstrip('/')})",
                  *[f"Read(//{str(p).lstrip('/')})" for p in EXTRA_READS]],
        "deny": deny,
    }}


def command(prompt: str, capture_dir: Path, procedure: Path, resume: str | None = None) -> list[str]:
    cmd = [str(CLAUDE), "-p", prompt, "--output-format", "json",
           "--permission-mode", "dontAsk", "--setting-sources", "local",
           "--settings", json.dumps(settings(capture_dir, procedure)), "--model", "opus"]
    if resume:
        cmd += ["--resume", resume]
    return cmd


def environment(capture: str, gpu: int, scratch: Path, batch: str | None,
                scope: str = "sparse", control: bool = False) -> dict:
    env = dict(os.environ)
    env.pop("SFM_CONTROL", None)
    env.update({"SFM_CAPTURE": capture, "SFM_GPU": str(gpu), "TMPDIR": str(scratch),
                "SFM_EXP": str(EXP), "SFM_SCOPE": scope,
                "PATH": f"{HARNESS / 'bin'}:{env.get('PATH', '')}",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
    if batch:
        env["SFM_BATCH"] = batch
    if control:
        env["SFM_CONTROL"] = "1"
    # Context overrides. Absent, sfmx reads the repository's skills/ and modules/;
    # an inherited value is dropped so a batch never reads a view by accident.
    for var, value in (("SFM_SKILLS", SKILLS), ("SFM_MODULES", MODULES), ("SFM_WITHHOLD", WITHHOLD),
                       ("SFM_BARE", "1" if BARE else None), ("SFM_SEALED", "1" if SEALED else None),
                       ("SFM_MCMC_N", MCMC.get("n")),
                       ("SFM_MCMC_T", MCMC.get("t")), ("SFM_MCMC_SEED", MCMC.get("seed"))):
        env.pop(var, None)
        if value:
            env[var] = str(value)
    return env


def paths_for(capture: str, batch: str | None, control: bool = False) -> dict:
    (EXP / capture / "scratch").mkdir(parents=True, exist_ok=True)
    out = subprocess.run([str(HARNESS / "bin" / "sfmx"), "running"], env=environment(
        capture, 0, EXP / capture / "scratch", batch, control=control),
        capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(out.stderr.strip() or out.stdout.strip())
    sys.path.insert(0, str(HARNESS))
    if batch:
        for e in json.loads(Path(batch).read_text()):
            if e["capture"] == capture:
                return e
    fam, _, name = capture.partition("/")
    if fam == "DTU":
        return {"image_dir": f"/home/anthonyq/datasets/DTU/{name}",
                "calibration_path": "/home/anthonyq/datasets/DTU/calibration_DTU_new.npz"}
    base = f"/home/anthonyq/datasets/ETH/{name}"
    return {"image_dir": f"{base}/images/dslr_images_undistorted",
            "calibration_path": f"{base}/dslr_calibration_undistorted/calibration_ETH_new.npz"}


def transcript_dir(scratch: Path, projects: Path | None = None) -> Path:
    """Where Claude Code keeps a session's transcript: the working directory, every
    character that is not a letter or digit turned into a hyphen."""
    root = projects or Path.home() / ".claude" / "projects"
    return root / re.sub(r"[^A-Za-z0-9]", "-", str(scratch))


def brief_topic(name: str) -> str | None:
    """`brief_guide.md` is the planning guide, `brief_<stage>.md` that stage's file."""
    m = re.fullmatch(r"brief_(\w+)\.md", name)
    if not m:
        return None
    return "plan/scene_to_pipeline" if m.group(1) == "guide" else f"plan/{m.group(1)}"


def record_brief_reads(capture_dir: Path, session_ids: list, projects: Path | None = None) -> int:
    """Append the agent's file-reader reads of the brief's Markdown to context_reads.jsonl.

    `sfmx brief` writes the planning guide and each stage file beside brief.json so the
    reader can page them, and agents read them there -- the guide in nine sessions of ten,
    the pose stage in seven -- through the file reader, which no `sfmx` call sees. The
    context log, which every reading analysis counts from, recorded `plan/pose` in one
    session of those ten. The transcript has each read; this copies them across, one
    entry per page read, under the topic the file stands for.
    """
    tdir = transcript_dir(capture_dir / "scratch", projects)
    rows = []
    for sid in [s for s in session_ids if s]:
        path = tdir / f"{sid}.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            for part in (msg.get("message") or {}).get("content") or []:
                if not (isinstance(part, dict) and part.get("type") == "tool_use"
                        and part.get("name") == "Read"):
                    continue
                target = Path(str((part.get("input") or {}).get("file_path", "")))
                topic = brief_topic(target.name)
                if topic is None or target.parent != capture_dir:
                    continue
                stamp = msg.get("timestamp", "")
                try:
                    t = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    t = None
                rows.append({"t": t, "kind": "file_read", "topic": topic,
                             "path": str(target), "via": "brief file",
                             "offset": part["input"].get("offset"),
                             "limit": part["input"].get("limit")})
    if rows:
        with open(capture_dir / "context_reads.jsonl", "a") as fh:
            for r in sorted(rows, key=lambda r: r["t"] or 0):
                fh.write(json.dumps(r) + "\n")
    return len(rows)


def objective_line(capture: str, scope: str, entry: dict | None = None) -> str:
    """The brief's deliverable line, or nothing: dense only, and only where measured."""
    if scope != "dense":
        return ""
    obj = (entry or {}).get("objective") or DENSE_OBJECTIVE.get(capture.split("/")[0])
    return "\n" + OBJECTIVE_TEXT[obj] + "\n" if obj in OBJECTIVE_TEXT else ""


# What `claude -p --output-format json` reports about the attempt's cost. Kept whole, as the
# CLI gives it: tokens by kind, cost in dollars overall and per model, turns, wall and API time.
SPEND = ("total_cost_usd", "usage", "modelUsage", "num_turns", "duration_ms", "duration_api_ms",
         "is_error", "subtype", "stop_reason")


def attempt_record(returncode: int, stderr: str, out: dict) -> dict:
    """One attempt's line in agent_log.json. A field the CLI did not report is left out, never
    filled in, so a missing cost reads as missing rather than as zero."""
    return {"exit": returncode, "stderr": stderr[-2000:], "session_id": out.get("session_id"),
            "result": str(out.get("result", ""))[-4000:],
            **{k: out[k] for k in SPEND if k in out}}


def drive(capture: str, gpu: int, batch: str | None, prompt: str | None = None,
          timeout: float = 6 * 3600, scope: str = "sparse", control: bool = False) -> dict:
    capture_dir = EXP / capture
    scratch = capture_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    env = environment(capture, gpu, scratch, batch, scope, control)
    procedure = PROCEDURE or PROCEDURES[scope]
    if prompt is None and PROMPT_FILE:
        paths = paths_for(capture, batch, control)
        prompt = PROMPT_FILE.read_text().format(procedure=procedure, capture=capture, goal=GOALS[scope],
                                                image_dir=paths["image_dir"],
                                                calibration_path=paths["calibration_path"])
    if prompt is None:
        # Name the brief's fields rather than splatting: a --batch entry carries its own
        # `capture` key alongside the two paths, and `capture` is already passed here by
        # name, so splatting handed str.format() two of them and the batch path could not
        # start an agent at all. It went unnoticed because the only earlier use of --batch
        # was the smoke test, which supplies its own prompt and never reaches this line.
        paths = paths_for(capture, batch, control)
        prompt = BRIEF.format(procedure=procedure, capture=capture, goal=GOALS[scope],
                              image_dir=paths["image_dir"],
                              calibration_path=paths["calibration_path"],
                              objective=objective_line(capture, scope, paths))
    log = {"capture": capture, "gpu": gpu, "scope": scope, "control": control,
           "started": time.time(), "attempts": [],
           **({"procedure": str(procedure), "bare": BARE, "mcmc": MCMC} if PROCEDURE else {})}
    resume = None
    for attempt in range(2):
        proc = subprocess.run(command(prompt if resume is None else RESUME, capture_dir, procedure, resume),
                              cwd=scratch, env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              timeout=timeout)
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            out = {"raw": proc.stdout[-4000:]}
        log["attempts"].append(attempt_record(proc.returncode, proc.stderr, out))
        (capture_dir / "agent_log.json").write_text(json.dumps(log, indent=1))
        if (capture_dir / "agent_report.json").exists() or prompt == SMOKE:
            break
        resume = out.get("session_id")
        if not resume:
            break
    log["finished"] = time.time()
    log["report_written"] = (capture_dir / "agent_report.json").exists()
    if prompt != SMOKE:
        log["brief_reads"] = record_brief_reads(
            capture_dir, [a.get("session_id") for a in log["attempts"]])
    (capture_dir / "agent_log.json").write_text(json.dumps(log, indent=1))
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="*")
    ap.add_argument("--gpus", default="4,5,6,7")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--batch", help="JSON list of {capture, image_dir, calibration_path}")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--scope", choices=sorted(GOALS), default="sparse")
    ap.add_argument("--exp", help="root for capture directories (default: the experiments dir)")
    ap.add_argument("--controls", default="",
                    help="comma-separated captures that are in the planning corpus and run as named controls")
    ap.add_argument("--timeout-h", type=float, default=6.0, help="per attempt")
    ap.add_argument("--skills", help="a generated context view's skills/ (ablation batches "
                    "only; default: the repository's)")
    ap.add_argument("--modules", help="a modules/ tree to describe modules from (ablation "
                    "batches only; default: the repository's)")
    ap.add_argument("--withhold", help="comma-separated scene-analysis signals to withhold "
                    "(visual, illumination, motion; experiments only; default: none)")
    ap.add_argument("--sealed", action="store_true", help="P11 sealing: no store reads, images as "
                    "scratch copies (harness/views.py); experiments only")
    ap.add_argument("--prompt-file", help="a fixed prompt in place of the brief (leak tests only)")
    ap.add_argument("--procedure", help="an ablation arm's procedure in place of the scope's (experiments only)")
    ap.add_argument("--read", action="append", default=[], help="a further file the agent may read (repeatable)")
    ap.add_argument("--bare", action="store_true", help="bare service mode (harness/bare.py; experiments only)")
    ap.add_argument("--mcmc-n", help="enable `sfmx mcmc` with this many iterations (arm A3 only)")
    ap.add_argument("--mcmc-t", default="5", help="MCMC temperature, in health-percentile points")
    ap.add_argument("--mcmc-seed", default="0", help="MCMC base seed")
    a = ap.parse_args()
    global EXP, SKILLS, MODULES, WITHHOLD, PROCEDURE, EXTRA_READS, BARE, MCMC, SEALED, PROMPT_FILE
    SEALED = a.sealed
    if a.prompt_file:
        PROMPT_FILE = Path(a.prompt_file).expanduser().resolve()
    if a.procedure:
        PROCEDURE = Path(a.procedure).expanduser().resolve()
        if not PROCEDURE.is_file():
            sys.exit(f"--procedure {PROCEDURE}: no such file")
    EXTRA_READS = [Path(r).expanduser().resolve() for r in a.read]
    BARE = a.bare
    if a.mcmc_n:
        MCMC = {"n": a.mcmc_n, "t": a.mcmc_t, "seed": a.mcmc_seed}
    if a.exp:
        EXP = Path(a.exp).expanduser().resolve()
    if a.skills:
        SKILLS = Path(a.skills).expanduser().resolve()
        if not (SKILLS / "evidence" / "CORPUS.txt").is_file():
            sys.exit(f"--skills {SKILLS}: no evidence/CORPUS.txt there, so not a context tree")
    if a.modules:
        MODULES = Path(a.modules).expanduser().resolve()
    if a.withhold:
        sys.path.insert(0, str(HARNESS))
        from withhold import parse as parse_withhold
        WITHHOLD = ",".join(sorted(parse_withhold(a.withhold)))
    controls = {c for c in a.controls.split(",") if c}
    gpus = [int(g) for g in a.gpus.split(",")]
    if a.smoke:
        # Under the experiment root, not HARNESS: this harness lives in the
        # repository and a run-time file written beside it lands in the checkout.
        batch = EXP / "SMOKE" / "isolation" / "smoke_batch.json"
        batch.parent.mkdir(parents=True, exist_ok=True)
        batch.write_text(json.dumps([{"capture": "SMOKE/isolation",
                                      "image_dir": "/home/anthonyq/datasets/DTU/scan1",
                                      "calibration_path": "/home/anthonyq/datasets/DTU/calibration_DTU_new.npz"}]))
        # control=True because the smoke batch points at a corpus capture's frames;
        # without it the corpus guard refuses every call and the check cannot reach
        # the context it is meant to verify is reachable.
        log = drive("SMOKE/isolation", gpus[0], str(batch), prompt=SMOKE, timeout=900,
                    control=True)
        print(log["attempts"][-1]["result"])
        print("stderr:", log["attempts"][-1]["stderr"][-600:])
        return 0
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = [pool.submit(drive, c, gpus[i % len(gpus)], a.batch, None, a.timeout_h * 3600,
                            a.scope, c in controls)
                for i, c in enumerate(a.captures)]
        for f in futs:
            log = f.result()
            print(f"{log['capture']}: report_written={log['report_written']} "
                  f"attempts={len(log['attempts'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
