---
module: FeatureMatchFLANN
module_version: 1.6.0
curated_at: 2026-08-07
---

# When FLANN is the wrong tool

## It is slower than brute force at ordinary scales

*Symptom:* the module works fine and takes longer than `FeatureMatchNN`.

Measured on a turntable capture of a compact object, 8 images, 4096 SIFT keypoints, exhaustive pairing: 4.2s
against 0.7s. With ORB: 3.2s against 0.3s.

*Why:* a fresh index is built for every pair, and brute force over
4096×4096 float32 descriptors is one well-optimised GEMM. The approximation has
nothing to save when the exact computation is already a single matrix multiply.

*What to do:* use `FeatureMatchNN`. This is not a tuning problem; it is the wrong
module for the problem size. FLANN pays off when descriptor counts are large enough
that the exact computation stops fitting comfortably — tens of thousands of
keypoints per image — or in a design that amortises one index over many queries,
which per-pair matching does not.

Recorded prominently because "approximate nearest neighbour is faster" is true in
general and false here, and the general claim is what leads people to reach for it.

## When the approximation is the problem

*Symptom:* `no_pairs`, or `inlier_ratio` well below what `FeatureMatchNN` gets on
the same features.

*The diagnostic:* run `FeatureMatchNN` on the same features artifact. It is the
same pipeline after the search, so any difference is the search.

- **NN succeeds, FLANN fails** → raise `checks`, or stop using FLANN.
- **Both fail** → the problem is the features or the pairing, not the search. See
  `FeatureMatchNN`'s limitations file.

`match_agreement` usually tells you this before you have to run the comparison.

## LSH on binary descriptors is the weaker path

*Symptom:* poor agreement with ORB descriptors that no amount of `lsh_tables`
fixes.

Hamming space is not metric in the way a KD-tree exploits, and LSH's recall is more
data-dependent than a KD-tree's — it degrades when the descriptor set has low
entropy, which happens on repetitive or low-texture scenes.

OpenCV's LSH implementation can also fail outright on degenerate descriptor sets
rather than returning nothing; this module catches that and treats the pair as
having produced no matches, which is the honest interpretation but means a silent
`cv2.error` is being absorbed. If `weak_pairs` is unexpectedly high with binary
descriptors, that is a plausible cause.

*What to do:* `FeatureMatchNN` with Hamming is exact and fast for ORB-sized
descriptor sets. There is very little reason to approximate a 32-byte comparison.

## What would make this module worth its place

Recorded because the honest current answer is "it usually is not":

- **Reusing one index per image across all its pairs**, rather than rebuilding per
  pair. With exhaustive pairing each image participates in N-1 pairs, so this is
  an N-fold reduction in index construction and would change the timing table
  completely. This is the real fix and it is a code change, not a parameter.
- **A GPU matcher.** If matching is genuinely the bottleneck, a GPU brute-force
  matcher is both exact and faster than any CPU approximation.

Until the first of those exists, treat this module as the reference
implementation of the approximate path rather than as the fast one.
