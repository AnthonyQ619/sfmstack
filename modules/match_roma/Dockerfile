# FeatureMatchRoMa 1.0.0
#
#   docker build -t sfmstack/runtime-roma:1.0 -f docker/runtime-roma/Dockerfile .
#   docker build -t sfmstack/match-roma:1.0.0  -f modules/match_roma/Dockerfile .
#
# Build context is the repository root. The base carries torch, romatch and both
# weight sets baked in, so no job downloads anything.
#
# For `use_custom_corr: true`, build against sfmstack/runtime-roma-fused:1.0
# instead -- it carries RoMa's fused local-correlation kernel. Measured at 1024px
# on an A6000 the kernel is worth 3% of runtime and 40% of peak GPU memory
# (2.58 vs 4.26 GiB), and it costs a torch major version because the wheel is
# built against CUDA 13. Memory is the reason to take it, not speed.

FROM sfmstack/runtime-roma:1.0

RUN pip install --no-cache-dir "opencv-contrib-python-headless==5.0.0.93"

COPY modules/match_roma /module
