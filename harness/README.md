# harness

The experiment driver: it launches one isolated agent per capture, gives each the
procedure below as its prompt, and gates the GPUs. It is not part of the pipeline and
no module depends on it.

**It sits beside `skills/`, not inside it, for the same reason `docs/` does.**
`skills/` is the knowledge base the driving agent retrieves through `sfm_workflow_skill`,
and everything in it is a document an agent may be handed. Nothing here is: `launch.py`
and `gpu_gate.py` are operator tools, and `PROCEDURE.md` is *injected* by `launch.py` as
the agent's prompt rather than fetched by it. Putting this directory under `skills/`
would also make `sfm_workflow_skill('harness/launch.py')` resolve, because that call
reads `skills_dir / topic` directly.

## Why it is in the repository at all

It used to live in `~/sfm_experiments/harness`, unversioned, beside the run data. Two
problems with that, and the second is the one that matters.

It was not reviewed alongside the context it exercises. A change to the procedure an
agent is given is as much a change to the experiment as a change to a skill file, and
it left no trace in the history.

**And it could name any capture.** An example in a docstring, a smoke test's image
directory, an error message suggesting `SFM_CAPTURE=DTU/scan11` — each is a holdout
capture written into the repository, and a holdout that has been written down is no
longer able to measure whether the context generalises. The old harness named four.

**Every capture named anywhere in this directory is a member of
[`skills/evidence/CORPUS.txt`](../skills/evidence/CORPUS.txt).** Keep it that way. If
you need an example, take a corpus capture; there are nineteen.

## What did not come across

- `INTERVENTIONS.md` — a historical record of what was done to earlier batches, which
  names holdout captures by necessity. It stays in the frozen harness, with the batches
  it describes.
- `smoke_batch.json` — written by `launch.py --smoke` at run time, not source.

## The frozen predecessor

`~/sfm_experiments/harness` is kept exactly as it was, with its data, so an earlier
batch can be reproduced or the two compared. It is frozen: fixes belong here. Do not
copy examples back from it — it still names holdouts.

## Layout

```
launch.py           one isolated `claude -p` per capture; --scope, --exp, --controls, --smoke
sfmx.py             the only tool an agent may call; every context read goes through it
gpu_gate.py         one dense step per GPU at a time
PROCEDURE.md        the agent's prompt: raw frames to a refined sparse model
PROCEDURE_dense.md  the same, with the dense stage in scope
bin/sfmx            the wrapper an agent's PATH points at
```

## Where it writes

`launch.py` writes run directories under the experiment record, **not** into the
repository. That root defaults to `~/sfm_experiments` and is overridden by `--exp` or
`SFM_EXP_ROOT`. It used to be derived as `HARNESS.parent`, which was correct only while
the harness lived inside the experiment record; here that would resolve to the repo
root. If a run ever appears inside this repository, that default is what to check.

`--smoke`'s batch file goes there too, under `SMOKE/isolation/`. It used to be written
beside `launch.py`, which was harmless in the old location and drops an untracked file
into the checkout in this one. **Nothing this harness writes belongs in the repository**
— that is the rule these two defaults are instances of, and the one to apply to any
path added here.
