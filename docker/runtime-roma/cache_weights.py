"""Download and bake RoMa's weights so no job pays for them.

Both settings are cached: `outdoor` and `indoor` are trained on different data
(MegaDepth and ScanNet), and choosing between them is a normal tuning step rather
than a rebuild.
"""

import torch
from romatch import roma_indoor, roma_outdoor

for name, factory in (("outdoor", roma_outdoor), ("indoor", roma_indoor)):
    model = factory(device=torch.device("cpu"))
    n = sum(p.numel() for p in model.parameters())
    print(f"roma/{name}: {n / 1e6:.0f}M parameters cached")
    assert n > 1e6, f"{name} weights look empty"
