# Driving one capture to a dense reconstruction (arm A3: mechanics, plan, then MCMC)

You are driving a structure-from-motion pipeline for ONE capture, from raw frames to a dense reconstruction.
You have never seen this capture.

## The rules

1. **Use what you know.** Nothing tells you how to build or tune this pipeline beyond the mechanics file below. You may use your own
   knowledge of structure from motion; record in the report where you relied on it.
2. **Only `sfmx`, and only your own capture directory.** Anything else is refused. Do not try to get around a
   refusal: it is part of the setup.
3. **No ground truth, no outside sources.** You get the two paths below as facts, and nothing else about the capture.
4. **The deliverable is a dense reconstruction,** together with the refined sparse model it is built on.
5. **Stay in the foreground.** Never start a command in the background and never end your turn to wait for one:
   nothing will wake you. Wait for a long step with `sfmx wait`, as often as it takes.

Read `/home/anthonyq/projects/sfmstack/harness/ablation/MECHANICS.md` first, in full. It explains how the modules connect and how to plan.

## The tool

`sfmx` is on your PATH, and your capture is already set.

    sfmx list [consumes=..|produces=..|kind=..]
    sfmx find <produces>
    sfmx describe <module>
    sfmx run <module> '<params json>' [slot=artifact_id ...]
    sfmx run <module> --params-file <file> [slot=artifact_id ...]
    sfmx wait [seconds]
    sfmx running
    sfmx state
    sfmx replay <artifact_id> [overrides-json]
    sfmx pin <slot> <artifact_id>
    sfmx artifact <id>
    sfmx image <id> [name]
    sfmx compare <id> <id> [...]
    sfmx summary
    sfmx series <id> <group>
    sfmx cloud <id> [n]
    sfmx mcmc init | propose | score <refined_artifact> | status

In `run`, a slot you name takes that artifact; a required slot you leave out is wired from the chain's current
artifact of that type, and an optional one stays empty. `image` returns a path: open it with your image reader.

**Call `sfmx` as a bare command:** no pipe, no redirect, no `;` or `&&`. Anything that does not begin with `sfmx`
is refused. Every answer is also saved in your `scratch/` directory as `last_<command>.json`; read a long answer
from there with the file reader. Write your own files in `scratch/` only.

**Long steps.** Give each `sfmx` call a Bash timeout of 600000 ms. `run` returns after at most nine minutes; if the
step is still going it says so. Call `sfmx wait` until nothing is in flight, then read the step from `sfmx state`.
Never re-issue a step that is in flight.

## The task

1. Load the scene and run the analysis modules you choose.
2. **Write your plan** in `scratch/plan.md`, in the shape the mechanics file gives.
3. **Execute the plan once** through the optimization stage (stage 8), to a refined sparse model. Do not run the
   dense stage yet. A step that *fails* may be fixed with the least change that makes it run (record it under
   `recoveries`); otherwise, no tuning of your own.
4. **Search with the sampler.** `sfmx mcmc` runs a Markov chain Monte Carlo search over the pipeline. You execute its
   proposals; it draws them and decides whether to accept them. Do not choose proposals yourself.
   - `sfmx mcmc init` starts the chain from your refined model and tells you how many iterations to run.
   - Then repeat: `sfmx mcmc propose` gives you the exact `sfmx` commands for the next proposal. Run them in order.
     If one fails, stop that proposal. Then call `sfmx mcmc score <refined_artifact>` with the refined model the
     proposal produced, or `sfmx mcmc score failed` if it produced none. The answer says whether the proposal was
     accepted, which artifacts to `pin` if it was not, and how many iterations remain.
   - Stop when `sfmx mcmc status` says the chain is done. It names the best refined model the chain found.
5. **Densify the best model once:** pin it, run your planned dense stage on it, and deliver that.

## What to write when you are done

Write `../agent_report.json` (your capture directory), exactly this shape:

```json
{
  "capture": "<capture>",
  "arm": "A3",
  "final": {"dense_artifact": "", "refined_artifact": "", "scene_artifact": "",
            "pipeline": [{"stage": "", "module": "", "params": {}, "artifact": "", "why": ""}],
            "metrics": {}, "runs_spent": 0,
            "selection_rule": "how you chose this model over any others you built"},
  "first_plan": [{"stage": "", "module": "", "params": {}}],
  "mcmc": {"iterations": 0, "accepted": 0, "best_refined_artifact": "", "best_score": 0},
  "other_models": [{"refined_artifact": "", "pipeline": "", "why_not_chosen": ""}],
  "recoveries": [{"step": "", "error": "", "what_you_changed": ""}],
  "own_knowledge_used": [{"decision": "", "what_you_relied_on": ""}],
  "notes": ""
}
```

`dense_artifact` is the dense model you deliver, and `refined_artifact` is the optimization-stage model it is built
on. `recoveries` lists every step you re-ran because it failed.
