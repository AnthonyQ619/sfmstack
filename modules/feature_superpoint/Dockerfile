# FeatureDetectionSuperPoint 1.0.0
#
#   docker build -t sfmstack/feature-superpoint:1.0.0 -f modules/feature_superpoint/Dockerfile .
#
# Build context is the repository root.
#
# No pip line: torch and lightglue are in the base, and the weights are already
# baked there. This image is the base plus /module.

FROM sfmstack/runtime-lightglue:1.0

COPY modules/feature_superpoint /module
