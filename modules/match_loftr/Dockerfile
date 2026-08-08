# FeatureMatchLoFTR 1.0.0
#
#   docker build -t sfmstack/match-loftr:1.0.0 -f modules/match_loftr/Dockerfile .
#
# Build context is the repository root.
#
# Kornia lives in its own base rather than beside lightglue. The predecessor's two
# conda environments pinned kornia 0.8.1 and 0.7.1 -- LoFTR's default_cfg import
# path moved between them -- and reconciling that is exactly the problem this
# architecture removes by never putting them in one place.

FROM sfmstack/runtime-kornia:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_loftr /module
