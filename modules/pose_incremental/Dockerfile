# PoseEssentialToPnP 1.0.0
#
#   docker build -t sfmstack/pose-incremental:1.0.0 -f modules/pose_incremental/Dockerfile .
#
# Build context is the repository root.
#
# Same pip line as feature_sift and match_nn, so the OpenCV layer is shared.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/pose_incremental /module
