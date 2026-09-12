# SparseVerification 1.0.0
#
#   docker build -t sfmstack/sparse-verification:1.0.0 -f modules/sparse_verification/Dockerfile .
#
# Build context is the repository root.
#
# The plain runtime, not runtime-torch. This runs after every final adjustment,
# automatically, so it has to be cheap enough never to be the reason to skip it.
# OpenCV is here for undistortPoints alone -- the distortion model has to be the
# one every producer used on its own observations -- and everything else is numpy.
#
# Requires a runtime base whose sfmkit registers a manifest's `types:` block in
# the container: this module produces a custom type, and a container that does
# not know it refuses to seal the artifact.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-python-headless==4.10.0.84"

COPY modules/sparse_verification /module
