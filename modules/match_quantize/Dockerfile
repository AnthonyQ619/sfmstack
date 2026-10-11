# MatchQuantize 1.0.0
#
#   docker build -t sfmstack/match-quantize:1.0.0 -f modules/match_quantize/Dockerfile .
#
# Build context is the repository root.
#
# The pip line is character-for-character the one in modules/match_nn/Dockerfile and
# modules/feature_sift/Dockerfile. Same parent layer plus the same command means Docker
# reuses the cached layer outright, so this image costs nothing beyond /module on disk.
# opencv is here for ONE reason: re-measuring inlier_ratio on the output at the same
# threshold the classical matcher uses, which is the only way that metric is comparable
# across the stage. Nothing in the binning itself needs it.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_quantize /module
