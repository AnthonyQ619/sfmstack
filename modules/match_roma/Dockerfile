# FeatureMatchRoMa 1.0.0
#
#   docker build -t sfmstack/runtime-roma:1.0 -f docker/runtime-roma/Dockerfile .
#   docker build -t sfmstack/match-roma:1.0.0  -f modules/match_roma/Dockerfile .
#
# Build context is the repository root. The base carries torch, romatch and both
# weight sets baked in, so no job downloads anything.

FROM sfmstack/runtime-roma:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_roma /module
