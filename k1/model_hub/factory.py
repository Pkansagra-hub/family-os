"""ModelHubFactory -- DI wiring and construction [F60].

Creates the Model Hub with all services, adapters, and plugins
wired together. Three creation modes:

  - create_standalone(config) -> IModelHubPort
  - create_for_testing(overrides?) -> (IModelHubPort, dict[str, service])
  - create_with_ports(ports: dict) -> IModelHubPort

Import graph (Layer 3 -- factory)
----------------------------------
k1.model_hub.factory
  -> k1.model_hub.config          (Layer 0)
  -> k1.model_hub.ports           (Layer 1)
  -> k1.model_hub.services        (Layer 2)
  -> k1.model_hub.adapters        (Layer 3)
  -> k1.model_hub.plugins         (Layer 2/4)

References
----------
- model_hub.mmd: Factory wiring
- ADR-0001b: Model Hub Architecture
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from k1.model_hub.loader import ProviderConfig, ProviderLoadResult

from k1.model_hub.adapters.credential_store_adapter import CredentialStoreAdapter
from k1.model_hub.adapters.health_report_adapter import HealthReportAdapter
from k1.model_hub.config import ModelHubConfig
from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import IProviderPlugin
from k1.model_hub.ports.config_port import IConfigPort
from k1.model_hub.ports.credential_port import ICredentialPort
from k1.model_hub.ports.event_port import IEventPort
from k1.model_hub.ports.health_port import IHealthPort
from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.ports.metrics_port import IMetricsPort
from k1.model_hub.ports.state_read_port import IStateReadPort
from k1.model_hub.services.audit_logger import AuditLogger
from k1.model_hub.services.capability_router import CapabilityRouter
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.model_selector import ModelSelector
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.services.provider_dispatcher import ProviderDispatcher
from k1.model_hub.services.provider_registry import ProviderRegistry
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.services.request_router import RequestRouter
from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    CapabilityType,
    HealthStatus,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


# Per-plugin timeout for ``_HubCore.shutdown`` plugin draining.
_PLUGIN_CLOSE_TIMEOUT_S: float = 5.0


# ===========================================================================
# _DefaultHealthQuery -- IHealthQuery stub for CapabilityRouter
# ===========================================================================


class _DefaultHealthQuery:
    """Default IHealthQuery returning HEALTHY for all providers.

    CapabilityRouter requires IHealthQuery (get_status(provider_id)),
    not IHealthPort (report_health/check_health). This bridges the gap.
    """

    def __init__(self, health_adapter: HealthReportAdapter | None = None) -> None:
        self._adapter = health_adapter

    def get_status(self, provider_id: str) -> HealthStatus:
        """Return HEALTHY for all providers by default."""
        return HealthStatus.HEALTHY


# ===========================================================================
# _HubCore -- IModelHubPort bridge over RequestRouter
# ===========================================================================


class _HubCore:
    """IModelHubPort implementation bridging RequestRouter + Registry.

    RequestRouter has route()/stream_route() (internal API).
    IModelHubPort needs execute()/stream_execute() + discovery + health.
    This class bridges the two interfaces.
    """

    def __init__(
        self,
        router: RequestRouter,
        registry: ProviderRegistry,
        health_adapter: HealthReportAdapter,
    ) -> None:
        self._router = router
        self._registry = registry
        self._health = health_adapter

    def register_plugin(
        self,
        manifest: ProviderManifest,
        plugin: IProviderPlugin,
    ) -> None:
        """Register a provider plugin with both registry and dispatcher.

        P0.1 minimal shim: the public ``ModelHubFactory.create_with_ports``
        ``plugins=`` argument only populates the dispatcher's plugin map and
        leaves the registry's capability index empty, which causes
        ``NoEligibleProviderError`` for every request. This method does both
        sides of the registration in one call so callers (currently only
        ``k1.kernel.service._register_model_hub_plugins_from_env``) do not
        have to reach into private attributes.

        Superseded by P2's declarative ``ProviderLoader`` + ``from_config``.
        """
        self._registry.register(manifest, plugin)
        self._router._dispatcher.register_plugin(manifest.provider_id, plugin)

    async def execute(self, request: HubRequest) -> HubResponse:
        return await self._router.route(request)

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        async for chunk in self._router.stream_route(request):
            yield chunk

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        index = self._registry.get_capability_index()
        return {cap: [p.provider_id for p in providers] for cap, providers in index.items()}

    async def discover_models(
        self,
        capability: Optional[CapabilityType] = None,
    ) -> List[ModelInfo]:
        results: List[ModelInfo] = []
        for info in self._registry.list_providers():
            for model in info.models:
                if capability and capability not in model.capabilities:
                    continue
                results.append(
                    ModelInfo(
                        id=model.id,
                        provider_id=info.provider_id,
                        capabilities=list(model.capabilities),
                        cost_per_1m_input=model.cost_per_1m_input,
                        cost_per_1m_output=model.cost_per_1m_output,
                        max_context=model.max_context,
                        max_output=model.max_output,
                        supports_streaming=model.supports_streaming,
                    )
                )
        return results

    async def health(self) -> HubHealthReport:
        report = self._health.check_health()
        return HubHealthReport(status=report.status)

    async def shutdown(self) -> None:
        """Drain registered plugins. Idempotent. Never raises.

        Iterates the dispatcher's plugin store, calls ``await plugin.close()``
        on each under a per-plugin timeout, gathers with ``return_exceptions``,
        logs exceptions at WARNING. Safe to call multiple times -- each
        plugin's ``close()`` is idempotent (guards with ``_session.closed``
        or ``_client is None``).

        NOTE: reaches into ``self._router._dispatcher._plugins`` directly.
        Same private-attr seam as ``register_plugin``; cleaned up in P2.3.
        """
        plugins = list(self._router._dispatcher._plugins.values())
        if not plugins:
            return
        results = await asyncio.gather(
            *[asyncio.wait_for(p.close(), timeout=_PLUGIN_CLOSE_TIMEOUT_S) for p in plugins],
            return_exceptions=True,
        )
        for plugin, outcome in zip(plugins, results, strict=True):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "ModelHub plugin close failed: %s (%s: %s)",
                    type(plugin).__name__,
                    type(outcome).__name__,
                    outcome,
                )


# ===========================================================================
# ModelHubFactory
# ===========================================================================


class ModelHubFactory:
    """Factory for constructing a fully-wired Model Hub.

    Three creation modes:
      - create_standalone: production mode with real adapters
      - create_for_testing: test mode with test adapters (no mocks)
      - create_with_ports: custom mode with caller-supplied ports

    Wiring sequence (11 steps):
      1. Load config
      2. Initialize CredentialStore
      3. Create ProviderRegistry
      4. Create resilience services (CircuitBreaker, RateLimiter)
      5. Create cost/cache/budget services
      6. Create routing services (CapabilityRouter, ModelSelector)
      7. Create NormalizationLayer
      8. Create ProviderDispatcher
      9. Create RequestRouter wiring all services
      10. Create HealthMonitor + AuditLogger
      11. Return IModelHubPort facade (_HubCore)

    DI validation: all 7 ports checked via isinstance(port, Protocol).
    """

    @staticmethod
    def create_standalone(
        config: ModelHubConfig | None = None,
        plugins: Dict[str, IProviderPlugin] | None = None,
    ) -> IModelHubPort:
        """Create a production Model Hub with real adapters.

        Args:
            config: Hub config (default: ModelHubConfig()).
            plugins: Pre-registered plugins (optional).

        Returns:
            IModelHubPort facade (_HubCore wrapping RequestRouter).
        """
        cfg = config or ModelHubConfig()

        # Step 2: Credential store
        credential_adapter = CredentialStoreAdapter()

        # Step 3: Provider registry
        registry = ProviderRegistry(cfg)

        # Step 4: Resilience services
        circuit_mgr = CircuitBreakerManager()
        rate_limiter = RateLimiter(
            default_headroom_pct=cfg.rate_limit_headroom_pct,
        )

        # Step 5: Cache
        response_cache = ResponseCache(cfg)

        # Step 6: Routing services
        health_adapter = HealthReportAdapter()
        health_query = _DefaultHealthQuery(health_adapter)
        capability_router = CapabilityRouter(
            registry=registry,
            circuit_breaker=circuit_mgr,
            rate_limiter=rate_limiter,
            health_monitor=health_query,
        )
        model_selector = ModelSelector()

        # Step 7: Normalization
        normalization = NormalizationLayer()

        # Step 8: Provider dispatcher
        dispatcher = ProviderDispatcher(
            circuit_mgr=circuit_mgr,
            rate_limiter=rate_limiter,
            credential_port=credential_adapter,
            plugins=plugins or {},
        )

        # Step 9: Request router
        router = RequestRouter(
            capability_router=capability_router,
            model_selector=model_selector,
            response_cache=response_cache,
            normalization_layer=normalization,
            dispatcher=dispatcher,
            audit_logger=AuditLogger(),
        )

        # Step 11: Return IModelHubPort facade
        return _HubCore(router=router, registry=registry, health_adapter=health_adapter)

    @staticmethod
    def create_for_testing(
        overrides: Dict[str, Any] | None = None,
    ) -> Tuple[IModelHubPort, Dict[str, Any]]:
        """Create a test Model Hub with test adapters.

        Returns:
            Tuple of (IModelHubPort facade, dict of all adapters/services).
            The dict keys match service/adapter names for direct access.

        Args:
            overrides: Optional dict to override default wiring.
                Keys: "config", "credential_port", "plugins", "event_port",
                      "state_read_port", "metrics_port", "config_port",
                      "health_port".
        """
        from tests.k1.model_hub.adapters.test_config_adapter import TestConfigAdapter
        from tests.k1.model_hub.adapters.test_credential_adapter import (
            TestCredentialAdapter,
        )
        from tests.k1.model_hub.adapters.test_event_adapter import TestEventAdapter
        from tests.k1.model_hub.adapters.test_health_adapter import TestHealthAdapter
        from tests.k1.model_hub.adapters.test_metrics_adapter import TestMetricsAdapter
        from tests.k1.model_hub.adapters.test_state_read_adapter import (
            TestStateReadAdapter,
        )

        ov = overrides or {}
        cfg: ModelHubConfig = ov.get("config", ModelHubConfig())

        # Test adapters (port implementations)
        credential_port: ICredentialPort = ov.get("credential_port", TestCredentialAdapter())
        event_port: IEventPort = ov.get("event_port", TestEventAdapter())
        state_read_port: IStateReadPort = ov.get("state_read_port", TestStateReadAdapter())
        metrics_port: IMetricsPort = ov.get("metrics_port", TestMetricsAdapter())
        config_port: IConfigPort = ov.get("config_port", TestConfigAdapter())
        health_port: IHealthPort = ov.get("health_port", TestHealthAdapter())

        # Validate all ports
        _validate_ports(
            credential_port=credential_port,
            event_port=event_port,
            state_read_port=state_read_port,
            metrics_port=metrics_port,
            config_port=config_port,
            health_port=health_port,
        )

        # Wire services
        registry = ProviderRegistry(cfg)
        circuit_mgr = CircuitBreakerManager()
        rate_limiter = RateLimiter(
            default_headroom_pct=cfg.rate_limit_headroom_pct,
        )
        response_cache = ResponseCache(cfg)

        health_query = _DefaultHealthQuery()
        capability_router = CapabilityRouter(
            registry=registry,
            circuit_breaker=circuit_mgr,
            rate_limiter=rate_limiter,
            health_monitor=health_query,
        )
        model_selector = ModelSelector()
        normalization = NormalizationLayer()

        plugins: Dict[str, IProviderPlugin] = ov.get("plugins", {})
        dispatcher = ProviderDispatcher(
            circuit_mgr=circuit_mgr,
            rate_limiter=rate_limiter,
            credential_port=credential_port,
            plugins=plugins,
        )

        audit_logger = AuditLogger()
        router = RequestRouter(
            capability_router=capability_router,
            model_selector=model_selector,
            response_cache=response_cache,
            normalization_layer=normalization,
            dispatcher=dispatcher,
            audit_logger=audit_logger,
            metrics_port=metrics_port,
            event_port=event_port,
            state_read_port=state_read_port,  # 3.1.3
        )

        health_adapter = health_port if health_port is not None else HealthReportAdapter()
        facade = _HubCore(
            router=router,
            registry=registry,
            health_adapter=health_adapter,
        )

        adapters: Dict[str, Any] = {
            "credential_port": credential_port,
            "event_port": event_port,
            "state_read_port": state_read_port,
            "metrics_port": metrics_port,
            "config_port": config_port,
            "health_port": health_port,
            "config": cfg,
            "registry": registry,
            "circuit_mgr": circuit_mgr,
            "rate_limiter": rate_limiter,
            "response_cache": response_cache,
            "capability_router": capability_router,
            "model_selector": model_selector,
            "normalization": normalization,
            "dispatcher": dispatcher,
            "audit_logger": audit_logger,
            "router": router,
            "health_adapter": health_adapter,
        }

        return facade, adapters

    @staticmethod
    def create_with_ports(
        ports: Dict[str, Any],
        config: ModelHubConfig | None = None,
        plugins: Dict[str, IProviderPlugin] | None = None,
    ) -> IModelHubPort:
        """Create Model Hub with caller-supplied ports.

        Args:
            ports: Dict mapping port name to implementation.
                Required keys: "credential_port".
                Optional: "event_port", "state_read_port", "metrics_port",
                          "config_port", "health_port".
            config: Hub config (default: ModelHubConfig()).
            plugins: Pre-registered plugins.

        Returns:
            IModelHubPort facade.
        """
        cfg = config or ModelHubConfig()

        credential_port: ICredentialPort = ports["credential_port"]
        event_port: IEventPort | None = ports.get("event_port")
        state_read_port: IStateReadPort | None = ports.get("state_read_port")
        metrics_port: IMetricsPort | None = ports.get("metrics_port")
        config_port: IConfigPort | None = ports.get("config_port")
        health_port: IHealthPort | None = ports.get("health_port")

        _validate_ports(
            credential_port=credential_port,
            event_port=event_port,
            state_read_port=state_read_port,
            metrics_port=metrics_port,
            config_port=config_port,
            health_port=health_port,
        )

        registry = ProviderRegistry(cfg)
        circuit_mgr = CircuitBreakerManager()
        rate_limiter = RateLimiter(
            default_headroom_pct=cfg.rate_limit_headroom_pct,
        )

        health_query = _DefaultHealthQuery()
        capability_router = CapabilityRouter(
            registry=registry,
            circuit_breaker=circuit_mgr,
            rate_limiter=rate_limiter,
            health_monitor=health_query,
        )

        dispatcher = ProviderDispatcher(
            circuit_mgr=circuit_mgr,
            rate_limiter=rate_limiter,
            credential_port=credential_port,
            plugins=plugins or {},
        )

        router = RequestRouter(
            capability_router=capability_router,
            model_selector=ModelSelector(),
            response_cache=ResponseCache(cfg),
            normalization_layer=NormalizationLayer(),
            dispatcher=dispatcher,
            audit_logger=AuditLogger(),
            metrics_port=metrics_port,
            event_port=event_port,
            state_read_port=state_read_port,  # 3.1.3
        )

        health_adapter = health_port if health_port is not None else HealthReportAdapter()
        return _HubCore(
            router=router,
            registry=registry,
            health_adapter=health_adapter,
        )

    @staticmethod
    async def from_config(
        config: "ProviderConfig",
        ports: Dict[str, Any] | None = None,
        *,
        hub_config: ModelHubConfig | None = None,
        manifest_root: Path | None = None,
    ) -> Tuple[IModelHubPort, "ProviderLoadResult"]:
        """Recommended production entry point. Builds a hub via
        ``create_with_ports`` (or ``create_standalone`` when ``ports`` is
        ``None``), then runs ``ProviderLoader(hub).load(config)`` so the
        returned hub is already populated with every provider whose
        env-var resolved.

        Returns ``(hub, ProviderLoadResult)``. Never raises on partial
        provider failure -- inspect ``result.failed`` / ``result.skipped``
        to decide. Caller owns the hub's lifecycle; call
        ``await hub.shutdown()`` on teardown to drain plugin sessions.

        Only ``credential_port`` is consumed from ``ports``;
        ``metrics_port``, ``event_port``, and ``state_read_port`` (3.1.3)
        flow into the ``RequestRouter``. Other accepted keys
        (``config_port``, ``health_port``) are validated but not yet
        wired into any service -- pre-existing factory behavior; not
        addressed by P2.2.

        Idempotency: calling ``from_config`` twice on the same hub is
        not supported. The loader will record every entry as ``failed``
        on the second call (registry raises ``ValueError`` on duplicate
        ``provider_id``); the hub stays functional with the first call's
        plugins. Construct a new hub for re-registration.
        """
        from k1.model_hub.loader import ProviderLoader  # local import: avoid cycle

        if ports is None:
            hub = ModelHubFactory.create_standalone(config=hub_config)
            loader = ProviderLoader(hub, manifest_root=manifest_root)
        else:
            hub = ModelHubFactory.create_with_ports(ports, config=hub_config)
            loader = ProviderLoader(
                hub,  # type: ignore[arg-type]
                manifest_root=manifest_root,
                event_port=ports.get("event_port"),
            )
        result = await loader.load(config)
        return hub, result


# ===========================================================================
# DI Validation
# ===========================================================================


def _validate_ports(**ports: Any) -> None:
    """Validate that all provided ports implement their Protocol.

    Raises TypeError if any port fails isinstance check.
    """
    protocol_map: Dict[str, type] = {
        "credential_port": ICredentialPort,
        "event_port": IEventPort,
        "state_read_port": IStateReadPort,
        "metrics_port": IMetricsPort,
        "config_port": IConfigPort,
        "health_port": IHealthPort,
    }
    for name, port in ports.items():
        if name in protocol_map and port is not None:
            protocol = protocol_map[name]
            if not isinstance(port, protocol):
                raise TypeError(
                    f"Port '{name}' must implement {protocol.__name__}, "
                    f"got {type(port).__name__}"
                )


__all__ = ["ModelHubFactory"]
