# FeatureMatchFLANN 1.0.0
#
#   docker build -t sfmstack/match-flann:1.0.0 -f modules/match_flann/Dockerfile .
#
# Build context is the repository root. Same pip line as the other OpenCV
# modules, so the layer is shared.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_flann /module
