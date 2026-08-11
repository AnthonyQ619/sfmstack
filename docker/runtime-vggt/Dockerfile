# sfmstack/runtime-vggt:1.0
#
#   docker build -t sfmstack/runtime-vggt:1.0 -f docker/runtime-vggt/Dockerfile .
#
# Shared by PoseVGGT, SparseVGGT and DenseVGGT. One base, three modules: each
# fills exactly one payload type, and each runs its own forward pass. That
# recompute is the accepted cost of being able to swap any one of the three for a
# classical counterpart -- see docs/design/target-architecture.md, "Parked idea".
#
# The 5 GB checkpoint is baked in. A module that downloads it on its first job is
# a module that fails on an air-gapped host, minutes into a run.

FROM sfmstack/runtime-torch:1.0

ARG VGGT_COMMIT=a288dd0f14786c93483e45524328726ab7b1b4ce

RUN pip install --no-cache-dir \
      "git+https://github.com/facebookresearch/vggt.git@${VGGT_COMMIT}"

COPY docker/runtime-vggt/cache_weights.py /tmp/cache_weights.py
RUN python /tmp/cache_weights.py && rm /tmp/cache_weights.py

# Where cache_weights.py put it. Modules load from here rather than from the hub,
# so no job touches the network.
ENV VGGT_CHECKPOINT=/opt/weights/vggt-1b.pt
