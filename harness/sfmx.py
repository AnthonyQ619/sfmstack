"""The MCP surface for driving ONE capture from raw frames to a refined sparse
model, or on to a dense one when SFM_SCOPE=dense. Every agent sees exactly this
and nothing else.

The capture comes from the environment (SFM_CAPTURE, e.g. DTU/scan1), so no
command takes a scene argument. Its paths come from SFM_BATCH (a JSON list of
{capture, image_dir, calibration_path}) when set, else from the dataset layout.

  skills   [topic]                  sfm_workflow_skill; no topic prints the index
  brief                             sfm_plan_brief; also saved to <capture>/brief.json
  describe <module>                 sfm_describe_module (params, defaults, metrics, bands)
  skill    <module> <topic>         sfm_module_skill: SKILL | tuning | limitations | artifact | sources
  list     [k=v ...]                sfm_list_modules (consumes=/produces=/kind=)
  find     <produces> [k=v ...]     sfm_find_alternatives
  run      <module> <params-json> [slot=artifact_id ...]
  run      <module> --params-file <path> [slot=artifact_id ...]
                                    sfm_run; each consumed slot is wired from the chain
                                    unless overridden. Blocks until the step finishes.
                                    One run at a time per capture: a second waits.
  wait     [seconds]                block until this capture's in-flight run finishes
                                    (default 540 s), then print the last recorded step
  running                           what this capture is running right now, if anything
  state                             the chain so far: current artifact per slot, and history
  replay   <artifact_id> [overrides-json]
                                    sfm_replay: re-run the step that produced the artifact
                                    with these parameter overrides, plus the steps built on
                                    it; the new outputs become current. Blocks like `run`.
  pin      <slot> <artifact_id>     make an EARLIER artifact current again (backtracking)
  artifact <id>                     sfm_artifact
  image    <id> [name]              sfm_artifact_image: a PATH to open with your image reader
  compare  <id> <id> [...]          sfm_compare
  summary                           sfm_run_summary for this capture's run
  series   <id> <group>             one stored group of an artifact, as JSON
  cloud    <id> [n]                 extent and a random sample of a model's points

Nothing is ever deleted, so every attempt stays comparable.
"""
import fcntl
from contextlib import nullcontext
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

REPO = Path("/home/anthonyq/projects/sfmstack")
sys.path.insert(0, str(REPO / "packages" / "sfmorch" / "src"))
sys.path.insert(0, str(REPO / "packages" / "sfmkit" / "src"))
from sfmorch.mcp_server import build_service  # noqa: E402
from gpu_gate import gpu_gate  # noqa: E402

DATASETS = Path("/home/anthonyq/datasets")
# Where capture directories live; a batch with its own root sets SFM_EXP.
EXP = Path(os.environ.get("SFM_EXP") or "/home/anthonyq/sfm_experiments")
CORPUS = REPO / "skills" / "evidence" / "CORPUS.txt"
# The deliverable is the refined sparse model unless SFM_SCOPE=dense, in which case
# the dense model built on it is.
SCOPE = os.environ.get("SFM_SCOPE", "sparse")
OUT_OF_SCOPE = set() if SCOPE == "dense" else {"dense_model/v1"}


def capture_paths(capture: str) -> dict:
    batch = os.environ.get("SFM_BATCH")
    if batch:
        for entry in json.loads(Path(batch).read_text()):
            if entry["capture"] == capture:
                return entry
    fam, _, name = capture.partition("/")
    if fam == "DTU":
        return {"image_dir": str(DATASETS / "DTU" / name),
                "calibration_path": str(DATASETS / "DTU" / "calibration_DTU_new.npz")}
    if fam == "ETH":
        base = DATASETS / "ETH" / name
        return {"image_dir": str(base / "images" / "dslr_images_undistorted"),
                "calibration_path": str(base / "dslr_calibration_undistorted" / "calibration_ETH_new.npz")}
    sys.exit(f"no paths for {capture!r}: list it in an SFM_BATCH file")


def corpus_entry(image_dir: str):
    """The CORPUS.txt entry this capture is, matched on whole path segments."""
    source = image_dir.rstrip("/") + "/"
    entries = [ln.strip() for ln in CORPUS.read_text().splitlines()
               if ln.strip() and not ln.startswith("#")]
    return next((e for e in entries if e.rstrip("/") + "/" in source), None)


CAPTURE = os.environ.get("SFM_CAPTURE", "")
if not CAPTURE or "/" not in CAPTURE:
    sys.exit("set SFM_CAPTURE, e.g. DTU/scan1")
PATHS = capture_paths(CAPTURE)
if not Path(PATHS["image_dir"]).is_dir():
    sys.exit(f"{CAPTURE}: no image directory at {PATHS['image_dir']}")
_hit = corpus_entry(PATHS["image_dir"])
if _hit and os.environ.get("SFM_CONTROL") != "1":
    sys.exit(f"{CAPTURE} is in the planning corpus ({_hit} in evidence/CORPUS.txt), so it "
             "cannot be a holdout capture. Set SFM_CONTROL=1 to run it as a named control.")

HOME = EXP / CAPTURE
SCRATCH = HOME / "scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)
STORE = HOME / "store"
CHAIN = HOME / "chain.json"
CTXLOG = HOME / "context_reads.jsonl"
LOCK = HOME / "run.lock"
RUNNING = HOME / "running.json"
RUN_ID = CAPTURE.replace("/", "_")
GPU = int(os.environ.get("SFM_GPU", "4"))


def emit(obj):
    """Print, and keep a copy in this capture's scratch directory, so a long
    answer can be re-read with the file reader instead of piped through tools."""
    text = json.dumps(obj, indent=1, default=str)
    print(text)
    (SCRATCH / f"last_{sys.argv[1] if len(sys.argv) > 1 else 'out'}.json").write_text(text)


def show(text):
    print(text)
    (SCRATCH / f"last_{sys.argv[1] if len(sys.argv) > 1 else 'out'}.md").write_text(text)


def log_ctx(kind, **kw):
    """Every context read, appended: which files get opened is part of what the
    run measures."""
    with CTXLOG.open("a") as fh:
        fh.write(json.dumps({"t": time.time(), "kind": kind, **kw}) + "\n")


def service(docker=False):
    return build_service(modules_dir=REPO / "modules", store_root=STORE,
                         skills_dir=REPO / "skills", use_docker=docker,
                         mounts=[str(DATASETS)], gpus=[GPU])


@contextmanager
def capture_lock(timeout: float | None = None):
    """One writer per capture. A `run` holds it for the whole step, so two calls
    from one agent queue instead of overwriting each other's records; `pin` and
    `wait` take it briefly. Yields False only when `timeout` ran out."""
    LOCK.touch(exist_ok=True)
    with LOCK.open("r+") as fh:
        start = time.time()
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if timeout is not None and time.time() - start > timeout:
                    yield False
                    return
                time.sleep(2)
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def load_chain():
    if CHAIN.exists():
        return json.loads(CHAIN.read_text())
    return {"capture": CAPTURE, "run_id": RUN_ID, "current": {}, "history": []}


def save_chain(ch):
    tmp = CHAIN.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ch, indent=1))
    os.replace(tmp, CHAIN)


def kv(items):
    return dict(a.split("=", 1) for a in items)


def last_step():
    runs = [h for h in load_chain()["history"] if h.get("action") in ("run", "replay")]
    return runs[-1] if runs else None


cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("help", [])

if cmd == "skills":
    topic = args[0] if args else "SKILLS"
    log_ctx("workflow_skill", topic=topic)
    show(service().workflow_skill(topic)["text"])

elif cmd == "brief":
    ch = load_chain()
    if "scene" not in ch["current"]:
        sys.exit("no scene artifact yet. Run SceneLoader first: its image_dir is "
                 f"{PATHS['image_dir']} and its calibration_path is {PATHS['calibration_path']}.")
    log_ctx("plan_brief")
    brief = service().plan_brief(ch["current"]["scene"])
    (HOME / "brief.json").write_text(json.dumps(brief, indent=1, default=str))
    emit(brief)

elif cmd == "describe":
    log_ctx("describe_module", module=args[0])
    emit(service().describe_module(args[0]))

elif cmd == "skill":
    log_ctx("module_skill", module=args[0], topic=args[1])
    show(service().module_skill(args[0], args[1])["text"])

elif cmd == "list":
    log_ctx("list_modules", **kv(args))
    emit(service().list_modules(**kv(args)))

elif cmd == "find":
    log_ctx("find_alternatives", produces=args[0], **kv(args[1:]))
    emit(service().find_alternatives(produces=args[0], **kv(args[1:])))

elif cmd == "state":
    emit(load_chain())

elif cmd == "pin":
    slot, aid = args
    with capture_lock():
        ch = load_chain()
        ch["current"][slot] = aid
        ch["history"].append({"t": time.time(), "action": "pin", "slot": slot, "artifact": aid})
        save_chain(ch)
    log_ctx("pin", slot=slot, artifact=aid)
    emit(ch["current"])

elif cmd == "run":
    module = args[0]
    if len(args) > 2 and args[1] == "--params-file":
        params, rest = json.loads(Path(args[2]).read_text()), args[3:]
    else:
        params = (json.loads(Path(args[1]).read_text()) if Path(args[1]).is_file()
                  else json.loads(args[1]))
        rest = args[2:]
    svc = service(docker=True)
    desc = svc.describe_module(module)
    produces = {v.get("type") if isinstance(v, dict) else v
                for v in (desc.get("produces") or {}).values()}
    if produces & OUT_OF_SCOPE:
        sys.exit(f"{module} produces {sorted(produces & OUT_OF_SCOPE)}; this run stops at "
                 "the refined sparse model.")
    consumes = desc.get("consumes") or {}
    overrides = kv(rest)
    bad = [s for s in overrides if s not in consumes]
    if bad:
        sys.exit(f"{module} does not consume {bad}; it takes {sorted(consumes)}")
    with capture_lock():
        ch = load_chain()  # read under the lock: nothing else writes it meanwhile
        inputs = {s: overrides.get(s, ch["current"].get(s)) for s in consumes}
        inputs = {s: a for s, a in inputs.items() if a}
        missing = [s for s in consumes if s not in inputs]
        if missing and module != "SceneLoader":
            sys.exit(f"{module} needs {missing}, which this capture's chain does not carry. "
                     f"It has {sorted(ch['current'])}. Produce them first, or pass slot=artifact_id.")
        RUNNING.write_text(json.dumps({"module": module, "params": params,
                                       "inputs": inputs, "started": time.time()}))
        t0 = time.time()
        # Dense steps get their GPU to themselves; see gpu_gate.py.
        gate = (gpu_gate(EXP, GPU, desc.get("kind") == "dense", f"{CAPTURE} {module}")
                if (desc.get("resources") or {}).get("gpu") else nullcontext())
        try:
            with gate:
                r = svc.run(module, run_id=RUN_ID, inputs=inputs, params=params, wait_s=21600)
        except Exception as e:
            r = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        finally:
            RUNNING.unlink(missing_ok=True)
        if "outputs" not in r:
            ch["history"].append({"t": t0, "action": "run", "module": module, "params": params,
                                  "inputs": inputs, "status": "FAILED",
                                  "error": str(r.get("error", ""))[:600]})
            save_chain(ch)
            emit(r)
            sys.exit(1)
        for slot, aid in r["outputs"].items():
            ch["current"][slot] = aid
        kept = (r.get("second_solve") or {}).get("kept")
        ch["history"].append({"t": t0, "action": "run", "module": module, "params": params,
                              "inputs": inputs, "status": "ok", "outputs": r["outputs"],
                              "cached": r.get("cached"), "seconds": round(time.time() - t0, 1),
                              "metrics": r.get("metrics"),
                              "diagnostics": [d.get("code") for d in r.get("diagnostics") or []],
                              "second_solve_kept": kept})
        save_chain(ch)
    emit(r)

elif cmd == "replay":
    if not args:
        sys.exit("usage: replay <artifact_id> [overrides-json]")
    source = args[0]
    overrides = {}
    if len(args) > 1:
        overrides = (json.loads(Path(args[1]).read_text()) if Path(args[1]).is_file()
                     else json.loads(args[1]))
    svc = service(docker=True)
    origin = svc.orch.open_run(RUN_ID).producer_of(source)
    if origin is None:
        sys.exit(f"{source} was not produced in this capture's run, so there is no step to "
                 "replay. `state` lists the artifacts this chain produced.")
    desc = svc.describe_module(origin.module)
    with capture_lock():
        ch = load_chain()
        RUNNING.write_text(json.dumps({"module": origin.module, "replay_of": source,
                                       "overrides": overrides, "started": time.time()}))
        t0 = time.time()
        # The same GPU gate `run` uses, keyed on the step being replayed.
        gate = (gpu_gate(EXP, GPU, desc.get("kind") == "dense", f"{CAPTURE} replay {origin.module}")
                if (desc.get("resources") or {}).get("gpu") else nullcontext())
        try:
            with gate:
                r = svc.replay(run_id=RUN_ID, from_artifact=source, overrides=overrides,
                               wait_s=21600)
        except Exception as e:
            r = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        finally:
            RUNNING.unlink(missing_ok=True)
        steps = r.get("replayed") or []
        if r.get("status") != "ok" or not steps:
            ch["history"].append({"t": t0, "action": "replay", "from": source,
                                  "overrides": overrides, "status": "FAILED",
                                  "error": str(r.get("error", ""))[:600]})
            save_chain(ch)
            emit(r)
            sys.exit(1)
        for step in steps:
            for slot, aid in (step.get("outputs") or {}).items():
                ch["current"][slot] = aid
            ch["history"].append({"t": t0, "action": "replay", "from": source,
                                  "overrides": overrides, "module": step.get("module"),
                                  "params": step.get("params"), "status": "ok",
                                  "outputs": step.get("outputs"), "cached": step.get("cached"),
                                  "seconds": round(time.time() - t0, 1),
                                  "metrics": step.get("metrics"),
                                  "diagnostics": [d.get("code") for d in step.get("diagnostics") or []]})
        save_chain(ch)
    emit(r)

elif cmd == "wait":
    limit = float(args[0]) if args else 540.0
    with capture_lock(timeout=limit) as free:
        if free:
            emit({"in_flight": None, "last_step": last_step()})
        else:
            emit({"in_flight": json.loads(RUNNING.read_text()) if RUNNING.exists() else None,
                  "note": "still running; call `wait` again. Do not re-issue the run."})

elif cmd == "running":
    emit({"in_flight": json.loads(RUNNING.read_text()) if RUNNING.exists() else None})

elif cmd == "artifact":
    log_ctx("artifact", artifact=args[0])
    emit(service().artifact(args[0], full=True))

elif cmd == "image":
    emit(service().artifact_image(args[0], name=args[1] if len(args) > 1 else ""))

elif cmd == "compare":
    emit(service().compare(args))

elif cmd == "summary":
    emit(service().run_summary(RUN_ID))

elif cmd == "series":
    import numpy as np
    grp = service().store.open(args[0]).load(args[1])
    emit({k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in grp.items()})

elif cmd == "cloud":
    import numpy as np
    n = int(args[1]) if len(args) > 1 else 200
    xyz = np.asarray(service().store.open(args[0]).load("points")["xyz"])
    sel = np.random.default_rng(0).choice(len(xyz), size=min(n, len(xyz)), replace=False)
    d = np.linalg.norm(xyz - xyz.mean(0), axis=1)
    emit({"n_points": len(xyz), "bbox_min": xyz.min(0).tolist(), "bbox_max": xyz.max(0).tolist(),
          "centroid": xyz.mean(0).tolist(),
          "radius_percentiles": {f"p{q}": float(v) for q, v in
                                 zip((5, 25, 50, 75, 95), np.percentile(d, [5, 25, 50, 75, 95]))},
          "sample": xyz[sel].round(4).tolist()})

else:
    sys.exit(__doc__)
