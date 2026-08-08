# FeatureMatchNN 1.0.0
#
#   docker build -t sfmstack/match-nn:1.0.0 -f modules/match_nn/Dockerfile .
#
# Build context is the repository root.
#
# The pip line is character-for-character the one in modules/feature_sift/Dockerfile.
# Same parent layer plus same command means Docker reuses the cached layer outright,
# so this image costs nothing beyond /module on disk. Keeping them identical is worth
# more than trimming to the smaller non-contrib wheel would be.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_nn /module
