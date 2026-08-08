# sfm-runtime -- the base every module image builds on.
#
# Carries exactly the contract layer and nothing else. Docker stores these layers
# once, so N module images cost `base + N * delta` rather than `N * full`, which
# is what makes strict one-image-per-module affordable.
#
#   docker build -t sfmstack/runtime:1.0 -f docker/runtime/Dockerfile .
#
# Build context is the repository root, so sfmkit can be copied in.

FROM python:3.11-slim

# libgl / libglib are needed by opencv and by several vendored model repos. They
# live here rather than in each module image because nearly every module ends up
# wanting them, and duplicating an apt layer across 23 images is the one thing
# layer sharing cannot fix.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY packages/sfmkit /opt/sfmkit
RUN pip install --no-cache-dir /opt/sfmkit

# Module images COPY their code to /module and are run as:
#   --module-dir /module --store <path> --port 8080
ENTRYPOINT ["python", "-m", "sfmkit.server"]
CMD ["--module-dir", "/module", "--store", "/store", "--host", "0.0.0.0", "--port", "8080"]

EXPOSE 8080
