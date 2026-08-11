"""Bake the VGGSfM tracker weights and the DINOv2 query-ranking model.

Two downloads, from two different places:

  * `vggsfm_v2_tracker.pt` (186 MB) from the HuggingFace hub, which
    `build_vggsfm_tracker(None)` would otherwise fetch on first use -- a network
    call in the middle of a job. Saved to a fixed path the module names
    explicitly.
  * `dinov2_vitb14_reg` from torch hub, both the repository and its 330 MB
    checkpoint, used by `query_selection: dino`. Left in TORCH_HOME because
    upstream reaches for it by name, not by path.

The DINOv2 download is the easy one to miss: it only happens on the default query
selection, so an image built without it works under `interval` and fails under
`dino`.
"""

import pathlib

import torch
from vggt.dependency.vggsfm_utils import build_vggsfm_tracker

out = pathlib.Path("/opt/weights/vggsfm_v2_tracker.pt")
out.parent.mkdir(parents=True, exist_ok=True)

tracker = build_vggsfm_tracker()
torch.save(tracker.state_dict(), out)
n = sum(p.numel() for p in tracker.parameters())
print(f"vggsfm tracker: {n / 1e6:.1f}M parameters, "
      f"{out.stat().st_size / 2**20:.0f} MiB at {out}")
assert n > 1e6, "checkpoint looks empty"

model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14_reg")
print(f"dinov2_vitb14_reg: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M "
      f"parameters cached")
