# DenseMVS 1.0.0
#
#   docker build -t sfmstack/dense-mvs:1.0.0 -f modules/dense_mvs/Dockerfile .
#
# Build context is the repository root.
#
# `pycolmap-cuda12` rather than `pycolmap`. PatchMatch stereo is the one part of
# COLMAP with no CPU implementation at all -- `patch_match_stereo` raises without
# CUDA -- and the PyPI `pycolmap` wheels are built without it. This is the same
# package, same version, same import name, compiled with CUDA support, so the
# only thing that changes is the pip line.
#
# It does not build FROM runtime-torch: nothing here uses torch, and inheriting
# 5.8 GB to reach a CUDA runtime that the wheel already carries would be paying
# for the wrong thing twice.

FROM sfmstack/runtime:1.0

# The CUDA build links X11 session-management, which the CPU wheel does not, so
# it fails to import on the base's libgl1 alone: `libSM.so.6: cannot open shared
# object file`. Nothing here opens a window -- these are transitive dependencies
# of the OpenGL context COLMAP's mvs code links against.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "pycolmap-cuda12==4.1.1"

COPY modules/dense_mvs /module
