# PoseFill 1.0.0
#
#   docker build -t sfmstack/pose-fill:1.1.0 -f modules/pose_fill/Dockerfile .
#
# Build context is the repository root.
#
# The plain runtime. This is a similarity fit over camera centres and nothing
# else -- no images are read, no network runs, and numpy is the only dependency.
# It has to be cheap, because it sits between a pose stage and a triangulation
# and the whole point of it is to be reachable without a second thought.

FROM sfmstack/runtime:1.0

COPY modules/pose_fill /module
