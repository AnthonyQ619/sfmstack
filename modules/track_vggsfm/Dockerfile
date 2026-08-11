# FeatureTrackVGGSfM 1.0.0
#
#   docker build -t sfmstack/track-vggsfm:1.0.0 -f modules/track_vggsfm/Dockerfile .
#
# Build context is the repository root.
#
# FROM runtime-lightglue rather than runtime-vggt, though the code comes from the
# vggt package. Two reasons: this module does not use the VGGT model at all, so the
# 5 GB VGGT-1B checkpoint baked into that base would be dead weight; and
# `vggt.dependency.vggsfm_utils` imports lightglue at module scope, which this base
# already has. The vggt package itself is small -- it is the checkpoint that is not.
#
# hydra-core and pycolmap are the other two module-scope imports on that path.
# Neither is used by anything this module calls; they are import-time dependencies
# of the file the tracker lives in.

FROM sfmstack/runtime-lightglue:1.0

ARG VGGT_COMMIT=a288dd0f14786c93483e45524328726ab7b1b4ce

RUN pip install --no-cache-dir \
      "pycolmap==4.1.1" \
      "hydra-core" \
      "git+https://github.com/facebookresearch/vggt.git@${VGGT_COMMIT}"

COPY modules/track_vggsfm/cache_weights.py /tmp/cache_weights.py
RUN python /tmp/cache_weights.py && rm /tmp/cache_weights.py \
    && chmod -R a+rX /opt/weights /weights

# Where cache_weights.py put the tracker. DINOv2 stays in TORCH_HOME, which the
# torch base already points at /weights, because upstream loads it by name.
ENV VGGSFM_TRACKER=/opt/weights/vggsfm_v2_tracker.pt

COPY modules/track_vggsfm /module
