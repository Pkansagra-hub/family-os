"""Static configuration assets shipped with the kernel."""

from __future__ import annotations

from pathlib import Path

from k0.config.postgres import (
    DatabaseSettings,
    PostgresSettings,
    get_database_settings,
    get_postgres_settings,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
KERNEL_CONFIG_PATH = PACKAGE_ROOT / "kernel.yaml"
LOGGING_CONFIG_PATH = PACKAGE_ROOT / "logging.yaml"

__all__ = [
    "DatabaseSettings",
    "KERNEL_CONFIG_PATH",
    "LOGGING_CONFIG_PATH",
    "PACKAGE_ROOT",
    "PostgresSettings",
    "get_database_settings",
    "get_postgres_settings",
]
