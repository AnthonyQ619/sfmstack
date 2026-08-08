"""Download every LightGlue-family weight at image build time.

Run by docker/runtime-lightglue/Dockerfile. A separate file rather than an inline
heredoc because this daemon uses the legacy builder, where a Dockerfile heredoc is
not a heredoc -- the parser takes the first line as the whole RUN and treats the
script body as further Dockerfile instructions. `python -` then reads an empty
stdin, succeeds, and produces an image with no weights in it.
"""

import os

from lightglue import ALIKED, LightGlue, SuperPoint

# Instantiating each model is what triggers the download into TORCH_HOME.
# Tiny keypoint caps: we want the weights on disk, not a useful model.
SuperPoint(max_num_keypoints=16).eval()
ALIKED(max_num_keypoints=16).eval()
for features in ("superpoint", "aliked", "sift"):
    LightGlue(features=features).eval()

cache = os.environ.get("TORCH_HOME", "~/.cache/torch")
print(f"cached LightGlue-family weights under {cache}")
