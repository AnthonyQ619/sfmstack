# sfmstack/runtime-mapanything:1.0
#
#   docker build -t sfmstack/runtime-mapanything:1.0 \
#     -f docker/runtime-mapanything/Dockerfile .
#
# MapAnything is not on PyPI, so it installs from the upstream repository at a
# pinned commit -- the same arrangement as SuperGlue and VGGT. A base of its own
# rather than a layer on runtime-vggt: nothing is shared between the two beyond
# torch, and the checkpoint is baked here.

FROM sfmstack/runtime-torch:1.0

ARG MAPANYTHING_COMMIT=3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9

# Which checkpoint gets baked. CC-BY-NC by default, matching the predecessor;
# facebook/map-anything-apache is the commercially usable variant, same
# architecture and same API. Rebuild with --build-arg to switch.
ARG MAPANYTHING_MODEL_ID=facebook/map-anything

# Overriding the torch base's /weights, which is a mounted-volume path. Here the
# caches ARE the delivery mechanism for the baked weights, so they have to live
# inside the image. See cache_weights.py -- MapAnything's own config cannot be
# json-serialised, so save_pretrained is not available as an alternative.
ENV HF_HOME=/opt/weights/hf \
    TORCH_HOME=/opt/weights/torch \
    XDG_CACHE_HOME=/opt/weights/cache

RUN pip install --no-cache-dir \
      "git+https://github.com/facebookresearch/map-anything.git@${MAPANYTHING_COMMIT}"

COPY docker/runtime-mapanything/cache_weights.py /tmp/cache_weights.py
RUN MAPANYTHING_MODEL_ID=${MAPANYTHING_MODEL_ID} python /tmp/cache_weights.py \
    && rm /tmp/cache_weights.py \
    && chmod -R a+rX /opt/weights

# The container runs as the host uid and cannot write into /opt/weights. Offline
# is therefore both correct and necessary: a cache miss becomes an immediate,
# legible error rather than a network fetch that fails later and less clearly.
ENV MAPANYTHING_MODEL_ID=${MAPANYTHING_MODEL_ID} \
    HF_HUB_OFFLINE=1
