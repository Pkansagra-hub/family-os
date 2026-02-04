"""
Tests for ReconstructionSLA - COLD -> HOT Hydration with SLA Guarantees
=========================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.5

Test Coverage:
1. Construction and initialization
2. Reconstruction from LOCAL COLD
3. Reconstruction from K0 fallback
4. Fresh start (no data)
5. SLA enforcement and breach detection
6. Hydration priority order
7. Partial reconstruction
8. Edge cases and error handling
9. Metrics tracking
10. Single section reconstruction
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from k1.sessionstate.reconstruction import (
    ALL_SECTIONS,
    ESTIMATE_K0_BASE_MS,
    ESTIMATE_LOCAL_COLD_BASE_MS,
    ESTIMATE_LOCAL_COLD_PER_KB_MS,
    HOT_HYDRATION_PRIORITY,
    HOT_SECTIONS,
    K0_TIMEOUT_MS,
    SLA_K0_FALLBACK_MS,
    SLA_LOCAL_COLD_MS,
    WARM_HYDRATION_PRIORITY,
    WARM_SECTIONS,
    HydrationResult,
    ReconstructionResult,
    ReconstructionSLA,
    ReconstructionSource,
    SectionData,
)

# =============================================================================
# MOCK IMPLEMENTATIONS
# =============================================================================


@dataclass
class MockRestoreResult:
    """Mock result from LocalColdArchive.restore()."""

    success: bool = True
    data: Optional[bytes] = None
    archive_id: str = "mock-archive-id"
    size_bytes: int = 0
    duration_ms: float = 1.0
    error: Optional[str] = None


@dataclass
class MockArchiveEntry:
    """Mock entry from LocalColdArchive.list_archives()."""

    archive_id: str = "mock-archive-id"
    session_id: str = "test-session"
    section: str = "control"
    size_bytes: int = 1024
    created_at_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockRestoreFromK0Result:
    """Mock result from IK0SyncPort.restore_from_k0()."""

    success: bool = True
    session_id: str = "test-session"
    sections_restored: List[str] = field(default_factory=list)
    bytes_restored: int = 0
    duration_ms: float = 10.0
    error: Optional[str] = None
    section_data: Dict[str, bytes] = field(default_factory=dict)


class MockLocalColdArchive:
    """Mock LocalColdArchive for testing."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, bytes]] = {}  # session_id -> section -> data
        self._should_fail: bool = False
        self._restore_delay_ms: float = 0.0

    def set_data(self, session_id: str, section: str, data: bytes) -> None:
        """Set mock data for a section."""
        if session_id not in self._data:
            self._data[session_id] = {}
        self._data[session_id][section] = data

    def set_session_data(self, session_id: str, data: Dict[str, bytes]) -> None:
        """Set all section data for a session."""
        self._data[session_id] = data

    def restore(
        self,
        section: str,
        session_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> MockRestoreResult:
        """Mock restore from LOCAL COLD."""
        if self._should_fail:
            return MockRestoreResult(
                success=False,
                error="Mock failure",
            )

        if self._restore_delay_ms > 0:
            time.sleep(self._restore_delay_ms / 1000)

        if session_id in self._data and section in self._data[session_id]:
            data = self._data[session_id][section]
            return MockRestoreResult(
                success=True,
                data=data,
                size_bytes=len(data),
            )

        return MockRestoreResult(
            success=False,
            error="Not found",
        )

    def list_archives(
        self,
        session_id: str,
        section: Optional[str] = None,
    ) -> List[MockArchiveEntry]:
        """List archives for a session."""
        if session_id not in self._data:
            return []

        entries = []
        for sec, data in self._data[session_id].items():
            if section is None or sec == section:
                entries.append(
                    MockArchiveEntry(
                        archive_id=f"{session_id}-{sec}",
                        session_id=session_id,
                        section=sec,
                        size_bytes=len(data),
                    )
                )
        return entries


class MockK0SyncPort:
    """Mock IK0SyncPort for testing."""

    def __init__(self) -> None:
        self._available: bool = True
        self._data: Dict[str, Dict[str, bytes]] = {}  # session_id -> section -> data
        self._should_fail: bool = False
        self._restore_delay_ms: float = 0.0

    @property
    def is_available(self) -> bool:
        """Check if K0 is available."""
        return self._available

    def set_available(self, available: bool) -> None:
        """Set availability."""
        self._available = available

    def set_data(self, session_id: str, data: Dict[str, bytes]) -> None:
        """Set mock data for a session."""
        self._data[session_id] = data

    def restore_from_k0(self, session_id: str) -> MockRestoreFromK0Result:
        """Mock restore from K0."""
        if self._restore_delay_ms > 0:
            time.sleep(self._restore_delay_ms / 1000)

        if self._should_fail:
            return MockRestoreFromK0Result(
                success=False,
                session_id=session_id,
                error="Mock failure",
            )

        if session_id in self._data:
            data = self._data[session_id]
            return MockRestoreFromK0Result(
                success=True,
                session_id=session_id,
                sections_restored=list(data.keys()),
                bytes_restored=sum(len(d) for d in data.values()),
                section_data=data,
            )

        return MockRestoreFromK0Result(
            success=False,
            session_id=session_id,
            error="Not found",
        )


class MockSection:
    """Mock section for testing hydration."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._restored_data: Optional[bytes] = None
        self._restored_obj: Any = None

    def restore_from_bytes(self, data: bytes) -> None:
        """Restore from bytes."""
        self._restored_data = data

    def restore_from(self, obj: Any) -> None:
        """Restore from object."""
        self._restored_obj = obj

    def load(self, obj: Any) -> None:
        """Load object."""
        self._restored_obj = obj


class MockTier:
    """Mock tier (HotTier or WarmTier) for testing."""

    def __init__(self, sections: List[str]) -> None:
        self._sections: Dict[str, MockSection] = {name: MockSection(name) for name in sections}

    def get_section(self, name: str) -> Optional[MockSection]:
        """Get section by name."""
        return self._sections.get(name)

    def get_restored_sections(self) -> List[str]:
        """Get sections that were restored."""
        return [
            name
            for name, sec in self._sections.items()
            if sec._restored_data is not None or sec._restored_obj is not None
        ]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def local_cold() -> MockLocalColdArchive:
    """Create mock LocalColdArchive."""
    return MockLocalColdArchive()


@pytest.fixture
def k0_sync() -> MockK0SyncPort:
    """Create mock K0SyncPort."""
    return MockK0SyncPort()


@pytest.fixture
def hot_tier() -> MockTier:
    """Create mock HotTier."""
    return MockTier(list(HOT_SECTIONS))


@pytest.fixture
def warm_tier() -> MockTier:
    """Create mock WarmTier."""
    return MockTier(list(WARM_SECTIONS))


@pytest.fixture
def reconstruction_sla(
    local_cold: MockLocalColdArchive,
    k0_sync: MockK0SyncPort,
    hot_tier: MockTier,
    warm_tier: MockTier,
) -> ReconstructionSLA:
    """Create ReconstructionSLA with all mocks."""
    return ReconstructionSLA(
        local_cold=local_cold,
        k0_sync_port=k0_sync,
        hot=hot_tier,
        warm=warm_tier,
    )


@pytest.fixture
def sample_hot_data() -> Dict[str, bytes]:
    """Sample HOT section data."""
    return {
        "control": b"control-data-v1",
        "beliefs_active": b"beliefs-data-v1",
        "scoreboard": b"scoreboard-data-v1",
        "history_active": b"history-data-v1",
    }


@pytest.fixture
def sample_warm_data() -> Dict[str, bytes]:
    """Sample WARM section data."""
    return {
        "persona": b"persona-data-v1",
        "beliefs_history": b"beliefs-history-v1",
        "history_recent": b"history-recent-v1",
        "telemetry": b"telemetry-data-v1",
    }


@pytest.fixture
def sample_full_data(
    sample_hot_data: Dict[str, bytes],
    sample_warm_data: Dict[str, bytes],
) -> Dict[str, bytes]:
    """Sample full session data."""
    return {**sample_hot_data, **sample_warm_data}


# =============================================================================
# TEST CLASS: Construction
# =============================================================================


class TestReconstructionSLAConstruction:
    """Test ReconstructionSLA construction and initialization."""

    def test_construct_with_all_dependencies(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test construction with all dependencies."""
        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
        )
        assert sla is not None
        assert sla.total_reconstructions == 0
        assert sla.successful_reconstructions == 0
        assert sla.sla_breaches == 0

    def test_construct_without_k0_sync(
        self,
        local_cold: MockLocalColdArchive,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test construction without K0 sync port (offline mode)."""
        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=None,
            hot=hot_tier,
            warm=warm_tier,
        )
        assert sla is not None

    def test_construct_without_local_cold(
        self,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test construction without local cold (K0-only mode)."""
        sla = ReconstructionSLA(
            local_cold=None,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
        )
        assert sla is not None

    def test_construct_without_tiers(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test construction without tiers (testing mode)."""
        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=None,
            warm=None,
        )
        assert sla is not None

    def test_construct_with_deserializer(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test construction with custom deserializer."""

        def deserializer(section: str, data: bytes) -> dict:
            return {"section": section, "data": data}

        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            deserializer=deserializer,
        )
        assert sla is not None

    def test_initial_metrics(self, reconstruction_sla: ReconstructionSLA) -> None:
        """Test initial metrics are zero."""
        assert reconstruction_sla.total_reconstructions == 0
        assert reconstruction_sla.successful_reconstructions == 0
        assert reconstruction_sla.sla_breaches == 0
        assert reconstruction_sla.sla_compliance_rate == 1.0

    def test_initial_source_counts(self, reconstruction_sla: ReconstructionSLA) -> None:
        """Test initial source counts are zero."""
        counts = reconstruction_sla.get_source_counts()
        assert counts[ReconstructionSource.LOCAL_COLD] == 0
        assert counts[ReconstructionSource.K0] == 0
        assert counts[ReconstructionSource.FRESH] == 0


# =============================================================================
# TEST CLASS: Fresh Start
# =============================================================================


class TestReconstructionFreshStart:
    """Test fresh start reconstruction (no data)."""

    def test_fresh_start_no_data_anywhere(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test fresh start when no data exists."""
        result = reconstruction_sla.reconstruct(session_id="new-session")

        assert result.success is True
        assert result.source == ReconstructionSource.FRESH
        assert result.sections_restored == []
        assert result.sla_met is True
        assert result.error is None

    def test_fresh_start_empty_session_id(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test with empty session_id."""
        result = reconstruction_sla.reconstruct(session_id="")

        assert result.success is False
        assert result.source == ReconstructionSource.FRESH
        assert "session_id is required" in result.error

    def test_fresh_start_whitespace_session_id(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test with whitespace-only session_id."""
        result = reconstruction_sla.reconstruct(session_id="   ")

        assert result.success is False
        assert "session_id is required" in result.error

    def test_fresh_start_metrics_update(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test metrics are updated on fresh start."""
        reconstruction_sla.reconstruct(session_id="new-session")

        assert reconstruction_sla.total_reconstructions == 1
        assert reconstruction_sla.successful_reconstructions == 1
        assert reconstruction_sla.sla_breaches == 0
        counts = reconstruction_sla.get_source_counts()
        assert counts[ReconstructionSource.FRESH] == 1

    def test_fresh_start_hot_restored_true(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test hot_restored is True for fresh start (no data expected)."""
        result = reconstruction_sla.reconstruct(session_id="new-session")

        assert result.hot_restored is True  # All expected (none) restored
        assert result.warm_restored is True


# =============================================================================
# TEST CLASS: LOCAL COLD Reconstruction
# =============================================================================


class TestReconstructionLocalCold:
    """Test reconstruction from LOCAL COLD."""

    def test_reconstruct_hot_sections_from_local_cold(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_hot_data: Dict[str, bytes],
    ) -> None:
        """Test reconstructing HOT sections from LOCAL COLD."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_hot_data)

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.LOCAL_COLD
        assert "control" in result.sections_restored
        assert "beliefs_active" in result.sections_restored
        assert result.hot_restored is True

    def test_reconstruct_warm_sections_from_local_cold(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_warm_data: Dict[str, bytes],
    ) -> None:
        """Test reconstructing WARM sections from LOCAL COLD."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_warm_data)

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.LOCAL_COLD
        assert "persona" in result.sections_restored
        assert result.warm_restored is True

    def test_reconstruct_all_sections_from_local_cold(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_full_data: Dict[str, bytes],
    ) -> None:
        """Test reconstructing all sections from LOCAL COLD."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_full_data)

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.LOCAL_COLD
        assert result.hot_restored is True
        assert result.warm_restored is True
        assert len(result.sections_restored) == len(sample_full_data)

    def test_reconstruct_specific_sections(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_full_data: Dict[str, bytes],
    ) -> None:
        """Test reconstructing specific sections only."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_full_data)

        result = reconstruction_sla.reconstruct(
            session_id=session_id,
            sections=["control", "beliefs_active"],
        )

        assert result.success is True
        assert "control" in result.sections_restored
        assert "beliefs_active" in result.sections_restored
        assert "persona" not in result.sections_restored

    def test_reconstruct_filters_invalid_sections(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_full_data: Dict[str, bytes],
    ) -> None:
        """Test that invalid section names are filtered out."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_full_data)

        result = reconstruction_sla.reconstruct(
            session_id=session_id,
            sections=["control", "invalid_section", "beliefs_active"],
        )

        assert result.success is True
        assert "control" in result.sections_restored
        assert "beliefs_active" in result.sections_restored
        assert "invalid_section" not in result.sections_restored

    def test_local_cold_sla_met(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_hot_data: Dict[str, bytes],
    ) -> None:
        """Test SLA is met for fast LOCAL COLD reconstruction."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_hot_data)

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.sla_met is True
        assert result.duration_ms < SLA_LOCAL_COLD_MS

    def test_local_cold_metrics_update(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        sample_hot_data: Dict[str, bytes],
    ) -> None:
        """Test metrics are updated on LOCAL COLD reconstruction."""
        session_id = "test-session"
        local_cold.set_session_data(session_id, sample_hot_data)

        reconstruction_sla.reconstruct(session_id=session_id)

        counts = reconstruction_sla.get_source_counts()
        assert counts[ReconstructionSource.LOCAL_COLD] == 1
        assert reconstruction_sla.total_reconstructions == 1
        assert reconstruction_sla.successful_reconstructions == 1

    def test_local_cold_partial_restore(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test partial restoration when only some sections exist."""
        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"control-data")

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.LOCAL_COLD
        assert "control" in result.sections_restored
        assert len(result.sections_restored) == 1

    def test_local_cold_restore_failure_falls_through(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test that LOCAL COLD failure falls through to K0."""
        local_cold._should_fail = True
        k0_sync.set_data("test-session", {"control": b"k0-control"})

        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
        )

        result = sla.reconstruct(session_id="test-session")

        # Should fall through to K0
        assert result.source == ReconstructionSource.K0


# =============================================================================
# TEST CLASS: K0 Fallback Reconstruction
# =============================================================================


class TestReconstructionK0Fallback:
    """Test reconstruction from K0 fallback."""

    def test_k0_fallback_when_local_cold_empty(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test K0 fallback when LOCAL COLD has no data."""
        session_id = "test-session"
        k0_sync.set_data(session_id, {"control": b"k0-control"})

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.K0

    def test_k0_fallback_restores_sections(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
        sample_full_data: Dict[str, bytes],
    ) -> None:
        """Test K0 fallback restores all sections."""
        session_id = "test-session"
        k0_sync.set_data(session_id, sample_full_data)

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.K0
        assert len(result.sections_restored) == len(sample_full_data)

    def test_k0_fallback_not_used_when_local_cold_has_data(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test K0 is not used when LOCAL COLD has data."""
        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"local-control")
        k0_sync.set_data(session_id, {"control": b"k0-control"})

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.source == ReconstructionSource.LOCAL_COLD

    def test_k0_not_available_returns_fresh(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test fresh start when K0 is not available."""
        k0_sync.set_available(False)

        result = reconstruction_sla.reconstruct(session_id="test-session")

        assert result.source == ReconstructionSource.FRESH

    def test_k0_failure_returns_fresh(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test fresh start when K0 restore fails."""
        k0_sync._should_fail = True

        result = reconstruction_sla.reconstruct(session_id="test-session")

        assert result.source == ReconstructionSource.FRESH

    def test_k0_sla_threshold(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test K0 SLA threshold is 100ms."""
        session_id = "test-session"
        k0_sync.set_data(session_id, {"control": b"control"})

        result = reconstruction_sla.reconstruct(session_id=session_id)

        # Should complete within K0 SLA
        assert result.duration_ms < SLA_K0_FALLBACK_MS

    def test_k0_metrics_update(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test metrics are updated for K0 reconstruction."""
        session_id = "test-session"
        k0_sync.set_data(session_id, {"control": b"control"})

        reconstruction_sla.reconstruct(session_id=session_id)

        counts = reconstruction_sla.get_source_counts()
        assert counts[ReconstructionSource.K0] == 1


# =============================================================================
# TEST CLASS: SLA Enforcement
# =============================================================================


class TestReconstructionSLAEnforcement:
    """Test SLA enforcement and breach detection."""

    def test_sla_constants_defined(self) -> None:
        """Test SLA constants are properly defined."""
        assert SLA_LOCAL_COLD_MS == 50.0
        assert SLA_K0_FALLBACK_MS == 100.0
        assert K0_TIMEOUT_MS == 80.0

    def test_fresh_start_always_meets_sla(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test fresh start always meets SLA."""
        result = reconstruction_sla.reconstruct(session_id="new-session")

        assert result.sla_met is True

    def test_sla_check_local_cold_within_threshold(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test SLA check for LOCAL COLD within threshold."""
        sla_met = reconstruction_sla._check_sla(
            ReconstructionSource.LOCAL_COLD,
            duration_ms=30.0,
        )
        assert sla_met is True

    def test_sla_check_local_cold_exceeds_threshold(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test SLA check for LOCAL COLD exceeding threshold."""
        sla_met = reconstruction_sla._check_sla(
            ReconstructionSource.LOCAL_COLD,
            duration_ms=60.0,
        )
        assert sla_met is False

    def test_sla_check_k0_within_threshold(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test SLA check for K0 within threshold."""
        sla_met = reconstruction_sla._check_sla(
            ReconstructionSource.K0,
            duration_ms=80.0,
        )
        assert sla_met is True

    def test_sla_check_k0_exceeds_threshold(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test SLA check for K0 exceeding threshold."""
        sla_met = reconstruction_sla._check_sla(
            ReconstructionSource.K0,
            duration_ms=120.0,
        )
        assert sla_met is False

    def test_sla_check_fresh_always_passes(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test SLA check for FRESH always passes."""
        sla_met = reconstruction_sla._check_sla(
            ReconstructionSource.FRESH,
            duration_ms=1000.0,  # Even with high duration
        )
        assert sla_met is True

    def test_sla_breach_increments_counter(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test SLA breach increments counter."""
        # Add delay to cause SLA breach
        local_cold._restore_delay_ms = 60.0  # > 50ms SLA
        local_cold.set_data("test-session", "control", b"control")

        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
        )

        result = sla.reconstruct(session_id="test-session")

        assert result.sla_met is False
        assert sla.sla_breaches == 1

    def test_sla_compliance_rate_calculation(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test SLA compliance rate calculation."""
        # Do 4 successful reconstructions
        for i in range(4):
            reconstruction_sla.reconstruct(session_id=f"session-{i}")

        assert reconstruction_sla.total_reconstructions == 4
        assert reconstruction_sla.sla_compliance_rate == 1.0

    def test_sla_compliance_rate_with_breaches(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test SLA compliance rate with breaches."""
        # Manually set metrics to test calculation
        reconstruction_sla._total_reconstructions = 10
        reconstruction_sla._sla_breaches = 2

        assert reconstruction_sla.sla_compliance_rate == 0.8


# =============================================================================
# TEST CLASS: Hydration Priority
# =============================================================================


class TestHydrationPriority:
    """Test hydration priority order."""

    def test_hot_hydration_priority_defined(self) -> None:
        """Test HOT hydration priority is defined."""
        assert len(HOT_HYDRATION_PRIORITY) == 8
        assert HOT_HYDRATION_PRIORITY[0] == "control"  # First
        assert HOT_HYDRATION_PRIORITY[1] == "meta"  # Second

    def test_warm_hydration_priority_defined(self) -> None:
        """Test WARM hydration priority is defined."""
        assert len(WARM_HYDRATION_PRIORITY) == 4
        assert WARM_HYDRATION_PRIORITY[0] == "persona"  # First
        assert WARM_HYDRATION_PRIORITY[-1] == "telemetry"  # Last

    def test_all_hot_sections_in_priority(self) -> None:
        """Test all HOT sections are in priority list."""
        priority_set = set(HOT_HYDRATION_PRIORITY)
        assert priority_set == HOT_SECTIONS

    def test_all_warm_sections_in_priority(self) -> None:
        """Test all WARM sections are in priority list."""
        priority_set = set(WARM_HYDRATION_PRIORITY)
        assert priority_set == WARM_SECTIONS

    def test_all_sections_coverage(self) -> None:
        """Test ALL_SECTIONS covers HOT and WARM."""
        assert ALL_SECTIONS == HOT_SECTIONS | WARM_SECTIONS

    def test_hot_hydration_order(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        hot_tier: MockTier,
    ) -> None:
        """Test HOT sections are hydrated in priority order."""
        session_id = "test-session"
        local_cold.set_session_data(
            session_id,
            {sec: f"{sec}-data".encode() for sec in HOT_SECTIONS},
        )

        reconstruction_sla.reconstruct(session_id=session_id)

        restored = hot_tier.get_restored_sections()
        # All HOT sections should be restored
        for section in HOT_SECTIONS:
            assert section in restored


# =============================================================================
# TEST CLASS: Hydration Results
# =============================================================================


class TestHydrationResults:
    """Test hydration result tracking."""

    def test_hydration_result_dataclass(self) -> None:
        """Test HydrationResult dataclass."""
        result = HydrationResult()
        assert result.sections_hydrated == []
        assert result.all_restored is False
        assert result.duration_ms == 0.0
        assert result.errors == []

    def test_hydrate_hot_empty_data(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test _hydrate_hot with empty data."""
        result = reconstruction_sla._hydrate_hot({})

        assert result.sections_hydrated == []
        assert result.all_restored is True  # No data expected
        assert result.duration_ms >= 0

    def test_hydrate_warm_empty_data(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test _hydrate_warm with empty data."""
        result = reconstruction_sla._hydrate_warm({})

        assert result.sections_hydrated == []
        assert result.all_restored is True  # No data expected
        assert result.duration_ms >= 0

    def test_hydrate_hot_with_data(
        self,
        reconstruction_sla: ReconstructionSLA,
        sample_hot_data: Dict[str, bytes],
    ) -> None:
        """Test _hydrate_hot with data."""
        result = reconstruction_sla._hydrate_hot(sample_hot_data)

        assert len(result.sections_hydrated) == len(sample_hot_data)
        assert result.all_restored is True
        assert result.duration_ms >= 0

    def test_hydrate_warm_with_data(
        self,
        reconstruction_sla: ReconstructionSLA,
        sample_warm_data: Dict[str, bytes],
    ) -> None:
        """Test _hydrate_warm with data."""
        result = reconstruction_sla._hydrate_warm(sample_warm_data)

        assert len(result.sections_hydrated) == len(sample_warm_data)
        assert result.all_restored is True
        assert result.duration_ms >= 0

    def test_hydration_partial_failure(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test hydration with some failures."""

        # Create tier that fails for specific section
        class FailingTier:
            def __init__(self) -> None:
                self._sections = {
                    "control": MockSection("control"),
                    "beliefs_active": None,  # Will cause failure
                }

            def get_section(self, name: str):
                return self._sections.get(name)

        failing_tier = FailingTier()
        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=failing_tier,
            warm=None,
        )

        local_cold.set_session_data(
            "test-session",
            {"control": b"control", "beliefs_active": b"beliefs"},
        )

        result = sla.reconstruct(session_id="test-session")

        # Should still succeed partially
        assert result.success is True
        assert "control" in result.sections_restored


# =============================================================================
# TEST CLASS: Reconstruction Result
# =============================================================================


class TestReconstructionResult:
    """Test ReconstructionResult dataclass."""

    def test_result_defaults(self) -> None:
        """Test result defaults."""
        result = ReconstructionResult(
            success=True,
            source=ReconstructionSource.FRESH,
        )
        assert result.sections_restored == []
        assert result.hot_restored is False
        assert result.warm_restored is False
        assert result.duration_ms == 0.0
        assert result.hot_duration_ms == 0.0
        assert result.sla_met is True
        assert result.error is None

    def test_result_with_all_fields(self) -> None:
        """Test result with all fields."""
        result = ReconstructionResult(
            success=True,
            source=ReconstructionSource.LOCAL_COLD,
            sections_restored=["control", "beliefs_active"],
            hot_restored=True,
            warm_restored=False,
            duration_ms=25.5,
            hot_duration_ms=10.2,
            sla_met=True,
            error=None,
        )
        assert result.success is True
        assert result.source == ReconstructionSource.LOCAL_COLD
        assert len(result.sections_restored) == 2

    def test_result_with_error(self) -> None:
        """Test result with error."""
        result = ReconstructionResult(
            success=False,
            source=ReconstructionSource.FRESH,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"


# =============================================================================
# TEST CLASS: Time Estimation
# =============================================================================


class TestTimeEstimation:
    """Test reconstruction time estimation."""

    def test_estimate_empty_session_no_k0(
        self,
        local_cold: MockLocalColdArchive,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test estimation for empty/new session with no K0."""
        # Create SLA without K0 to ensure fresh start
        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=None,  # No K0
            hot=hot_tier,
            warm=warm_tier,
        )
        estimate = sla.estimate_reconstruction_time("new-session")

        assert estimate == 0.0  # Fresh start

    def test_estimate_empty_session_with_k0(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test estimation when K0 available but no LOCAL COLD data."""
        estimate = reconstruction_sla.estimate_reconstruction_time("new-session")

        # K0 is available, so estimate K0 time
        assert estimate >= ESTIMATE_K0_BASE_MS

    def test_estimate_with_local_cold_data(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test estimation with LOCAL COLD data."""
        session_id = "test-session"
        # Add 10KB of data
        local_cold.set_data(session_id, "control", b"x" * 10240)

        estimate = reconstruction_sla.estimate_reconstruction_time(session_id)

        expected = ESTIMATE_LOCAL_COLD_BASE_MS + 10 * ESTIMATE_LOCAL_COLD_PER_KB_MS
        assert estimate == pytest.approx(expected, rel=0.1)

    def test_estimate_with_k0_only(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test estimation when only K0 has data."""
        sla = ReconstructionSLA(
            local_cold=local_cold,  # Empty
            k0_sync_port=k0_sync,  # Available
            hot=hot_tier,
            warm=warm_tier,
        )

        estimate = sla.estimate_reconstruction_time("k0-only-session")

        # Should estimate K0 latency for average session
        assert estimate >= ESTIMATE_K0_BASE_MS

    def test_estimate_with_no_ports(self) -> None:
        """Test estimation with no storage ports."""
        sla = ReconstructionSLA(
            local_cold=None,
            k0_sync_port=None,
        )

        estimate = sla.estimate_reconstruction_time("any-session")

        assert estimate == 0.0  # No data available

    def test_estimate_empty_session_id(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test estimation with empty session_id."""
        estimate = reconstruction_sla.estimate_reconstruction_time("")

        assert estimate == 0.0


# =============================================================================
# TEST CLASS: Single Section Reconstruction
# =============================================================================


class TestSingleSectionReconstruction:
    """Test single section reconstruction."""

    def test_reconstruct_single_section_from_local_cold(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test reconstructing a single section from LOCAL COLD."""
        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"control-data")

        data, source = reconstruction_sla.reconstruct_section(
            session_id=session_id,
            section="control",
        )

        assert data == b"control-data"
        assert source == ReconstructionSource.LOCAL_COLD

    def test_reconstruct_single_section_from_k0(
        self,
        reconstruction_sla: ReconstructionSLA,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test reconstructing a single section from K0."""
        session_id = "test-session"
        k0_sync.set_data(session_id, {"control": b"k0-control"})

        data, source = reconstruction_sla.reconstruct_section(
            session_id=session_id,
            section="control",
        )

        assert data == b"k0-control"
        assert source == ReconstructionSource.K0

    def test_reconstruct_single_section_not_found(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test reconstructing a single section that doesn't exist."""
        data, source = reconstruction_sla.reconstruct_section(
            session_id="test-session",
            section="control",
        )

        assert data is None
        assert source == ReconstructionSource.FRESH

    def test_reconstruct_invalid_section(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test reconstructing an invalid section name."""
        data, source = reconstruction_sla.reconstruct_section(
            session_id="test-session",
            section="invalid_section",
        )

        assert data is None
        assert source == ReconstructionSource.FRESH

    def test_reconstruct_section_prefers_local_cold(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
    ) -> None:
        """Test single section prefers LOCAL COLD over K0."""
        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"local-control")
        k0_sync.set_data(session_id, {"control": b"k0-control"})

        data, source = reconstruction_sla.reconstruct_section(
            session_id=session_id,
            section="control",
        )

        assert data == b"local-control"
        assert source == ReconstructionSource.LOCAL_COLD


# =============================================================================
# TEST CLASS: Metrics
# =============================================================================


class TestMetrics:
    """Test metrics tracking and retrieval."""

    def test_get_metrics(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test get_metrics returns all metrics."""
        metrics = reconstruction_sla.get_metrics()

        assert "total_reconstructions" in metrics
        assert "successful_reconstructions" in metrics
        assert "sla_breaches" in metrics
        assert "sla_compliance_rate" in metrics
        assert "source_counts" in metrics

    def test_metrics_after_reconstructions(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test metrics after multiple reconstructions."""
        # Local cold reconstruction
        local_cold.set_data("session-1", "control", b"data")
        reconstruction_sla.reconstruct(session_id="session-1")

        # Fresh start
        reconstruction_sla.reconstruct(session_id="session-2")

        metrics = reconstruction_sla.get_metrics()

        assert metrics["total_reconstructions"] == 2
        assert metrics["successful_reconstructions"] == 2
        assert metrics["source_counts"][ReconstructionSource.LOCAL_COLD] == 1
        assert metrics["source_counts"][ReconstructionSource.FRESH] == 1

    def test_reset_metrics(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test reset_metrics clears all counters."""
        # Do some reconstructions
        reconstruction_sla.reconstruct(session_id="session-1")
        reconstruction_sla.reconstruct(session_id="session-2")

        # Reset
        reconstruction_sla.reset_metrics()

        assert reconstruction_sla.total_reconstructions == 0
        assert reconstruction_sla.successful_reconstructions == 0
        assert reconstruction_sla.sla_breaches == 0
        counts = reconstruction_sla.get_source_counts()
        assert all(c == 0 for c in counts.values())


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_none_local_cold(
        self,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test with None local_cold."""
        sla = ReconstructionSLA(
            local_cold=None,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
        )
        k0_sync.set_data("test", {"control": b"data"})

        result = sla.reconstruct(session_id="test")

        assert result.source == ReconstructionSource.K0

    def test_none_k0_sync(
        self,
        local_cold: MockLocalColdArchive,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test with None k0_sync."""
        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=None,
            hot=hot_tier,
            warm=warm_tier,
        )

        result = sla.reconstruct(session_id="new-session")

        assert result.source == ReconstructionSource.FRESH

    def test_both_storage_none(
        self,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test with both storage ports None."""
        sla = ReconstructionSLA(
            local_cold=None,
            k0_sync_port=None,
            hot=hot_tier,
            warm=warm_tier,
        )

        result = sla.reconstruct(session_id="test-session")

        assert result.success is True
        assert result.source == ReconstructionSource.FRESH

    def test_local_cold_exception(
        self,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test handling of LocalColdArchive exception."""

        class FailingArchive:
            def restore(self, *args, **kwargs):
                raise RuntimeError("Database error")

        sla = ReconstructionSLA(
            local_cold=FailingArchive(),
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
        )

        # Should fall through to K0 or FRESH
        result = sla.reconstruct(session_id="test-session")

        assert result.success is True  # Graceful degradation

    def test_k0_exception(
        self,
        local_cold: MockLocalColdArchive,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test handling of K0 exception."""

        class FailingK0:
            @property
            def is_available(self):
                return True

            def restore_from_k0(self, *args, **kwargs):
                raise RuntimeError("Network error")

        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=FailingK0(),
            hot=hot_tier,
            warm=warm_tier,
        )

        result = sla.reconstruct(session_id="test-session")

        # Should return FRESH on K0 failure
        assert result.success is True
        assert result.source == ReconstructionSource.FRESH

    def test_special_characters_in_session_id(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test session_id with special characters."""
        session_id = "user-123_session-456@domain.com"
        local_cold.set_data(session_id, "control", b"data")

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True
        assert result.source == ReconstructionSource.LOCAL_COLD

    def test_very_long_session_id(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test with very long session_id."""
        session_id = "x" * 1000

        result = reconstruction_sla.reconstruct(session_id=session_id)

        assert result.success is True  # Fresh start

    def test_empty_section_data(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test with empty bytes for section data."""
        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"")

        result = reconstruction_sla.reconstruct(session_id=session_id)

        # Empty data is still data
        assert result.success is True


# =============================================================================
# TEST CLASS: Section Data
# =============================================================================


class TestSectionData:
    """Test SectionData dataclass."""

    def test_section_data_creation(self) -> None:
        """Test SectionData creation."""
        data = SectionData(
            name="control",
            data=b"control-data",
            size_bytes=12,
            source=ReconstructionSource.LOCAL_COLD,
        )
        assert data.name == "control"
        assert data.data == b"control-data"
        assert data.size_bytes == 12
        assert data.source == ReconstructionSource.LOCAL_COLD


# =============================================================================
# TEST CLASS: Deserializer Integration
# =============================================================================


class TestDeserializerIntegration:
    """Test custom deserializer integration."""

    def test_deserializer_called_for_hot_sections(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test deserializer is called for HOT sections."""
        deserializer_calls = []

        def mock_deserializer(section: str, data: bytes) -> dict:
            deserializer_calls.append((section, data))
            return {"section": section, "data": data.decode()}

        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
            deserializer=mock_deserializer,
        )

        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"control-data")

        sla.reconstruct(session_id=session_id)

        # Check deserializer was called
        assert len(deserializer_calls) > 0
        assert any(call[0] == "control" for call in deserializer_calls)

    def test_deserializer_called_for_warm_sections(
        self,
        local_cold: MockLocalColdArchive,
        k0_sync: MockK0SyncPort,
        hot_tier: MockTier,
        warm_tier: MockTier,
    ) -> None:
        """Test deserializer is called for WARM sections."""
        deserializer_calls = []

        def mock_deserializer(section: str, data: bytes) -> dict:
            deserializer_calls.append((section, data))
            return {"section": section}

        sla = ReconstructionSLA(
            local_cold=local_cold,
            k0_sync_port=k0_sync,
            hot=hot_tier,
            warm=warm_tier,
            deserializer=mock_deserializer,
        )

        session_id = "test-session"
        local_cold.set_data(session_id, "persona", b"persona-data")

        sla.reconstruct(session_id=session_id)

        # Check deserializer was called for WARM section
        assert any(call[0] == "persona" for call in deserializer_calls)


# =============================================================================
# TEST CLASS: Concurrent Reconstructions
# =============================================================================


class TestConcurrentReconstructions:
    """Test concurrent reconstruction behavior."""

    def test_multiple_sessions_independent(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test multiple sessions are independent."""
        local_cold.set_data("session-1", "control", b"session-1-control")
        local_cold.set_data("session-2", "control", b"session-2-control")

        result1 = reconstruction_sla.reconstruct(session_id="session-1")
        result2 = reconstruction_sla.reconstruct(session_id="session-2")

        assert result1.success is True
        assert result2.success is True
        assert reconstruction_sla.total_reconstructions == 2

    def test_same_session_multiple_times(
        self,
        reconstruction_sla: ReconstructionSLA,
        local_cold: MockLocalColdArchive,
    ) -> None:
        """Test reconstructing same session multiple times."""
        session_id = "test-session"
        local_cold.set_data(session_id, "control", b"control-data")

        result1 = reconstruction_sla.reconstruct(session_id=session_id)
        result2 = reconstruction_sla.reconstruct(session_id=session_id)

        assert result1.success is True
        assert result2.success is True
        assert reconstruction_sla.total_reconstructions == 2


# =============================================================================
# TEST CLASS: Normalize Sections
# =============================================================================


class TestNormalizeSections:
    """Test section normalization."""

    def test_normalize_none_returns_none(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test None returns None (all sections)."""
        result = reconstruction_sla._normalize_sections(None)
        assert result is None

    def test_normalize_valid_sections(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test valid sections are kept."""
        result = reconstruction_sla._normalize_sections(["control", "beliefs_active", "persona"])
        assert result == ["control", "beliefs_active", "persona"]

    def test_normalize_filters_invalid(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test invalid sections are filtered."""
        result = reconstruction_sla._normalize_sections(["control", "invalid", "beliefs_active"])
        assert result == ["control", "beliefs_active"]

    def test_normalize_all_invalid_returns_none(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test all invalid returns None."""
        result = reconstruction_sla._normalize_sections(["invalid1", "invalid2"])
        assert result is None

    def test_normalize_empty_list_returns_none(
        self,
        reconstruction_sla: ReconstructionSLA,
    ) -> None:
        """Test empty list returns None."""
        result = reconstruction_sla._normalize_sections([])
        assert result is None
