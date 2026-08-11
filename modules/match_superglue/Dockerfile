# FeatureMatchSuperGlue 1.0.0
#
#   docker build -t sfmstack/runtime-superglue:1.0 -f docker/runtime-superglue/Dockerfile .
#   docker build -t sfmstack/match-superglue:1.0.0 -f modules/match_superglue/Dockerfile .
#
# Build context is the repository root. The base carries torch and the upstream
# SuperGlue clone; its code and weights are Magic Leap's under a research-only
# licence, which is why they are cloned at build time rather than vendored.

FROM sfmstack/runtime-superglue:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_superglue /module
