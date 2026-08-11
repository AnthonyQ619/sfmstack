# PoseVGGT 1.0.0
#
#   docker build -t sfmstack/runtime-vggt:1.0 -f docker/runtime-vggt/Dockerfile .
#   docker build -t sfmstack/pose-vggt:1.0.0   -f modules/pose_vggt/Dockerfile .
#
# Build context is the repository root. The base carries torch, the vggt package
# and the 5 GB checkpoint, and is shared with SparseVGGT and DenseVGGT.

FROM sfmstack/runtime-vggt:1.0

RUN pip install --no-cache-dir "pillow==12.3.0"

COPY modules/pose_vggt /module
