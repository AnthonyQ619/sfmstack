# SparseTriangulation 1.0.0
#
#   docker build -t sfmstack/sparse-triangulation:1.0.0 -f modules/sparse_triangulation/Dockerfile .
#
# Build context is the repository root. Same pip line as the other OpenCV
# modules, so the layer is shared.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/sparse_triangulation /module
