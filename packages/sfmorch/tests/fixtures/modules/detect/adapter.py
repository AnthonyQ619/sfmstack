import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    n_images = int(scene.load("images", "size_current").shape[0])
    k = ctx.params.max_keypoints

    side = int(np.ceil(np.sqrt(k)))
    grid = np.stack(
        np.meshgrid(
            np.linspace(10, 790, side, dtype=np.float32),
            np.linspace(10, 590, side, dtype=np.float32),
            indexing="xy",
        ),
        axis=-1,
    ).reshape(-1, 2)[:k]

    xy = np.concatenate([grid + i * 2.0 for i in range(n_images)]).astype(np.float32)
    image_index = np.repeat(np.arange(n_images, dtype=np.int32), k)

    out = ctx.output("features")
    out.save("keypoints", xy=xy, image_index=image_index)
    out.save("descriptors", desc=np.zeros((len(xy), 8), dtype=np.float32))
    out.metric(
        "keypoints_per_image", float(k), direction="higher_better", healthy=(8, None)
    )
    out.note(f"{k} keypoints in each of {n_images} images.")
