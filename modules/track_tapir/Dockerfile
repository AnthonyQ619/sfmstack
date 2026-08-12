# FeatureTrackTapir 1.0.0
#
#   docker build -t sfmstack/track-tapir:1.0.0 -f modules/track_tapir/Dockerfile .
#
# Build context is the repository root.
#
# `--no-deps` on tapnet, deliberately. The package is JAX-first -- its declared
# dependencies are chex, jax, jaxline, optax, dm-haiku and more -- and none of that
# is on the torch code path. `tapnet.torch.tapir_model` needs numpy, torch, dm-tree
# and einshape, which are installed explicitly below. `tapnet/__init__.py` is lazy,
# so importing the torch submodule never touches the JAX ones.
#
# The alternative is a 2 GB JAX stack sitting unused next to torch, with two
# frameworks competing for the same GPU allocator.

FROM sfmstack/runtime-torch:1.0

# opencv-python-headless is here only for the trifocal_transfer_px metric, which
# needs a robust essential-matrix and PnP solve. sfmkit does not depend on OpenCV
# -- it is installed in every image including this one's 415 MB base -- so a module
# that calls that measurement provides it. It costs ~180 MB, which on this image is
# noticeable and on the learned trackers' multi-gigabyte ones is not.
RUN pip install --no-cache-dir "opencv-python-headless==4.10.0.84"


ARG TAPNET_COMMIT=c2cbab81cc06092b5f05bfe2da7bfec54e2079c9

RUN pip install --no-cache-dir "dm-tree" "einshape" \
    && pip install --no-cache-dir --no-deps \
      "git+https://github.com/google-deepmind/tapnet.git@${TAPNET_COMMIT}"

COPY modules/track_tapir/cache_weights.py /tmp/cache_weights.py
RUN python /tmp/cache_weights.py && rm /tmp/cache_weights.py \
    && chmod -R a+rX /opt/weights

ENV TAPIR_CHECKPOINT=/opt/weights/bootstapir_v2.pt

COPY modules/track_tapir /module
