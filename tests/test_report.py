"""The HTML report, against a real store built from the hermetic fixture modules.

No dataset and no Docker: what is under test is the arrangement of what artifacts
and run records already say, not any reconstruction.
"""

import importlib.util
import json
import shutil
import subprocess
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from sfmkit import ArtifactStore

from dataset_paths import REPO
from sfmorch import ModuleRegistry, Orchestrator
from sfmorch.run_record import Step

FIXTURES = REPO / "packages" / "sfmorch" / "tests" / "fixtures" / "modules"
# FakeDensifier lives apart from the main fixture set: several registry, service
# and MCP tests assert over that set directly -- counts, terminality, which types
# have no consumer -- so adding a module to it changes what those assertions mean.
EXTRA_FIXTURES = REPO / "packages" / "sfmorch" / "tests" / "fixtures" / "extra"


def _load_report_module():
    spec = importlib.util.spec_from_file_location(
        "sfm_report", REPO / "tools" / "sfm_report.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sfm_report"] = mod
    spec.loader.exec_module(mod)
    return mod


report = _load_report_module()


@pytest.fixture
def built(tmp_path):
    """A session with a superseded attempt, a varied parameter, and a failure."""
    registry = ModuleRegistry()
    registry.load_dir(FIXTURES)
    store = ArtifactStore(tmp_path / "store")
    orch = Orchestrator(store=store, registry=registry)

    scene = orch.run("MakeScene", run_id="r1", params={"n_images": 4}).primary
    features = orch.run(
        "FakeDetector", run_id="r1", inputs={"scene": scene.id},
        params={"max_keypoints": 16},
    ).primary

    # Two matcher attempts: the first is superseded by the second.
    orch.run("FakeMatcher", run_id="r1", inputs={"scene": scene.id, "features": features.id},
             params={"keep_ratio": 0.25})
    pairs = orch.run("FakeMatcher", run_id="r1", inputs={"scene": scene.id, "features": features.id},
                     params={"keep_ratio": 1.0}).primary
    tracks = orch.run("FakeTracker", run_id="r1", inputs={"scene": scene.id, "pairs": pairs.id}).primary
    sparse = orch.run(
        "FakeReconstructor", run_id="r1",
        inputs={"scene": scene.id, "tracks": tracks.id},
    ).primary

    # A failed step, written exactly as the orchestrator writes one: no outputs,
    # the inputs it was given, and the error. Provoking a genuine failure out of a
    # fixture module would test the fixture rather than the report.
    run = orch.open_run("r1")
    run.add(Step(
        index=-1,
        module="FakeReconstructor",
        module_version="1.0.0",
        params={"min_observe": 99},
        inputs={"scene": scene.id, "tracks": tracks.id},
        status="failed",
        duration_s=0.2,
        error="RuntimeError: ValueError: only 0 points triangulated at min_observe=99",
    ))
    return store, sparse.id


def collected(built):
    store, final = built
    steps = report.collect(store, final)
    return report.attempts(store, final, {s["id"] for s in steps})


# --------------------------------------------------------------------------- #
# What the lineage cannot say
# --------------------------------------------------------------------------- #


def test_a_failed_attempt_appears_even_though_it_produced_no_artifact(built):
    """The reason this section reads run.md instead of the store. A module that
    failed leaves nothing to walk lineage back through, so a report built from
    artifacts alone shows a pipeline that went right the first time."""
    tried = collected(built)
    failed = [e for e in tried["entries"] if e["status"] == "failed"]

    assert len(failed) == 1
    assert failed[0]["module"] == "FakeReconstructor"
    assert tried["counts"]["failed"] == 1


def test_the_error_shown_is_the_modules_own_not_the_transports(built):
    """Crossing a container boundary re-raises the module's exception inside the
    transport's, and each hop prepends a class name. Only the innermost describes
    what went wrong; 'RuntimeError' describes nothing."""
    tried = collected(built)
    error = next(e["error"] for e in tried["entries"] if e["status"] == "failed")

    assert error.startswith("ValueError:")
    assert "RuntimeError" not in error


def test_a_long_error_is_cut_at_a_word_boundary():
    long = "ValueError: " + "wordy " * 60 + "end."
    cut = report._innermost(long)
    assert cut.endswith("…")
    assert not cut.endswith(" …")


def test_an_attempt_that_worked_but_lost_is_marked_superseded(built):
    """The other thing lineage cannot say: an artifact nothing points at. It was
    produced successfully and then not used, which is a different fact from a
    failure and has to read differently."""
    tried = collected(built)
    matchers = [e for e in tried["entries"] if e["module"] == "FakeMatcher"]

    assert len(matchers) == 2
    assert {e["used"] for e in matchers} == {True, False}
    assert tried["counts"]["superseded"] >= 1


def test_only_the_parameters_that_actually_differ_are_surfaced(built):
    """A fifteen-key parameter block in a summary row is unreadable, and the part
    that explains why two attempts differed is the part that differed."""
    tried = collected(built)
    matchers = [e for e in tried["entries"] if e["module"] == "FakeMatcher"]

    assert all(set(e["differs"]) == {"keep_ratio"} for e in matchers)
    assert {e["differs"]["keep_ratio"] for e in matchers} == {0.25, 1.0}

    # A module attempted once has nothing to compare against, so nothing varied.
    detector = next(e for e in tried["entries"] if e["module"] == "FakeDetector")
    assert detector["differs"] == {}


def test_attempts_are_ordered_by_stage_then_by_when_they_were_run(built):
    """Alphabetical within a stage would put a bundle adjuster above the
    triangulator that fed it, which reads as a pipeline nobody ran."""
    tried = collected(built)
    stages = [e["stage"] for e in tried["entries"]]

    order = [report.STAGE_ORDER.index(s) for s in stages if s in report.STAGE_ORDER]
    assert order == sorted(order)


def test_a_failed_step_is_placed_by_what_it_consumed(built):
    """It produced no artifact to take a stage from, but it recorded its inputs,
    and those pin it as precisely as an output would have."""
    tried = collected(built)
    failed = next(e for e in tried["entries"] if e["status"] == "failed")
    assert failed["stage"] == "sparse"


def test_headline_numbers_are_the_ones_the_type_requires(built):
    """Two attempts at one stage have to be compared on the same numbers.
    Declaration order is per-module, so it cannot supply that."""
    tried = collected(built)
    entry = next(e for e in tried["entries"] if e["module"] == "FakeReconstructor"
                 and e["status"] == "ok")

    from sfmkit.schema import registry as core_types
    required = list(core_types().get("sparse_model/v1").metrics)
    assert [m["name"] for m in entry["metrics"]] == required[:3]


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_page_is_self_contained(built, tmp_path):
    """A report that needs the network is a blank page exactly when you most want
    to look at a result -- on a cluster node, offline, after the run finished."""
    store, final = built
    steps = report.collect(store, final)
    html = report.render(steps, None, collected(built), "test")

    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
    assert "cdn" not in html.lower()
    assert "What was tried" in html


def test_a_store_with_no_run_record_still_renders(built, tmp_path):
    """The section is additive. Pointed at a store whose runs directory is absent
    -- an artifact set copied off a machine, say -- the report drops it rather
    than failing."""
    store, final = built
    for child in Path(store.runs_dir).iterdir():
        for f in child.rglob("*"):
            f.unlink()
        child.rmdir()
    Path(store.runs_dir).rmdir()

    assert report.attempts(store, final, set()) is None
    assert report.render(report.collect(store, final), None, None, "test")


# --------------------------------------------------------------------------- #
# The dense cloud and its .ply
# --------------------------------------------------------------------------- #


@pytest.fixture
def densified(built):
    """The same run, carried one stage further into a dense_model/v1."""
    store, sparse_id = built
    registry = ModuleRegistry()
    registry.load_dir(FIXTURES)
    registry.load_dir(EXTRA_FIXTURES)
    orch = Orchestrator(store=store, registry=registry)
    scene_id = store.open(sparse_id).manifest.scene
    dense = orch.run(
        "FakeDensifier", run_id="r1",
        inputs={"scene": scene_id, "sparse": sparse_id},
    ).primary
    return store, dense.id, sparse_id


def test_a_dense_final_artifact_gets_a_cloud(densified):
    """Before this the viewer handled sparse_model/v1 only, so a pipeline that
    ended in a dense stage rendered a report with no reconstruction in it."""
    store, dense_id, _ = densified
    payload = report.scene_payload(store, dense_id, 60000)

    assert payload is not None
    assert [c["kind"] for c in payload["clouds"]] == ["sparse", "dense"]
    assert all(c["count"] > 0 for c in payload["clouds"])


def test_both_clouds_share_one_normalisation(densified):
    """Switching between sparse and dense must not move the view, and the cameras
    have to stay where they belong against either -- so one transform is applied
    to everything rather than each cloud being framed on its own."""
    import base64

    store, dense_id, _ = densified
    payload = report.scene_payload(store, dense_id, 60000)
    extent = {}
    for c in payload["clouds"]:
        raw = np.frombuffer(base64.b64decode(c["xyz"]), dtype="<f4").reshape(-1, 3)
        extent[c["kind"]] = float(np.abs(raw).max())

    # The fixture scatters dense points around the sparse ones, so a shared
    # normalisation keeps the two within a small factor. Per-cloud normalisation
    # would drive both to the same extent exactly.
    assert extent["dense"] != pytest.approx(extent["sparse"])
    assert 0.2 < extent["dense"] / extent["sparse"] < 5


def test_a_dense_cloud_offers_no_error_colouring(densified):
    """dense_model/v1 has no per-point error. A control that does nothing is
    worse than one that is absent, so error_max is null and the JS drops it."""
    store, dense_id, _ = densified
    clouds = {c["kind"]: c for c in report.scene_payload(store, dense_id, 60000)["clouds"]}
    assert clouds["dense"]["error_max"] is None
    assert clouds["sparse"]["error_max"] is not None


def test_cameras_are_reported_once_not_per_cloud(densified):
    """They come from the pose source, which is one artifact for the whole run --
    duplicating them per cloud would let the two disagree."""
    store, dense_id, sparse_id = densified
    payload = report.scene_payload(store, dense_id, 60000)

    assert len(payload["cameras"]) > 0
    assert payload["camera_source"] == "FakeReconstructor"
    assert not any("cameras" in c for c in payload["clouds"])


def test_a_pose_only_run_still_has_something_to_draw(built):
    """"If we declare only up to pose estimation, the poses are viewable." The
    normalisation then comes from the camera centres, since there are no points."""
    store, sparse_id = built
    sparse = store.open(sparse_id)
    # The sparse model IS the pose carrier in this fixture chain; asking for it
    # exercises the same path a poses/v1 final artifact would take.
    payload = report.scene_payload(store, sparse.id, 60000)
    assert len(payload["cameras"]) > 0


def test_downsampling_reports_what_it_dropped(densified):
    """`total` beside `count`, so the legend can say the viewer is showing a
    sample rather than implying the cloud is that size."""
    store, dense_id, _ = densified
    full = {c["kind"]: c for c in report.scene_payload(store, dense_id, 60000)["clouds"]}
    small = {c["kind"]: c for c in report.scene_payload(store, dense_id, 10)["clouds"]}

    assert small["dense"]["count"] == 10
    assert small["dense"]["total"] == full["dense"]["total"] == full["dense"]["count"]


def test_the_ply_sidecar_is_found_and_embedded(densified):
    store, dense_id, _ = densified
    files = report.downloads(store, dense_id, max_embed_mb=64)

    assert len(files) == 1
    assert files[0]["module"] == "FakeDensifier"
    assert files[0]["name"].endswith(".ply")
    assert files[0]["data"] is not None
    assert files[0]["points"] == store.open(dense_id).metric("point_count")


def test_an_embedded_ply_decodes_to_the_file_on_disk(densified):
    """The download has to be the artifact's own bytes, not a re-serialisation:
    the point of the link is that it is what an evaluation script would read."""
    import base64

    store, dense_id, _ = densified
    entry = report.downloads(store, dense_id, max_embed_mb=64)[0]
    assert base64.b64decode(entry["data"]) == Path(entry["path"]).read_bytes()


def test_an_oversized_ply_is_linked_by_path_rather_than_embedded(densified):
    """A 200 MB base64 blob is not a document. Above the cap the report says
    where the file is instead of refusing or producing something unopenable."""
    store, dense_id, _ = densified
    entry = report.downloads(store, dense_id, max_embed_mb=0.0)[0]

    assert entry["data"] is None
    assert Path(entry["path"]).exists()


def test_a_run_with_no_ply_offers_no_download(built):
    store, sparse_id = built
    assert report.downloads(store, sparse_id, max_embed_mb=64) == []


def test_the_download_link_reaches_the_page(densified):
    store, dense_id, _ = densified
    steps = report.collect(store, dense_id)
    html = report.render(
        steps, report.scene_payload(store, dense_id, 60000), None, "test",
        report.downloads(store, dense_id, max_embed_mb=64),
    )

    assert "downloads-card" in html
    assert 'data:application/octet-stream;base64' in html
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)


# --------------------------------------------------------------------------- #
# The pose export
# --------------------------------------------------------------------------- #


def test_poses_are_exported_in_two_forms(built):
    """A COLMAP images.txt for the tools that exist, and a json that states its
    own convention for the ones that do not."""
    store, sparse_id = built
    files = report.pose_exports(store, sparse_id)

    assert [f["name"].split("-", 1)[1] for f in files] == ["images.txt", "poses.json"]
    assert all(f["data"] for f in files)


def decoded(entry):
    import base64
    return base64.b64decode(entry["data"]).decode()


def test_images_txt_has_two_lines_per_image_in_colmap_order(built):
    """COLMAP's reader takes IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME followed
    by a POINTS2D line. Getting the pairing wrong makes the file load as half the
    images with garbage poses rather than fail."""
    store, sparse_id = built
    text = decoded(report.pose_exports(store, sparse_id)[0])

    body = [ln for ln in text.splitlines() if not ln.startswith("#")]
    data = [ln for ln in body if ln.strip()]
    assert len(body) == 2 * len(data)          # one blank POINTS2D line each
    for line in data:
        parts = line.split()
        assert len(parts) == 10
        assert parts[0].isdigit()
        float(parts[1]); float(parts[7])


def test_the_exported_quaternion_reproduces_the_rotation(built):
    """The whole export is worthless if this is wrong, and it is wrong silently:
    a bad quaternion still parses and still evaluates, just against a rotation
    nobody estimated."""
    store, sparse_id = built
    entry = report.pose_exports(store, sparse_id)[1]
    document = json.loads(decoded(entry))

    for image in document["images"]:
        if not image["registered"]:
            continue
        R = np.asarray(image["cam_from_world"])[:, :3]
        w, x, y, z = image["quaternion_wxyz"]
        back = np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - z*w),     2*(x*z + y*w)],
            [2*(x*y + z*w),     1 - 2*(x*x + z*z), 2*(y*z - x*w)],
            [2*(x*z - y*w),     2*(y*z + x*w),     1 - 2*(x*x + y*y)],
        ])
        assert np.allclose(R, back, atol=1e-9)


def test_the_quaternion_survives_a_half_turn(built):
    """The naive w = sqrt(1 + trace)/2 divides by zero near 180 degrees, which is
    exactly where a pose evaluation cares."""
    R = np.diag([1.0, -1.0, -1.0])            # 180 degrees about x
    w, x, y, z = report.quaternion_wxyz(R)
    assert np.isfinite([w, x, y, z]).all()
    assert abs(w) < 1e-9 and abs(abs(x) - 1) < 1e-9


def test_the_quaternion_sign_is_pinned(built):
    """q and -q are the same rotation, so two exports of one pose would otherwise
    differ componentwise and a diff would look like a change."""
    R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert report.quaternion_wxyz(R)[0] >= 0
    assert report.quaternion_wxyz(R.T)[0] >= 0


def test_unregistered_images_are_named_in_json_and_absent_from_images_txt(built):
    """images.txt has no way to say "no pose". An evaluation that silently scored
    a missing camera as identity would be measuring nothing, so the json says so
    and the txt leaves it out."""
    store, sparse_id = built
    art = store.open(sparse_id)
    poses = art.load("poses")
    n = len(poses["valid"])

    document = json.loads(decoded(report.pose_exports(store, sparse_id)[1]))
    assert len(document["images"]) == n
    assert document["registered"] == int(np.asarray(poses["valid"]).sum())

    text = decoded(report.pose_exports(store, sparse_id)[0])
    data = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    assert len(data) == document["registered"]


def test_the_json_states_its_convention_rather_than_implying_it(built):
    store, sparse_id = built
    document = json.loads(decoded(report.pose_exports(store, sparse_id)[1]))
    assert "cam_from_world" in document["convention"]
    assert "X_camera" in document["convention"]


def test_a_run_with_no_poses_exports_nothing(built):
    store, sparse_id = built
    scene_id = store.open(sparse_id).manifest.scene
    assert report.pose_exports(store, scene_id) == []


# --------------------------------------------------------------------------- #
# The page's script, actually executed
# --------------------------------------------------------------------------- #

SHIM = Path(__file__).resolve().parent / "fixtures" / "report_dom_shim.js"

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def run_page(html: str, tmp_path: Path) -> str:
    """Execute the report's script against a minimal DOM and return its output.

    A syntax check cannot catch `$("#c-err")` returning null and `.remove()`
    throwing on it, and the failure mode is a blank viewer with an error only in
    a console nobody opens. This caught exactly that once already: a headline
    that still read `DATA.cloud.count` after the payload grew a `clouds` list.
    """
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    (tmp_path / "report.js").write_text(script)
    result = subprocess.run(
        ["node", "-e",
         f"require({str(SHIM)!r});"
         f"eval(require('fs').readFileSync({str(tmp_path / 'report.js')!r},'utf8'));"
         "console.log('OK', JSON.stringify(global.removed));"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout


@needs_node
def test_the_page_script_runs_for_a_sparse_run(built, tmp_path):
    store, sparse_id = built
    html = report.render(
        report.collect(store, sparse_id),
        report.scene_payload(store, sparse_id, 60000),
        collected(built), "test", report.pose_exports(store, sparse_id),
    )
    out = run_page(html, tmp_path)
    assert out.startswith("OK")
    # One cloud, so the sparse/dense selector is not offered.
    assert "c-clouds" in out


@needs_node
def test_the_page_script_runs_for_a_dense_run(densified, tmp_path):
    store, dense_id, _ = densified
    html = report.render(
        report.collect(store, dense_id),
        report.scene_payload(store, dense_id, 60000), None, "test",
        report.pose_exports(store, dense_id)
        + report.downloads(store, dense_id, max_embed_mb=64),
    )
    out = run_page(html, tmp_path)
    assert out.startswith("OK")
    # Two clouds and cameras: every control has a subject, so none is removed.
    assert "[]" in out


@needs_node
def test_the_page_script_runs_with_cameras_and_no_points(built, tmp_path):
    """"If we declare only up to pose estimation, the poses are viewable." The
    point and colour controls have no subject then and are removed."""
    store, sparse_id = built
    payload = report.scene_payload(store, sparse_id, 60000)
    payload["clouds"] = []
    html = report.render(report.collect(store, sparse_id), payload, None, "test")

    out = run_page(html, tmp_path)
    assert out.startswith("OK")
    assert "c-pts" in out and "c-rgb" in out


@needs_node
def test_the_page_script_runs_with_no_reconstruction_at_all(built, tmp_path):
    """Pointed at a scene or a feature set, the report is still a report -- the
    viewer hides itself rather than throwing."""
    store, sparse_id = built
    scene_id = store.open(sparse_id).manifest.scene
    html = report.render(report.collect(store, scene_id),
                         report.scene_payload(store, scene_id, 60000),
                         None, "test")
    assert run_page(html, tmp_path).startswith("OK")
