# Driving one capture to a dense reconstruction

You are driving a structure-from-motion pipeline for ONE capture, from raw frames
to a dense reconstruction. You have never seen this capture. Everything you know
about the modules comes from the written context, reached through the tool below.

## The rules

1. **Decide from the retrievable context, not from what you already know about SfM.**
   You may know how a detector or a robust estimator works. That knowledge is not
   what is being tested, and using it silently defeats the purpose of the run. If
   the context does not tell you something you need, that is a FINDING: record it
   under `gaps`, say what you did instead, and set `outside_knowledge_used` honestly.
2. **Every context read goes through `sfmx`.** Your permissions allow `sfmx` and file
   reads and writes inside your own capture directory, and nothing else; anything
   else is refused. Do not try to get around a refusal: it is part of the setup.
3. **No ground truth, no outside sources.** You get the two paths below as facts,
   and nothing else about the capture.
4. **Go through to a dense reconstruction.** The dense model is the deliverable,
   together with the refined sparse model it is built on.
5. **Stay in the foreground.** Never start a command in the background and never
   end your turn to wait for one: nothing will wake you. A long step is waited for
   with `sfmx wait`, in the foreground, as often as it takes.

## The tool

`sfmx` is on your PATH, and your capture is already set in the environment:

    sfmx skills [topic]              # always-resident index; then by topic
    sfmx brief                       # the plan brief, once a scene exists
    sfmx describe <module>           # manifest: params, defaults, metrics, bands
    sfmx skill <module> <topic>      # SKILL | tuning | limitations | artifact | sources
    sfmx list [consumes=..|produces=..]
    sfmx find <produces> [k=v ...]   # capability query
    sfmx run <module> '<params json>' [slot=artifact_id ...]
    sfmx run <module> --params-file <file> [slot=artifact_id ...]
    sfmx wait [seconds]              # block until this capture's step in flight ends
    sfmx running                     # what this capture is running right now
    sfmx state                       # the chain so far
    sfmx replay <artifact_id> [overrides-json]  # re-run the step that made it, with overrides
    sfmx pin <slot> <artifact_id>    # make an earlier artifact current again
    sfmx artifact <id>
    sfmx image <id> [name]           # returns a PATH; open it with your image reader
    sfmx compare <id> <id> [...]
    sfmx summary
    sfmx series <id> <group>
    sfmx cloud <id> [n]

`skills` with no topic prints the index; start there. `image` returns a path:
open it with your image-capable file reader to actually see the picture. A
description of frames you have not looked at is fabrication, not analysis.

**Call `sfmx` as a bare command.** No pipe, no redirect, no second statement after
`;` or `&&`, no wrapping in `bash -c`. Only a command that begins with `sfmx` is
permitted; anything else is refused outright rather than asked about, and a refusal
costs you a turn. So not `sfmx skills | head -20` — just `sfmx skills`.

Your working directory is your capture's `scratch/` directory. Write every file you
need there, and nowhere else. Every `sfmx` answer is also saved there as
`last_<command>.json` (or `.md`), so a long one can be re-read with the file
reader — that is the way to read part of a long answer, in place of piping it. `sfmx brief` saves the brief as `../brief.json`. A long params object, such
as the scene description report, goes in a file and is passed with `--params-file`.

`run` prints the service's whole response. Read all of it, including fields you
did not ask for; the service can act on its own after a step, and when it does,
the response says so.

A step can take many minutes on a shared machine, and a dense step far longer.
Give each `sfmx run` call a Bash timeout of 600000 ms. If a call times out, the
step is still running: call `sfmx wait` until it reports nothing in flight, then
read the step from `sfmx state`. Do not re-issue a run that is still in flight.
One capture runs one step at a time; a second `run` waits for the first.

## The pipeline

You choose the module AND its parameters at every stage:

1. **Scene loading.** The capture's `image_dir` and `calibration_path` are given
   below as facts. Everything else about loading is yours.
2. **Analysis.** The scene-measuring modules.
3. **Detection.**
4. **Matching.** Some paths do not need a separate detection or matching step.
5. **Tracking.**
6. **Pose.**
7. **Sparse reconstruction.**
8. **Optimization.** The refined sparse model this produces is what the dense
   stage is built on.
9. **Dense reconstruction.** The dense model this produces is the deliverable.

## How to work

- **Read before running.** A run costs minutes; a context read costs nothing.
- **Let the metrics and diagnostics drive the next decision.** If a diagnostic
  fires, read its suggested actions and its pointers.
- **Backtracking is expected.** If a stage's output is poor and the cause is
  upstream, go back, change something, and re-run forward. Use `pin` to make an
  earlier artifact current. Record every backtrack.
- **Do not stop at the first thing that runs.** The deliverable is a good model.
  When you have more than one finished model, choose between them the way the
  context tells you to, and say which rule you applied.
- Budget roughly 25-40 runs in all, the dense stage included. Stop earlier when the
  model is clearly good and further moves are not paying.

## What to write when you are done

Write `../agent_report.json` (your capture directory), exactly this shape:

```json
{
  "capture": "<capture>",
  "final": {"dense_artifact": "", "refined_artifact": "", "scene_artifact": "",
            "pipeline": [{"stage": "", "module": "", "params": {}, "artifact": "", "why": ""}],
            "metrics": {}, "runs_spent": 0,
            "selection_rule": "which rule chose this model over the others you built"},
  "first_plan": [{"stage": "", "module": "", "params": {}}],
  "other_models": [{"refined_artifact": "", "pipeline": "", "why_not_chosen": ""}],
  "other_dense": [{"dense_artifact": "", "built_on": "", "params": {}, "why_not_chosen": ""}],
  "backtracks": [{"trigger": "", "from_stage": "", "changed": "", "outcome": "", "helped": true}],
  "context_that_worked": [{"where": "", "what": "", "decision_it_drove": ""}],
  "context_that_was_weak": [{"where": "", "problem": "", "cost": ""}],
  "context_that_was_wrong_or_stale": [{"where": "", "claim": "", "observed": "", "confidence": ""}],
  "gaps": [{"question": "", "why_it_mattered": "", "where_i_looked": "",
            "what_i_did_instead": "", "outside_knowledge_used": true}],
  "notes": ""
}
```

`dense_artifact` is the dense model you are delivering, and `refined_artifact` is
the optimization-stage model it was built on. If the service kept a second solve
for that model, build on the model the service kept and say so. `selection_rule`
covers both choices: the sparse model the dense stage was built on, and the dense
model among any you built.

`gaps` is the most valuable section. "Where I looked" means the topics and modules
you actually queried before concluding the answer was absent. In
`context_that_was_wrong_or_stale`, quote the claim, give the reading that
contradicts it, and say whether it might be specific to this capture.
