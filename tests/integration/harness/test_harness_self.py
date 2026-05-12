"""Self-tests for the live-system harness (Epic 7.1).

These tests assume that:

* K0 is already running in Docker on ``localhost:8080`` (and ``5432``).
* psutil is installed in the test environment.

Tests marked ``requires_live_k0`` are auto-skipped (see conftest) when
the Docker stack is not up.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from .family_layout import (
    default_father_mother_kid_layout,
    single_father_layout,
)
from .k0_handle import K0Handle, K0NotReachableError
from .leak_detector import LeakDetector
from .live_system import LiveSystem
from .port_allocator import allocate_free_port
from .process_supervisor import ProcessSupervisor

# ---------------------------------------------------------------------------
# Pure-unit tests (no live K0 required)
# ---------------------------------------------------------------------------


class TestPortAllocator:
    def test_returns_free_port_above_zero(self) -> None:
        port = allocate_free_port()
        assert 1024 < port < 65536

    def test_returns_distinct_ports_in_burst(self) -> None:
        ports = {allocate_free_port() for _ in range(20)}
        # Not strictly guaranteed unique but should be in practice
        assert len(ports) >= 5


class TestLeakDetector:
    def test_clean_on_empty(self) -> None:
        det = LeakDetector()
        det.assert_clean()

    def test_detects_live_pid(self) -> None:
        det = LeakDetector()
        det.track_pid(os.getpid())  # current process is alive
        report = det.collect()
        assert os.getpid() in report.live_pids
        with pytest.raises(AssertionError):
            det.assert_clean()

    def test_untrack_clears(self) -> None:
        det = LeakDetector()
        det.track_pid(os.getpid())
        det.untrack_pid(os.getpid())
        det.assert_clean()

    def test_detects_bound_port(self, tmp_path: Path) -> None:
        det = LeakDetector()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            det.track_port(port)
            report = det.collect()
            assert port in report.bound_ports

    def test_detects_surviving_tempdir(self, tmp_path: Path) -> None:
        det = LeakDetector()
        det.track_tempdir(tmp_path)
        report = det.collect()
        assert str(tmp_path) in report.surviving_tempdirs


class TestFamilyLayout:
    def test_default_father_mother_kid(self) -> None:
        layout = default_father_mother_kid_layout()
        roles = [p.role for p in layout.people]
        assert roles == ["father", "mother", "kid"]
        assert layout.total_devices == 3

    def test_single_father(self) -> None:
        layout = single_father_layout()
        assert len(layout.people) == 1
        assert layout.people[0].role == "single"


# ---------------------------------------------------------------------------
# Live-K0 integration tests
# ---------------------------------------------------------------------------


@pytest.mark.requires_live_k0
class TestK0Handle:
    def test_attach_returns_ok_healthz(self) -> None:
        h = K0Handle.attach()
        payload = h.healthz()
        assert payload.get("status") == "ok"

    def test_metrics_endpoint_returns_text(self) -> None:
        h = K0Handle.attach()
        text = h.metrics()
        assert isinstance(text, str)
        # Prometheus exposition format is line-oriented
        assert "\n" in text

    def test_attach_fails_for_bogus_url(self) -> None:
        with pytest.raises(K0NotReachableError):
            K0Handle.attach(base_url="http://127.0.0.1:1", wait_seconds=0.5)


@pytest.mark.requires_live_k0
class TestProcessSupervisorAgainstSimpleChild:
    """Validate SIGTERM→SIGKILL behaviour with a trivial Python child."""

    def test_spawn_then_terminate_clean(self, tmp_path: Path) -> None:
        sup = ProcessSupervisor(grace_seconds=2.0)
        argv = ["python", "-c", "import time; time.sleep(60)"]
        h = sup.spawn("sleeper", argv, cwd=tmp_path, log_path=tmp_path / "child.log")
        assert h.is_alive()
        rc = sup.terminate(h)
        assert not h.is_alive()
        # On Windows CTRL_BREAK_EVENT may yield a non-zero rc; that's fine.
        assert rc is not None


# ---------------------------------------------------------------------------
# Full live-system smoke test
# ---------------------------------------------------------------------------


@pytest.mark.requires_live_k0
@pytest.mark.asyncio
class TestLiveSystemSmoke:
    async def test_attach_and_shutdown_single_father(self) -> None:
        layout = single_father_layout()
        async with LiveSystem(family=layout) as sys_:
            assert sys_.k0 is not None
            assert sys_.k0.healthz()["status"] == "ok"
            assert len(sys_.k1s) == 1
            k1 = sys_.k1s[0]
            # Subprocess should actually be alive
            assert k1.is_alive
            assert k1.health()["k0_reachable"] is True

    async def test_attach_and_shutdown_full_family(self) -> None:
        async with LiveSystem() as sys_:
            assert len(sys_.k1s) == 3
            roles = sorted({k1.person.role for k1 in sys_.k1s})
            assert roles == ["father", "kid", "mother"]
            for k1 in sys_.k1s:
                assert k1.is_alive
