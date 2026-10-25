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


def _with_index(tmp_path, rows):
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence" / "INDEX.md").write_text(
        "# Index\n\n| capture | pipeline |\n| --- | --- |\n" + "\n".join(rows) + "\n",
        encoding="utf-8")


def test_a_member_gets_its_index_row(tmp_path):
    _with_index(tmp_path, ["| [ETH/meadow](a.md#m) | RoMa → BA |",
                           "| [TT/Barn](a.md#b) | SIFT → BA |"])
    out = _membership(tmp_path, ["/ETH/meadow", "/tanks_and_temples/Barn"],
                      "/data/ETH/meadow/images/dslr_images_undistorted")
    assert out["worked_precedent"]["row"].startswith("| [ETH/meadow]")
    out = _membership(tmp_path, ["/ETH/meadow", "/tanks_and_temples/Barn"],
                      "/data/tanks_and_temples/Barn/n090/rgb")
    assert out["worked_precedent"]["row"].startswith("| [TT/Barn]")


def test_control_a_capture_outside_the_corpus_gets_no_row(tmp_path):
    _with_index(tmp_path, ["| [ETH/meadow](a.md#m) | RoMa → BA |"])
    out = _membership(tmp_path, ["/ETH/meadow"], "/data/ETH/elsewhere/images")
    assert out["is_member"] is False and "worked_precedent" not in out


def test_a_member_without_a_row_gets_none(tmp_path):
    _with_index(tmp_path, ["| [ETH/meadow](a.md#m) | RoMa → BA |"])
    out = _membership(tmp_path, ["/ETH/meadow", "/DTU/scan1"], "/data/DTU/scan1")
    assert out["is_member"] is True and "worked_precedent" not in out
