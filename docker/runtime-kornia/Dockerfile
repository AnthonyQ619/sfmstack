# sfm-runtime-kornia -- base for the kornia-backed detector-free matchers.
#
#   docker build -t sfmstack/runtime-kornia:1.0 -f docker/runtime-kornia/Dockerfile .
#
# Build context is the repository root.
#
# Separate from runtime-lightglue on purpose. The predecessor's two conda
# environments pinned kornia 0.8.1 and 0.7.1 respectively -- LoFTR's `default_cfg`
# import path moved between them -- and that conflict is exactly what forced the
# old system into two environments neither of which ran the whole pipeline.
# Here the two stacks simply never meet.

FROM sfmstack/runtime-torch:1.0

RUN pip install --no-cache-dir "kornia==0.8.3"

COPY docker/runtime-kornia/cache_weights.py /tmp/cache_weights.py
RUN mkdir -p /weights \
    && python /tmp/cache_weights.py \
    && rm /tmp/cache_weights.py \
    && chmod -R a+rX /weights

ENTRYPOINT ["python", "-m", "sfmkit.server"]
CMD ["--module-dir", "/module", "--store", "/store", "--host", "0.0.0.0", "--port", "8080"]

EXPOSE 8080
