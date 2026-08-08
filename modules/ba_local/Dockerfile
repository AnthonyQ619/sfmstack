# BundleAdjustmentLocal 1.0.0
#
#   docker build -t sfmstack/ba-local:1.0.0 -f modules/ba_local/Dockerfile .
#
# Build context is the repository root. Same pip line as ba_global, so the
# pycolmap layer is shared.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "pycolmap==4.1.1"

COPY modules/ba_local /module
