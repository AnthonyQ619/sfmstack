"""Dataset locations and skip markers for the integration suite.

A module of its own rather than conftest, because two conftest.py files in one
pytest run collide on `import conftest` when neither directory is a package.
"""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULES = REPO / "modules"
DATASETS = Path("/home/anthonyq/datasets")

DTU_SCAN1 = DATASETS / "DTU" / "scan1"
DTU_CALIB = DATASETS / "DTU" / "calibration_DTU_new.npz"
ETH_COURTYARD = DATASETS / "ETH" / "courtyard" / "images" / "dslr_images_undistorted"
ETH_CALIB = (
    DATASETS / "ETH" / "courtyard" / "dslr_calibration_undistorted"
    / "calibration_ETH_new.npz"
)


def _importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


needs_dtu = pytest.mark.skipif(
    not DTU_SCAN1.is_dir() or not DTU_CALIB.exists(), reason="DTU not present"
)
needs_eth = pytest.mark.skipif(
    not ETH_COURTYARD.is_dir(), reason="ETH3D courtyard not present"
)
needs_pil = pytest.mark.skipif(not _importable("PIL"), reason="Pillow not installed")
needs_cv2 = pytest.mark.skipif(not _importable("cv2"), reason="OpenCV not installed")
