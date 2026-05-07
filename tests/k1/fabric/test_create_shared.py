"""
Issue 2.0.13 -- test_create_shared.py -- FabricFactory.create_shared() wiring.

Verifies the shared Fabric factory method:
  1. Returns a fully wired Fabric instance.
  2. Uses NullSessionStateReaderAdapter internally.
  3. All subsystems are wired (facade, retrieval, registry, etc.).
  4. Defaults to production_mode=True.
  5. Accepts optional capability_registry for sharing (SIM-D-36).

References:
  - 09_wiring_plan.md Issue 2.0.13
  - 12_fabric_audit.md S3 shared Fabric requirements
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.null_state_reader import NullSessionStateReaderAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def shared_fabric() -> Fabric:
    """Shared Fabric built with test adapters via create_shared()."""
    return FabricFactory.create_shared(
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
        contracts_dir=str(_FIXTURES_DIR),
    )


class TestCreateSharedReturnsWiredFabric:
    """Verify create_shared() returns a fully wired Fabric container."""

    def test_returns_fabric_instance(self, shared_fabric: Fabric) -> None:
        assert isinstance(shared_fabric, Fabric)

    def test_has_facade(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.facade is not None

    def test_has_retrieval(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.retrieval is not None

    def test_has_registry_api(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.registry_api is not None

    def test_has_registry(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.registry is not None

    def test_has_health_checker(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.health_checker is not None

    def test_has_module_loader(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.module_loader is not None

    def test_has_event_port(self, shared_fabric: Fabric) -> None:
        assert shared_fabric.event_port is not None

    def test_facade_has_resolver(self, shared_fabric: Fabric) -> None:
        assert hasattr(shared_fabric.facade, "_resolver")

    def test_facade_has_context_builder(self, shared_fabric: Fabric) -> None:
        assert hasattr(shared_fabric.facade, "_context_builder")

    def test_facade_has_validation_pipeline(self, shared_fabric: Fabric) -> None:
        assert hasattr(shared_fabric.facade, "_validation_pipeline")

    def test_facade_has_provider_factory(self, shared_fabric: Fabric) -> None:
        assert hasattr(shared_fabric.facade, "_provider_factory")


class TestCreateSharedUsesNullStateReader:
    """Verify NullSessionStateReaderAdapter is wired internally."""

    def test_context_builder_uses_null_reader(self) -> None:
        """The ContextBuilder inside the facade receives NullSessionStateReaderAdapter."""
        fabric = FabricFactory.create_shared(
            event_port=LocalEventAdapter(capture_mode=False),
            bridge=TestBridgeAdapter(),
            model_gateway=TestModelGatewayAdapter(),
            prompt_system=TestPromptSystemAdapter(),
            delta_bus=TestDeltaBusAdapter(),
            contracts_dir=str(_FIXTURES_DIR),
        )
        ctx_builder = fabric.facade._context_builder
        state_reader = getattr(ctx_builder, "_state_reader", None)
        assert isinstance(state_reader, NullSessionStateReaderAdapter)


class TestCreateSharedDefaults:
    """Verify default values for optional parameters."""

    def test_production_mode_default_true(self) -> None:
        """Shared Fabric defaults to production_mode=True."""
        fabric = FabricFactory.create_shared(
            event_port=LocalEventAdapter(capture_mode=False),
            bridge=TestBridgeAdapter(),
            model_gateway=TestModelGatewayAdapter(),
            prompt_system=TestPromptSystemAdapter(),
            delta_bus=TestDeltaBusAdapter(),
            contracts_dir=str(_FIXTURES_DIR),
        )
        # production_mode=True enables FabricDispatcher
        dispatcher = getattr(fabric.facade, "_dispatcher", None)
        assert dispatcher is not None, "production_mode=True should wire a FabricDispatcher"

    def test_production_mode_override_false(self) -> None:
        """Can disable production_mode for testing."""
        fabric = FabricFactory.create_shared(
            event_port=LocalEventAdapter(capture_mode=False),
            bridge=TestBridgeAdapter(),
            model_gateway=TestModelGatewayAdapter(),
            prompt_system=TestPromptSystemAdapter(),
            delta_bus=TestDeltaBusAdapter(),
            production_mode=False,
            contracts_dir=str(_FIXTURES_DIR),
        )
        assert isinstance(fabric, Fabric)

    def test_accepts_capability_registry(self) -> None:
        """Optional capability_registry parameter is accepted (SIM-D-36)."""
        from k1.fabric.core.contract_validator import ContractValidator
        from k1.fabric.core.registry import CapabilityRegistry

        event_port = LocalEventAdapter(capture_mode=False)
        validator = ContractValidator()
        shared_registry = CapabilityRegistry(validator=validator, event_port=event_port)

        fabric = FabricFactory.create_shared(
            event_port=event_port,
            bridge=TestBridgeAdapter(),
            model_gateway=TestModelGatewayAdapter(),
            prompt_system=TestPromptSystemAdapter(),
            delta_bus=TestDeltaBusAdapter(),
            capability_registry=shared_registry,
            contracts_dir=str(_FIXTURES_DIR),
        )
        # The fabric should use the provided registry
        assert fabric.registry is shared_registry
