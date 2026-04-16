"""
MWSessionReader -- Reads SessionState via ISessionReadPort.

Section-agnostic: reads all sections except config.skip_sections.
Returns raw dict. No section-name hardcoding.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from k1.memory_writer.config import MWConfig
from k1.memory_writer.invariants import assert_mw02_read_latency
from k1.memory_writer.ports.session_read_port import ISessionReadPort


class MWSessionReader:
    """Reads SessionState sections via ISessionReadPort.

    Section-agnostic: reads all sections except config.skip_sections.
    Returns raw dict. No section-name hardcoding.
    """

    __slots__ = ("_port", "_config")

    def __init__(self, port: ISessionReadPort, config: MWConfig) -> None:
        self._port = port
        self._config = config

    async def read_snapshot(self) -> Dict[str, Any]:
        """Read all non-skipped sections in one atomic snapshot.

        Uses snapshot_all(exclude=config.skip_sections) from Phase 0.
        Measures latency for MW-02 enforcement.
        """
        start = time.perf_counter_ns()
        snapshot = await self._port.snapshot_all(exclude=self._config.skip_sections)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        assert_mw02_read_latency(elapsed_ms)
        return snapshot
