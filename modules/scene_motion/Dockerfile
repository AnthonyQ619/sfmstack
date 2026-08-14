# SceneMotion 1.0.0
#
#   docker build -t sfmstack/scene-motion:1.0.0 -f modules/scene_motion/Dockerfile .
#
# Build context is the repository root.
#
# RAFT ships inside torchvision, which the shared torch base already carries, so
# this image adds only OpenCV and a 20 MB checkpoint. That is the cheapest GPU
# module here by a wide margin -- worth knowing when deciding whether scene
# analysis is affordable to run by default.
#
# opencv-python-headless for the model fits: homography, fundamental and
# essential estimation with USAC_MAGSAC. sfmkit does not depend on OpenCV, so a
# module that needs a robust solver brings its own.

FROM sfmstack/runtime-torch:1.0

RUN pip install --no-cache-dir "opencv-python-headless==4.10.0.84"

COPY modules/scene_motion/cache_weights.py /tmp/cache_weights.py
RUN python /tmp/cache_weights.py && rm /tmp/cache_weights.py \
    && chmod -R a+rX /opt/weights

ENV RAFT_CHECKPOINT=/opt/weights/raft_large.pt

COPY modules/scene_motion /module
