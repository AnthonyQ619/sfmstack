"""Bake the BootsTAPIR checkpoint into the image.

`bootstapir_checkpoint_v2.pt` from Google Cloud Storage, which the module would
otherwise fetch on first use -- a network call in the middle of a job. Saved to a
fixed path the module names explicitly rather than left in TORCH_HOME, whose
location follows HOME and which the container overrides.
"""

import pathlib

import torch

URL = ("https://storage.googleapis.com/dm-tapnet/bootstap/"
       "bootstapir_checkpoint_v2.pt")

out = pathlib.Path("/opt/weights/bootstapir_v2.pt")
out.parent.mkdir(parents=True, exist_ok=True)

state = torch.hub.load_state_dict_from_url(URL, map_location="cpu")
if isinstance(state, dict) and "state_dict" in state:
    state = state["state_dict"]
torch.save(state, out)

total = sum(v.numel() for v in state.values() if hasattr(v, "numel"))
print(f"bootstapir v2: {total / 1e6:.1f}M parameters, "
      f"{out.stat().st_size / 2**20:.0f} MiB at {out}")
assert total > 1e6, "checkpoint looks empty"

# Prove it loads into the architecture the module builds, before the layer is
# committed -- a strict=False load hides a mismatched checkpoint completely.
from tapnet.torch import tapir_model  # noqa: E402

model = tapir_model.TAPIR(pyramid_level=1, extra_convs=True)
missing, unexpected = model.load_state_dict(state, strict=False)
print(f"load_state_dict: {len(missing)} missing, {len(unexpected)} unexpected")
assert not missing, f"architecture expects weights the checkpoint lacks: {missing[:5]}"
