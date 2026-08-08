# FeatureMatchLightGlue 1.0.0
#
#   docker build -t sfmstack/match-lightglue:1.0.0 -f modules/match_lightglue/Dockerfile .
#
# Build context is the repository root.
#
# No pip line: torch and lightglue are in the base and the weights are baked
# there, so this image is the base plus /module. All three LightGlue-family
# modules share that 6.2 GB base exactly once on disk.

FROM sfmstack/runtime-lightglue:1.0

COPY modules/match_lightglue /module
