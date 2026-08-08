# SceneLoader 1.0.0
#
#   docker build -t sfmstack/scene-loader:1.0.0 -f modules/scene_loader/Dockerfile .
#
# Build context is the repository root. Every module Dockerfile follows this
# skeleton: FROM the pinned runtime, install this module's dependencies, COPY the
# module directory to /module. Nothing else.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "pillow==12.3.0"

COPY modules/scene_loader /module
