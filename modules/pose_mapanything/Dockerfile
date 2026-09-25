# PoseMapAnything 1.0.0
#
#   docker build -t sfmstack/runtime-mapanything:1.0 -f docker/runtime-mapanything/Dockerfile .
#   docker build -t sfmstack/pose-mapanything:1.0.0 -f modules/pose_mapanything/Dockerfile .
#
# Build context is the repository root. The base carries mapanything, the baked
# checkpoint and the baked DINOv2 torch-hub cache, and is shared with
# SparseMapAnything. HF_HOME is baked at /opt/weights/hf and the container runs
# offline: do NOT mount a host cache over it, which hides the weights and sends
# the run to the Hub.

FROM sfmstack/runtime-mapanything:1.0

COPY modules/pose_mapanything /module
