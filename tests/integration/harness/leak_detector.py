"""Leak detector for the live-system harness.

Tracks PIDs, TCP ports, and tempdirs allocated during a test run.
``assert_clean()`` fails the test if any tracked resource is still
alive at teardown — this is what catches "process didn't get cleaned
up" bugs early.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:  # psutil is required for accurate process liveness checks
    import psutil  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - psutil missing
    psutil = None  # type: ignore[assignment]


@dataclass
class LeakReport:
    live_pids: list[int] = field(default_factory=list)
    bound_ports: list[int] = field(default_factory=list)
    surviving_tempdirs: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (self.live_pids or self.bound_ports or self.surviving_tempdirs)

    def format(self) -> str:
        lines: list[str] = []
        if self.live_pids:
            lines.append(f"  - live pids: {self.live_pids}")
        if self.bound_ports:
            lines.append(f"  - still-bound ports: {self.bound_ports}")
        if self.surviving_tempdirs:
            lines.append(f"  - surviving tempdirs: {self.surviving_tempdirs}")
        return "Resource leaks detected:\n" + "\n".join(lines)


class LeakDetector:
    """Track resources and detect leaks at teardown.

    Usage::

        det = LeakDetector()
        det.track_pid(123)
        det.track_port(45678)
        det.track_tempdir(Path("/tmp/foo"))
        ...
        report = det.collect()
        det.assert_clean()
    """

    def __init__(self) -> None:
        self._pids: set[int] = set()
        self._ports: set[int] = set()
        self._tempdirs: set[Path] = set()

    # -- tracking ----------------------------------------------------------
    def track_pid(self, pid: int) -> None:
        self._pids.add(pid)

    def untrack_pid(self, pid: int) -> None:
        self._pids.discard(pid)

    def track_port(self, port: int) -> None:
        self._ports.add(port)

    def untrack_port(self, port: int) -> None:
        self._ports.discard(port)

    def track_tempdir(self, path: Path | str) -> None:
        self._tempdirs.add(Path(path))

    def untrack_tempdir(self, path: Path | str) -> None:
        self._tempdirs.discard(Path(path))

    # -- inspection --------------------------------------------------------
    def collect(self) -> LeakReport:
        report = LeakReport()
        for pid in self._pids:
            if _pid_alive(pid):
                report.live_pids.append(pid)
        for port in self._ports:
            if _port_bound(port):
                report.bound_ports.append(port)
        for d in self._tempdirs:
            if d.exists():
                report.surviving_tempdirs.append(str(d))
        return report

    def assert_clean(self) -> None:
        report = self.collect()
        if not report.is_clean:
            raise AssertionError(report.format())

    # -- iteration helpers -------------------------------------------------
    @property
    def tracked_pids(self) -> Iterable[int]:
        return tuple(self._pids)

    @property
    def tracked_ports(self) -> Iterable[int]:
        return tuple(self._ports)


def _pid_alive(pid: int) -> bool:
    if psutil is not None:
        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
    # Fallback: signal 0 probe
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _port_bound(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if ``port`` is currently in use on ``host``.

    We attempt to bind; success means the port is free.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return True
        return False
