# FeatureDetectionORB 1.0.0
#
#   docker build -t sfmstack/feature-orb:1.0.0 -f modules/feature_orb/Dockerfile .
#
# Build context is the repository root. Same pip line as the other OpenCV
# modules, so the layer is shared rather than duplicated.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/feature_orb /module
