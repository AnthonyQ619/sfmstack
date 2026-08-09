# PoseEssentialToPnP 1.0.0
#
#   docker build -t sfmstack/pose-incremental:1.0.0 -f modules/pose_incremental/Dockerfile .
#
# Build context is the repository root.
#
# Same pip lines as feature_sift/match_nn (OpenCV) and ba_local/ba_global
# (pycolmap), so both layers are shared with those images. pycolmap is here for the
# in-loop local BA -- see module.yaml `local_ba`.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"
RUN pip install --no-cache-dir "pycolmap==4.1.1"

COPY modules/pose_incremental /module
