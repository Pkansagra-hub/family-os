"""Static configuration assets shipped with the kernel."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
KERNEL_CONFIG_PATH = PACKAGE_ROOT / "kernel.yaml"
LOGGING_CONFIG_PATH = PACKAGE_ROOT / "logging.yaml"
