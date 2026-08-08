"""The Docker path, against real images and real data.

Skipped unless Docker is present, the module images are built, and the datasets
exist. Everything the container path shares with the subprocess path is already
covered hermetically in packages/sfmorch/tests/test_server.py; what is proven
*here* is the part that only Docker can prove -- that the modules are genuinely
isolated from one another and still interoperate.

    docker build -t sfmstack/runtime:1.0      -f docker/runtime/Dockerfile .
    docker build -t sfmstack/scene-loader:1.0.0 -f modules/scene_loader/Dockerfile .
    docker build -t sfmstack/feature-sift:1.0.0 -f modules/feature_sift/Dockerfile .
"""

import shutil
import subprocess

import pytest
from sfmkit import ArtifactStore

from dataset_paths import DTU_CALIB, DTU_SCAN1, needs_dtu
from sfmorch import ContainerRunner, DockerBackend, GpuBroker, Orchestrator

IMAGES = ("sfmstack/scene-loader:1.0.0", "sfmstack/feature-sift:1.0.0")


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
    image, and they still compose."""
    for image, present, absent in (
        ("sfmstack/scene-loader:1.0.0", "PIL", "cv2"),
        ("sfmstack/feature-sift:1.0.0", "cv2", "PIL"),
    ):
        probe = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "python", image, "-c",
             f"import importlib.util as u;"
             f"print(bool(u.find_spec('{present}')), bool(u.find_spec('{absent}')))"],
            capture_output=True, text=True, timeout=120,
        )
        assert probe.stdout.strip() == "True False", f"{image}: {probe.stdout}"


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

    endpoints = runner.endpoints()
    assert set(endpoints) == {"SceneLoader@1.0.0", "FeatureDetectionSIFT@1.0.0"}
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
