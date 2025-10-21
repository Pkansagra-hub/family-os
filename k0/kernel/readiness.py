"""Readiness tracking utilities for the K0 kernel runtime."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ReadinessSnapshot:
    """Immutable snapshot describing readiness components."""

    migrations_applied: bool
    wal_replay_complete: bool

    @property
    def ready(self) -> bool:
        return self.migrations_applied and self.wal_replay_complete

    def asdict(self) -> Dict[str, bool]:
        return {
            "migrations_applied": self.migrations_applied,
            "wal_replay_complete": self.wal_replay_complete,
        }


class ReadinessState:
    """Thread-safe readiness tracker.

    Readiness depends on completion of schema migrations *and* WAL replay. The
    state is pessimistic by default (both flags false) so `/readyz` remains
    blocked until the bootstrap sequence explicitly marks each component as
    complete.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._migrations_applied = False
        self._wal_replay_complete = False

    def snapshot(self) -> ReadinessSnapshot:
        with self._lock:
            return ReadinessSnapshot(
                migrations_applied=self._migrations_applied,
                wal_replay_complete=self._wal_replay_complete,
            )

    def mark_migrations_complete(self) -> None:
        with self._lock:
            self._migrations_applied = True

    def mark_wal_replay_complete(self) -> None:
        with self._lock:
            self._wal_replay_complete = True

    def reset(self) -> None:
        with self._lock:
            self._migrations_applied = False
            self._wal_replay_complete = False


__all__ = ["ReadinessSnapshot", "ReadinessState"]
