# FeatureTrackUnionFind 1.0.0
#
#   docker build -t sfmstack/track-union-find:1.0.0 -f modules/track_union_find/Dockerfile .
#
# Build context is the repository root.
#
# No pip line at all: this module needs nothing beyond the numpy that sfmkit
# already requires. The image is the runtime base plus /module, which is a few
# kilobytes of unique layer.

FROM sfmstack/runtime:1.0

COPY modules/track_union_find /module
