"""Tests for k0.kernel.syscalls - Capability-Gated Storage Access."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.kernel.syscalls import PermissionError, Syscalls


class TestPermissionError:
    """Tests for PermissionError exception."""

    def test_permission_error_is_exception(self) -> None:
        """PermissionError should be an Exception subclass."""
        assert issubclass(PermissionError, Exception)

    def test_permission_error_message(self) -> None:
        """PermissionError should store message."""
        error = PermissionError("Missing capability: test.write")
        assert str(error) == "Missing capability: test.write"


class TestSyscallsInitialization:
    """Tests for Syscalls initialization."""

    def test_init_stores_pipeline_id(self) -> None:
        """Syscalls should store pipeline_id."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"test.read"},
            uow_factory=MagicMock(),
        )
        assert syscalls._pipeline_id == "P02"

    def test_init_stores_granted_caps_as_frozenset(self) -> None:
        """Syscalls should convert granted_caps to frozenset for immutability."""
        caps = {"test.read", "test.write"}
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=caps,
            uow_factory=MagicMock(),
        )
        assert isinstance(syscalls._granted_caps, frozenset)
        assert syscalls._granted_caps == frozenset(caps)

    def test_init_stores_uow_factory(self) -> None:
        """Syscalls should store uow_factory."""
        factory = MagicMock()
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"test.read"},
            uow_factory=factory,
        )
        assert syscalls._uow_factory is factory

    def test_init_with_empty_caps(self) -> None:
        """Syscalls should allow empty capabilities set."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),
            uow_factory=MagicMock(),
        )
        assert len(syscalls._granted_caps) == 0


class TestRequireCapability:
    """Tests for _require_cap method."""

    def test_require_cap_granted_does_not_raise(self) -> None:
        """_require_cap should not raise when capability is granted."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"test.read", "test.write"},
            uow_factory=MagicMock(),
        )
        # Should not raise
        syscalls._require_cap("test.read")
        syscalls._require_cap("test.write")

    def test_require_cap_not_granted_raises_permission_error(self) -> None:
        """_require_cap should raise PermissionError when capability not granted."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"test.read"},
            uow_factory=MagicMock(),
        )
        with pytest.raises(PermissionError) as exc_info:
            syscalls._require_cap("test.write")

        assert "P02" in str(exc_info.value)
        assert "test.write" in str(exc_info.value)

    def test_require_cap_empty_caps_raises_for_any(self) -> None:
        """_require_cap should raise for any capability when set is empty."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),
            uow_factory=MagicMock(),
        )
        with pytest.raises(PermissionError):
            syscalls._require_cap("any.capability")

    def test_require_cap_error_includes_granted_caps(self) -> None:
        """PermissionError should include list of granted capabilities."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"a.read", "b.write"},
            uow_factory=MagicMock(),
        )
        with pytest.raises(PermissionError) as exc_info:
            syscalls._require_cap("c.delete")

        error_msg = str(exc_info.value)
        assert "a.read" in error_msg or "Granted:" in error_msg


class TestHippStoreUpsertDeprecated:
    """Tests for deprecated hipp_store_upsert method."""

    @pytest.mark.asyncio
    async def test_hipp_store_upsert_raises_runtime_error(self) -> None:
        """hipp_store_upsert should raise RuntimeError (deprecated)."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_store.write"},
            uow_factory=MagicMock(),
        )
        with pytest.raises(RuntimeError) as exc_info:
            await syscalls.hipp_store_upsert(
                space_id="space_123",
                event_id="evt_123",
                payload={"text": "test"},
                cognitive_trace_id="trace_123",
            )

        assert "deprecated" in str(exc_info.value).lower()
        assert "hipp_events_upsert" in str(exc_info.value)


class TestHippEventsUpsert:
    """Tests for hipp_events_upsert method."""

    @pytest.fixture
    def mock_uow(self) -> MagicMock:
        """Create mock UnitOfWork."""
        uow = MagicMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=None)
        uow._connection = MagicMock()
        uow._connection.execute = AsyncMock(return_value="INSERT 1")
        return uow

    @pytest.fixture
    def mock_uow_factory(self, mock_uow: MagicMock) -> MagicMock:
        """Create mock UoW factory."""
        factory = MagicMock(return_value=mock_uow)
        return factory

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_requires_capability(
        self, mock_uow_factory: MagicMock
    ) -> None:
        """hipp_events_upsert should require st_hipp_events.write capability."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),  # No capabilities
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(PermissionError) as exc_info:
            await syscalls.hipp_events_upsert(
                event_id="evt_123",
                embedding_id="emb_123",
                wal_pos=42,
                policy_band="GREEN",
            )

        assert "st_hipp_events.write" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_validates_event_id(self, mock_uow_factory: MagicMock) -> None:
        """hipp_events_upsert should require event_id."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(ValueError) as exc_info:
            await syscalls.hipp_events_upsert(
                event_id="",  # Empty
                embedding_id="emb_123",
                wal_pos=42,
                policy_band="GREEN",
            )

        assert "event_id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_validates_embedding_id(
        self, mock_uow_factory: MagicMock
    ) -> None:
        """hipp_events_upsert should require embedding_id."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(ValueError) as exc_info:
            await syscalls.hipp_events_upsert(
                event_id="evt_123",
                embedding_id="",  # Empty
                wal_pos=42,
                policy_band="GREEN",
            )

        assert "embedding_id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_validates_wal_pos(self, mock_uow_factory: MagicMock) -> None:
        """hipp_events_upsert should require wal_pos."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(ValueError) as exc_info:
            await syscalls.hipp_events_upsert(
                event_id="evt_123",
                embedding_id="emb_123",
                wal_pos=None,  # type: ignore
                policy_band="GREEN",
            )

        assert "wal_pos" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_validates_policy_band(
        self, mock_uow_factory: MagicMock
    ) -> None:
        """hipp_events_upsert should validate policy_band values."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(ValueError) as exc_info:
            await syscalls.hipp_events_upsert(
                event_id="evt_123",
                embedding_id="emb_123",
                wal_pos=42,
                policy_band="INVALID",  # Invalid band
            )

        assert "policy_band" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_accepts_green_band(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """hipp_events_upsert should accept GREEN policy band."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            embedding_id="emb_123",
            wal_pos=42,
            policy_band="GREEN",
            cognitive_trace_id="trace_123",
        )

        assert result["event_id"] == "evt_123"
        assert result["inserted"] is True

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_accepts_amber_band(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """hipp_events_upsert should accept AMBER policy band."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            embedding_id="emb_123",
            wal_pos=42,
            policy_band="AMBER",
            cognitive_trace_id="trace_123",
        )

        assert result["event_id"] == "evt_123"

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_accepts_red_band(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """hipp_events_upsert should accept RED policy band."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            embedding_id="emb_123",
            wal_pos=42,
            policy_band="RED",
            cognitive_trace_id="trace_123",
        )

        assert result["event_id"] == "evt_123"

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_returns_inserted_true(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """hipp_events_upsert should return inserted=True on successful insert."""
        mock_uow._connection.execute = AsyncMock(return_value="INSERT 1")

        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            embedding_id="emb_123",
            wal_pos=42,
            policy_band="GREEN",
        )

        assert result["inserted"] is True
        assert result["status"] == "INSERTED"

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_returns_inserted_false_on_duplicate(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """hipp_events_upsert should return inserted=False on duplicate."""
        mock_uow._connection.execute = AsyncMock(return_value="INSERT 0")

        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            embedding_id="emb_123",
            wal_pos=42,
            policy_band="GREEN",
        )

        assert result["inserted"] is False
        assert result["status"] == "SKIPPED_DUPLICATE"


class TestPipelineProcessedUpsert:
    """Tests for pipeline_processed_upsert method."""

    @pytest.fixture
    def mock_uow(self) -> MagicMock:
        """Create mock UnitOfWork."""
        uow = MagicMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=None)
        uow._connection = MagicMock()
        uow._connection.execute = AsyncMock(return_value="INSERT 1")
        return uow

    @pytest.fixture
    def mock_uow_factory(self, mock_uow: MagicMock) -> MagicMock:
        """Create mock UoW factory."""
        factory = MagicMock(return_value=mock_uow)
        return factory

    @pytest.mark.asyncio
    async def test_pipeline_processed_requires_capability(
        self, mock_uow_factory: MagicMock
    ) -> None:
        """pipeline_processed_upsert should require st_pipeline_processed.write."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),  # No capabilities
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(PermissionError) as exc_info:
            await syscalls.pipeline_processed_upsert(
                pipeline_id="P02_WRITE",
                wal_pos=42,
                tenant_id="tenant_abc",
                space_id="space_xyz",
                status="OK",
            )

        assert "st_pipeline_processed.write" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pipeline_processed_validates_pipeline_id(
        self, mock_uow_factory: MagicMock
    ) -> None:
        """pipeline_processed_upsert should require pipeline_id."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_pipeline_processed.write"},
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(ValueError) as exc_info:
            await syscalls.pipeline_processed_upsert(
                pipeline_id="",  # Empty
                wal_pos=42,
                tenant_id="tenant_abc",
                space_id="space_xyz",
                status="OK",
            )

        assert "pipeline_id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pipeline_processed_validates_status(self, mock_uow_factory: MagicMock) -> None:
        """pipeline_processed_upsert should validate status values."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_pipeline_processed.write"},
            uow_factory=mock_uow_factory,
        )
        with pytest.raises(ValueError) as exc_info:
            await syscalls.pipeline_processed_upsert(
                pipeline_id="P02_WRITE",
                wal_pos=42,
                tenant_id="tenant_abc",
                space_id="space_xyz",
                status="INVALID",  # Invalid status
            )

        assert "status" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_pipeline_processed_accepts_ok_status(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """pipeline_processed_upsert should accept OK status."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_pipeline_processed.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.pipeline_processed_upsert(
            pipeline_id="P02_WRITE",
            wal_pos=42,
            tenant_id="tenant_abc",
            space_id="space_xyz",
            status="OK",
        )

        assert result["status"] == "OK"

    @pytest.mark.asyncio
    async def test_pipeline_processed_accepts_error_status(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """pipeline_processed_upsert should accept ERROR status."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_pipeline_processed.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.pipeline_processed_upsert(
            pipeline_id="P02_WRITE",
            wal_pos=42,
            tenant_id="tenant_abc",
            space_id="space_xyz",
            status="ERROR",
        )

        assert result["status"] == "ERROR"

    @pytest.mark.asyncio
    async def test_pipeline_processed_accepts_skipped_status(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """pipeline_processed_upsert should accept SKIPPED status."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_pipeline_processed.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.pipeline_processed_upsert(
            pipeline_id="P02_WRITE",
            wal_pos=42,
            tenant_id="tenant_abc",
            space_id="space_xyz",
            status="SKIPPED",
        )

        assert result["status"] == "SKIPPED"

    @pytest.mark.asyncio
    async def test_pipeline_processed_returns_correct_fields(
        self, mock_uow_factory: MagicMock, mock_uow: MagicMock
    ) -> None:
        """pipeline_processed_upsert should return expected fields."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_pipeline_processed.write"},
            uow_factory=mock_uow_factory,
        )
        result = await syscalls.pipeline_processed_upsert(
            pipeline_id="P02_WRITE",
            wal_pos=42,
            tenant_id="tenant_abc",
            space_id="space_xyz",
            status="OK",
        )

        assert "inserted" in result
        assert "pipeline_id" in result
        assert "wal_pos" in result
        assert "status" in result
        assert result["pipeline_id"] == "P02_WRITE"
        assert result["wal_pos"] == 42


class TestCapabilityImmutability:
    """Tests for capability set immutability."""

    def test_granted_caps_cannot_be_modified_externally(self) -> None:
        """Original caps set should not affect Syscalls after init."""
        caps = {"test.read"}
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=caps,
            uow_factory=MagicMock(),
        )

        # Modify original set
        caps.add("test.write")

        # Syscalls should not be affected
        with pytest.raises(PermissionError):
            syscalls._require_cap("test.write")

    def test_granted_caps_is_frozenset(self) -> None:
        """Granted caps should be frozenset (immutable)."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"test.read"},
            uow_factory=MagicMock(),
        )
        assert isinstance(syscalls._granted_caps, frozenset)


class TestSyscallsAuditLogging:
    """Tests for audit logging in Syscalls."""

    def test_init_logs_capabilities(self, caplog: pytest.LogCaptureFixture) -> None:
        """Syscalls init should log granted capabilities."""
        import logging

        with caplog.at_level(logging.INFO):
            Syscalls(
                pipeline_id="P02",
                granted_caps={"test.read", "test.write"},
                uow_factory=MagicMock(),
            )

        assert any("P02" in record.message for record in caplog.records)

    def test_require_cap_logs_violation(self, caplog: pytest.LogCaptureFixture) -> None:
        """_require_cap should log security violations."""
        import logging

        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),
            uow_factory=MagicMock(),
        )

        with caplog.at_level(logging.ERROR):
            with pytest.raises(PermissionError):
                syscalls._require_cap("test.write")

        assert any("Permission denied" in record.message for record in caplog.records)
