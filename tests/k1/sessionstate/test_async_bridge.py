"""
Tests for k1.sessionstate.async_bridge -- AsyncSSMBridge.

Coverage targets:
    - All 10 properties pass-through correctly
    - All 6 read methods pass-through correctly
    - mutate / start / stop / checkpoint / restore are async (offloaded)
    - Return types preserved (MutationResult, StartResult, etc.)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from k1.sessionstate.async_bridge import AsyncSSMBridge
from k1.sessionstate.events import PressureLevel
from k1.sessionstate.manager import (
    CheckpointResult,
    ManagerState,
    MutationResult,
    RestoreResult,
    SessionSnapshot,
    StartResult,
    StopResult,
)

# ===================================================================
# Stub SessionStateManager
# ===================================================================


class StubSSM:
    """
    Minimal SessionStateManager stub.

    Provides all properties and methods that AsyncSSMBridge delegates to.
    """

    def __init__(self) -> None:
        self._session_id = "test-session-001"
        self._state = ManagerState.CREATED
        self._mutation_calls: list[dict] = []

    # -- Properties --
    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def state(self) -> ManagerState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == ManagerState.RUNNING

    @property
    def hot(self) -> str:
        return "hot-tier-stub"

    @property
    def warm(self) -> str:
        return "warm-tier-stub"

    @property
    def local_cold(self) -> str:
        return "local-cold-stub"

    @property
    def size_tracker(self) -> str:
        return "size-tracker-stub"

    @property
    def mutation_guard(self) -> str:
        return "mutation-guard-stub"

    @property
    def eviction_engine(self) -> str:
        return "eviction-engine-stub"

    @property
    def migration_engine(self) -> str:
        return "migration-engine-stub"

    # -- Read API --
    def get_section(self, name: str) -> str:
        return f"section:{name}"

    def get_hot(self) -> str:
        return "hot-tier-stub"

    def get_warm(self) -> str:
        return "warm-tier-stub"

    def get_all_section_sizes(self) -> Dict[str, int]:
        return {"control": 100, "beliefs_active": 200}

    def get_local_cold(self) -> str:
        return "local-cold-stub"

    def get_snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self._session_id,
            total_size_bytes=300,
            hot_size_bytes=100,
            warm_size_bytes=200,
            hot_utilization_pct=10.0,
            warm_utilization_pct=20.0,
            total_utilization_pct=15.0,
            pressure=PressureLevel.NORMAL,
            sections={},
            last_mutation_ms=0,
            is_running=self._state == ManagerState.RUNNING,
            timestamp_ms=1234567890,
        )

    # -- Write / Lifecycle --
    def mutate(
        self,
        section: str,
        operation: str,
        data: Any,
        estimated_bytes: Optional[int] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> MutationResult:
        self._mutation_calls.append({"section": section, "operation": operation, "data": data})
        return MutationResult(
            success=True,
            section=section,
            operation=operation,
            bytes_delta=10,
            new_size_bytes=10,
            cognitive_trace_id=cognitive_trace_id or "",
        )

    def start(
        self,
        restore_if_exists: bool = True,
        cognitive_trace_id: Optional[str] = None,
    ) -> StartResult:
        self._state = ManagerState.RUNNING
        return StartResult(
            success=True,
            session_id=self._session_id,
            cognitive_trace_id=cognitive_trace_id or "",
        )

    def stop(
        self,
        checkpoint_before_stop: bool = True,
        cognitive_trace_id: Optional[str] = None,
    ) -> StopResult:
        self._state = ManagerState.STOPPED
        return StopResult(
            success=True,
            cognitive_trace_id=cognitive_trace_id or "",
        )

    def checkpoint(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> CheckpointResult:
        return CheckpointResult(
            success=True,
            checkpoint_id="ckpt-001",
            cognitive_trace_id=cognitive_trace_id or "",
        )

    def restore(
        self,
        session_id: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> RestoreResult:
        return RestoreResult(
            success=True,
            source="local_cold",
            cognitive_trace_id=cognitive_trace_id or "",
        )


# ===================================================================
# Property pass-through tests
# ===================================================================


class TestAsyncSSMBridgeProperties:
    def test_session_id(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.session_id == "test-session-001"

    def test_state(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.state == ManagerState.CREATED

    def test_is_running(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.is_running is False

    def test_hot(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.hot == "hot-tier-stub"

    def test_warm(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.warm == "warm-tier-stub"

    def test_local_cold(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.local_cold == "local-cold-stub"

    def test_size_tracker(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.size_tracker == "size-tracker-stub"

    def test_mutation_guard(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.mutation_guard == "mutation-guard-stub"

    def test_eviction_engine(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.eviction_engine == "eviction-engine-stub"

    def test_migration_engine(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.migration_engine == "migration-engine-stub"


# ===================================================================
# Read API pass-through tests
# ===================================================================


class TestAsyncSSMBridgeReadAPI:
    def test_get_section(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.get_section("control") == "section:control"

    def test_get_hot(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.get_hot() == "hot-tier-stub"

    def test_get_warm(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.get_warm() == "warm-tier-stub"

    def test_get_all_section_sizes(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        sizes = bridge.get_all_section_sizes()
        assert sizes == {"control": 100, "beliefs_active": 200}

    def test_get_local_cold(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        assert bridge.get_local_cold() == "local-cold-stub"

    def test_get_snapshot_returns_session_snapshot(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        snap = bridge.get_snapshot()
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "test-session-001"


# ===================================================================
# Write API (async) tests
# ===================================================================


class TestAsyncSSMBridgeMutate:
    @pytest.mark.asyncio
    async def test_mutate_success(self) -> None:
        stub = StubSSM()
        bridge = AsyncSSMBridge(stub)
        result = await bridge.mutate(
            section="beliefs_active",
            operation="set",
            data={"key": "value"},
            cognitive_trace_id="trace-001",
        )
        assert isinstance(result, MutationResult)
        assert result.success is True
        assert result.section == "beliefs_active"
        assert len(stub._mutation_calls) == 1

    @pytest.mark.asyncio
    async def test_mutate_passes_all_args(self) -> None:
        stub = StubSSM()
        bridge = AsyncSSMBridge(stub)
        await bridge.mutate(
            section="control",
            operation="update",
            data={"turn": 5},
            estimated_bytes=128,
            cognitive_trace_id="trace-002",
        )
        call = stub._mutation_calls[0]
        assert call["section"] == "control"
        assert call["operation"] == "update"
        assert call["data"] == {"turn": 5}


# ===================================================================
# Lifecycle (async) tests
# ===================================================================


class TestAsyncSSMBridgeLifecycle:
    @pytest.mark.asyncio
    async def test_start(self) -> None:
        stub = StubSSM()
        bridge = AsyncSSMBridge(stub)
        result = await bridge.start(restore_if_exists=False, cognitive_trace_id="t-1")
        assert isinstance(result, StartResult)
        assert result.success is True
        assert stub.state == ManagerState.RUNNING

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        stub = StubSSM()
        stub._state = ManagerState.RUNNING
        bridge = AsyncSSMBridge(stub)
        result = await bridge.stop(checkpoint_before_stop=False, cognitive_trace_id="t-2")
        assert isinstance(result, StopResult)
        assert result.success is True
        assert stub.state == ManagerState.STOPPED

    @pytest.mark.asyncio
    async def test_checkpoint(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        result = await bridge.checkpoint(cognitive_trace_id="t-3")
        assert isinstance(result, CheckpointResult)
        assert result.success is True
        assert result.checkpoint_id == "ckpt-001"

    @pytest.mark.asyncio
    async def test_restore(self) -> None:
        bridge = AsyncSSMBridge(StubSSM())
        result = await bridge.restore(session_id="sess-abc", cognitive_trace_id="t-4")
        assert isinstance(result, RestoreResult)
        assert result.success is True
        assert result.source == "local_cold"
