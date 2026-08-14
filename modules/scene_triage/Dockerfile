# SceneTriage 1.0.0
#
#   docker build -t sfmstack/scene-triage:1.0.0 -f modules/scene_triage/Dockerfile .
#
# Build context is the repository root.
#
# The plain runtime, not runtime-torch. This module is deliberately CPU-only and
# small: it is the one that should be affordable to run on every scene without a
# decision, and a 2.5 GB torch layer it never imports would make it the same
# weight as a model. `SceneMotion` is the GPU half and pays that cost knowingly.
#
# headless: no display here, and the GUI wheel adds ~200 MB of stack that cannot
# work in a container. Core opencv only -- no SIFT, no contrib algorithms; this
# module uses boxFilter, Laplacian, goodFeaturesToTrack, matchTemplate, calcHist
# and compareHist, all of which are in the base package.

FROM sfmstack/runtime:1.0

# pillow is here only for EXIF. OpenCV decodes the pixels and discards metadata
# entirely, so the `source_dir` path -- which reads capture timestamps off the
# ORIGINAL files -- needs a second decoder. It is imported lazily, so a run
# without source_dir never touches it.
RUN pip install --no-cache-dir \
        "opencv-python-headless==4.10.0.84" \
        "pillow==12.3.0"

COPY modules/scene_triage /module
