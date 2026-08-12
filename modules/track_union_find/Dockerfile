# FeatureTrackUnionFind 1.0.0
#
#   docker build -t sfmstack/track-union-find:1.0.0 -f modules/track_union_find/Dockerfile .
#
# Build context is the repository root.
#
# One pip line, and only for a metric. Everything the algorithm itself does needs
# nothing beyond the numpy sfmkit already requires.

FROM sfmstack/runtime:1.0

# opencv-python-headless is here only for the trifocal_transfer_px metric, which
# needs a robust essential-matrix and PnP solve. sfmkit does not depend on OpenCV
# -- it is installed in every image including this one's 415 MB base -- so a module
# that calls that measurement provides it. It costs ~180 MB, which on this image is
# noticeable and on the learned trackers' multi-gigabyte ones is not.
RUN pip install --no-cache-dir "opencv-python-headless==4.10.0.84"


COPY modules/track_union_find /module
