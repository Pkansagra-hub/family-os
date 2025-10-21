"""SQLite driver implementation placeholder."""

from __future__ import annotations

from pathlib import Path


class SQLiteDriver:
    """Manage SQLite connections for the ACID cohort."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> None:
        raise NotImplementedError("SQLite driver connect not yet implemented")
