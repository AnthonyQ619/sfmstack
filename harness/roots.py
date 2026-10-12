"""Which context a run reads.

The default, and the only thing an ordinary run ever does, is the repository's own
`skills/` and `modules/`. An ablation experiment sets `SFM_SKILLS` and, if it is
reducing the module tier too, `SFM_MODULES`, each pointing at a generated view
(`tools/build_context_view.py`). Nothing else in the stack reads these variables, so
leaving them unset is not a configuration: it is the absence of one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def context_roots(repo: Path, env: os._Environ | dict) -> tuple[Path, Path]:
    """(skills_dir, modules_dir), each the repository's unless the override names one.

    An override that does not point at a context tree is refused rather than fallen
    back from: silently reading the full context under a label that claims a reduced
    one is the one failure an ablation cannot afford.
    """
    skills = Path(env["SFM_SKILLS"]).expanduser().resolve() if env.get("SFM_SKILLS") else repo / "skills"
    modules = Path(env["SFM_MODULES"]).expanduser().resolve() if env.get("SFM_MODULES") else repo / "modules"
    if not (skills / "evidence" / "CORPUS.txt").is_file():
        raise SystemExit(f"SFM_SKILLS={skills}: no evidence/CORPUS.txt there, so it is not a context tree")
    view = skills.parent / "VIEW.json"
    if view.is_file() and not json.loads(view.read_text()).get("clean", False):
        raise SystemExit(f"SFM_SKILLS={skills}: its VIEW.json says the view is not clean "
                         "(dropped captures still named); refusing to drive an agent against it")
    if not any(modules.glob("*/module.yaml")):
        raise SystemExit(f"SFM_MODULES={modules}: no */module.yaml there, so it is not a modules tree")
    return skills, modules
