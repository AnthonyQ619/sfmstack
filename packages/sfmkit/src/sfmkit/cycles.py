"""Three-view agreement over a `pairwise_matches/v1` table, shared by every matcher.

In sfmkit rather than in each module for the reason `split_rate` is: the number is
meant to be compared ACROSS matchers, and a rate measured at one module's chosen
tolerance says nothing about the one beside it.

WHAT THIS SEES THAT NOTHING ELSE AT THIS STAGE DOES. Geometric verification checks
each pair against its own two-view model, so a correspondence that is wrong but
epipolar-consistent survives it -- and on a capture with repeated structure, a
match displaced onto the next identical bay is epipolar-consistent by
construction when the camera slides along the repeat. Every published metric at
this stage is blind to it: `inlier_ratio` counts it as an inlier, `planarity` is
unmoved, `graph_components` and `min_image_degree` count the edge as connectivity.
The error only becomes visible when three views are compared, which is why it has
always been reported one stage later, by the tracker, as `inconsistent_rate`.

It does not need to wait. Chain the i->j correspondence with j->k and ask whether
the direct i->k match names the same keypoint. Both legs individually satisfy
their own two-view check; the disagreement is the evidence.

TWO RATES, NOT ONE, AND THE SPLIT IS NOT COSMETIC. A disagreement where the two
candidate keypoints sit a couple of pixels apart is one scene point detected
twice: it SPLITS a track and costs length. One where they sit tens of pixels apart
is a different piece of the scene: it MERGES two points and corrupts geometry.
Summed into a single number the cheap failure dominates by volume -- measured here
it is 70-78% of all disagreements -- and the metric ranks matchers backwards. On
one capture a joint matcher showed thirty-four times the raw disagreement rate of
a ratio test while producing ZERO of the geometry-corrupting kind against the
ratio test's fifty-four. The ungraded number would have chosen the worse branch.

They are named for the tracker metrics they anticipate: this stage's
`cycle_merge_rate` is what arrives later as `inconsistent_rate`, and
`cycle_split_rate` is what arrives later as `split_rate`.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .tracks import SPLIT_TOLERANCE_PX

__all__ = [
    "MERGE_TOLERANCE_PX",
    "SPLIT_TOLERANCE_PX",
    "MAX_CHAINS",
    "cycle_rates",
]

# Fixed by the type, not by the module, and not exposed as a parameter.
#
# The lower bound is the tracker's own split tolerance, reused rather than
# reinvented so a matching-stage reading is directly comparable to the tracking
# reading it predicts.
#
# The upper bound is twenty times that: far beyond any detector's localisation
# error and beyond every NMS radius in this repo, so a disagreement at that
# distance is a statement about which piece of the scene was matched rather than
# about where exactly it sits. Measured across three captures and two matchers,
# the two populations separate here -- a joint matcher's disagreements pile up
# below 20 px and stop by 40, while a ratio test's run out past 320.
MERGE_TOLERANCE_PX = 40.0

# Disagreements BETWEEN the two tolerances are counted in neither rate. They
# cannot be attributed: too far to be one point detected twice, too near to be
# confidently a different one. Reporting them in either direction would be
# inventing a verdict the measurement does not support.

# Chains are quadratic in matches per pair and cubic in images, and a dense
# matcher on a large set can offer hundreds of millions. Past this many the rate
# has long since converged, so triples are visited in a fixed order and the walk
# stops -- deterministic, because the same artifact must yield the same number.
MAX_CHAINS = 4_000_000


def cycle_rates(
    image_pair: np.ndarray,
    pair_index: np.ndarray,
    feature_index: np.ndarray | None,
    xy: np.ndarray,
) -> tuple[float | None, float | None, int]:
    """Return (merge_rate, split_rate, chains_tested).

    `(None, None, 0)` when the rates are not defined for this artifact, which is
    the honest answer in two cases and not a failure in either: a detector-free
    matcher publishes no `feature_index`, so there is no keypoint identity to
    agree about; and a view graph with no closed triple offers nothing to test --
    a sequential chain never revisits, so a matcher run at `pairing: sequential`
    reports null here rather than a flattering zero.
    """
    if feature_index is None or len(image_pair) == 0:
        return None, None, 0

    image_pair = np.asarray(image_pair)
    pair_index = np.asarray(pair_index)
    feature_index = np.asarray(feature_index)
    xy = np.asarray(xy, dtype=np.float64)

    # feature id -> its coordinate, and (a, b) -> {feature in a: feature in b}.
    # Both directions of every pair, so a chain can traverse an edge either way.
    link: dict[tuple[int, int], dict[int, int]] = defaultdict(dict)
    pos: dict[int, np.ndarray] = {}
    order = np.argsort(pair_index, kind="stable")
    bounds = np.searchsorted(pair_index[order], np.arange(len(image_pair) + 1))
    for p, (i, j) in enumerate(image_pair):
        rows = order[bounds[p]:bounds[p + 1]]
        if len(rows) == 0:
            continue
        fa_all, fb_all = feature_index[rows, 0], feature_index[rows, 1]
        fwd, rev = link[(int(i), int(j))], link[(int(j), int(i))]
        for r, fa, fb in zip(rows, fa_all, fb_all):
            fa, fb = int(fa), int(fb)
            fwd[fa] = fb
            rev[fb] = fa
            pos[fa] = xy[r, :2]
            pos[fb] = xy[r, 2:4]

    n_images = int(image_pair.max()) + 1
    chains = merged = split = 0

    for i in range(n_images):
        for j in range(i + 1, n_images):
            ij = link.get((i, j))
            if not ij:
                continue
            for k in range(j + 1, n_images):
                jk, ik = link.get((j, k)), link.get((i, k))
                if not jk or not ik:
                    continue
                # All three rotations of the triple, not just one. Anchoring only
                # at i tests the features seen in i, which is about a third of the
                # chains the triple offers -- and a merge is a RARE event, so
                # under-sampling it reads as a clean zero. Measured: a capture
                # with two structure-scale merges reported none from the single
                # anchor. The reversed orderings are not walked, because they
                # retest the same chains backwards.
                for a1, a2, a3 in ((i, j, k), (j, k, i), (k, i, j)):
                    first, second, direct_map = (
                        link.get((a1, a2)), link.get((a2, a3)), link.get((a1, a3))
                    )
                    if not first or not second or not direct_map:
                        continue
                    for fa, fb in first.items():
                        fc = second.get(fb)
                        if fc is None:
                            continue
                        direct = direct_map.get(fa)
                        if direct is None:
                            continue
                        chains += 1
                        if fc == direct:
                            continue
                        a, b = pos.get(fc), pos.get(direct)
                        if a is None or b is None:
                            continue
                        d = float(np.hypot(a[0] - b[0], a[1] - b[1]))
                        if d <= SPLIT_TOLERANCE_PX:
                            split += 1
                        elif d >= MERGE_TOLERANCE_PX:
                            merged += 1
                if chains >= MAX_CHAINS:
                    break
            if chains >= MAX_CHAINS:
                break
        if chains >= MAX_CHAINS:
            break

    if chains == 0:
        return None, None, 0
    return merged / chains, split / chains, chains
