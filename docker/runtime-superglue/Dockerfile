# sfmstack/runtime-superglue:1.0
#
#   docker build -t sfmstack/runtime-superglue:1.0 -f docker/runtime-superglue/Dockerfile .
#
# SuperGlue's code AND weights are Magic Leap's, under a research-only licence
# that forbids redistribution. They are therefore cloned from upstream at build
# time rather than vendored into this repository -- the predecessor kept a copy of
# both in its tree, which is convenient and is not ours to do.
#
# The clone is pinned to a commit so a rebuild is reproducible.

FROM sfmstack/runtime-torch:1.0

ARG SUPERGLUE_COMMIT=ddcf11f42e7e0732a0c4607648f9448ea8d73590

RUN git clone https://github.com/magicleap/SuperGluePretrainedNetwork /opt/superglue \
 && cd /opt/superglue \
 && git checkout ${SUPERGLUE_COMMIT} \
 && rm -rf .git assets

# The upstream repo is a demo script, not a package: `models/` sits at the root
# with no __init__ chain above it, so the path is added rather than pip-installed.
ENV PYTHONPATH=/opt/superglue:$PYTHONPATH

COPY docker/runtime-superglue/check_weights.py /tmp/check_weights.py
RUN python /tmp/check_weights.py && rm /tmp/check_weights.py
