"""M0.E1.I1 — Verify k1.selfmodel package layout is present and importable.

Asserts every documented sub-path from
``docs/whiteboard/SERVICE_DESIGN_SELF_MODEL.md`` §7.1 exists on disk and
imports without error. This test is intentionally structural; it fails
loudly if a package is removed or renamed without updating the design
document.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# Repo root inferred from this test file's location:
# tests/k1/selfmodel/test_module_layout.py -> repo root is parents[3].
REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_ROOT = REPO_ROOT / "k1" / "selfmodel"


EXPECTED_SUBPACKAGES = [
    "ports",
    "adapters",
    "contracts",
    "service",
    "kernel",
    "obs",
    "events",
    "migrations",
]


EXPECTED_FILES = [
    "ARCHITECTURE.md",
    "selfmodel.mmd",
    "__init__.py",
]


def test_package_root_exists() -> None:
    assert PKG_ROOT.is_dir(), f"k1/selfmodel package directory missing at {PKG_ROOT}"


@pytest.mark.parametrize("filename", EXPECTED_FILES)
def test_root_files_exist(filename: str) -> None:
    target = PKG_ROOT / filename
    assert target.is_file(), f"required file missing: {target}"


@pytest.mark.parametrize("subpkg", EXPECTED_SUBPACKAGES)
def test_subpackage_directory_exists(subpkg: str) -> None:
    target = PKG_ROOT / subpkg
    assert target.is_dir(), f"required subpackage directory missing: {target}"


@pytest.mark.parametrize("subpkg", EXPECTED_SUBPACKAGES)
def test_subpackage_init_exists(subpkg: str) -> None:
    init = PKG_ROOT / subpkg / "__init__.py"
    assert init.is_file(), f"required __init__.py missing: {init}"


def test_root_package_importable() -> None:
    mod = importlib.import_module("k1.selfmodel")
    assert mod is not None
    assert hasattr(mod, "__all__")


@pytest.mark.parametrize("subpkg", EXPECTED_SUBPACKAGES)
def test_subpackage_importable(subpkg: str) -> None:
    mod = importlib.import_module(f"k1.selfmodel.{subpkg}")
    assert mod is not None
    assert hasattr(mod, "__all__")
