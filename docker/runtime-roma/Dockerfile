# sfmstack/runtime-roma:1.0
#
#   docker build -t sfmstack/runtime-roma:1.0 -f docker/runtime-roma/Dockerfile .
#
# RoMa's weights are downloaded from the authors' release URLs on first use, so
# they are fetched at BUILD time and cached in the image -- a module that downloads
# 1GB on its first job inside a container is a module that fails on an air-gapped
# host, an hour into a run.

FROM sfmstack/runtime-torch:1.0

RUN pip install --no-cache-dir "romatch==0.1.2"

COPY docker/runtime-roma/cache_weights.py /tmp/cache_weights.py
RUN python /tmp/cache_weights.py && rm /tmp/cache_weights.py
