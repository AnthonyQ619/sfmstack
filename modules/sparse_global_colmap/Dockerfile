# SparseGlobalCOLMAP 1.0.0
#
#   docker build -t sfmstack/sparse-global-colmap:1.0.0 -f modules/sparse_global_colmap/Dockerfile .
#
# Build context is the repository root. Same pycolmap line as ba_global/ba_local
# and pose_incremental, so the layer is shared with all three.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "pycolmap==4.1.1"

COPY modules/sparse_global_colmap /module
