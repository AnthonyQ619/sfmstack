# sfm-runtime-torch -- the base every GPU module image builds on.
#
#   docker build -t sfmstack/runtime-torch:1.0 -f docker/runtime-torch/Dockerfile .
#
# Build context is the repository root.
#
# Why torch lives in a shared base rather than in each module image: it is ~2.5 GB
# and roughly a dozen of the 23 modules need it. Docker stores the layer once, so
# "one image per module" stays affordable -- which is the whole reason that rule is
# tenable. A module needing a DIFFERENT torch (a vendored repo pinning 2.11 when
# this is 2.6) does not build FROM here; it installs its own and pays full price.
# That is the correct outcome, and it is the case the old single-environment
# system could not express at all.
#
# No CUDA base image. The cu124 wheels bundle their own CUDA runtime, so the only
# host requirement is the NVIDIA driver, reached through `docker run --gpus`.
# nvidia/cuda:12.4-base would add ~250 MB to duplicate what the wheel carries.

FROM sfmstack/runtime:1.0

RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu124 \
        "torch==2.6.0" "torchvision==0.21.0"

# Torch reads HOME for its hub cache. Containers run as the host uid with no
# passwd entry, so HOME is forced to /tmp by DockerBackend; weights that must
# survive a container restart belong in a mounted volume, not here.
ENV TORCH_HOME=/weights \
    HF_HOME=/weights \
    XDG_CACHE_HOME=/weights

ENTRYPOINT ["python", "-m", "sfmkit.server"]
CMD ["--module-dir", "/module", "--store", "/store", "--host", "0.0.0.0", "--port", "8080"]

EXPOSE 8080
