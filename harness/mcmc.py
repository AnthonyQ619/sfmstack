"""The MCMC sampler for ablation arm A3 (`sfmx mcmc ...`; plan and pre-registration in the experiment record).

The agent executes; the sampler draws and decides. The chain's state is a finished pipeline up to a refined sparse
model, read back from that model's lineage in the store. One iteration:

  propose   pick one step of the pipeline uniformly (detection through optimization), then either swap its module
            for another that produces the same type and whose required inputs the pipeline already holds, or
            perturb one of its parameters within the module's declared range. The answer is the exact list of
            `sfmx` commands that rebuild the pipeline from that step on.
  score     the refined model the proposal produced: the weakest rung of its health profile (0-100), or rejected
            outright when the verifier says it is contradicted, or when no model came out. Metropolis acceptance at
            temperature T; the best model seen is kept apart from the chain's current one.

Every iteration counts, failed ones included. Randomness comes from numpy, seeded per capture and per iteration, so
a chain can be re-derived from its log. Configured by SFM_MCMC_N, SFM_MCMC_T and SFM_MCMC_SEED (launch.py --mcmc).
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

SEARCH_KINDS = ("detection", "matching", "tracking", "pose", "sparse", "optimization")
# Never proposed as swap targets: post-processors and the fill, whose inputs are not a plain stage's.
NO_SWAP = {"MatchQuantize", "PoseFill", "SparseVerification"}
UNSCORED = -1.0


class Sampler:
    def __init__(self, svc, home: Path, capture: str, run_id: str, n: int, temp: float, seed: int):
        self.svc, self.home, self.capture, self.run_id = svc, home, capture, run_id
        self.n, self.temp, self.seed = n, temp, seed
        self.path = home / "mcmc.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else None

    # ------------------------------------------------------------------ helpers
    def rng(self, it: int, purpose: str) -> np.random.Generator:
        h = int(hashlib.sha256(f"{self.capture}|{purpose}".encode()).hexdigest()[:8], 16)
        return np.random.default_rng([self.seed, h, it])

    def save(self):
        self.path.write_text(json.dumps(self.state, indent=1, default=str))

    def kind(self, module: str) -> str:
        return self.svc.registry.get(module).kind

    def io(self, module: str):
        d = self.svc.describe_module(module)
        typ = lambda v: v.get("type") if isinstance(v, dict) else v
        cons = {s: (typ(v), not isinstance(v, dict) or v.get("required", True))
                for s, v in (d.get("consumes") or {}).items()}
        prod = {s: typ(v) for s, v in (d.get("produces") or {}).items()}
        props = ((d.get("params") or {}).get("properties") or {})
        return cons, prod, props

    def lineage(self, refined: str) -> list[dict]:
        """The steps that built `refined`, parents first: module, params, kind, output slot and artifact, and each
        input slot's artifact."""
        store = self.svc.store
        order, seen = [], set()

        def visit(aid):
            if aid in seen:
                return
            seen.add(aid)
            art = store.open(aid)
            for parent in art.manifest.inputs:
                visit(parent)
            made = art.manifest.produced_by
            if made is None:
                return
            cons, prod, _ = self.io(made.module)
            slot = next((s for s, t in prod.items() if t == art.type), None)
            ins = {}
            for parent in art.manifest.inputs:
                ptype = store.open(parent).type
                for s, (t, _) in cons.items():
                    if t == ptype and s not in ins:
                        ins[s] = parent
                        break
            order.append({"module": made.module, "params": dict(made.params or {}),
                          "kind": self.kind(made.module), "slot": slot, "artifact": aid, "inputs": ins})

        visit(refined)
        return order

    def score_of(self, refined: str) -> tuple[float, dict]:
        model = self.svc.store.open(refined)
        if model.type != "sparse_model/v1":
            return UNSCORED, {"why": f"{refined} is a {model.type}, not a refined sparse model"}
        verdict = self.svc._verify_model(model, self.run_id)
        if self.svc._vetoed(verdict):
            return UNSCORED, {"why": "the verifier says the model is contradicted"}
        prof = self.svc._health_digest_of(model) or {}
        pcts = [r.get("percentile") for r in (prof.get("rungs") or {}).values()
                if isinstance(r, dict) and isinstance(r.get("percentile"), (int, float))]
        if not pcts:
            return UNSCORED, {"why": "no health rung could be evaluated"}
        return float(min(pcts)), {"rungs": {k: r.get("percentile") for k, r in prof["rungs"].items()
                                            if isinstance(r, dict)}}

    # ------------------------------------------------------------------ commands
    def init(self, refined: str) -> dict:
        if self.state:
            return {"error": "the chain is already started", **self.status()}
        steps = self.lineage(refined)
        if not any(s["kind"] == "optimization" for s in steps):
            return {"error": f"{refined} was not produced by an optimization step; start from the refined model"}
        score, detail = self.score_of(refined)
        cur = {"refined": refined, "score": score, "steps": steps}
        self.state = {"n": self.n, "temperature": self.temp, "seed": self.seed, "iterations": 0, "accepted": 0,
                      "current": cur, "best": {"refined": refined, "score": score}, "pending": None, "log": []}
        self.save()
        return {"started_from": refined, "score": score, "score_detail": detail, "iterations_to_run": self.n,
                "next": "sfmx mcmc propose"}

    def propose(self) -> dict:
        st = self.state
        if not st:
            return {"error": "no chain yet: sfmx mcmc init <refined_artifact>"}
        if st["iterations"] >= st["n"]:
            return {"done": True, **self.status()}
        if st["pending"]:
            return {"error": "a proposal is waiting to be scored", "pending": st["pending"]}
        it = st["iterations"]
        rng = self.rng(it, "propose")
        steps = st["current"]["steps"]
        idx = [i for i, s in enumerate(steps) if s["kind"] in SEARCH_KINDS]
        for _ in range(50):
            i = int(rng.choice(idx))
            move = self._swap(steps, i, rng) if rng.random() < 0.5 else self._perturb(steps[i], rng)
            move = move or self._perturb(steps[i], rng) or self._swap(steps, i, rng)
            if move:
                break
        else:
            return {"error": "no step of this pipeline has a module to swap or a parameter to change"}
        module, params, change = move
        commands = self._commands(steps, i, module, params)
        st["pending"] = {"iteration": it + 1, "step": i, "stage": steps[i]["kind"], "change": change,
                         "module": module, "params": params, "commands": commands}
        self.save()
        return {"iteration": it + 1, "of": st["n"], "change": change, "commands": commands,
                "then": "run the commands in order, then: sfmx mcmc score <refined_artifact the last one produced> "
                        "(or `sfmx mcmc score failed` if a command failed)"}

    def score(self, refined: str) -> dict:
        st = self.state
        if not st or not st["pending"]:
            return {"error": "nothing is waiting to be scored: sfmx mcmc propose"}
        p, cur = st["pending"], st["current"]
        if refined == "failed":
            new, detail = UNSCORED, {"why": "the proposal failed to run"}
        else:
            new, detail = self.score_of(refined)
        u = float(self.rng(p["iteration"], "accept").random())
        if new == UNSCORED:
            accept = False
        elif new >= cur["score"]:
            accept = True
        else:
            accept = u < math.exp((new - cur["score"]) / st["temperature"])
        entry = {"iteration": p["iteration"], "change": p["change"], "refined": refined, "score": new,
                 "detail": detail, "current_score": cur["score"], "u": u, "accepted": accept}
        if accept:
            st["current"] = {"refined": refined, "score": new, "steps": self.lineage(refined)}
            st["accepted"] += 1
        if new != UNSCORED and new > st["best"]["score"]:
            st["best"] = {"refined": refined, "score": new}
        st["iterations"] += 1
        st["pending"] = None
        st["log"].append(entry)
        self.save()
        out = {"iteration": entry["iteration"], "score": new, "accepted": accept,
               "current": st["current"]["refined"], "current_score": st["current"]["score"],
               "remaining": st["n"] - st["iterations"]}
        if not accept:
            out["pin_back"] = self._pins(st["current"]["steps"], len(st["current"]["steps"]))
        if st["iterations"] >= st["n"]:
            out["done"] = True
            out["best"] = st["best"]
            out["next"] = f"pin sparse {st['best']['refined']}, then run your planned dense stage on it"
        else:
            out["next"] = "sfmx mcmc propose"
        return out

    def status(self) -> dict:
        st = self.state
        if not st:
            return {"started": False}
        return {"iterations": st["iterations"], "of": st["n"], "accepted": st["accepted"],
                "done": st["iterations"] >= st["n"], "current": st["current"]["refined"],
                "current_score": st["current"]["score"], "best": st["best"], "pending": st["pending"]}

    # ------------------------------------------------------------------ moves
    def _perturb(self, step: dict, rng):
        _, _, props = self.io(step["module"])
        cands = []
        for name, spec in props.items():
            t = spec.get("type")
            if "enum" in spec and len(spec["enum"]) > 1:
                cands.append((name, "enum"))
            elif t == "boolean":
                cands.append((name, "bool"))
            elif t in ("integer", "number"):
                cands.append((name, t))
        if not cands:
            return None
        name, t = cands[int(rng.integers(len(cands)))]
        spec = props[name]
        old = step["params"].get(name, spec.get("default"))
        if t == "enum":
            new = rng.choice([v for v in spec["enum"] if v != old])
            new = new.item() if hasattr(new, "item") else new
        elif t == "bool":
            new = not bool(old)
        else:
            base = old if isinstance(old, (int, float)) and old not in (0, None) else (
                spec.get("minimum") or spec.get("maximum") or 1)
            new = float(base) * math.exp(rng.uniform(-math.log(2), math.log(2)))
            lo, hi = spec.get("minimum"), spec.get("maximum")
            if lo is not None:
                new = max(new, lo)
            if hi is not None:
                new = min(new, hi)
            if t == "integer":
                new = int(round(new))
                if new == old:
                    new = old + (1 if (hi is None or old + 1 <= hi) else -1)
        if new == old:
            return None
        params = {**step["params"], name: new}
        return step["module"], params, f"{step['kind']}: {step['module']}.{name} {old!r} -> {new!r}"

    def _swap(self, steps: list[dict], i: int, rng):
        step = steps[i]
        if step["module"] in NO_SWAP:
            return None
        _, prod, _ = self.io(step["module"])
        out_type = prod.get(step["slot"])
        held = {"scene/v1"} | {self.io(s["module"])[1].get(s["slot"]) for s in steps[:i]}
        cands = []
        for name in sorted(self.svc.registry.names()):
            if name == step["module"] or name in NO_SWAP or self.kind(name) != step["kind"]:
                continue
            cons, p2, _ = self.io(name)
            if out_type not in p2.values():
                continue
            if all(t in held for t, req in cons.values() if req):
                cands.append(name)
        if not cands:
            return None
        name = cands[int(rng.integers(len(cands)))]
        return name, {}, f"{step['kind']}: {step['module']} -> {name} (defaults)"

    def _downstream(self, steps: list[dict], i: int) -> set[int]:
        out = {i}
        for k in range(i + 1, len(steps)):
            if any(a == steps[j]["artifact"] for j in out for a in steps[k]["inputs"].values()):
                out.add(k)
        return out

    def _pins(self, steps: list[dict], upto: int) -> list[str]:
        pins, last = [], {}
        for s in steps[:upto]:
            if s["slot"]:
                last[s["slot"]] = s["artifact"]
        scene = next((a for s in steps for a in [s["inputs"].get("scene")] if a), None)
        if scene:
            last.setdefault("scene", scene)
        return [f"sfmx pin {slot} {aid}" for slot, aid in last.items()]

    def _commands(self, steps: list[dict], i: int, module: str, params: dict) -> list[str]:
        down = self._downstream(steps, i)
        keep = [s for k, s in enumerate(steps) if k not in down]
        cmds = self._pins(keep, len(keep))
        rebuilt = {steps[k]["artifact"] for k in down}
        for k in sorted(down):
            mod, par = (module, params) if k == i else (steps[k]["module"], steps[k]["params"])
            cons, _, _ = self.io(mod)
            explicit = []
            if k != i:
                explicit = [f"{s}={a}" for s, a in steps[k]["inputs"].items()
                            if a not in rebuilt and s in cons]
            cmds.append(" ".join(["sfmx run", mod, "'" + json.dumps(par) + "'", *explicit]).strip())
        return cmds
