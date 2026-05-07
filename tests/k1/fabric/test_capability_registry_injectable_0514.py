"""
Tests for E-0.5.14: Fabric CapabilityRegistry Not Injectable.

I-0.5.14.1 -- capability_registry param on create_with_ports()
I-0.5.14.2 -- shared registry across 2 Fabric instances

Coverage:
  - Backward compatibility: None → creates fresh registry (default)
  - Injection: pre-built registry is used as-is
  - Shared registry: 2 Fabric instances share the same registry object
  - Cross-instance visibility: contract registered via f1 visible via f2
  - Identity: injected registry is `is` the same object on Fabric.registry
"""

from __future__ import annotations

from typing import Any

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityContract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_adapters() -> dict[str, Any]:
    """Return a dict of all 6 required port adapters for create_with_ports()."""
    return dict(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
    )


def _make_contract(name: str, version: str = "1.0.0", domain: str = "test") -> CapabilityContract:
    """Create a minimal CapabilityContract for registry tests."""
    return CapabilityContract(
        name=name,
        version=version,
        domain=[domain],
        description=f"Test contract {name}",
        provider_type="mcp",
        provider_id=f"provider-{name}",
    )


# ===========================================================================
# I-0.5.14.1 -- capability_registry parameter on create_with_ports()
# ===========================================================================


class TestCapabilityRegistryParam:
    """Tests for the new capability_registry parameter."""

    def test_default_none_creates_fresh_registry(self) -> None:
        """Without capability_registry, a NEW registry is constructed."""
        adapters = _make_test_adapters()
        fabric = FabricFactory.create_with_ports(**adapters)
        assert fabric.registry is not None
        assert isinstance(fabric.registry, CapabilityRegistry)

    def test_injected_registry_is_used(self) -> None:
        """When capability_registry is provided, it is used directly."""
        shared = CapabilityRegistry(validator=ContractValidator())
        adapters = _make_test_adapters()
        fabric = FabricFactory.create_with_ports(**adapters, capability_registry=shared)
        assert fabric.registry is shared

    def test_injected_registry_identity(self) -> None:
        """The injected registry object is the EXACT same instance (not a copy)."""
        shared = CapabilityRegistry(validator=ContractValidator())
        adapters = _make_test_adapters()
        fabric = FabricFactory.create_with_ports(**adapters, capability_registry=shared)
        assert id(fabric.registry) == id(shared)

    def test_standalone_always_creates_fresh(self) -> None:
        """create_standalone() always creates a new registry (no param)."""
        f1 = FabricFactory.create_standalone()
        f2 = FabricFactory.create_standalone()
        assert f1.registry is not f2.registry

    def test_for_testing_always_creates_fresh(self) -> None:
        """create_for_testing() always creates a new registry (no param)."""
        f1 = FabricFactory.create_for_testing()
        f2 = FabricFactory.create_for_testing()
        assert f1.registry is not f2.registry

    def test_none_explicit_creates_fresh(self) -> None:
        """Explicit capability_registry=None behaves same as default."""
        adapters = _make_test_adapters()
        fabric = FabricFactory.create_with_ports(**adapters, capability_registry=None)
        assert fabric.registry is not None
        assert isinstance(fabric.registry, CapabilityRegistry)


# ===========================================================================
# I-0.5.14.2 -- Shared registry across multiple Fabric instances
# ===========================================================================


class TestSharedRegistry:
    """Tests for sharing a registry across 2+ Fabric instances (SIM-D-36)."""

    def test_two_fabrics_share_same_registry(self) -> None:
        """Two Fabric instances injected with same registry share it."""
        shared = CapabilityRegistry(validator=ContractValidator())
        f1 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)
        f2 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)
        assert f1.registry is f2.registry

    def test_contract_registered_via_f1_visible_via_f2(self) -> None:
        """Contract registered through f1's registry is visible from f2."""
        shared = CapabilityRegistry(validator=ContractValidator())
        f1 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)
        f2 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)

        contract = _make_contract("tool.read.shared_test", "1.0.0", "shared")
        shared.register(contract, skip_validation=True)

        # Both instances see the contract
        assert f1.registry.lookup("tool.read.shared_test") is contract
        assert f2.registry.lookup("tool.read.shared_test") is contract

    def test_contract_registered_via_shared_visible_in_both(self) -> None:
        """Register directly on shared, verify both Fabrics see it."""
        shared = CapabilityRegistry(validator=ContractValidator())
        f1 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)
        f2 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)

        c1 = _make_contract("tool.read.alpha", "1.0.0", "domain_a")
        c2 = _make_contract("tool.read.beta", "2.0.0", "domain_b")
        shared.register(c1, skip_validation=True)
        shared.register(c2, skip_validation=True)

        assert f1.registry.contains("tool.read.alpha")
        assert f1.registry.contains("tool.read.beta")
        assert f2.registry.contains("tool.read.alpha")
        assert f2.registry.contains("tool.read.beta")

    def test_unregister_visible_in_both(self) -> None:
        """Unregistering from shared registry is visible in both Fabrics."""
        shared = CapabilityRegistry(validator=ContractValidator())
        contract = _make_contract("tool.read.removable", "1.0.0")
        shared.register(contract, skip_validation=True)

        f1 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)
        f2 = FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)

        assert f1.registry.contains("tool.read.removable")
        shared.unregister("tool.read.removable")
        assert not f1.registry.contains("tool.read.removable")
        assert not f2.registry.contains("tool.read.removable")

    def test_three_fabrics_share_registry(self) -> None:
        """Three Fabric instances all share the same registry."""
        shared = CapabilityRegistry(validator=ContractValidator())
        fabrics = [
            FabricFactory.create_with_ports(**_make_test_adapters(), capability_registry=shared)
            for _ in range(3)
        ]
        assert all(f.registry is shared for f in fabrics)

    def test_mixed_injected_and_standalone(self) -> None:
        """Injected and standalone Fabrics have DIFFERENT registries."""
        shared = CapabilityRegistry(validator=ContractValidator())
        f_injected = FabricFactory.create_with_ports(
            **_make_test_adapters(), capability_registry=shared
        )
        f_standalone = FabricFactory.create_standalone()
        assert f_injected.registry is shared
        assert f_standalone.registry is not shared

    def test_pre_populated_registry_visible_after_injection(self) -> None:
        """Contracts registered BEFORE injection are visible in Fabric."""
        shared = CapabilityRegistry(validator=ContractValidator())
        contract = _make_contract("tool.read.pre_pop", "1.0.0")
        shared.register(contract, skip_validation=True)

        fabric = FabricFactory.create_with_ports(
            **_make_test_adapters(), capability_registry=shared
        )
        assert fabric.registry.lookup("tool.read.pre_pop") is contract
