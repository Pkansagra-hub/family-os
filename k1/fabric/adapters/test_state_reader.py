"""
k1.fabric.adapters.test_state_reader -- Test SessionState adapter (5.2.2).

In-memory dict-based SessionState stub for standalone testing.
No real SessionState dependency.

Design:
  - Pure in-memory: Dict[session_id:section, data].
  - Pre-load sections via ``load()`` / ``load_many()`` before tests.
  - Thread-safe reads via RLock (test harness may run concurrent tasks).
  - Implements ISessionStateReader protocol structurally.
  - No external dependencies (no k1.sessionstate import).

Usage:
  reader = TestSessionStateReaderAdapter()
  reader.load("sess-1", "affective_now", {"emotion": "calm", "intensity": 0.3})
  reader.load("sess-1", "cognitive", {"load": "low"})

  data = reader.read_section("sess-1", "affective_now")
  assert data["emotion"] == "calm"

  snap = reader.get_snapshot("sess-1")
  assert snap.has_section("affective_now")

References:
  - ISessionStateReader (5.1.1)
  - FAB-01 (read-only, no writes)

Exports:
  TestSessionStateReaderAdapter
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot


class TestSessionStateReaderAdapter:
    """
    In-memory test adapter for ISessionStateReader.

    Pre-load sections with ``load()`` or ``load_many()``, then
    use ``read_section()``, ``read_sections()``, ``get_snapshot()``
    to read them back.

    Thread-safe via RLock for concurrent test scenarios.

    Attributes:
        _sections: Dict["{session_id}:{section_name}"] -> section_data
        _lock: RLock for thread safety
    """

    __slots__ = ("_sections", "_lock")

    def __init__(self) -> None:
        self._sections: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Test setup helpers
    # ------------------------------------------------------------------

    def load(
        self,
        session_id: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Pre-load a section for testing.

        Args:
            session_id: Session identifier.
            section: Section name (e.g. "affective_now").
            data: Section data as dict.
        """
        with self._lock:
            self._sections[f"{session_id}:{section}"] = data

    def load_many(
        self,
        session_id: str,
        sections: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        Pre-load multiple sections at once.

        Args:
            session_id: Session identifier.
            sections: Dict of section_name -> section_data.
        """
        with self._lock:
            for name, data in sections.items():
                self._sections[f"{session_id}:{name}"] = data

    def remove(self, session_id: str, section: str) -> bool:
        """
        Remove a pre-loaded section.

        Args:
            session_id: Session identifier.
            section: Section name.

        Returns:
            True if section existed and was removed, False otherwise.
        """
        with self._lock:
            key = f"{session_id}:{section}"
            if key in self._sections:
                del self._sections[key]
                return True
            return False

    def clear(self) -> None:
        """Remove all pre-loaded sections."""
        with self._lock:
            self._sections.clear()

    def section_count(self, session_id: Optional[str] = None) -> int:
        """
        Count pre-loaded sections.

        Args:
            session_id: If provided, count only for this session.
                If None, count all sections across all sessions.
        """
        with self._lock:
            if session_id is None:
                return len(self._sections)
            prefix = f"{session_id}:"
            return sum(1 for k in self._sections if k.startswith(prefix))

    # ------------------------------------------------------------------
    # ISessionStateReader protocol methods
    # ------------------------------------------------------------------

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Read a section from the in-memory store.

        Args:
            session_id: Session identifier.
            section: Section name.

        Returns:
            Section data dict, or None if not loaded.
        """
        with self._lock:
            return self._sections.get(f"{session_id}:{section}")

    def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        """
        Read multiple sections in a single call.

        Args:
            session_id: Session identifier.
            names: List of section names to read.

        Returns:
            Dict of section_name -> section_data.
            Missing sections are omitted.
        """
        result: Dict[str, Any] = {}
        with self._lock:
            for name in names:
                data = self._sections.get(f"{session_id}:{name}")
                if data is not None:
                    result[name] = data
        return result

    def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """
        Capture a snapshot of all sections for a session.

        Args:
            session_id: Session identifier.

        Returns:
            SessionSnapshot with all loaded sections for this session.
        """
        with self._lock:
            prefix = f"{session_id}:"
            sections = {
                k[len(prefix) :]: v for k, v in self._sections.items() if k.startswith(prefix)
            }
        return SessionSnapshot(
            session_id=session_id,
            sections=sections,
            timestamp_ms=int(time.time() * 1000),
        )

    def __repr__(self) -> str:
        with self._lock:
            return f"TestSessionStateReaderAdapter(" f"sections={len(self._sections)})"
