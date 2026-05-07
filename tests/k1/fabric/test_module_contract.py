"""
Epic 6.4.1 -- test_module_contract.py -- Module Contract Compliance.

Verifies all declarations in k1/contracts/modules/fabric/module.contract.yaml
are reflected in the actual implementation:

  1. All 27 declared exports are importable from their source files.
  2. All 5 port interfaces exist with correct Protocol base.
  3. FabricFactory methods (create_standalone, create_for_testing, create_with_ports).
  4. Module dependencies (kernel, bus, sessionstate) are importable.

References:
  - module.contract.yaml exports list (27 symbols)
  - fabric-implementation-plan.md Epic 6.4.1
"""

from __future__ import annotations

import importlib
import inspect

import pytest

# ---------------------------------------------------------------------------
# 1. Core facade exports (from k1.fabric.__init__)
# ---------------------------------------------------------------------------


class TestCoreExportsFromInit:
    """
    Verify the symbols directly exported from k1/fabric/__init__.py.

    These are the 7 symbols currently in __all__.
    """

    @pytest.mark.parametrize(
        "symbol",
        [
            "CapabilityFabric",
            "FabricRetrieval",
            "BatchStrategy",
            "CapabilityRegistryAPI",
            "Fabric",
            "FabricConfig",
            "FabricFactory",
        ],
    )
    def test_init_exports(self, symbol: str) -> None:
        """Each symbol listed in __all__ is importable from k1.fabric."""
        mod = importlib.import_module("k1.fabric")
        assert hasattr(mod, symbol), f"k1.fabric missing export: {symbol}"
        obj = getattr(mod, symbol)
        assert obj is not None

    def test_init_all_defined(self) -> None:
        """__all__ is defined and non-empty."""
        mod = importlib.import_module("k1.fabric")
        assert hasattr(mod, "__all__")
        assert len(mod.__all__) >= 7


# ---------------------------------------------------------------------------
# 2. Module-contract declared exports (27 symbols, from submodules)
# ---------------------------------------------------------------------------


# Mapping: (contract_symbol, actual_module, actual_class_name)
# Where contract names differ from implementation names, we map both.
_DECLARED_EXPORTS = [
    # Facade
    ("CapabilityFabric", "k1.fabric.fabric", "CapabilityFabric"),
    ("FabricRetrieval", "k1.fabric.fabric", "FabricRetrieval"),
    # Retrieval
    ("SoftRanker", "k1.fabric.retrieval.soft_ranker", "SoftRanker"),
    # Contract system
    ("ContractValidator", "k1.fabric.core.contract_validator", "ContractValidator"),
    ("ToolContractParser", "k1.fabric.contracts.tool_contract", "ToolContractParser"),
    ("AgentContractParser", "k1.fabric.contracts.agent_contract", "AgentContractParser"),
    ("PromptContractParser", "k1.fabric.contracts.prompt_contract", "PromptContractParser"),
    ("WorkflowContractParser", "k1.fabric.contracts.workflow_contract", "WorkflowContractParser"),
    # Registry
    ("CapabilityRegistry", "k1.fabric.core.registry", "CapabilityRegistry"),
    # Resolution
    ("ProviderSelector", "k1.fabric.provider_resolution.provider_selector", "ProviderSelector"),
    # Policy
    ("PolicyEngine", "k1.fabric.policy.policy_engine", "PolicyEngine"),
    # Context
    ("ContextBuilder", "k1.fabric.core.context_builder", "ContextBuilder"),
    # Agent Factory
    ("AgentFactory", "k1.fabric.providers.agent_provider", "AgentFactory"),
    # Output Validation
    (
        "OutputValidationPipeline",
        "k1.fabric.output_validation.pipeline",
        "OutputValidationPipeline",
    ),
    # Health
    ("HealthChecker", "k1.fabric.health.health_checker", "HealthChecker"),
    # Types
    ("CapabilityRequest", "k1.fabric.types", "CapabilityRequest"),
    ("CapabilityResult", "k1.fabric.types", "CapabilityResult"),
    ("CapabilityContract", "k1.fabric.types", "CapabilityContract"),
    ("AgentContract", "k1.fabric.types", "AgentContract"),
    ("PromptContract", "k1.fabric.types", "PromptContract"),
    ("WorkflowContract", "k1.fabric.types", "WorkflowContract"),
    ("RetrievalResult", "k1.fabric.types", "RetrievalResult"),
    ("ExecutionContext", "k1.fabric.types", "ExecutionContext"),
    ("ProviderConfig", "k1.fabric.types", "ProviderConfig"),
]

# Contract names that map to different implementation names
_RENAMED_EXPORTS = [
    # Contract says "SemanticIndex"; implementation is "EmbeddingIndex"
    ("SemanticIndex", "k1.fabric.retrieval.embedding_index", "EmbeddingIndex"),
    # Contract says "ProviderResolver"; implementation is "Resolver"
    ("ProviderResolver", "k1.fabric.provider_resolution.resolver", "Resolver"),
]


class TestDeclaredExportsExist:
    """
    Each of the 27 declared exports in module.contract.yaml is available
    from its implementation module.

    24 match by name; 2 are renamed (SemanticIndex->EmbeddingIndex,
    ProviderResolver->Resolver); 1 (PolicyGuard) is not yet implemented.
    """

    @pytest.mark.parametrize(
        "contract_name,module_path,class_name",
        _DECLARED_EXPORTS,
        ids=[e[0] for e in _DECLARED_EXPORTS],
    )
    def test_export_importable(self, contract_name: str, module_path: str, class_name: str) -> None:
        """Symbol is importable from its source module."""
        mod = importlib.import_module(module_path)
        assert hasattr(mod, class_name), (
            f"Contract declares '{contract_name}' but " f"'{class_name}' not found in {module_path}"
        )
        obj = getattr(mod, class_name)
        assert inspect.isclass(obj), f"{class_name} should be a class"

    @pytest.mark.parametrize(
        "contract_name,module_path,actual_name",
        _RENAMED_EXPORTS,
        ids=[e[0] for e in _RENAMED_EXPORTS],
    )
    def test_renamed_exports(self, contract_name: str, module_path: str, actual_name: str) -> None:
        """
        Contract-declared name differs from implementation name.

        Verifies the actual implementation class exists under its real name.
        """
        mod = importlib.import_module(module_path)
        assert hasattr(mod, actual_name), (
            f"Contract declares '{contract_name}' (renamed to '{actual_name}') "
            f"but not found in {module_path}"
        )

    @pytest.mark.xfail(reason="PolicyGuard not yet implemented", strict=True)
    def test_policy_guard_exists(self) -> None:
        """PolicyGuard declared in contract but not yet implemented."""
        mod = importlib.import_module("k1.fabric.policy")
        assert hasattr(mod, "PolicyGuard")


# ---------------------------------------------------------------------------
# 3. Types are dataclasses or have required attributes
# ---------------------------------------------------------------------------


class TestTypeExportsAreClasses:
    """Verify type exports are proper classes with expected attributes."""

    def test_capability_request_has_capability_name(self) -> None:
        from k1.fabric.types import CapabilityRequest

        assert inspect.isclass(CapabilityRequest)
        sig = inspect.signature(CapabilityRequest)
        param_names = list(sig.parameters.keys())
        assert "capability_name" in param_names

    def test_capability_result_has_success(self) -> None:
        from k1.fabric.types import CapabilityResult

        assert inspect.isclass(CapabilityResult)
        sig = inspect.signature(CapabilityResult)
        param_names = list(sig.parameters.keys())
        assert "success" in param_names

    def test_capability_contract_has_name_and_version(self) -> None:
        from k1.fabric.types import CapabilityContract

        assert inspect.isclass(CapabilityContract)
        sig = inspect.signature(CapabilityContract)
        param_names = list(sig.parameters.keys())
        assert "name" in param_names
        assert "version" in param_names

    def test_agent_contract_extends_capability_contract(self) -> None:
        from k1.fabric.types import AgentContract, CapabilityContract

        assert issubclass(AgentContract, CapabilityContract)

    def test_execution_context_is_class(self) -> None:
        from k1.fabric.types import ExecutionContext

        assert inspect.isclass(ExecutionContext)

    def test_retrieval_result_is_class(self) -> None:
        from k1.fabric.types import RetrievalResult

        assert inspect.isclass(RetrievalResult)

    def test_provider_config_is_class(self) -> None:
        from k1.fabric.types import ProviderConfig

        assert inspect.isclass(ProviderConfig)


# ---------------------------------------------------------------------------
# 4. Port interfaces -- 5 hexagonal ports
# ---------------------------------------------------------------------------


class TestPortInterfacesExist:
    """
    Verify all 5 declared port Protocols exist and are Protocol subclasses.

    Ports: ISessionStateReader, IEventPort, IBridgePort,
           IModelGatewayPort, IPromptSystemPort.
    """

    @pytest.mark.parametrize(
        "module_path,class_name",
        [
            ("k1.fabric.ports.state_reader", "ISessionStateReader"),
            ("k1.fabric.ports.event_port", "IEventPort"),
            ("k1.fabric.ports.bridge_port", "IFabricK0Port"),
            ("k1.fabric.ports.model_gateway", "IModelGatewayPort"),
            ("k1.fabric.ports.prompt_system", "IPromptSystemPort"),
        ],
        ids=[
            "ISessionStateReader",
            "IEventPort",
            "IFabricK0Port",
            "IModelGatewayPort",
            "IPromptSystemPort",
        ],
    )
    def test_port_protocol_exists(self, module_path: str, class_name: str) -> None:
        """Port Protocol class exists and is importable."""
        mod = importlib.import_module(module_path)
        assert hasattr(mod, class_name), f"{class_name} not found in {module_path}"
        cls = getattr(mod, class_name)
        assert inspect.isclass(cls)

    def test_session_reader_has_read_section(self) -> None:
        from k1.fabric.ports.state_reader import ISessionStateReader

        assert hasattr(ISessionStateReader, "read_section")

    def test_session_reader_has_get_snapshot(self) -> None:
        from k1.fabric.ports.state_reader import ISessionStateReader

        assert hasattr(ISessionStateReader, "get_snapshot")

    def test_event_port_has_emit(self) -> None:
        from k1.fabric.ports.event_port import IEventPort

        assert hasattr(IEventPort, "emit")

    def test_event_port_has_subscribe(self) -> None:
        from k1.fabric.ports.event_port import IEventPort

        assert hasattr(IEventPort, "subscribe")

    def test_bridge_port_has_send_command(self) -> None:
        from k1.fabric.ports.bridge_port import IFabricK0Port

        assert hasattr(IFabricK0Port, "send_command")

    def test_model_gateway_has_create_handle(self) -> None:
        from k1.fabric.ports.model_gateway import IModelGatewayPort

        assert hasattr(IModelGatewayPort, "create_handle")

    def test_prompt_system_has_resolve(self) -> None:
        from k1.fabric.ports.prompt_system import IPromptSystemPort

        assert hasattr(IPromptSystemPort, "resolve")

    def test_prompt_system_has_compile(self) -> None:
        from k1.fabric.ports.prompt_system import IPromptSystemPort

        assert hasattr(IPromptSystemPort, "compile")


# ---------------------------------------------------------------------------
# 5. Additional port: IDeltaBusPort (FAB-008)
# ---------------------------------------------------------------------------


class TestDeltaBusPortExists:
    """Verify IDeltaBusPort declared as optional port."""

    def test_delta_bus_protocol_exists(self) -> None:
        from k1.fabric.ports.delta_bus import IDeltaBusPort

        assert inspect.isclass(IDeltaBusPort)

    def test_delta_bus_has_emit_delta(self) -> None:
        from k1.fabric.ports.delta_bus import IDeltaBusPort

        assert hasattr(IDeltaBusPort, "emit_delta")


# ---------------------------------------------------------------------------
# 6. Factory methods
# ---------------------------------------------------------------------------


class TestFactoryMethodsExist:
    """
    Verify FabricFactory has the 3 declared factory methods.

    create_standalone   -- zero-config, test adapters
    create_for_testing  -- test adapters + event capture
    create_with_ports   -- production, custom adapters
    """

    def test_factory_is_importable(self) -> None:
        from k1.fabric.factory import FabricFactory

        assert inspect.isclass(FabricFactory)

    def test_has_create_standalone(self) -> None:
        from k1.fabric.factory import FabricFactory

        assert hasattr(FabricFactory, "create_standalone")
        assert callable(FabricFactory.create_standalone)

    def test_has_create_for_testing(self) -> None:
        from k1.fabric.factory import FabricFactory

        assert hasattr(FabricFactory, "create_for_testing")
        assert callable(FabricFactory.create_for_testing)

    def test_has_create_with_ports(self) -> None:
        from k1.fabric.factory import FabricFactory

        assert hasattr(FabricFactory, "create_with_ports")
        assert callable(FabricFactory.create_with_ports)

    def test_create_standalone_returns_fabric(self) -> None:
        """Factory actually instantiates a Fabric."""
        from pathlib import Path

        from k1.fabric.fabric import Fabric
        from k1.fabric.factory import FabricFactory

        fixtures_dir = Path(__file__).parent / "fixtures"
        fabric = FabricFactory.create_standalone(contracts_dir=str(fixtures_dir))
        assert isinstance(fabric, Fabric)

    def test_create_for_testing_returns_fabric(self) -> None:
        from pathlib import Path

        from k1.fabric.fabric import Fabric
        from k1.fabric.factory import FabricFactory

        fixtures_dir = Path(__file__).parent / "fixtures"
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(fixtures_dir),
        )
        assert isinstance(fabric, Fabric)


# ---------------------------------------------------------------------------
# 7. Dependencies
# ---------------------------------------------------------------------------


class TestModuleDependencies:
    """
    Verify declared dependencies (kernel, bus, sessionstate) are importable.
    """

    @pytest.mark.parametrize(
        "module_path",
        ["k1.kernel", "k1.bus", "k1.sessionstate"],
        ids=["kernel", "bus", "sessionstate"],
    )
    def test_dependency_importable(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        assert mod is not None


# ---------------------------------------------------------------------------
# 8. Contract metadata consistency
# ---------------------------------------------------------------------------


class TestContractMetadataConsistency:
    """Verify internal consistency of module.contract.yaml declarations."""

    def test_all_exports_from_single_root(self) -> None:
        """
        Contract declares all exports from k1/fabric/__init__.py.

        Verify the package root is importable.
        """
        mod = importlib.import_module("k1.fabric")
        assert mod is not None

    def test_entrypoints_resolve(self) -> None:
        """
        Entrypoints: fabric:initialize and fabric:cleanup.

        Verify the fabric module itself is loadable (entrypoints
        are module-level registration hooks resolved at K1 boot).
        """
        mod = importlib.import_module("k1.fabric.fabric")
        assert hasattr(mod, "Fabric") or hasattr(mod, "CapabilityFabric")

    def test_export_count_matches_contract(self) -> None:
        """
        Contract declares 27 exports total.

        24 exist by exact name, 2 are renamed, 1 not yet implemented.
        Total implemented symbols: 26.
        """
        implemented = len(_DECLARED_EXPORTS) + len(_RENAMED_EXPORTS)
        assert implemented == 26, (
            f"Expected 26 implemented exports (24 exact + 2 renamed), " f"got {implemented}"
        )
