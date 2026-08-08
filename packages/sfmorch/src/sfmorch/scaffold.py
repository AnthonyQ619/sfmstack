"""Generate a new module directory.

The extensibility claim is that turning an upstream repository into a working,
isolated module is three files. This writes those three files plus skill stubs,
so the remaining work is genuinely just the adapter body and the curation.

Deliberately generates stubs that FAIL loudly rather than placeholders that
quietly succeed -- a scaffolded module that runs and produces an empty artifact
is worse than one that refuses to start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

import yaml

from .errors import ManifestError

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def to_slug(name: str) -> str:
    """CamelCase -> snake_case, for the directory and image name."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


@dataclass
class ScaffoldRequest:
    name: str
    kind: str = ""
    summary: str = ""
    consumes: dict[str, str] = field(default_factory=dict)  # slot -> type
    produces: dict[str, str] = field(default_factory=dict)  # slot -> type
    gpu: bool = False
    pip: list[str] = field(default_factory=list)
    repo: str = ""
    paper: str = ""
    version: str = "0.1.0"


def scaffold_module(
    request: ScaffoldRequest, modules_dir: str | Path, *, force: bool = False
) -> dict[str, object]:
    if not NAME_RE.match(request.name):
        raise ManifestError(
            f"module name {request.name!r} must be a bare identifier -- it becomes "
            f"the registry key and appears in every artifact's provenance"
        )
    if not request.produces:
        raise ManifestError("a module must declare at least one output in `produces`")

    slug = to_slug(request.name)
    root = Path(modules_dir) / slug
    if root.exists() and not force:
        raise ManifestError(f"{root} already exists (pass force to overwrite)")

    (root / "skills").mkdir(parents=True, exist_ok=True)

    (root / "module.yaml").write_text(_manifest(request, slug), encoding="utf-8")
    (root / "adapter.py").write_text(_adapter(request), encoding="utf-8")
    (root / "Dockerfile").write_text(_dockerfile(request, slug), encoding="utf-8")

    for topic, body in _skill_stubs(request).items():
        (root / "skills" / f"{topic}.md").write_text(body, encoding="utf-8")

    return {
        "module": request.name,
        "root": str(root),
        "image": f"sfmstack/{slug.replace('_', '-')}:{request.version}",
        "files": sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()),
        "next_steps": [
            f"Implement the body of run() in {root / 'adapter.py'} "
            f"(it raises NotImplementedError until you do).",
            f"Fill the params, metrics and diagnostics blocks in {root / 'module.yaml'}.",
            "Curate skills/tuning.md and skills/limitations.md from the paper, "
            "the upstream source, and its issue tracker; tag every claim in sources.md.",
            f"sfm_build_module('{request.name}') then "
            f"sfm_smoke_test('{request.name}', scene=<artifact id>).",
        ],
    }


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #


def _manifest(r: ScaffoldRequest, slug: str) -> str:
    doc: dict[str, object] = {
        "name": r.name,
        "version": r.version,
        "kind": r.kind,
        "summary": r.summary or f"TODO: one line on what {r.name} does.",
        "description": (
            "TODO: when to reach for this, and when not to. The 'when not to' half\n"
            "is what stops the agent burning runs on a scene this cannot handle.\n"
            + (f"\nUpstream: {r.repo}\n" if r.repo else "")
            + (f"Paper: {r.paper}\n" if r.paper else "")
        ),
        "image": f"sfmstack/{slug.replace('_', '-')}:{r.version}",
        "entrypoint": "adapter:run",
        "resources": {
            "gpu": r.gpu,
            # How long a typical job takes. Not a limit -- it decides whether a
            # caller blocks inline or gets a job id to poll, so a wrong value
            # here costs either pointless blocking or pointless round trips.
            "expected_duration_s": 300 if r.gpu else 30,
            "timeout_s": 3600 if r.gpu else 1800,
        },
    }
    if r.consumes:
        doc["consumes"] = {
            slot: {"type": t, "required": True} for slot, t in r.consumes.items()
        }
    doc["produces"] = {slot: {"type": t} for slot, t in r.produces.items()}
    doc["params"] = {
        "example_param": {
            "type": "integer",
            "default": 1,
            "minimum": 1,
            "description": "TODO: replace. Every param needs a description.",
            "tuning": "TODO: which metric this moves, in which direction, how much.",
        }
    }
    doc["metrics"] = {
        "example_metric": {
            "direction": "higher_better",
            "healthy": [1, None],
            "meaning": "TODO: what this number means and when to worry about it.",
        }
    }
    doc["diagnostics"] = [
        {
            "code": "example_problem",
            "severity": "warn",
            "message": "TODO: what went wrong, in one sentence.",
            "suggested_actions": ["TODO: the first thing to try."],
            "see_also": "tuning.md#example_metric-below-1",
        }
    ]

    header = dedent(f"""\
        # {r.name} {r.version}
        #
        # Generated by sfm_scaffold_module. Every TODO below is load-bearing:
        # params feed the MCP tool schema, metrics feed the agent's ability to tell
        # whether this module is working, and diagnostics feed its ability to fix it.
        """)
    return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=88)


def _adapter(r: ScaffoldRequest) -> str:
    inputs = "\n".join(
        f'    {slot} = ctx.inputs["{slot}"]  # {t}' for slot, t in r.consumes.items()
    )
    first_out = next(iter(r.produces))

    return dedent(f'''\
        """{r.name} -- {" + ".join(r.consumes.values()) or "no inputs"} -> {" + ".join(r.produces.values())}."""

        from __future__ import annotations

        import numpy as np
        from sfmkit import Ctx, module


        # def warmup() -> None:
        #     """Optional. Called once at server startup, before any job.
        #
        #     Load model weights here so they stay resident across jobs -- without
        #     it a warm container buys nothing over a cold process, which is most of
        #     the point of running as a server.
        #     """


        @module
        def run(ctx: Ctx):
        {inputs or "    # no declared inputs"}
            # params = ctx.params.example_param

            # Report progress from any loop running more than a few seconds. It
            # is the only thing that lets a caller tell a working module from a
            # stuck one on a job that legitimately takes twenty minutes.
            # for i, item in enumerate(items):
            #     ctx.progress(i / len(items), f"stage {{i + 1}}/{{len(items)}}")

            raise NotImplementedError(
                "{r.name}: implement run() in adapter.py. "
                "Scaffolded modules refuse to run rather than producing an empty "
                "artifact that looks like a successful reconstruction."
            )

            out = ctx.output("{first_out}")
            # out.save("<file>", <array_name>=np.asarray(...))
            # out.metric("example_metric", 1.0, direction="higher_better", healthy=(1, None))
            # out.diagnostic("example_problem", see_also="tuning.md#example_metric-below-1")
            # out.note("One or two sentences on what happened, for the driving agent.")
        ''')


def _dockerfile(r: ScaffoldRequest, slug: str) -> str:
    pip = "\n".join(
        f'RUN pip install --no-cache-dir "{p}"' for p in r.pip
    ) or '# RUN pip install --no-cache-dir "<dependency>==<version>"'
    clone = (
        dedent(f"""\

        # Pin to a commit, never a branch: the image must be reproducible, and
        # `main` moving under you silently changes what an artifact's
        # module_version claims to describe.
        # RUN git clone {r.repo} /opt/upstream \\
        #     && cd /opt/upstream && git checkout <COMMIT> \\
        #     && pip install --no-cache-dir -e .
        """)
        if r.repo
        else ""
    )

    return dedent(f"""\
        # {r.name} {r.version}
        #
        #   docker build -t sfmstack/{slug.replace("_", "-")}:{r.version} \\
        #       -f modules/{slug}/Dockerfile .
        #
        # Build context is the repository root.

        FROM sfmstack/runtime:1.0
        {clone}
        {pip}

        COPY modules/{slug} /module
        """)


def _skill_stubs(r: ScaffoldRequest) -> dict[str, str]:
    consumed = ", ".join(r.consumes.values()) or "nothing"
    produced = ", ".join(r.produces.values())

    return {
        "SKILL": dedent(f"""\
            ---
            module: {r.name}
            module_version: {r.version}
            upstream: {r.repo or "TODO"}
            curated_at: TODO
            sources: 0
            ---

            TODO: one paragraph on what this does and how it works, in plain terms.

            **Use when** TODO -- the scene conditions this is genuinely good at.

            **Prefer something else when** TODO. Be specific; this half is what stops
            the agent burning runs. See [limitations](limitations.md).

            **Cheapest thing that usually works:** TODO.

            **Reading the output:** [artifact.md](artifact.md).
            """),
        "tuning": dedent("""\
            # Tuning — TODO

            Index sections by **observed metric state**, not by parameter. The agent
            arrives holding metrics, not a hypothesis, so `## <metric> below <value>`
            is findable and `## <param_name>` is not.

            ---

            ## `example_metric` below 1

            **Read it as:** TODO.

            **Related upstream signal (advisory):** TODO. A pointer, never an ordering
            rule -- the agent decides what to try first.

            **Gradient, in order of expected effect:**

            1. TODO. *Expect:* magnitude and cost.
            2. TODO.

            **Diminishing returns:** TODO [S1].

            **Do not** TODO -- the change that looks right and makes things worse.

            ### Observed

            *None yet. Populated by the distillation loop from real runs.*
            """),
        "limitations": dedent("""\
            # Limitations — TODO

            When to stop tuning and switch. Escapes name a **capability query**, never
            a module -- module names go stale, capability queries resolve against the
            live registry.

            ---

            ## TODO: the failure mode

            **Signature:** TODO -- what the metrics look like when this is happening.

            **Why no parameter helps:** TODO. This is the important part; without it
            the agent keeps tuning.

            **Escape:**

            ```
            sfm_find_alternatives(produces="<type>", not_consuming="<type>")
            ```

            **Expected trade:** TODO.

            ---

            ## Observed switches

            *None yet.*
            """),
        "artifact": dedent(f"""\
            # Reading the output — TODO

            Consumes {consumed}. Produces {produced}.

            ## Payload

            ```
            data/<file>.npz
              <array>  [N, ?] dtype   TODO: what it holds, in which coordinate frame
            ```

            ## Sanity checks

            - TODO: the check that catches a producer bug.
            - TODO: the value that looks fine and is not.

            ## Metrics, and which to trust

            | Metric | Read it as |
            | --- | --- |
            | TODO | TODO |
            """),
        "sources": dedent(f"""\
            # Sources — TODO

            Every quantitative claim in the principled sections resolves to a tag here.
            Uncited numbers are not allowed in those sections.

            | Tag | Source | Where | Claims it supports |
            | --- | --- | --- | --- |
            | S1 | {r.paper or "TODO: paper"} | §TODO | TODO |
            | S2 | {r.repo or "TODO: upstream repo"} | TODO | TODO |

            ## Review triggers

            - The upstream pin moves.
            - An observed card contradicts a principled claim. The measurement wins.
            """),
    }
