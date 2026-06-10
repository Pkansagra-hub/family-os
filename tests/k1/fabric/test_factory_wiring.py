"""GAP-P1-022 — Tests for FabricFactory Phase 1 wiring (Issue 7.2, step 21)."""

from __future__ import annotations

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.factory import FabricFactory
from k1.fabric.resolver.situated_resolver import ResolveSituationService
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.idempotency_store import IdempotencyStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Adapter helpers
# ──────────────────────────────────────────────────────────────────────


def _shared_adapters() -> dict:
    return {
        "event_port": LocalEventAdapter(capture_mode=False),
        "bridge": TestBridgeAdapter(),
        "model_gateway": TestModelGatewayAdapter(),
        "prompt_system": TestPromptSystemAdapter(),
        "delta_bus": TestDeltaBusAdapter(),
    }


def _ports_adapters() -> dict:
    return {
        "state_reader": TestSessionStateReaderAdapter(),
        **_shared_adapters(),
    }


def _gps() -> GlobalProjectionStore:
    s = GlobalProjectionStore(":memory:")
    s.open()
    return s


# ══════════════════════════════════════════════════════════════════════
# TestCreateSharedWithStores
# ══════════════════════════════════════════════════════════════════════


class TestCreateSharedWithStores:
    def test_wires_all_components(self):
        store = _gps()
        idem = IdempotencyStore(":memory:")
        idem.open()
        fabric = FabricFactory.create_shared(
            **_shared_adapters(),
            global_projection_store=store,
            idempotency_store=idem,
        )
        assert fabric.global_projection_store is store
        assert fabric.idempotency_store is idem
        assert fabric.constitution_loader is not None
        assert fabric.policy_selector is not None
        assert fabric.prompt_pack_builder is not None
        assert isinstance(fabric.situated_resolver, ResolveSituationService)

    def test_local_store_created_when_not_provided(self):
        store = _gps()
        fabric = FabricFactory.create_shared(
            **_shared_adapters(),
            global_projection_store=store,
        )
        # NEVER the global store as local.
        assert fabric.local_projection_store is not None
        assert fabric.local_projection_store is not store
        assert isinstance(fabric.local_projection_store, LocalProjectionStore)


# ══════════════════════════════════════════════════════════════════════
# TestCreateSharedWithoutStores
# ══════════════════════════════════════════════════════════════════════


class TestCreateSharedWithoutStores:
    def test_no_stores_leaves_phase1_none(self):
        fabric = FabricFactory.create_shared(**_shared_adapters())
        assert fabric.global_projection_store is None
        assert fabric.situated_resolver is None
        assert fabric.constitution_loader is None
        assert fabric.prompt_pack_builder is None


# ══════════════════════════════════════════════════════════════════════
# TestCreateWithPortsWithLocalStore
# ══════════════════════════════════════════════════════════════════════


class TestCreateWithPortsWithLocalStore:
    def test_uses_provided_local_store(self):
        store = _gps()
        local = LocalProjectionStore(":memory:")
        local.open()
        fabric = FabricFactory.create_with_ports(
            **_ports_adapters(),
            global_projection_store=store,
            local_projection_store=local,
        )
        assert fabric.local_projection_store is local


# ══════════════════════════════════════════════════════════════════════
# TestCreateWithPortsFallsBackToMemory
# ══════════════════════════════════════════════════════════════════════


class TestCreateWithPortsFallsBackToMemory:
    def test_creates_memory_local_not_global(self):
        store = _gps()
        fabric = FabricFactory.create_with_ports(
            **_ports_adapters(),
            global_projection_store=store,
        )
        assert fabric.local_projection_store is not None
        assert fabric.local_projection_store is not store
        assert isinstance(fabric.local_projection_store, LocalProjectionStore)


# ══════════════════════════════════════════════════════════════════════
# TestConstitutionLoaderShared
# ══════════════════════════════════════════════════════════════════════


class TestConstitutionLoaderShared:
    def test_same_loader_instance_everywhere(self):
        store = _gps()
        fabric = FabricFactory.create_shared(
            **_shared_adapters(),
            global_projection_store=store,
        )
        loader = fabric.constitution_loader
        assert loader is not None
        assert fabric.prompt_pack_builder.constitution_loader is loader
        assert fabric.situated_resolver.constitution_loader is loader


# ══════════════════════════════════════════════════════════════════════
# TestIdempotencyWiredToFacade
# ══════════════════════════════════════════════════════════════════════


class TestIdempotencyWiredToFacade:
    def test_facade_gets_idempotency_store(self):
        store = _gps()
        idem = IdempotencyStore(":memory:")
        idem.open()
        fabric = FabricFactory.create_shared(
            **_shared_adapters(),
            global_projection_store=store,
            idempotency_store=idem,
        )
        assert getattr(fabric.facade, "_idempotency_store", None) is idem
        # And the resolver gets it too (for the idempotency verdict step).
        assert fabric.situated_resolver.idempotency_store is idem


# ══════════════════════════════════════════════════════════════════════
# TestVerificationRunnerNotWiredByFactory
# ══════════════════════════════════════════════════════════════════════


class TestVerificationRunnerNotWiredByFactory:
    def test_verification_runner_none(self):
        store = _gps()
        fabric = FabricFactory.create_shared(
            **_shared_adapters(),
            global_projection_store=store,
        )
        # The verifier needs a native provider (S8) — kernel wires it later.
        assert fabric.verification_runner is None


# ══════════════════════════════════════════════════════════════════════
# TestResolveSituationServiceReceivesAllDeps
# ══════════════════════════════════════════════════════════════════════


class TestResolveSituationServiceReceivesAllDeps:
    def test_all_deps_wired(self):
        store = _gps()
        idem = IdempotencyStore(":memory:")
        idem.open()
        fabric = FabricFactory.create_shared(
            **_shared_adapters(),
            global_projection_store=store,
            idempotency_store=idem,
        )
        resolver = fabric.situated_resolver
        assert resolver.global_store is store
        assert resolver.local_store is fabric.local_projection_store
        assert resolver.policy_selector is fabric.policy_selector
        assert resolver.prompt_pack_builder is fabric.prompt_pack_builder
        assert resolver.constitution_loader is fabric.constitution_loader
        assert resolver.idempotency_store is idem
        assert resolver.resource_resolver is not None
        assert resolver.type_resolver is not None
        assert resolver.capability_binder is not None
