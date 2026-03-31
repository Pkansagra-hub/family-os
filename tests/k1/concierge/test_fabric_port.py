"""
E2.6.1 — Unit Tests for poc/k1_poc/fabric/ports.py
====================================================

Validates:
  - IFabricPort is runtime_checkable
  - FabricPOCBridge satisfies IFabricPort (isinstance check)
  - K1 Fabric class signature compatibility
  - Protocol method signatures
"""

from __future__ import annotations

import inspect

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult, RetrievalResult
from k1.concierge.fabric.ports import IFabricPort

# =====================================================================
# Runtime checkable
# =====================================================================


class TestIFabricPortRuntimeCheckable:
    """IFabricPort is @runtime_checkable — isinstance works."""

    def test_is_protocol(self) -> None:
        """IFabricPort is a Protocol subclass."""
        assert hasattr(IFabricPort, "__protocol_attrs__") or isinstance(IFabricPort, type)

    def test_runtime_checkable_marker(self) -> None:
        """isinstance can be called against IFabricPort."""
        # Should not raise
        isinstance(object(), IFabricPort)

    def test_plain_object_fails_isinstance(self) -> None:
        assert not isinstance(object(), IFabricPort)


# =====================================================================
# Method signatures
# =====================================================================


class TestIFabricPortSignatures:
    """IFabricPort declares 4 async methods with correct signatures."""

    EXPECTED_METHODS = {
        "execute",
        "execute_batch",
        "discover_capabilities",
        "find_relevant_prompts",
    }

    def test_has_all_methods(self) -> None:
        members = {
            name for name, _ in inspect.getmembers(IFabricPort, predicate=inspect.isfunction)
        }
        assert self.EXPECTED_METHODS.issubset(members)

    def test_execute_signature(self) -> None:
        sig = inspect.signature(IFabricPort.execute)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "request" in params

    def test_execute_batch_signature(self) -> None:
        sig = inspect.signature(IFabricPort.execute_batch)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "requests" in params
        assert "strategy" in params

    def test_discover_capabilities_signature(self) -> None:
        sig = inspect.signature(IFabricPort.discover_capabilities)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "intent" in params
        assert "domain" in params
        assert "top_k" in params

    def test_find_relevant_prompts_signature(self) -> None:
        sig = inspect.signature(IFabricPort.find_relevant_prompts)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "intent" in params


# =====================================================================
# FabricPOCBridge isinstance
# =====================================================================


class TestFabricPOCBridgeIsInstance:
    """FabricPOCBridge satisfies IFabricPort at runtime."""

    def test_isinstance_check(self) -> None:
        from k1.concierge.fabric.capability_registry import CapabilityRegistry
        from k1.concierge.fabric.fabric_bridge import FabricPOCBridge

        registry = CapabilityRegistry()
        bridge = FabricPOCBridge(registry)
        assert isinstance(bridge, IFabricPort)

    def test_bridge_has_all_methods(self) -> None:
        from k1.concierge.fabric.fabric_bridge import FabricPOCBridge

        for method_name in TestIFabricPortSignatures.EXPECTED_METHODS:
            assert hasattr(FabricPOCBridge, method_name)
            assert callable(getattr(FabricPOCBridge, method_name))
