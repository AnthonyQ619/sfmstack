# SceneDescription 0.3.0
#
#   docker build -t sfmstack/scene-description:0.3.0 -f modules/scene_description/Dockerfile .
#
# Build context is the repository root.
#
# The smallest module image here: the plain runtime plus Pillow. No OpenCV, no
# torch, no model. It decodes images, downscales them, and pastes them into a
# grid -- and the thing it exists to produce comes from outside the container
# entirely.
#
# That is worth stating rather than leaving implicit. A module that shipped a
# vision model to describe the scene itself would be a multi-gigabyte image whose
# output could not be checked; this one is 20 MB over the base and its output is
# checkable for shape, though not for truth.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir "pillow==12.3.0"

COPY modules/scene_description /module
