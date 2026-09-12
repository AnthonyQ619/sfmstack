"""The container server honours a module manifest's `types:` block.

The host registry has always registered a module's declared types. The server that
runs inside every container did not, so a module producing a custom type sealed its
artifact in-process and failed at seal in a container -- the one execution path the
campaigns use. Nothing produced a custom type until SparseVerification, so nothing
noticed.
"""

import textwrap

from sfmkit.schema import registry
from sfmkit.server import ModuleService


def test_a_module_declared_type_is_known_inside_the_container(tmp_path):
    mod = tmp_path / "mod"
    mod.mkdir()
    (mod / "module.yaml").write_text(textwrap.dedent("""
        name: TypeProbe
        version: 0.0.1
        entrypoint: adapter:run
        types:
          - type: custom/server_type_probe/v1
            files:
              data:
                arrays:
                  x: {shape: [null], dtype: [float64]}
        produces:
          out: {type: custom/server_type_probe/v1}
    """))
    (mod / "adapter.py").write_text(
        "from sfmkit import module\n\n\n@module\ndef run(ctx):\n    return None\n"
    )

    assert "custom/server_type_probe/v1" not in registry()
    ModuleService(mod, tmp_path / "store")
    assert "custom/server_type_probe/v1" in registry()
