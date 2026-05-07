"""
Epic 6.4.2 -- test_wiring_contract.py -- Wiring Contract Compliance.

Verifies all declarations in k1/contracts/modules/fabric/wiring.contract.yaml
match the actual implementation:

  1. All required files exist on disk.
  2. Port interfaces have declared methods.
  3. All adapters implement their port Protocol.
  4. FabricFactory wiring creates a fully connected Fabric.

References:
  - wiring.contract.yaml (45+ required files, 5 capabilities, port interfaces)
  - fabric-implementation-plan.md Epic 6.4.2
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Project root for file-existence checks
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # d:\familyos
_FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ===================================================================
# 1. Required files exist on disk
# ===================================================================

# Files declared in wiring.contract.yaml -> code.required_files
# Split into files that exist and files that are renamed/missing.
_EXISTING_FILES = [
    "k1/fabric/__init__.py",
    "k1/fabric/types.py",
    "k1/fabric/core/__init__.py",
    "k1/fabric/core/registry.py",
    "k1/fabric/contracts/__init__.py",
    "k1/fabric/contracts/tool_contract.py",
    "k1/fabric/contracts/agent_contract.py",
    "k1/fabric/contracts/prompt_contract.py",
    "k1/fabric/contracts/workflow_contract.py",
    "k1/fabric/retrieval/__init__.py",
    "k1/fabric/retrieval/soft_ranker.py",
    "k1/fabric/provider_resolution/__init__.py",
    "k1/fabric/provider_resolution/resolver.py",
    "k1/fabric/policy/__init__.py",
    "k1/fabric/providers/__init__.py",
    "k1/fabric/providers/mcp_provider.py",
    "k1/fabric/providers/wasm_provider.py",
    "k1/fabric/providers/bridge_provider.py",
    "k1/fabric/providers/agent_provider.py",
    "k1/fabric/providers/workflow_provider.py",
    "k1/fabric/providers/concierge_provider.py",
    "k1/fabric/core/context_builder.py",
    "k1/fabric/output_validation/__init__.py",
    "k1/fabric/output_validation/pipeline.py",
    "k1/fabric/health/__init__.py",
    "k1/fabric/concurrency/__init__.py",
    "k1/fabric/concurrency/dispatcher.py",
    "k1/fabric/concurrency/timeout.py",
    "k1/fabric/ports/__init__.py",
    "k1/fabric/ports/event_port.py",
    "k1/fabric/ports/bridge_port.py",
]

# Files where contract name differs from implementation name
# (contract_path, actual_path)
_RENAMED_FILES = [
    ("k1/fabric/facade.py", "k1/fabric/fabric.py"),
    ("k1/fabric/contracts/validator.py", "k1/fabric/core/contract_validator.py"),
    ("k1/fabric/retrieval/semantic_index.py", "k1/fabric/retrieval/embedding_index.py"),
    (
        "k1/fabric/provider_resolution/selector.py",
        "k1/fabric/provider_resolution/provider_selector.py",
    ),
    ("k1/fabric/policy/engine.py", "k1/fabric/policy/policy_engine.py"),
    ("k1/fabric/health/checker.py", "k1/fabric/health/health_checker.py"),
    ("k1/fabric/ports/session_reader.py", "k1/fabric/ports/state_reader.py"),
    ("k1/fabric/ports/model_gateway_port.py", "k1/fabric/ports/model_gateway.py"),
    ("k1/fabric/ports/prompt_system_port.py", "k1/fabric/ports/prompt_system.py"),
]

# Files declared in contract but not yet implemented
_UNIMPLEMENTED_FILES = [
    "k1/fabric/provider_resolution/scoring.py",
    "k1/fabric/policy/guard.py",
    "k1/fabric/providers/agent_factory.py",
    "k1/fabric/providers/agent_pool.py",
    "k1/fabric/providers/scoped_tools.py",
    "k1/fabric/codecs/__init__.py",
    "k1/fabric/codecs/envelope_codec.py",
]

# Submodule __init__.py files required by the files constraints section
_REQUIRED_INITS = [
    "k1/fabric/__init__.py",
    "k1/fabric/core/__init__.py",
    "k1/fabric/contracts/__init__.py",
    "k1/fabric/retrieval/__init__.py",
    "k1/fabric/provider_resolution/__init__.py",
    "k1/fabric/policy/__init__.py",
    "k1/fabric/providers/__init__.py",
    "k1/fabric/output_validation/__init__.py",
    "k1/fabric/health/__init__.py",
    "k1/fabric/concurrency/__init__.py",
    "k1/fabric/ports/__init__.py",
]


class TestRequiredFilesExist:
    """Verify all files declared in wiring.contract.yaml exist on disk."""

    @pytest.mark.parametrize("rel_path", _EXISTING_FILES, ids=_EXISTING_FILES)
    def test_file_exists(self, rel_path: str) -> None:
        full = _PROJECT_ROOT / rel_path
        assert full.is_file(), f"Required file missing: {rel_path}"

    @pytest.mark.parametrize(
        "contract_path,actual_path",
        _RENAMED_FILES,
        ids=[f"{c}->{a}" for c, a in _RENAMED_FILES],
    )
    def test_renamed_file_exists(self, contract_path: str, actual_path: str) -> None:
        """
        Contract uses a different filename than implementation.

        Verify the ACTUAL file exists (the rename is documented).
        """
        full = _PROJECT_ROOT / actual_path
        assert full.is_file(), (
            f"Contract declares '{contract_path}' "
            f"(renamed to '{actual_path}') but actual file missing"
        )

    @pytest.mark.parametrize("rel_path", _REQUIRED_INITS, ids=_REQUIRED_INITS)
    def test_submodule_inits_exist(self, rel_path: str) -> None:
        """Submodule __init__.py files from files.required section."""
        full = _PROJECT_ROOT / rel_path
        assert full.is_file(), f"Required __init__.py missing: {rel_path}"


class TestUnimplementedFilesDocumented:
    """
    Files declared in contract that are not yet implemented.

    These are documented gaps -- xfail verifies they still don't exist
    (remove xfail when implemented).
    """

    @pytest.mark.parametrize("rel_path", _UNIMPLEMENTED_FILES, ids=_UNIMPLEMENTED_FILES)
    @pytest.mark.xfail(reason="Not yet implemented", strict=True)
    def test_unimplemented_file(self, rel_path: str) -> None:
        full = _PROJECT_ROOT / rel_path
        assert full.is_file(), f"Unimplemented: {rel_path}"


# ===================================================================
# 2. Port interfaces have declared methods
# ===================================================================


class TestSessionReaderPortMethods:
    """ISessionStateReader Protocol methods from wiring contract."""

    def _get_port(self) -> Any:
        from k1.fabric.ports.state_reader import ISessionStateReader

        return ISessionStateReader

    def test_has_read_section(self) -> None:
        cls = self._get_port()
        assert hasattr(cls, "read_section")

    def test_has_read_sections(self) -> None:
        cls = self._get_port()
        assert hasattr(cls, "read_sections")

    def test_has_get_snapshot(self) -> None:
        cls = self._get_port()
        assert hasattr(cls, "get_snapshot")


class TestEventPortMethods:
    """IEventPort Protocol methods."""

    def _get_port(self) -> Any:
        from k1.fabric.ports.event_port import IEventPort

        return IEventPort

    def test_has_emit(self) -> None:
        assert hasattr(self._get_port(), "emit")

    def test_has_subscribe(self) -> None:
        assert hasattr(self._get_port(), "subscribe")

    def test_has_unsubscribe(self) -> None:
        assert hasattr(self._get_port(), "unsubscribe")


class TestBridgePortMethods:
    """IBridgePort Protocol methods."""

    def _get_port(self) -> Any:
        from k1.fabric.ports.bridge_port import IFabricK0Port

        return IFabricK0Port

    def test_has_send_command(self) -> None:
        assert hasattr(self._get_port(), "send_command")

    def test_has_query(self) -> None:
        assert hasattr(self._get_port(), "query")

    def test_has_route_ifl(self) -> None:
        assert hasattr(self._get_port(), "route_ifl")

    def test_has_is_available(self) -> None:
        assert hasattr(self._get_port(), "is_available")

    def test_has_get_health(self) -> None:
        assert hasattr(self._get_port(), "get_health")


class TestModelGatewayPortMethods:
    """IModelGatewayPort Protocol methods."""

    def _get_port(self) -> Any:
        from k1.fabric.ports.model_gateway import IModelGatewayPort

        return IModelGatewayPort

    def test_has_create_handle(self) -> None:
        assert hasattr(self._get_port(), "create_handle")

    def test_has_is_model_loaded(self) -> None:
        assert hasattr(self._get_port(), "is_model_loaded")

    def test_has_list_models(self) -> None:
        assert hasattr(self._get_port(), "list_models")

    def test_has_find_model(self) -> None:
        assert hasattr(self._get_port(), "find_model")


class TestPromptSystemPortMethods:
    """IPromptSystemPort Protocol methods."""

    def _get_port(self) -> Any:
        from k1.fabric.ports.prompt_system import IPromptSystemPort

        return IPromptSystemPort

    def test_has_resolve(self) -> None:
        assert hasattr(self._get_port(), "resolve")

    def test_has_compile(self) -> None:
        assert hasattr(self._get_port(), "compile")


class TestDeltaBusPortMethods:
    """IDeltaBusPort Protocol methods (FAB-008)."""

    def _get_port(self) -> Any:
        from k1.fabric.ports.delta_bus import IDeltaBusPort

        return IDeltaBusPort

    def test_has_emit_delta(self) -> None:
        assert hasattr(self._get_port(), "emit_delta")


# ===================================================================
# 3. Adapters implement their port Protocol
# ===================================================================


class TestAdapterImplementsPort:
    """
    Verify each test adapter has the methods declared by its port Protocol.

    adapters/ contains both production and test adapters. We verify the
    test adapters (used by FabricFactory) implement port methods.
    """

    def test_session_reader_adapter(self) -> None:
        """TestSessionStateReaderAdapter implements ISessionStateReader methods."""
        from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter

        methods = ["read_section", "read_sections", "get_snapshot"]
        for method in methods:
            assert hasattr(
                TestSessionStateReaderAdapter, method
            ), f"TestSessionStateReaderAdapter missing method: {method}"

    def test_local_event_adapter(self) -> None:
        """LocalEventAdapter implements IEventPort methods."""
        from k1.fabric.adapters.local_event import LocalEventAdapter

        methods = ["emit", "subscribe", "unsubscribe"]
        for method in methods:
            assert hasattr(LocalEventAdapter, method), f"LocalEventAdapter missing method: {method}"

    def test_bridge_adapter(self) -> None:
        """TestBridgeAdapter implements IBridgePort methods."""
        from k1.fabric.adapters.test_bridge import TestBridgeAdapter

        methods = ["send_command", "query", "route_ifl", "is_available", "get_health"]
        for method in methods:
            assert hasattr(TestBridgeAdapter, method), f"TestBridgeAdapter missing method: {method}"

    def test_model_gateway_adapter(self) -> None:
        """TestModelGatewayAdapter implements IModelGatewayPort methods."""
        from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter

        methods = ["create_handle", "is_model_loaded", "list_models", "find_model"]
        for method in methods:
            assert hasattr(
                TestModelGatewayAdapter, method
            ), f"TestModelGatewayAdapter missing method: {method}"

    def test_prompt_system_adapter(self) -> None:
        """TestPromptSystemAdapter implements IPromptSystemPort methods."""
        from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter

        methods = ["resolve", "compile"]
        for method in methods:
            assert hasattr(
                TestPromptSystemAdapter, method
            ), f"TestPromptSystemAdapter missing method: {method}"

    def test_delta_bus_adapter(self) -> None:
        """TestDeltaBusAdapter implements IDeltaBusPort methods."""
        from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter

        methods = ["emit_delta"]
        for method in methods:
            assert hasattr(
                TestDeltaBusAdapter, method
            ), f"TestDeltaBusAdapter missing method: {method}"

    def test_mcp_transport_adapter(self) -> None:
        """TestMCPTransport adapter exists and is importable."""
        from k1.fabric.adapters.test_mcp_transport import TestMCPTransport

        assert inspect.isclass(TestMCPTransport)

    def test_wasm_runtime_adapter(self) -> None:
        """TestWASMRuntime adapter exists and is importable."""
        from k1.fabric.adapters.test_wasm_runtime import TestWASMRuntime

        assert inspect.isclass(TestWASMRuntime)


# ===================================================================
# 4. Production adapters
# ===================================================================


class TestProductionAdaptersExist:
    """Verify real (non-test) adapters exist."""

    def test_sessionstate_reader_adapter(self) -> None:
        from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter

        assert inspect.isclass(SessionStateReaderAdapter)

    def test_local_event_adapter(self) -> None:
        from k1.fabric.adapters.local_event import LocalEventAdapter

        assert inspect.isclass(LocalEventAdapter)

    def test_bridge_connection_adapter(self) -> None:
        from k1.fabric.adapters.bridge_connection import BridgeConnectionAdapter

        assert inspect.isclass(BridgeConnectionAdapter)

    def test_auto_mcp_transport(self) -> None:
        from k1.fabric.adapters.auto_mcp_transport import AutoDiscoveryMCPTransport

        assert inspect.isclass(AutoDiscoveryMCPTransport)

    def test_auto_wasm_runtime(self) -> None:
        from k1.fabric.adapters.auto_wasm_runtime import AutoDiscoveryWASMRuntime

        assert inspect.isclass(AutoDiscoveryWASMRuntime)


# ===================================================================
# 5. Factory wiring
# ===================================================================


class TestFactoryWiringContract:
    """
    Verify FabricFactory.create_standalone() wires all declared subsystems.

    The Fabric container holds: facade, retrieval, registry_api, registry,
    module_loader, health_checker, event_port, event_emitter.
    The CapabilityFabric (facade) holds: _resolver, _context_builder,
    _validation_pipeline, _event_emitter, _registry, _provider_factory.
    """

    @pytest.fixture()
    def fabric(self) -> Any:
        from k1.fabric.factory import FabricFactory

        return FabricFactory.create_standalone(contracts_dir=str(_FIXTURES_DIR))

    def test_has_registry(self, fabric: Any) -> None:
        assert hasattr(fabric, "registry")
        assert fabric.registry is not None

    def test_has_retrieval(self, fabric: Any) -> None:
        assert hasattr(fabric, "retrieval")
        assert fabric.retrieval is not None

    def test_has_facade(self, fabric: Any) -> None:
        assert hasattr(fabric, "facade")
        assert fabric.facade is not None

    def test_has_event_emitter(self, fabric: Any) -> None:
        assert hasattr(fabric, "event_emitter")

    def test_has_event_port(self, fabric: Any) -> None:
        assert hasattr(fabric, "event_port")

    def test_has_health_checker(self, fabric: Any) -> None:
        assert hasattr(fabric, "health_checker")
        assert fabric.health_checker is not None

    def test_has_module_loader(self, fabric: Any) -> None:
        assert hasattr(fabric, "module_loader")

    def test_has_registry_api(self, fabric: Any) -> None:
        assert hasattr(fabric, "registry_api")
        assert fabric.registry_api is not None

    def test_facade_has_resolver(self, fabric: Any) -> None:
        """CapabilityFabric facade has _resolver for provider resolution."""
        assert hasattr(fabric.facade, "_resolver")

    def test_facade_has_context_builder(self, fabric: Any) -> None:
        """CapabilityFabric facade has _context_builder."""
        assert hasattr(fabric.facade, "_context_builder")

    def test_facade_has_validation_pipeline(self, fabric: Any) -> None:
        """CapabilityFabric facade has _validation_pipeline."""
        assert hasattr(fabric.facade, "_validation_pipeline")

    def test_facade_has_provider_factory(self, fabric: Any) -> None:
        """CapabilityFabric facade has _provider_factory."""
        assert hasattr(fabric.facade, "_provider_factory")


class TestFactoryWiringPortInjection:
    """
    Verify create_for_testing injects test adapters into the Fabric.

    The event port should be a LocalEventAdapter in capture mode.
    """

    def test_event_port_is_local_adapter(self) -> None:
        from k1.fabric.adapters.local_event import LocalEventAdapter
        from k1.fabric.factory import FabricFactory

        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(_FIXTURES_DIR),
        )
        # Fabric container exposes event_port directly
        port = getattr(fabric, "event_port", None)
        assert port is not None, "Fabric.event_port not set"
        assert isinstance(port, LocalEventAdapter)


# ===================================================================
# 6. Wiring contract capability provisions
# ===================================================================


class TestCapabilityProvisions:
    """
    Verify the 5 capabilities declared in wiring.contract.yaml
    are backed by real implementation files.

    fabric:execute:v1  -> facade.py (fabric.py)
    fabric:retrieve:v1 -> retrieval (embedding_index.py)
    fabric:register:v1 -> core/registry.py
    fabric:resolve:v1  -> provider_resolution/resolver.py
    fabric:health:v1   -> health/health_checker.py
    """

    @pytest.mark.parametrize(
        "capability,impl_file",
        [
            ("fabric:execute:v1", "k1/fabric/fabric.py"),
            ("fabric:retrieve:v1", "k1/fabric/retrieval/embedding_index.py"),
            ("fabric:register:v1", "k1/fabric/core/registry.py"),
            ("fabric:resolve:v1", "k1/fabric/provider_resolution/resolver.py"),
            ("fabric:health:v1", "k1/fabric/health/health_checker.py"),
        ],
        ids=[
            "execute:v1",
            "retrieve:v1",
            "register:v1",
            "resolve:v1",
            "health:v1",
        ],
    )
    def test_capability_backed_by_file(self, capability: str, impl_file: str) -> None:
        """Each declared capability has an implementation file."""
        full = _PROJECT_ROOT / impl_file
        assert full.is_file(), f"Capability '{capability}' backed by '{impl_file}' but file missing"


# ===================================================================
# 7. Forbidden patterns
# ===================================================================


class TestForbiddenPatterns:
    """Verify forbidden patterns from wiring contract files section."""

    def test_no_pyc_in_fabric_root(self) -> None:
        """No .pyc files in k1/fabric/ (excluding __pycache__)."""
        fabric_root = _PROJECT_ROOT / "k1" / "fabric"
        pyc_files = [f for f in fabric_root.glob("*.pyc") if "__pycache__" not in str(f)]
        assert len(pyc_files) == 0, f"Found .pyc files: {pyc_files}"


# ===================================================================
# 8. Wiring imports (cross-module dependencies)
# ===================================================================


class TestWiringImports:
    """
    Verify wiring.imports declarations: fabric depends on
    kernel, bus, sessionstate and imports specific symbols.
    """

    def test_sessionstate_manager_importable(self) -> None:
        """SessionStateManager from sessionstate (used by context_builder)."""
        from k1.sessionstate import SessionStateManager

        assert inspect.isclass(SessionStateManager)

    def test_forbidden_sessionstate_writer_absent(self) -> None:
        """FAB-01: Fabric never imports a SessionState writer."""
        import k1.fabric

        assert not hasattr(k1.fabric, "ISessionStateWriter")

    def test_context_builder_uses_reader_not_writer(self) -> None:
        """ContextBuilder depends on ISessionStateReader, not writer."""
        source = (_PROJECT_ROOT / "k1" / "fabric" / "core" / "context_builder.py").read_text()
        assert (
            "ISessionStateReader" in source
            or "state_reader" in source
            or "session_reader" in source
        )
        assert "ISessionStateWriter" not in source
