---
campaign: features-only tracking
measured_at: 2026-10-03
captures: 8 corpus members
---

# The two trackers that consume features, not matches

`FeatureTrackTapir` and `FeatureTrackVGGSfM` consume `features/v1`.
`FeatureTrackUnionFind` consumes `pairwise_matches/v1`.
[`plan/tracking.md`](../plan/tracking.md) describes all three at length and gives
the trade between them, so these two are routed — but it finds that chaining wins
precision on detector-based input by margins running from tens of percent to
several-fold, and detector-based input is the common case. A reader following that
file correctly does not reach a predictive tracker, which is why neither had run on
a single corpus capture before this campaign.

This campaign ran them anyway, to see what the file's conclusion costs. It holds
where the delivered table is already accurate. It inverts, by a margin far outside
the span test that file demands, where the delivered table is large and wrong.

## What was run

Eight corpus captures spanning `studio`, `indoor` and `outdoor`. Each tracker was
given the capture's **stored** `scene` and **stored SIFT** `features` artifacts, so
the loader, working resolution and detector are held fixed between the two
trackers. Sixteen runs, eleven completed, 3.3 minutes total on one A6000.

**The union-find column is the incumbent, not a matched control.** It is the track
table that capture actually delivered, built from whatever detector and matcher
that run chose — which is often not SIFT. It answers "would a features-only
tracker have been a better table here", not "is this tracker better than
union-find on identical input".

## Two preconditions that stop these modules cold

**Both refuse a scene whose images are not all the same resolution.** They stack
the frames into one tensor and track across the stack. Two of the eight captures
were refused on this ground, both at the first step, by both trackers. The module
says so in its error and names the fix — re-run the loader with a fixed resize —
but nothing said so before the tracker was chosen.

**One run failed inside the backend**, not on any property of the capture: a
missing compute engine under this container's cuDNN build, with the model's own
xFormers fallback warning beside it. Read a single failure of this shape as an
environment fault and retry before concluding anything about the scene.

## Tracks and transfer error against the delivered table

`trifocal_transfer_px` is the held-out transfer error; lower is better. `—` is a
refusal, `null` a check that could not run for want of held-out samples.

| capture | UF tracks | UF transfer | Tapir tracks | Tapir transfer | VGGSfM tracks | VGGSfM transfer |
|---|---:|---:|---:|---:|---:|---:|
| `DTU/scan1` | 2663 | **3.428** | 1658 | 4.812 | 4529 | 7.490 |
| `DTU/scan48` | 22611 | 10.465 | 2024 | 11.046 | 484 | **2.408** |
| `ETH/relief` | 6988 | **0.509** | 1451 | 4.307 | 3342 | 3.017 |
| `tum_vi/room3` | 51288 | 15.890 | 347 | 1.020 | 1425 | **0.667** |
| `advio/advio-07` | 5384 | 2.807 | 2288 | **1.803** | — | — |
| `euroc/V2_01_easy` | 1076 | null | 633 | null | 3337 | **2.627** |
| `ETH/courtyard` | — | — | — | — | — | — |
| `ETH/electro` | — | — | — | — | — | — |

**The trackers return one to two orders of magnitude fewer tracks and that is not
the deciding quantity.** On `tum_vi/room3` union-find returned 51288 tracks at
15.890 px; VGGSfM returned 1425 at 0.667. A track table that large with a transfer
error that high is mostly wrong, and 3% of its size at a twentieth of its error is
the better input to anything downstream.

**Where the delivered table is already accurate, union-find wins outright.** On
`ETH/relief` it reads 0.509 px against 3.017 and 4.307 — a well-textured outdoor
capture where the matcher graph is sound and there is nothing to rescue.

**The crossing is in the incumbent's own transfer error, not in the scene
description.** Union-find won both captures where its reading was under about
3.5 px and lost both where it was over 10. The one capture that splits the rule is
`advio/advio-07` at 2.807, where Tapir still won narrowly at 1.803 — the capture
whose coherent reflector sat between camera and scene, already the exception in
[`short-core-2026-10.md`](short-core-2026-10.md).

**VGGSfM rescued a check union-find could not run.** On `euroc/V2_01_easy` the
delivered table produced no held-out samples at all, so `trifocal_transfer_px`
came back null and the capture shipped with no transfer verdict. VGGSfM produced
714 samples and a reading of 2.627. `trifocal_samples` is what distinguishes a
null verdict from a good one, and before this campaign nothing routed it.

## What this does not settle

Track quality is not registration. A better transfer error on a smaller table may
still register fewer cameras, and no pose stage was run on these tracks. That is
the next measurement, and until it exists these readings narrow which tracker is
worth paying pose for rather than deciding a delivery.
