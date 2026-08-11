# SparseMapAnything 1.0.0
#
#   docker build -t sfmstack/sparse-mapanything:1.0.0 \
#     -f modules/sparse_mapanything/Dockerfile .
#
# Build context is the repository root.
#
# The base carries mapanything, the baked checkpoint and the baked DINOv2 torch-hub
# cache. One module on this base today, unlike runtime-vggt's three -- the pose and
# dense counterparts are not ported.

FROM sfmstack/runtime-mapanything:1.0

COPY modules/sparse_mapanything /module
