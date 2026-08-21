import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    n_images = int(scene.load("images", "size_current").shape[0])
    fraction = float(ctx.params.textureless)

    out = ctx.output("analysis")
    if not ctx.params.emit:
        out.note(f"Nothing measured yet across {n_images} images.")
        return
    out.save("metadata", n_images=np.int32(n_images))
    out.save(
        "texture",
        textureless_fraction=np.float64(fraction),
        # A per-image series beside the summary, which is the shape every real
        # analysis module has: the metric is a median and the advice attached to
        # it is per-frame. The last image is the soft one, so a test can assert
        # the brief carries enough to say WHICH.
        sharpness=np.linspace(1.0, 0.1, n_images),
    )
    out.metric(
        "textureless_fraction", fraction,
        direction="lower_better", healthy=(None, 0.5),
    )
    if fraction > 0.5:
        out.diagnostic(
            "textureless",
            severity="warn",
            message=f"{fraction:.0%} of the frame carries no texture.",
            suggested_actions=[
                "Read `empty_regions` before acting - the fraction cannot say "
                "whether the region was wanted.",
            ],
            see_also="SKILL.md",
        )
    out.note(f"{fraction:.0%} textureless across {n_images} images.")
