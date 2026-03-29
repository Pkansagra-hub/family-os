"""
tests.poc.test_m01_e14_wiring -- E1.4 End-to-End Wiring & System Integration.

Validates:
    - KernelConfig.enable_ledger field and default
    - KernelRuntime.ledger / ledger_store fields
    - start_kernel() creates and wires ledger (1.4.1)
    - FSM _try_deserialize dual-mode bridge (1.4.3)
    - _serialize() auto-enriches legacy dicts (1.4.5)
    - Coordinator ledger slots exist (1.4.6)
    - Testing fixtures factory functions (1.4.7)
    - Backward compat: all 28 builders still work (1.4.8)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import fields as dc_fields

import pytest

from k1.bus.envelope import Envelope, Priority
from poc.k1_poc.bus.builders import BUILDERS, build_task_dispatch, build_user_input
from poc.k1_poc.bus.topics import ALL_TOPICS
from poc.k1_poc.kernel.bootstrap import KernelConfig, KernelRuntime

# ------------------------------------------------------------------
# 1.4.1  KernelConfig & KernelRuntime schema tests
# ------------------------------------------------------------------


class TestKernelConfigLedger:
    """KernelConfig has enable_ledger field with correct default."""

    def test_enable_ledger_field_exists(self) -> None:
        cfg = KernelConfig()
        assert hasattr(cfg, "enable_ledger")

    def test_enable_ledger_defaults_true(self) -> None:
        cfg = KernelConfig()
        assert cfg.enable_ledger is True

    def test_enable_ledger_override_false(self) -> None:
        cfg = KernelConfig(enable_ledger=False)
        assert cfg.enable_ledger is False


class TestKernelRuntimeLedger:
    """KernelRuntime has ledger and ledger_store slots."""

    def test_runtime_has_ledger_field(self) -> None:
        field_names = {f.name for f in dc_fields(KernelRuntime)}
        assert "ledger" in field_names

    def test_runtime_has_ledger_store_field(self) -> None:
        field_names = {f.name for f in dc_fields(KernelRuntime)}
        assert "ledger_store" in field_names

    def test_runtime_ledger_defaults_none(self) -> None:
        field_map = {f.name: f for f in dc_fields(KernelRuntime)}
        assert field_map["ledger"].default is None

    def test_runtime_ledger_store_defaults_none(self) -> None:
        field_map = {f.name: f for f in dc_fields(KernelRuntime)}
        assert field_map["ledger_store"].default is None


# ------------------------------------------------------------------
# 1.4.1  start_kernel() creates and wires ledger
# ------------------------------------------------------------------


class TestBootstrapLedgerWiring:
    """start_kernel() creates LedgerWriter and wires to FSM."""

    @pytest.mark.asyncio
    async def test_start_kernel_creates_ledger(self) -> None:
        from poc.k1_poc.kernel.bootstrap import start_kernel, stop_kernel

        cfg = KernelConfig(
            enable_ledger=True,
            test_mode=True,
            enable_experience=False,
            enable_delta=False,
            enable_hitl=False,
            enable_orchestrator=False,
            auto_start_consumer=False,
        )
        rt = await start_kernel(cfg)
        try:
            assert rt.ledger is not None
            assert rt.ledger_store is not None
        finally:
            await stop_kernel(rt)

    @pytest.mark.asyncio
    async def test_start_kernel_ledger_wired_to_fsm(self) -> None:
        from poc.k1_poc.kernel.bootstrap import start_kernel, stop_kernel

        cfg = KernelConfig(
            enable_ledger=True,
            test_mode=True,
            enable_experience=False,
            enable_delta=False,
            enable_hitl=False,
            enable_orchestrator=False,
            auto_start_consumer=False,
        )
        rt = await start_kernel(cfg)
        try:
            assert rt.fsm.ledger is rt.ledger
        finally:
            await stop_kernel(rt)

    @pytest.mark.asyncio
    async def test_start_kernel_skips_ledger_when_disabled(self) -> None:
        from poc.k1_poc.kernel.bootstrap import start_kernel, stop_kernel

        cfg = KernelConfig(
            enable_ledger=False,
            test_mode=True,
            enable_experience=False,
            enable_delta=False,
            enable_hitl=False,
            enable_orchestrator=False,
            auto_start_consumer=False,
        )
        rt = await start_kernel(cfg)
        try:
            assert rt.ledger is None
            assert rt.ledger_store is None
        finally:
            await stop_kernel(rt)

    @pytest.mark.asyncio
    async def test_start_kernel_session_id_propagates(self) -> None:
        from poc.k1_poc.kernel.bootstrap import start_kernel, stop_kernel

        cfg = KernelConfig(
            enable_ledger=True,
            session_id="test-wiring-sid",
            test_mode=True,
            enable_experience=False,
            enable_delta=False,
            enable_hitl=False,
            enable_orchestrator=False,
            auto_start_consumer=False,
        )
        rt = await start_kernel(cfg)
        try:
            assert rt.ledger is not None
            assert rt.ledger._session_id == "test-wiring-sid"
        finally:
            await stop_kernel(rt)


# ------------------------------------------------------------------
# 1.4.3  FSM _try_deserialize dual-mode bridge
# ------------------------------------------------------------------


class TestFsmTryDeserialize:
    """ConciergeController._try_deserialize works for canonical and legacy."""

    def _make_fsm(self):
        from poc.k1_poc.bus.setup import create_poc_bus, create_poc_router
        from poc.k1_poc.fsm.controller import ConciergeController

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        return ConciergeController(bus=bus, router=router)

    def test_try_deserialize_exists(self) -> None:
        fsm = self._make_fsm()
        assert hasattr(fsm, "_try_deserialize")
        assert callable(fsm._try_deserialize)

    def test_try_deserialize_returns_none_for_legacy(self) -> None:
        """Legacy dict payloads without event_type return None."""
        fsm = self._make_fsm()
        env = build_user_input({"text": "hello"})
        # Legacy enriched payloads have no event_type -> returns None
        result = fsm._try_deserialize(env)
        # auto-enriched payloads do NOT have event_type, so should be None
        assert result is None

    def test_try_deserialize_returns_typed_for_canonical(self) -> None:
        """Canonical events with event_type are deserialized to typed classes."""
        from poc.k1_poc.events.base import CanonicalEventMeta
        from poc.k1_poc.events.conversation import UserInputReceived

        fsm = self._make_fsm()
        # Build envelope from a canonical event
        canonical = UserInputReceived(
            event_id=str(uuid.uuid4()),
            text="hello typed",
        )
        env = build_user_input(canonical)  # type: ignore[arg-type]
        result = fsm._try_deserialize(env)
        assert result is not None
        assert isinstance(result, CanonicalEventMeta)
        assert isinstance(result, UserInputReceived)
        assert result.text == "hello typed"

    def test_try_deserialize_returns_none_on_empty_payload(self) -> None:
        """Empty envelope payload returns None."""
        fsm = self._make_fsm()
        env = Envelope(
            topic="k1.session.user.input.v1",
            priority=Priority.URGENT,
            payload=b"",
        )
        result = fsm._try_deserialize(env)
        assert result is None

    def test_try_deserialize_returns_none_on_bad_json(self) -> None:
        """Malformed JSON payload returns None (no exception)."""
        fsm = self._make_fsm()
        env = Envelope(
            topic="k1.session.user.input.v1",
            priority=Priority.URGENT,
            payload=b"not-json{{",
        )
        result = fsm._try_deserialize(env)
        assert result is None


# ------------------------------------------------------------------
# 1.4.5  _serialize() auto-enriches legacy dicts
# ------------------------------------------------------------------


class TestSerializeAutoEnrich:
    """_serialize() injects event_id, ts_utc, payload_schema_version."""

    def test_legacy_dict_gets_event_id(self) -> None:
        env = build_user_input({"text": "hi"})
        data = json.loads(env.payload)
        assert "event_id" in data
        # Must be a valid UUID4 string
        uuid.UUID(data["event_id"])

    def test_legacy_dict_gets_ts_utc(self) -> None:
        env = build_user_input({"text": "hi"})
        data = json.loads(env.payload)
        assert "ts_utc" in data
        assert "T" in data["ts_utc"]  # ISO 8601 format

    def test_legacy_dict_gets_payload_schema_version(self) -> None:
        env = build_user_input({"text": "hi"})
        data = json.loads(env.payload)
        assert data["payload_schema_version"] == "0.1.0"

    def test_existing_event_id_not_overwritten(self) -> None:
        my_id = "custom-id-1234"
        env = build_user_input({"text": "hi", "event_id": my_id})
        data = json.loads(env.payload)
        assert data["event_id"] == my_id

    def test_existing_ts_utc_not_overwritten(self) -> None:
        ts = "2025-01-01T00:00:00+00:00"
        env = build_user_input({"text": "hi", "ts_utc": ts})
        data = json.loads(env.payload)
        assert data["ts_utc"] == ts

    def test_existing_payload_schema_version_not_overwritten(self) -> None:
        env = build_user_input({"text": "hi", "payload_schema_version": "1.0.0"})
        data = json.loads(env.payload)
        assert data["payload_schema_version"] == "1.0.0"

    def test_canonical_event_not_enriched(self) -> None:
        """CanonicalEventMeta subclasses are NOT auto-enriched (they have their own fields)."""
        from poc.k1_poc.events.conversation import UserInputReceived

        canonical = UserInputReceived(event_id="e-123", text="typed")
        env = build_user_input(canonical)  # type: ignore[arg-type]
        data = json.loads(env.payload)
        # Canonical events have event_type, which dicts do not
        assert "event_type" in data
        # Should NOT have the pre-migration marker
        assert data.get("payload_schema_version") != "0.1.0"

    def test_all_28_builders_produce_enriched_payloads(self) -> None:
        """Every builder accepting a dict payload produces enriched output."""
        sample = {"key": "value"}
        for topic, builder_entry in BUILDERS.items():
            builder_fn = builder_entry if callable(builder_entry) else builder_entry.fn
            env = builder_fn(sample)
            data = json.loads(env.payload)
            assert "event_id" in data, f"Builder for {topic} missing event_id"
            assert "ts_utc" in data, f"Builder for {topic} missing ts_utc"
            assert (
                "payload_schema_version" in data
            ), f"Builder for {topic} missing payload_schema_version"


# ------------------------------------------------------------------
# 1.4.6  Coordinator ledger slots
# ------------------------------------------------------------------


class TestCoordinatorLedgerSlots:
    """K1DemoCoordinator has ledger and ledger_store attributes."""

    def test_coordinator_has_ledger_slot(self) -> None:
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator.__init__)
        assert "self.ledger" in source

    def test_coordinator_has_ledger_store_slot(self) -> None:
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator.__init__)
        assert "self.ledger_store" in source


# ------------------------------------------------------------------
# 1.4.7  Testing fixtures
# ------------------------------------------------------------------


class TestFixtureCreateTestLedger:
    """create_test_ledger() factory produces wired pair."""

    def test_returns_tuple(self) -> None:
        from poc.k1_poc.testing.fixtures import create_test_ledger

        result = create_test_ledger()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_writer_type(self) -> None:
        from poc.k1_poc.ledger.writer import LedgerWriter
        from poc.k1_poc.testing.fixtures import create_test_ledger

        writer, _ = create_test_ledger()
        assert isinstance(writer, LedgerWriter)

    def test_store_type(self) -> None:
        from poc.k1_poc.ledger.store import InMemoryLedgerStore
        from poc.k1_poc.testing.fixtures import create_test_ledger

        _, store = create_test_ledger()
        assert isinstance(store, InMemoryLedgerStore)

    def test_custom_session_id(self) -> None:
        from poc.k1_poc.testing.fixtures import create_test_ledger

        writer, _ = create_test_ledger(session_id="sid-42")
        assert writer._session_id == "sid-42"

    def test_store_starts_empty(self) -> None:
        from poc.k1_poc.testing.fixtures import create_test_ledger

        _, store = create_test_ledger()
        assert store.count() == 0


class TestFixtureCreateWiredFsm:
    """create_wired_fsm() factory produces FSM with optional ledger."""

    def test_returns_dict_with_bus_router_fsm(self) -> None:
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        result = create_wired_fsm()
        assert "bus" in result
        assert "router" in result
        assert "fsm" in result

    def test_with_ledger_true(self) -> None:
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        result = create_wired_fsm(with_ledger=True)
        assert "ledger" in result
        assert "ledger_store" in result
        assert result["fsm"].ledger is result["ledger"]

    def test_with_ledger_false(self) -> None:
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        result = create_wired_fsm(with_ledger=False)
        assert "ledger" not in result
        assert "ledger_store" not in result

    def test_fsm_type(self) -> None:
        from poc.k1_poc.fsm.controller import ConciergeController
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        result = create_wired_fsm()
        assert isinstance(result["fsm"], ConciergeController)


class TestFixtureAssertLedgerContains:
    """assert_ledger_contains() assertion helper."""

    def test_passes_when_event_present(self) -> None:
        from poc.k1_poc.ledger.store import InMemoryLedgerStore, LedgerEntry
        from poc.k1_poc.testing.fixtures import assert_ledger_contains

        store = InMemoryLedgerStore()
        entry = LedgerEntry(
            seq=0,
            event_id="e1",
            session_id="s1",
            event_type="task.dispatched",
            payload={"task_id": "t1"},
            written_at_utc="2025-01-01T00:00:00+00:00",
        )
        store.append(entry)
        result = assert_ledger_contains(store, "task.dispatched")
        assert len(result) == 1

    def test_fails_when_event_absent(self) -> None:
        from poc.k1_poc.ledger.store import InMemoryLedgerStore
        from poc.k1_poc.testing.fixtures import assert_ledger_contains

        store = InMemoryLedgerStore()
        with pytest.raises(AssertionError, match="Expected at least 1"):
            assert_ledger_contains(store, "missing.event")

    def test_exact_count(self) -> None:
        from poc.k1_poc.ledger.store import InMemoryLedgerStore, LedgerEntry
        from poc.k1_poc.testing.fixtures import assert_ledger_contains

        store = InMemoryLedgerStore()
        for i in range(3):
            store.append(
                LedgerEntry(
                    seq=0,
                    event_id=f"e{i}",
                    session_id="s1",
                    event_type="repeat.event",
                    payload={},
                    written_at_utc="2025-01-01T00:00:00+00:00",
                )
            )
        result = assert_ledger_contains(store, "repeat.event", count=3)
        assert len(result) == 3


class TestFixtureAssertLedgerEmpty:
    """assert_ledger_empty() assertion helper."""

    def test_passes_when_empty(self) -> None:
        from poc.k1_poc.ledger.store import InMemoryLedgerStore
        from poc.k1_poc.testing.fixtures import assert_ledger_empty

        store = InMemoryLedgerStore()
        assert_ledger_empty(store)

    def test_fails_when_not_empty(self) -> None:
        from poc.k1_poc.ledger.store import InMemoryLedgerStore, LedgerEntry
        from poc.k1_poc.testing.fixtures import assert_ledger_empty

        store = InMemoryLedgerStore()
        store.append(
            LedgerEntry(
                seq=0,
                event_id="e1",
                session_id="s1",
                event_type="x",
                payload={},
                written_at_utc="2025-01-01T00:00:00+00:00",
            )
        )
        with pytest.raises(AssertionError, match="Expected empty ledger"):
            assert_ledger_empty(store)


# ------------------------------------------------------------------
# 1.4.8  Backward compatibility -- all builders still work
# ------------------------------------------------------------------


class TestBackwardCompatibility:
    """All 28 builders accept dict payloads and produce valid Envelopes."""

    def test_all_builders_produce_envelopes(self) -> None:
        for topic, builder_entry in BUILDERS.items():
            builder_fn = builder_entry if callable(builder_entry) else builder_entry.fn
            env = builder_fn({"test": True})
            assert isinstance(env, Envelope), f"Builder for {topic} did not return Envelope"
            assert env.topic == topic

    def test_all_builders_have_json_payload(self) -> None:
        for topic, builder_entry in BUILDERS.items():
            builder_fn = builder_entry if callable(builder_entry) else builder_entry.fn
            env = builder_fn({"test": True})
            data = json.loads(env.payload)
            assert isinstance(data, dict), f"Builder for {topic} payload is not dict"
            assert data.get("test") is True

    def test_builder_count_still_28(self) -> None:
        assert len(BUILDERS) == 40

    def test_builder_topics_match_all_topics(self) -> None:
        assert set(BUILDERS.keys()) == ALL_TOPICS

    def test_parent_id_still_works(self) -> None:
        env = build_task_dispatch({"task_id": "t1"}, parent_id=777)
        assert env.parent_id == 777

    def test_canonical_events_still_serialize(self) -> None:
        """CanonicalEventMeta subclasses still produce valid envelopes."""
        from poc.k1_poc.events.conversation import UserInputReceived

        evt = UserInputReceived(event_id="e-back", text="compat")
        env = build_user_input(evt)  # type: ignore[arg-type]
        assert isinstance(env, Envelope)
        data = json.loads(env.payload)
        assert data["text"] == "compat"
        assert data["event_type"] == "conversation.user_input.received"
