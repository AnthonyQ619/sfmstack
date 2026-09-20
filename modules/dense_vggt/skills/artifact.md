---
module: DenseVGGT
module_version: 1.2.0
curated_at: 2026-08-11
---

# Reading a DenseVGGT artifact

## Layout

`dense_model/v1`: `points` (xyz, rgb) and a `confidence` file. No `depth` maps —
see [limitations](limitations.md#no-depth-maps-in-the-artifact).

## `browse/cloud_views.png` — the one reading that is not a scalar

Three orthographic views of the delivered cloud, side by side in one image, written
whenever `write_cloud_views` is on. Fetch it with
`sfm_artifact_image(<artifact id>, 'browse/cloud_views.png')`.

**Two of the panels look from the plane the cameras occupy. The third looks down that
plane's axis — a direction no input image had.** That third panel is the one worth
spending attention on: a backdrop or support surface fused into the subject, a shell of
stray points standing off the true surface, and a surface reconstructed more than once
in slightly different places all sit *behind* the cloud from every camera and are only
visible from off the ring.

**Why an image is here at all.** Every other reading this module publishes is a single
number, and no single number separates a clean surface from a clean surface wrapped in
floaters. A cloud can carry a healthy point count, a healthy view count and a
plausible confidence while being visibly wrong.

**Read it as a check on the numbers, not as a measurement.** It is framed on the bulk
of the cloud, so points far outside that bulk sit at the frame edge or outside it; a
cloud that looks tidy here can still carry strays the frame does not reach. Nothing in
it is a quantity, and nothing in it should be quoted as one.

## The cloud is in the SUPPLIED poses' frame and scale

Not VGGT's. `depth_scale` is the scalar that got it there. Whether that scalar was
MEASURED or ASSUMED is the single most important thing about this artifact, and
`depth_scale_spread` being null is how you tell: null means no tracks were
supplied and the parameter was used.

## `confidence` is per point and unbounded

VGGT's own, carried through so a consumer can filter harder without re-running
inference. It is not a probability — means around 46 are normal — and it is not
comparable to any other module's confidence.
