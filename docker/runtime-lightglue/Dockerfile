# sfm-runtime-lightglue -- base for the LightGlue-family modules.
#
#   docker build -t sfmstack/runtime-lightglue:1.0 -f docker/runtime-lightglue/Dockerfile .
#
# Build context is the repository root.
#
# One base for SuperPoint, ALIKED and LightGlue because they ship in the same
# package and share weights infrastructure. Each still gets its own module image
# FROM here; this only means the torch and lightglue layers are stored once.
#
# This is also the first module dependency installed straight from git rather than
# from an index, which is the case the architecture exists to make routine:
# `pip install git+...` inside a Dockerfile is the whole integration story.

FROM sfmstack/runtime-torch:1.0

RUN pip install --no-cache-dir \
        "git+https://github.com/cvg/LightGlue.git@main"

# Bake the weights into the image rather than downloading them at run time.
#
# Three reasons. A container that fetches weights on first use fails on an
# air-gapped host, silently re-downloads on every cold start because the cache is
# in the container's ephemeral layer, and turns a module's first call into a
# multi-minute stall that the duration estimator then learns as normal.
#
# TORCH_HOME is /weights (set in runtime-torch), so this populates a path that
# survives into the running container and is readable by the host uid the module
# server runs as.
COPY docker/runtime-lightglue/cache_weights.py /tmp/cache_weights.py
RUN mkdir -p /weights \
    && python /tmp/cache_weights.py \
    && rm /tmp/cache_weights.py \
    && chmod -R a+rX /weights

ENTRYPOINT ["python", "-m", "sfmkit.server"]
CMD ["--module-dir", "/module", "--store", "/store", "--host", "0.0.0.0", "--port", "8080"]

EXPOSE 8080
