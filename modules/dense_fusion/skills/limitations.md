---
module: DenseFusion
module_version: 1.1.0
curated_at: 2026-09-16
---

# What DenseFusion cannot do

## It needs a kept workspace

A `dense_model/v1` carries the fused points, and optionally depth arrays. Fusion
needs more than that: the normal maps and the record of which views agreed on each
pixel. Only `DenseMVS` with `keep_workspace: true` keeps them. The fix is always the
same replay — [SKILL](SKILL.md#before-you-run-it).

`DenseVGGT` output cannot be re-fused at all. It has no workspace to keep.

## It cannot reach anything PatchMatch decided

The correlation filters, the triangulation-angle floor, the number of agreeing views,
the geometric check and the choice of source views all shape the depth maps before
they exist. A hole in the depth maps is a hole in every cloud fused from them. If
the missing surface is textured and well-seen, the lever is a new `DenseMVS` run,
not a lower setting here.

## Its output cannot be re-fused

The output carries the new cloud and not the workspace — copying it would double the
largest thing on disk for no gain. Every setting is fused from the **original**
`DenseMVS` artifact, never from a previous `DenseFusion` output.

## The workspace stays on disk

It is several times the size of the cloud: on the order of a gigabyte for a
fifty-view capture at a low working resolution, and several gigabytes at the usual
one. It lives inside the `DenseMVS` artifact, and no tool available to an agent
removes it. Say in the run summary which artifact holds it, so it can be deleted
once a setting is chosen.

## It adds no PatchMatch metrics

`depth_map_completeness` and `fusion_ratio` describe the stereo pass, so read them
on the input artifact; they are the same for every setting fused from it.
`views_contributing` is reported when COLMAP returns image records and is null
otherwise. `mean_depth_confidence` is always null, for the same reason as in
`DenseMVS`.

## Resolution is fixed

Fusion works at the resolution the depth maps were computed at. `max_image_size`
can only lower it, and a lower fusion resolution than the stereo pass throws away
evidence that was paid for.
