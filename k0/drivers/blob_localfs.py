"""Local filesystem-backed blob driver placeholder."""

from __future__ import annotations

from pathlib import Path


class LocalBlobDriver:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def store(self, payload: bytes, fingerprint: str) -> Path:
        raise NotImplementedError("Blob store not yet implemented")
