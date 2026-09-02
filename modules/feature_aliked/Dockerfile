# FeatureDetectionALIKED 1.2.0
#
#   docker build -t sfmstack/feature-aliked:1.2.0 -f modules/feature_aliked/Dockerfile .
#
# Build context is the repository root. Same base as SuperPoint and LightGlue.

FROM sfmstack/runtime-lightglue:1.0

# The base image bakes only `aliked-n16`, while this module's `model` enum offers
# four variants. Selecting any of the other three sent the container to the
# network at RUN time, where it has none -- so the module advertised a capability
# it could not perform, and `aliked-n16rot`, the variant the skills prescribe for
# in-plane rotation, failed on exactly the captures it exists for.
#
# Fetched at BUILD time, where the network is available, so the runtime stays
# offline. The size assertion is the point: a 404 or an HTML error page would
# otherwise be written to the path and fail much later as a corrupt checkpoint.
RUN python3 -c "\
import urllib.request, pathlib; \
dst = pathlib.Path('/weights/hub/checkpoints'); \
dst.mkdir(parents=True, exist_ok=True); \
base = 'https://raw.githubusercontent.com/Shiaoming/ALIKED/main/models'; \
[(urllib.request.urlretrieve(base + '/' + n + '.pth', dst / (n + '.pth')), \
  print('baked', n, (dst / (n + '.pth')).stat().st_size)) \
 for n in ('aliked-t16', 'aliked-n16rot', 'aliked-n32')]; \
[__import__('sys').exit('checkpoint too small: ' + n) \
 for n in ('aliked-t16', 'aliked-n16rot', 'aliked-n32') \
 if (dst / (n + '.pth')).stat().st_size < 100000]"

COPY modules/feature_aliked /module
