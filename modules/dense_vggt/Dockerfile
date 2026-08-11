# DenseVGGT 1.0.0
#
#   docker build -t sfmstack/dense-vggt:1.0.0 -f modules/dense_vggt/Dockerfile .
#
# Build context is the repository root. Shares the VGGT base with PoseVGGT and
# SparseVGGT; each runs its own forward pass.

FROM sfmstack/runtime-vggt:1.0

RUN pip install --no-cache-dir "pillow==12.3.0"

COPY modules/dense_vggt /module
