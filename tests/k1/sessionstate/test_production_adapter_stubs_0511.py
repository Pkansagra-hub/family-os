"""I-0.5.11.2 -- SessionState production adapter stub tests.

Verifies all 5 stub adapters:
  1. Instantiate without error
  2. Satisfy their ABC (isinstance check)
  3. Properties return safe defaults (False / empty / CREATED)
  4. All abstract methods raise NotImplementedError with blocking message
  5. Re-exported from adapters package
"""

from __future__ import annotations

import pytest

from k1.sessionstate.adapters import (
    BridgeStorageAdapter,
    BridgeSyncAdapter,
    ConciergeWriterAdapter,
    DeltaBusAdapter,
    FabricLifecycleAdapter,
)
from k1.sessionstate.ports.events import IEventPort
from k1.sessionstate.ports.k0_sync import IK0SyncPort
from k1.sessionstate.ports.lifecycle import ILifecyclePort, LifecycleState
from k1.sessionstate.ports.storage import IStoragePort
from k1.sessionstate.ports.writer import (
    BatchRequest,
    IWriterPort,
    MutationPriority,
    MutationRequest,
)

# ---------------------------------------------------------------------------
# BridgeStorageAdapter
# ---------------------------------------------------------------------------


class TestBridgeStorageAdapter:
    """BridgeStorageAdapter stub tests."""

    def test_instantiate(self) -> None:
        adapter = BridgeStorageAdapter()
        assert adapter is not None

    def test_is_abc_subclass(self) -> None:
        assert isinstance(BridgeStorageAdapter(), IStoragePort)

    def test_is_available_false(self) -> None:
        assert BridgeStorageAdapter().is_available is False

    def test_storage_type_k0(self) -> None:
        assert BridgeStorageAdapter().storage_type == "k0"

    def test_archive_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeStorageAdapter().archive("beliefs", b"data", {"session_id": "s1"})

    def test_restore_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeStorageAdapter().restore("beliefs", {"session_id": "s1"})

    def test_list_archives_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeStorageAdapter().list_archives("s1")

    def test_delete_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeStorageAdapter().delete("archive-123")


# ---------------------------------------------------------------------------
# DeltaBusAdapter
# ---------------------------------------------------------------------------


class TestDeltaBusAdapter:
    """DeltaBusAdapter stub tests."""

    def test_instantiate(self) -> None:
        adapter = DeltaBusAdapter()
        assert adapter is not None

    def test_is_abc_subclass(self) -> None:
        assert isinstance(DeltaBusAdapter(), IEventPort)

    def test_is_connected_false(self) -> None:
        assert DeltaBusAdapter().is_connected is False

    def test_emit_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bus"):
            DeltaBusAdapter().emit("sessionstate.mutation.approved", {})

    def test_subscribe_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bus"):
            DeltaBusAdapter().subscribe("sessionstate.mutation.approved", lambda p: None)

    def test_unsubscribe_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bus"):
            DeltaBusAdapter().unsubscribe("sub-123")


# ---------------------------------------------------------------------------
# ConciergeWriterAdapter
# ---------------------------------------------------------------------------


class TestConciergeWriterAdapter:
    """ConciergeWriterAdapter stub tests."""

    def test_instantiate(self) -> None:
        adapter = ConciergeWriterAdapter()
        assert adapter is not None

    def test_is_abc_subclass(self) -> None:
        assert isinstance(ConciergeWriterAdapter(), IWriterPort)

    def test_writer_id_concierge(self) -> None:
        assert ConciergeWriterAdapter().writer_id == "concierge"

    def test_is_connected_false(self) -> None:
        assert ConciergeWriterAdapter().is_connected is False

    def test_request_mutation_raises(self) -> None:
        req = MutationRequest(
            request_id="r1",
            section="beliefs_active",
            operation="set",
            data={"key": "value"},
            estimated_bytes=100,
            writer_id="concierge",
            cognitive_trace_id="trace-1",
            priority=MutationPriority.NORMAL,
        )
        with pytest.raises(NotImplementedError, match="Concierge"):
            ConciergeWriterAdapter().request_mutation(req)

    def test_batch_mutations_raises(self) -> None:
        batch = BatchRequest.create(
            requests=[],
            writer_id="concierge",
            cognitive_trace_id="trace-1",
        )
        with pytest.raises(NotImplementedError, match="Concierge"):
            ConciergeWriterAdapter().batch_mutations(batch)

    def test_validate_writer_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Concierge"):
            ConciergeWriterAdapter().validate_writer("concierge")


# ---------------------------------------------------------------------------
# FabricLifecycleAdapter
# ---------------------------------------------------------------------------


class TestFabricLifecycleAdapter:
    """FabricLifecycleAdapter stub tests."""

    def test_instantiate(self) -> None:
        adapter = FabricLifecycleAdapter()
        assert adapter is not None

    def test_is_abc_subclass(self) -> None:
        assert isinstance(FabricLifecycleAdapter(), ILifecyclePort)

    def test_state_created(self) -> None:
        assert FabricLifecycleAdapter().state == LifecycleState.CREATED

    def test_session_id_empty(self) -> None:
        assert FabricLifecycleAdapter().session_id == ""

    def test_config_default(self) -> None:
        cfg = FabricLifecycleAdapter().config
        assert cfg.checkpoint_interval_ms == 30000

    def test_started_at_ms_zero(self) -> None:
        assert FabricLifecycleAdapter().started_at_ms == 0

    def test_checkpoint_count_zero(self) -> None:
        assert FabricLifecycleAdapter().checkpoint_count == 0

    def test_last_checkpoint_ms_zero(self) -> None:
        assert FabricLifecycleAdapter().last_checkpoint_ms == 0

    def test_start_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Fabric"):
            FabricLifecycleAdapter().start()

    def test_stop_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Fabric"):
            FabricLifecycleAdapter().stop()

    def test_health_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Fabric"):
            FabricLifecycleAdapter().health()

    def test_checkpoint_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Fabric"):
            FabricLifecycleAdapter().checkpoint()


# ---------------------------------------------------------------------------
# BridgeSyncAdapter
# ---------------------------------------------------------------------------


class TestBridgeSyncAdapter:
    """BridgeSyncAdapter stub tests."""

    def test_instantiate(self) -> None:
        adapter = BridgeSyncAdapter()
        assert adapter is not None

    def test_is_abc_subclass(self) -> None:
        assert isinstance(BridgeSyncAdapter(), IK0SyncPort)

    def test_is_available_false(self) -> None:
        assert BridgeSyncAdapter().is_available is False

    def test_sync_to_k0_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeSyncAdapter().sync_to_k0("s1")

    def test_restore_from_k0_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeSyncAdapter().restore_from_k0("s1")

    def test_get_sync_status_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeSyncAdapter().get_sync_status("s1")

    def test_cancel_sync_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Bridge"):
            BridgeSyncAdapter().cancel_sync("s1")


# ---------------------------------------------------------------------------
# Package re-exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    """All 10 adapters importable from k1.sessionstate.adapters."""

    EXPECTED = {
        # Standalone (5)
        "SQLiteStorageAdapter",
        "InMemoryStorageAdapter",
        "LocalEventAdapter",
        "DirectWriterAdapter",
        "StandaloneLifecycle",
        # Production stubs (5)
        "BridgeStorageAdapter",
        "DeltaBusAdapter",
        "ConciergeWriterAdapter",
        "FabricLifecycleAdapter",
        "BridgeSyncAdapter",
    }

    def test_all_in___all__(self) -> None:
        from k1.sessionstate import adapters

        assert set(adapters.__all__) == self.EXPECTED

    def test_all_importable(self) -> None:
        from k1.sessionstate import adapters

        for name in self.EXPECTED:
            assert hasattr(adapters, name), f"Missing export: {name}"


# ---------------------------------------------------------------------------
# Slot efficiency
# ---------------------------------------------------------------------------


class TestSlotEfficiency:
    """All stubs use __slots__ for memory efficiency."""

    @pytest.mark.parametrize(
        "cls",
        [
            BridgeStorageAdapter,
            DeltaBusAdapter,
            ConciergeWriterAdapter,
            FabricLifecycleAdapter,
            BridgeSyncAdapter,
        ],
    )
    def test_has_slots(self, cls: type) -> None:
        assert hasattr(cls, "__slots__"), f"{cls.__name__} missing __slots__"

    @pytest.mark.parametrize(
        "cls",
        [
            BridgeStorageAdapter,
            DeltaBusAdapter,
            ConciergeWriterAdapter,
            FabricLifecycleAdapter,
            BridgeSyncAdapter,
        ],
    )
    def test_no_instance_attrs(self, cls: type) -> None:
        """Stubs declare __slots__ = () so no per-instance storage is added."""
        assert cls.__slots__ == ()
