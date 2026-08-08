# BundleAdjustmentGlobal 1.0.0
#
#   docker build -t sfmstack/ba-global:1.0.0 -f modules/ba_global/Dockerfile .
#
# Build context is the repository root.
#
# pycolmap ships Ceres, SuiteSparse and a COLMAP build inside the wheel, so no
# apt layer is needed. The same pip line appears in every pycolmap module, so the
# layer is built once and shared.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "pycolmap==4.1.1"

COPY modules/ba_global /module
