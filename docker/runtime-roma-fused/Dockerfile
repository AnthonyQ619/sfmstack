# sfmstack/runtime-roma-fused:1.0
#
#   docker build -t sfmstack/runtime-roma-fused:1.0 -f docker/runtime-roma-fused/Dockerfile .
#
# RoMa with its FUSED local-correlation CUDA kernel, via the `fused-local-corr`
# extra. The kernel is what `use_custom_corr: true` needs.
#
# It does NOT build on sfmstack/runtime-torch:1.0. The wheel is compiled against
# the CUDA 13 runtime, so installing it replaces torch 2.6.0+cu124 with torch
# 2.11.0 and the whole CUDA 13 stack; `--no-deps` gets an image that imports
# `local_corr` and dies on libcudart.so.13. This base therefore starts from the
# slim runtime and takes the versions the extra requires, which is precisely the
# situation one-image-per-module exists to contain: nothing else in the repository
# has to move.

FROM sfmstack/runtime:1.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "romatch[fused-local-corr]==0.1.2"

COPY docker/runtime-roma/cache_weights.py /tmp/cache_weights.py
RUN python /tmp/cache_weights.py && rm /tmp/cache_weights.py

RUN python -c "import torch, local_corr; print('torch', torch.__version__, '| local_corr ok')"
