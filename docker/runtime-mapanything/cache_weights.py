"""Pull everything MapAnything downloads into the image, at build time.

`save_pretrained` cannot be used to re-save the model at a fixed path -- its
config carries class objects and json refuses them -- so this instead builds the
model once with HF_HOME and TORCH_HOME pointed at a baked directory, and lets the
normal caches be the delivery mechanism. The module then loads by the same name
with HF_HUB_OFFLINE set, which turns a cache miss into an immediate error instead
of a silent network fetch on a host that may not have one.

Two downloads happen, not one, and the second is easy to miss:

  * the MapAnything checkpoint, from the HuggingFace hub;
  * the DINOv2 *code*, from torch hub. `_from_pretrained` sets
    `torch_hub_pretrained=False` so the encoder's weights are not fetched
    redundantly, but the repository itself still is.

Which checkpoint is a licensing choice, not a quality one:

    facebook/map-anything          CC-BY-NC 4.0, the predecessor's model, default
    facebook/map-anything-apache   Apache 2.0, trained on a commercial-safe subset
"""

import os

import torch
from mapanything.models import MapAnything

name = os.environ.get("MAPANYTHING_MODEL_ID", "facebook/map-anything")

model = MapAnything.from_pretrained(name)
n = sum(p.numel() for p in model.parameters())
print(f"{name}: {n / 1e9:.2f}B parameters")
assert n > 1e8, "checkpoint looks empty"

# Prove the cache is complete before the layer is committed: a second load with
# the network disabled is exactly what the module will do at run time.
del model
os.environ["HF_HUB_OFFLINE"] = "1"
again = MapAnything.from_pretrained(name)
assert sum(p.numel() for p in again.parameters()) == n
print(f"offline reload OK, torch {torch.__version__}")
