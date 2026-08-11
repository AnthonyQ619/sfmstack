# SparseTriangulationGTSAM 1.0.0
#
#   docker build -t sfmstack/sparse-gtsam:1.0.0 -f modules/sparse_gtsam/Dockerfile .
#
# Build context is the repository root. OpenCV for undistortion (shared layer with
# the classical modules), Pillow for colour sampling, gtsam for the estimator.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"
RUN pip install --no-cache-dir "pillow==12.3.0" "gtsam==4.2.2"

COPY modules/sparse_gtsam /module
