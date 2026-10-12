"""`sfm_workflow_skill` serves the context and nothing else.

The context an agent plans from is `skills/`, the design documents under `docs/`,
and the module pages. Before the bound existed, the resolver's search list held
`<repo>/<topic>`, so any repository path typed as a topic came back: adapter source,
the service, the test checkers. Every context read in the experiment record was
checked and none ever asked for one, but a strict-context experiment cannot rest on
nobody having tried.

The negative control is built from scratch in a temporary tree, so it does not
depend on what this repository happens to contain beside `skills/`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sfmorch.errors import OrchestratorError
from sfmorch.mcp_server import build_service

REPO = Path(__file__).resolve().parents[1]


def _service(skills: Path, modules: Path, tmp_path: Path):
    return build_service(modules_dir=modules, store_root=tmp_path / "store",
                         skills_dir=skills, use_docker=False)


@pytest.fixture
def tree(tmp_path):
    """A context tree with one page per served place, and a secret beside each."""
    root = tmp_path / "ctx"
    (root / "skills" / "plan").mkdir(parents=True)
    (root / "skills" / "plan" / "sparse.md").write_text("# sparse\n")
    (root / "skills" / "SKILLS.md").write_text("# index\n")
    (root / "docs" / "design").mkdir(parents=True)
    (root / "docs" / "import_lessons.md").write_text("# lessons\n")
    (root / "docs" / "design" / "DECISIONS.md").write_text("# decisions\n")
    (root / "modules" / "m" / "skills").mkdir(parents=True)
    (root / "modules" / "m" / "skills" / "tuning.md").write_text("# tuning\n")
    (root / "modules" / "m" / "adapter.py").write_text("SECRET = 1\n")
    (root / "modules" / "m" / "module.yaml").write_text("name: M\n")
    (root / "harness").mkdir()
    (root / "harness" / "PROCEDURE.md").write_text("# the prompt\n")
    (root / "service.py").write_text("SECRET = 2\n")
    (root / "skills" / "notes.py").write_text("SECRET = 3\n")
    return root


def test_the_context_resolves_by_every_spelling_the_tree_uses(tree, tmp_path):
    svc = _service(tree / "skills", REPO / "modules", tmp_path)
    for topic in ("plan/sparse", "sparse", "plan/sparse.md", "SKILLS",
                  "import_lessons", "docs/import_lessons", "design/DECISIONS",
                  "docs/design/DECISIONS", "modules/m/skills/tuning"):
        assert svc.workflow_skill(topic)["text"].startswith("#"), topic


@pytest.mark.parametrize("topic", [
    "harness/PROCEDURE",            # the harness is injected, never fetched
    "harness/PROCEDURE.md",
    "modules/m/adapter.py",         # source beside a module page
    "modules/m/module.yaml",        # the manifest has its own call
    "service.py",                   # anything at the repository root
    "../service.py",
    "notes.py",                     # non-Markdown inside skills/ itself
    "../modules/m/adapter.py",
])
def test_nothing_outside_the_context_is_served(tree, tmp_path, topic):
    svc = _service(tree / "skills", REPO / "modules", tmp_path)
    with pytest.raises(OrchestratorError):
        svc.workflow_skill(topic)


def test_the_real_repository_keeps_its_source_to_itself(tmp_path):
    svc = _service(REPO / "skills", REPO / "modules", tmp_path)
    assert svc.workflow_skill("plan/sparse")["path"].endswith("skills/plan/sparse.md")
    assert svc.workflow_skill("import_lessons")["path"].endswith("docs/import_lessons.md")
    for topic in ("harness/README", "modules/feature_sift/adapter.py",
                  "packages/sfmorch/src/sfmorch/service.py", "tests/context_checks.py",
                  "pyproject.toml"):
        with pytest.raises(OrchestratorError):
            svc.workflow_skill(topic)
