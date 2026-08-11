"""Fail the build if the weights are not in the image.

Both weight sets ship inside the upstream repository, so this is not a download
-- it is a guard against a layout change upstream leaving an image that builds
cleanly and then fails on the first job, in a container, an hour later.
"""

import torch
from models.superglue import SuperGlue

for weights in ("indoor", "outdoor"):
    model = SuperGlue({"weights": weights}).eval()
    n = sum(p.numel() for p in model.parameters())
    print(f"superglue/{weights}: {n / 1e6:.1f}M parameters loaded")
    assert n > 1e6, f"{weights} weights look empty"
