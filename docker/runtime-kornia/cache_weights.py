"""Download LoFTR's weights at image build time.

A real file rather than a Dockerfile heredoc: this daemon uses the legacy builder,
where a heredoc body is parsed as further Dockerfile instructions and `python -`
reads an empty stdin, exits 0, and bakes an image with no weights in it.
"""

import os

import kornia.feature as KF

# Constructing the matcher is what triggers the download into TORCH_HOME.
for setting in ("indoor", "outdoor"):
    KF.LoFTR(pretrained=setting).eval()

print(f"cached LoFTR weights under {os.environ.get('TORCH_HOME', '~/.cache/torch')}")
