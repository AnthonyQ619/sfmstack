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
GOALS = {"sparse": "a refined sparse model", "dense": "a dense reconstruction"}
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
    return {"permissions": {
        "defaultMode": "dontAsk",
        "allow": ["Bash(sfmx:*)", "Bash(sfmx *)",
                  f"Read({here}/**)", f"Write({here}/**)", f"Edit({here}/**)",
                  f"Read(//{str(procedure).lstrip('/')})"],
        "deny": ["WebFetch", "WebSearch", "Agent", "Task"],
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


def drive(capture: str, gpu: int, batch: str | None, prompt: str | None = None,
          timeout: float = 6 * 3600, scope: str = "sparse", control: bool = False) -> dict:
    capture_dir = EXP / capture
    scratch = capture_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    env = environment(capture, gpu, scratch, batch, scope, control)
    procedure = PROCEDURES[scope]
    if prompt is None:
        prompt = BRIEF.format(procedure=procedure, capture=capture, goal=GOALS[scope],
                              **paths_for(capture, batch, control))
    log = {"capture": capture, "gpu": gpu, "scope": scope, "control": control,
           "started": time.time(), "attempts": []}
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
        log["attempts"].append({"exit": proc.returncode, "stderr": proc.stderr[-2000:],
                                "session_id": out.get("session_id"),
                                "result": str(out.get("result", ""))[-4000:]})
        (capture_dir / "agent_log.json").write_text(json.dumps(log, indent=1))
        if (capture_dir / "agent_report.json").exists() or prompt == SMOKE:
            break
        resume = out.get("session_id")
        if not resume:
            break
    log["finished"] = time.time()
    log["report_written"] = (capture_dir / "agent_report.json").exists()
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
    a = ap.parse_args()
    global EXP
    if a.exp:
        EXP = Path(a.exp).expanduser().resolve()
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
