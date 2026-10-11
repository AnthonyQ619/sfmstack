"""MatchQuantize: the binning logic, and proof that each of its guards can fire.

Hermetic. The adapter's three load-bearing functions are pure numpy over a match
table, so they are tested directly on constructed inputs rather than through a
container -- which is what lets a NEGATIVE control exist here at all. A guard that has
never been seen to fire is not evidence, and two of the four diagnostics on this module
are reachable only on inputs no real capture conveniently provides.

The synthetic tables are built, not sampled: a physical point seen in three pairs with
a different sub-pixel estimate each time is exactly the defect this module repairs, and
constructing it is the only way to assert the repair rather than hope for it.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from dataset_paths import MODULES, needs_cv2

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ad():
    spec = importlib.util.spec_from_file_location(
        "mq_adapter", MODULES / "match_quantize" / "adapter.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mq_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


def three_view_point(jitter: float):
    """One physical point seen in all three pairs of a three-image set.

    Each pair estimates it independently, so each endpoint is displaced by `jitter`
    pixels -- which is the detector-free property, not noise added for convenience.
    Returns (image_pair, pair_index, xy).
    """
    image_pair = np.array([[0, 1], [0, 2], [1, 2]], dtype=np.int64)
    base = np.array([100.0, 200.0])
    rows, pidx = [], []
    for p, (i, j) in enumerate(image_pair):
        a = base + jitter * np.array([p + 1, 0.0])
        b = base + jitter * np.array([0.0, p + 1])
        rows.append([a[0], a[1], b[0], b[1]])
        pidx.append(p)
    return image_pair, np.array(pidx, dtype=np.int64), np.array(rows, dtype=np.float64)


def quantize(ad, image_pair, pair_index, xy, grid, confidence=None):
    n_images = int(image_pair.max()) + 1
    cells, rows = ad.cell_tables(xy, pair_index, image_pair, n_images, grid)
    keep, dup, conflict = ad.resolve_conflicts(
        rows, pair_index, len(image_pair), confidence)
    frac, multi, total = ad.multiview_fraction(image_pair, pair_index, rows, keep)
    return dict(cells=cells, rows=rows, keep=keep, dup=dup, conflict=conflict,
                frac=frac, multi=multi, total=total)


# --------------------------------------------------------------- the repair itself

def test_a_coarse_enough_grid_makes_a_three_view_track(ad):
    """The whole point of the module, asserted on the defect it exists to repair."""
    ip, pi, xy = three_view_point(jitter=1.0)
    got = quantize(ad, ip, pi, xy, grid=8.0)
    assert got["multi"] == 1, "the three estimates should collapse to one point"
    assert got["frac"] == 1.0


def test_a_grid_finer_than_the_jitter_merges_nothing(ad):
    """The NEGATIVE control for multiview_fraction, and for no_multiview_tracks.

    If this passed at every grid size the metric would be measuring nothing. At a grid
    finer than the matcher's own pair-to-pair disagreement, no two estimates of one
    point share a cell and the output is the input renumbered -- which is the state the
    diagnostic reports.
    """
    ip, pi, xy = three_view_point(jitter=4.0)
    got = quantize(ad, ip, pi, xy, grid=0.25)
    assert got["multi"] == 0, "nothing should merge at a grid below the jitter"
    assert got["frac"] == 0.0


def test_multiview_fraction_rises_with_the_grid(ad):
    """Monotone in the direction the tuning page tells a reader to move it."""
    ip, pi, xy = three_view_point(jitter=2.0)
    fine = quantize(ad, ip, pi, xy, grid=0.5)["frac"]
    coarse = quantize(ad, ip, pi, xy, grid=16.0)["frac"]
    assert fine < coarse, f"fine {fine} should merge less than coarse {coarse}"


# ------------------------------------------------------------------ the partition

def test_rounding_is_a_partition_not_single_linkage(ad):
    """Three points in a chain, each within one jitter of the next.

    A radius merge chains them into one blob; lattice rounding cannot, because a cell
    boundary does not move with its members. This is the property that made a grid the
    right choice over an epsilon, so it is asserted rather than assumed.
    """
    image_pair = np.array([[0, 1]], dtype=np.int64)
    xs = [100.0, 101.0, 102.0]       # a 1px chain spanning 2px end to end
    xy = np.array([[x, 50.0, x, 50.0] for x in xs], dtype=np.float64)
    pi = np.zeros(len(xs), dtype=np.int64)
    cells, _rows = ad.cell_tables(xy, pi, image_pair, 2, 1.0)
    assert len(cells[0]) == 3, (
        "a 1px grid must keep three points 1px apart distinct; a radius merge at the "
        "same tolerance would chain them")


def test_one_cell_never_claims_two_partners_in_a_pair(ad):
    """The invariant a keypoint table has to satisfy, and what conflict_rate counts.

    Two correspondences whose endpoints land in one cell cannot both survive: one cell
    is one keypoint and a keypoint matches at most one keypoint per pair. The
    predecessor resolved this by last-write-wins, silently.
    """
    image_pair = np.array([[0, 1]], dtype=np.int64)
    xy = np.array([
        [100.0, 100.0, 300.0, 300.0],
        [100.4, 100.4, 500.0, 500.0],   # same cell in image 0, different in image 1
    ], dtype=np.float64)
    pi = np.zeros(2, dtype=np.int64)
    got = quantize(ad, image_pair, pi, xy, grid=4.0)
    assert got["keep"].sum() == 1, "only one of the two may survive"
    assert got["conflict"] == 1, "and the other must be counted, not dropped silently"
    kept = got["rows"][got["keep"]]
    assert len(set(map(tuple, kept))) == len(kept)


def test_confidence_decides_which_conflicting_match_survives(ad):
    """`on_conflict: confidence` must keep the matcher's preferred match, not row order.

    Run the same conflict twice with the ranking reversed; if row order were deciding
    it, the survivor would not move.
    """
    image_pair = np.array([[0, 1]], dtype=np.int64)
    xy = np.array([
        [100.0, 100.0, 300.0, 300.0],
        [100.4, 100.4, 500.0, 500.0],
    ], dtype=np.float64)
    pi = np.zeros(2, dtype=np.int64)
    first = quantize(ad, image_pair, pi, xy, 4.0, confidence=np.array([0.9, 0.1]))
    second = quantize(ad, image_pair, pi, xy, 4.0, confidence=np.array([0.1, 0.9]))
    assert np.flatnonzero(first["keep"]).tolist() == [0]
    assert np.flatnonzero(second["keep"]).tolist() == [1], (
        "the survivor must follow the confidence, not the row order")


# ------------------------------------------------------------------ the refusal

@needs_cv2
def test_detector_based_input_is_refused(ad, tmp_path):
    """The NEGATIVE control for already_indexed, through the real run() entry point.

    Exercised with a stand-in Ctx rather than a container: what is being asserted is
    that the guard fires BEFORE any work, which is a property of the function and not
    of the transport.
    """
    class Writer:
        def __init__(self): self.diags = []
        def diagnostic(self, code, **kw): self.diags.append(code); return self
        def save(self, *a, **k): raise AssertionError("must not write anything")
        def metric(self, *a, **k): raise AssertionError("must not report anything")
        def note(self, *a, **k): return self

    class Src:
        def load(self, file, array=None):
            if file == "pairs":
                return np.array([[0, 1]], dtype=np.int64)
            return {"xy": np.zeros((9, 4)), "pair_index": np.zeros(9, dtype=np.int64),
                    "feature_index": np.zeros((9, 2), dtype=np.int64)}

    class Params:
        grid_px, on_conflict, min_matches = 4.0, "confidence", 15
        ransac_threshold, ransac_confidence = 3.0, 0.999

    w = Writer()

    class Ctx:
        inputs = {"matches": Src()}
        params = Params()
        def output(self, _slot): return w
        def progress(self, *a, **k): pass

    with pytest.raises(ValueError, match="already carry feature_index"):
        ad.run.__wrapped__(Ctx()) if hasattr(ad.run, "__wrapped__") else ad.run(Ctx())
    assert "already_indexed" in w.diags, "the refusal must also leave a diagnostic"
