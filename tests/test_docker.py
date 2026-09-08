"""The Docker path, against real images and real data.

Skipped unless Docker is present, the module images are built, and the datasets
exist. Everything the container path shares with the subprocess path is already
covered hermetically in packages/sfmorch/tests/test_server.py; what is proven
*here* is the part that only Docker can prove -- that the modules are genuinely
isolated from one another and still interoperate.

    docker build -t sfmstack/runtime:1.0            -f docker/runtime/Dockerfile .
    docker build -t sfmstack/scene-loader:1.0.0     -f modules/scene_loader/Dockerfile .
    docker build -t sfmstack/feature-sift:1.0.0     -f modules/feature_sift/Dockerfile .
    docker build -t sfmstack/match-nn:1.0.0         -f modules/match_nn/Dockerfile .
    docker build -t sfmstack/track-union-find:1.0.0 -f modules/track_union_find/Dockerfile .
"""

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from sfmkit import ArtifactStore

from dataset_paths import DTU_CALIB, DTU_SCAN1, needs_dtu
from sfmorch import ContainerRunner, DockerBackend, GpuBroker, Orchestrator

# Read out of the manifests, never pinned here. A literal tag list is a silent
# skip waiting to happen: bump any module's version and the tag it names stops
# existing, `_images_built` returns False, and this whole file skips while
# reporting nothing wrong. That is strictly worse than the failure it replaces.
MODULES = ("SceneLoader", "FeatureDetectionSIFT", "FeatureMatchNN",
           "FeatureTrackUnionFind", "SceneTriage")


def _image_of(module: str) -> str:
    manifest = REPO / "modules" / _DIRS[module] / "module.yaml"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("image:"):
            return line.split(maxsplit=1)[1].strip()
    raise AssertionError(f"no image: line in {manifest}")


_DIRS = {
    "SceneLoader": "scene_loader",
    "FeatureDetectionSIFT": "feature_sift",
    "FeatureMatchNN": "match_nn",
    "FeatureTrackUnionFind": "track_union_find",
    "SceneTriage": "scene_triage",
}
REPO = Path(__file__).resolve().parents[1]
IMAGES = tuple(_image_of(m) for m in MODULES)


def _images_built() -> bool:
    if shutil.which("docker") is None:
        return False
    have = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True, text=True,
    ).stdout.split()
    return all(image in have for image in IMAGES)


needs_docker = pytest.mark.skipif(
    not _images_built(), reason="docker unavailable or module images not built"
)

pytestmark = [needs_docker, needs_dtu]


@pytest.fixture
def runner():
    r = ContainerRunner(
        DockerBackend(mounts=["/home/anthonyq/datasets"]),
        gpus=GpuBroker(devices=[]),
        idle_ttl=3600,
    )
    yield r
    r.shutdown()


@pytest.fixture
def orch(tmp_path, registry, runner):
    # The store is mounted into containers at its own absolute path, so it has to
    # be one the daemon can see.
    return Orchestrator(
        store=ArtifactStore(tmp_path.resolve() / "store"),
        registry=registry,
        runner=runner,
    )


def test_modules_do_not_share_dependencies(orch):
    """The claim the whole architecture rests on. SceneLoader has Pillow and no
    OpenCV; SIFT has OpenCV and no Pillow. Neither could run in the other's
    image, and they still compose.

    The union-find tracker used to assert `cv2` absent as well -- a module needing
    nothing beyond sfmkit paying for nothing beyond sfmkit. It acquired OpenCV when
    `trifocal_transfer_px` became a required metric of `tracks/v1`, which is a real
    cost honestly recorded rather than a property quietly dropped: 415 MB to
    557 MB, for a measurement rather than for the algorithm. What it still does not
    carry is the learned stack, which is the expensive half.
    """
    for image, present, absent in (
        (_image_of("SceneLoader"), "PIL", "cv2"),
        (_image_of("FeatureDetectionSIFT"), "cv2", "PIL"),
        (_image_of("FeatureMatchNN"), "cv2", "PIL"),
        (_image_of("FeatureTrackUnionFind"), "cv2", "torch"),
        # The reason scene analysis is two modules rather than one: the CPU half
        # carries no torch at all (578 MB) and is cheap enough to run on every
        # scene, where the flow half pays for the shared torch base (5.98 GB).
        # Splitting them is what keeps the always-run one affordable.
        (_image_of("SceneTriage"), "cv2", "torch"),
    ):
        probe = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "python", image, "-c",
             f"import importlib.util as u;"
             f"print(bool(u.find_spec('{present}')), bool(u.find_spec('{absent}')))"],
            capture_output=True, text=True, timeout=120,
        )
        assert probe.stdout.strip() == "True False", f"{image}: {probe.stdout}"


def test_provenance_records_the_image_that_actually_ran(orch):
    """`image` is a tag and a tag is mutable, so it cannot answer "which software
    produced this artifact". Two builds of sfmstack/scene-loader:1.0.0 are the same
    string. Artifact ids are recipe-derived and do not cover the image either, so
    the digest is the only thing in the record that separates a result produced
    before a rebuild from one produced after.

    Read from the CONTAINER, so it is what ran rather than what the tag points at
    now.
    """
    scene = orch.run("SceneLoader", run_id="digest", params={
        "image_dir": str(DTU_SCAN1),
        "calibration_path": str(DTU_CALIB),
        "max_images": 2,
        "resize": "auto",
        "max_edge": 400,
    }).primary

    prov = scene.manifest.produced_by
    # From the live manifest, not a literal. What this test is about is that
    # provenance records the image that ACTUALLY ran and that its digest resolves --
    # a pinned tag turns that into a tripwire on every version bump, which has now
    # happened twice.
    assert prov.image == orch.registry.get("SceneLoader").image
    assert prov.image_digest.startswith("sha256:")

    live = subprocess.run(
        ["docker", "image", "inspect", "-f", "{{.Id}}", prov.image],
        capture_output=True, text=True, timeout=60,
    ).stdout.strip()
    assert prov.image_digest == live


@pytest.mark.parametrize("module", MODULES)
def test_the_image_still_carries_the_source_it_is_tagged_for(module):
    """A version tag does not pin behaviour, and the cache will not notice.

    The orchestrator's cache key is (module, module_version, slot, params, input
    ids). It does NOT cover adapter source, so an image built before an adapter
    edit keeps its tag, keeps satisfying the cache, and keeps running the old
    code -- while every skill file describes the new one.

    This is not hypothetical. The reference campaign's first attempt was
    invalidated by exactly this: an image at an unchanged version was running
    code from before the guard that stops one degenerate image pair from killing
    a whole exhaustive matching run, so a capture failed in a way the
    repository's own source says cannot happen. Fifteen of twenty-eight modules
    had drifted the same way.

    `tools/image_drift.py` is the same check over every module at once; this one
    is here so the suite fails rather than the next campaign.
    """
    src = REPO / "modules" / _DIRS[module]
    for name in ("adapter.py", "module.yaml"):
        want = hashlib.md5((src / name).read_bytes()).hexdigest()
        out = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "md5sum",
             _image_of(module), f"/module/{name}"],
            capture_output=True, text=True, timeout=180,
        )
        assert out.returncode == 0, f"cannot read {name} from the image: {out.stderr}"
        assert out.stdout.split()[0] == want, (
            f"{module}: the built image's {name} differs from "
            f"modules/{_DIRS[module]}/{name}. The image is stale at an unchanged "
            f"version tag -- rebuild it with tools/build_images.sh "
            f"{_DIRS[module]}, and re-run anything measured against it."
        )


def test_a_real_pipeline_runs_across_two_containers(orch):
    scene = orch.run("SceneLoader", run_id="docker", params={
        "image_dir": str(DTU_SCAN1),
        "calibration_path": str(DTU_CALIB),
        "max_images": 4,
        "resize": "auto",
        "max_edge": 800,
    }).primary

    feats = orch.run(
        "FeatureDetectionSIFT",
        run_id="docker",
        inputs={"scene": scene.id},
        params={"max_keypoints": 1024},
    ).primary

    assert scene.type == "scene/v1"
    assert feats.type == "features/v1"
    assert feats.load("descriptors", "desc").shape[1] == 128
    assert feats.manifest.inputs == [scene.id]


def test_the_whole_chain_runs_across_four_containers(orch, runner):
    """scene -> features -> pairs -> tracks, each stage in its own image with its
    own dependencies, sharing only the mounted store.

    `sampling: head` matters here. Uniformly sampling 6 of scan1's 49 images
    takes every eighth frame, and SIFT cannot bridge those baselines even with
    exhaustive pairing -- it yields 3 components and no track reaching a third
    view. Six contiguous frames connect completely."""
    scene = orch.run("SceneLoader", run_id="chain", params={
        "image_dir": str(DTU_SCAN1),
        "calibration_path": str(DTU_CALIB),
        "max_images": 6,
        "sampling": "head",
        "resize": "auto",
        "max_edge": 800,
    }).primary
    feats = orch.run(
        "FeatureDetectionSIFT", run_id="chain",
        inputs={"scene": scene.id}, params={"max_keypoints": 2048},
    ).primary
    matches = orch.run(
        "FeatureMatchNN", run_id="chain",
        inputs={"scene": scene.id, "features": feats.id},
        params={"pairing": "exhaustive"},
    ).primary
    tracks = orch.run(
        "FeatureTrackUnionFind", run_id="chain",
        inputs={"scene": scene.id, "matches": matches.id},
    ).primary

    assert matches.metric("graph_components") == 1
    assert matches.metric("pairs_matched") == 15  # every pair of 6 survived
    assert tracks.metric("track_count") > 1000
    assert tracks.metric("long_track_fraction") > 0.3
    assert tracks.manifest.inputs == [scene.id, matches.id]

    # Four distinct containers, one per module, all still alive and reusable.
    endpoints = runner.endpoints()
    assert len(endpoints) == 4
    assert len({e.handle for e in endpoints.values()}) == 4


def test_the_artifact_crosses_the_container_boundary_intact(orch):
    """The store is mounted at the same absolute path inside and outside, so an
    artifact written by one container resolves identically in the next."""
    scene = orch.run("SceneLoader", run_id="docker", params={
        "image_dir": str(DTU_SCAN1),
        "max_images": 3,
        "resize": "auto",
        "max_edge": 640,
    }).primary

    for rel in scene.load("images", "paths"):
        assert scene.resolve(str(rel)).exists()

    feats = orch.run(
        "FeatureDetectionSIFT", run_id="docker", inputs={"scene": scene.id}
    ).primary
    assert feats.metric("keypoints_per_image") > 0


def test_the_server_is_reused_between_jobs(orch, runner):
    scene = orch.run("SceneLoader", run_id="docker", params={
        "image_dir": str(DTU_SCAN1), "max_images": 3, "resize": "auto", "max_edge": 640,
    }).primary

    for k in (256, 512):
        orch.run(
            "FeatureDetectionSIFT", run_id="docker",
            inputs={"scene": scene.id}, params={"max_keypoints": k},
        )

    # Keyed by name@version, and the version comes from the live manifest rather
    # than a literal: what this test is about is that two runs of one module share
    # one endpoint, which a hardcoded version turns into a tripwire that fires on
    # every unrelated version bump.
    expected = {f"{m}@{orch.registry.get(m).version}"
                for m in ("SceneLoader", "FeatureDetectionSIFT")}
    endpoints = runner.endpoints()
    assert set(endpoints) == expected
    assert len({e.handle for e in endpoints.values()}) == 2


def test_artifacts_written_by_a_container_belong_to_the_host_user(orch):
    """Containers default to root, so without --user everything a module writes
    into the shared store is root-owned: the user cannot delete their own
    artifacts and a later in-process run cannot write beside them."""
    import os

    scene = orch.run("SceneLoader", run_id="docker", params={
        "image_dir": str(DTU_SCAN1), "max_images": 3, "resize": "auto", "max_edge": 640,
    }).primary

    stat = scene.root.stat()
    assert stat.st_uid == os.getuid()

    # And the payload written inside, not just the directory.
    image = scene.resolve(str(scene.load("images", "paths")[0]))
    assert image.stat().st_uid == os.getuid()


def _gpu_passthrough_works() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(
        ["docker", "run", "--rm", "--gpus", "device=0", "--entrypoint", "true",
         "sfmstack/runtime-torch:1.0"],
        capture_output=True,
    ).returncode == 0


needs_container_gpu = pytest.mark.skipif(
    not _gpu_passthrough_works(),
    reason="NVIDIA container toolkit not wired into the daemon",
)


@needs_container_gpu
def test_a_gpu_module_in_a_container_gets_the_device_it_was_leased(orch, tmp_path):
    """Three things at once, and only Docker can prove any of them: the daemon can
    hand a device in, the container sees exactly the leased one rather than all of
    them, and torch inside our image binds to it.

    The middle one is the point. `--gpus all` would pass this test's first
    assertion and break exclusive leasing, which is what keeps two modules off one
    device."""
    result = subprocess.run(
        ["docker", "run", "--rm", "--gpus", "device=5", "--entrypoint", "python",
         "sfmstack/runtime-lightglue:1.0", "-c",
         "import torch;print(torch.cuda.is_available(), torch.cuda.device_count())"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["True", "1"], result.stdout


@needs_container_gpu
def test_a_container_without_a_lease_sees_no_gpu(orch):
    """The default has to be off. A module that declares `gpu: false` and still
    sees eight devices will use one, and the broker's accounting becomes fiction."""
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python",
         "sfmstack/runtime-torch:1.0", "-c",
         "import torch;print(torch.cuda.is_available())"],
        capture_output=True, text=True,
    )
    assert result.stdout.strip() == "False", result.stdout


def test_shutdown_removes_the_containers(orch, runner):
    orch.run("SceneLoader", run_id="docker", params={
        "image_dir": str(DTU_SCAN1), "max_images": 3, "resize": "auto", "max_edge": 640,
    })
    handles = [e.handle for e in runner.endpoints().values()]
    runner.shutdown()

    running = subprocess.run(
        ["docker", "ps", "-q", "--no-trunc"], capture_output=True, text=True
    ).stdout
    assert all(h not in running for h in handles)
