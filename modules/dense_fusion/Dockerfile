# DenseFusion 1.0.0
#
#   docker build -t sfmstack/dense-fusion:1.0.0 -f modules/dense_fusion/Dockerfile .
#
# Build context is the repository root.
#
# CPU only, deliberately. Fusion is a merge over depth maps that already exist;
# nothing here touches a GPU, which is the whole point of separating it from the
# PatchMatch pass that does.

FROM sfmstack/runtime:1.0

# The same three X11 libraries DenseMVS installs. The pycolmap wheel links them and
# will not load its C++ backend without them -- the failure is an import error that
# looks like a broken install, and in a module server it surfaces only as a container
# that never becomes healthy.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Deliberately the SAME wheel and version DenseMVS uses. Fusion here has to be the
# fusion that module would have applied, and a different COLMAP version reading the
# same workspace is not that.
RUN pip install --no-cache-dir "pycolmap-cuda12==4.1.1"

COPY modules/dense_fusion /module
