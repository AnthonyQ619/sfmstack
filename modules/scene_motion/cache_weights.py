"""Bake the RAFT-large checkpoint into the image.

torchvision would otherwise fetch it into TORCH_HOME on first use -- a network
call in the middle of a job, into a directory the container remaps. Saved to a
fixed path the module names explicitly, exactly as track_tapir does.
"""

import pathlib

import torch
from torchvision.models.optical_flow import Raft_Large_Weights, raft_large

WEIGHTS = Raft_Large_Weights.C_T_SKHT_V2  # what .DEFAULT resolves to; pinned by name

out = pathlib.Path("/opt/weights/raft_large.pt")
out.parent.mkdir(parents=True, exist_ok=True)

state = torch.hub.load_state_dict_from_url(WEIGHTS.url, map_location="cpu")
torch.save(state, out)

total = sum(v.numel() for v in state.values() if hasattr(v, "numel"))
print(f"raft_large {WEIGHTS.name}: {total / 1e6:.1f}M parameters, "
      f"{out.stat().st_size / 2**20:.0f} MiB at {out}")

# Prove it loads STRICTLY into the architecture the module builds, before the
# layer is committed. The module loads with strict=True for the same reason: a
# silently-partial load gives a model that runs and returns noise.
model = raft_large(weights=None)
model.load_state_dict(state)
print("load_state_dict: strict load OK")
