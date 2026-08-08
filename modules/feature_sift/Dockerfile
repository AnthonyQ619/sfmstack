# FeatureDetectionSIFT 1.0.0
#
#   docker build -t sfmstack/feature-sift:1.0.0 -f modules/feature_sift/Dockerfile .
#
# Build context is the repository root.
#
# headless: this container has no display and never will. The non-headless
# opencv wheel pulls in a GUI stack that cannot work here and adds ~200 MB.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/feature_sift /module
