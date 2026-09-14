"""`in_planning_corpus` matches whole path segments of the loader's image_dir.

A bare substring match let a corpus entry claim every capture whose name it
prefixes -- one numbered scan claiming the scans numbered ten times it, a
subject claiming its second session -- and those captures were then told their
readings were recall rather than out-of-sample.
"""
from types import SimpleNamespace

import pytest

from sfmorch.service import SfmService


def _membership(tmp_path, entries, image_dir):
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence" / "CORPUS.txt").write_text(
        "# comment\n\n" + "\n".join(entries) + "\n", encoding="utf-8")
    svc = SimpleNamespace(config=SimpleNamespace(skills_dir=tmp_path))
    scene = SimpleNamespace(manifest=SimpleNamespace(
        produced_by=SimpleNamespace(params={"image_dir": image_dir})))
    return SfmService._corpus_membership(svc, scene)


@pytest.mark.parametrize("image_dir, member", [
    ("/data/DTU/scan1", True),
    ("/data/DTU/scan1/", True),
    ("/data/DTU/scan11", False),
    ("/data/DTU/scan118", False),
    ("/data/ETH/relief/images/dslr_images_undistorted", True),
    ("/data/ETH/relief_2/images/dslr_images_undistorted", False),
])
def test_membership_is_by_whole_segment(tmp_path, image_dir, member):
    out = _membership(tmp_path, ["/DTU/scan1", "/ETH/relief"], image_dir)
    assert out["known"] and out["is_member"] is member


def test_no_corpus_record_is_unknown(tmp_path):
    svc = SimpleNamespace(config=SimpleNamespace(skills_dir=tmp_path))
    scene = SimpleNamespace(manifest=SimpleNamespace(
        produced_by=SimpleNamespace(params={"image_dir": "/data/DTU/scan1"})))
    assert SfmService._corpus_membership(svc, scene)["known"] is False
