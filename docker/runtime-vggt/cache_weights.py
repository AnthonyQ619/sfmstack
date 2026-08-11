"""Download the VGGT-1B checkpoint into the image.

Saved as a plain state_dict at a fixed path rather than left in the HuggingFace
cache: the cache location depends on HOME, and the container runs as the host uid
with HOME=/tmp, so a hub-cached checkpoint written at build time as root is not
where the module looks at run time.
"""

import pathlib

import torch
from vggt.models.vggt import VGGT

out = pathlib.Path("/opt/weights/vggt-1b.pt")
out.parent.mkdir(parents=True, exist_ok=True)

model = VGGT.from_pretrained("facebook/VGGT-1B")
torch.save(model.state_dict(), out)

size_gb = out.stat().st_size / 2**30
n = sum(p.numel() for p in model.parameters())
print(f"vggt-1b: {n / 1e9:.2f}B parameters, {size_gb:.2f} GiB at {out}")
assert n > 1e9, "checkpoint looks empty"
