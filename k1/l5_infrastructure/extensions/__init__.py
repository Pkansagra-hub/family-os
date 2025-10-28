# Extensions - Plugin framework and extensibility

"""
Extensions Framework - K1 Extensibility Layer

Layer: L5 Infrastructure
Component: Extensions
Priority: 🔴 CRITICAL (Framework foundation)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0034: Extensions Framework Design

Extensions Philosophy:
    - Hot-reload capable plugin system
    - Type-safe extension interfaces
    - Runtime extension discovery and loading
    - Secure extension sandboxing

Extension Categories:
    - Configuration: config_provider
    - Resilience: circuit_breaker_strategy
    - Observability: log_handler, metrics_exporter, trace_exporter
    - Optimization: performance_optimizer, placement_strategy
    - Security: security_policy
    - Storage: storage_tier
    - Thermal: thermal_policy

Dependencies:
    Internal:
        - k1.l5_infrastructure.modules (hot-reload support)
    External:
        - importlib (dynamic loading)

Connects To:
    Upstream:
        - All K1 components (extension usage)
    Downstream:
        - k1.l5_infrastructure.modules (extension loading)

Observability:
    - Metrics: k1_extensions_loaded_total{category, status}
    - Metrics: k1_extensions_load_duration_seconds{category}
    - Logs: INFO extension loaded, ERROR extension failed

References:
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 14)
    - Test: tests/k1/l5_infrastructure/extensions/test_extensions.py
"""

# Resilience Extensions
from .circuit_breaker_strategy import (AdaptiveCircuitBreaker,
                                       CircuitBreakerManager,
                                       CircuitBreakerStrategy, CircuitState,
                                       CountBasedCircuitBreaker,
                                       TimeBasedCircuitBreaker,
                                       get_circuit_breaker_manager)
# Configuration Extensions
from .config_provider import (ConfigurationManager, ConfigurationProvider,
                              EnvironmentConfigurationProvider,
                              FileConfigurationProvider,
                              K0ConfigurationProvider, get_config_manager)
# Extension Registry (Core Framework)
from .extension_registry import (ActivationError, CircularDependencyError,
                                 DuplicateExtensionError, Extension,
                                 ExtensionMetadata, ExtensionNotFoundError,
                                 ExtensionPointDefinition,
                                 ExtensionPointNotFoundError,
                                 ExtensionRegistry, ExtensionRegistryError,
                                 ExtensionState, InterfaceComplianceError,
                                 UnresolvedDependencyError,
                                 get_extension_registry)
# Observability Extensions
from .log_handler import (ConsoleLogHandler, FileLogHandler, K0LogHandler,
                          LogHandler, LogHandlerManager,
                          get_log_handler_manager)
from .metrics_exporter import (FileMetricsExporter, K0MetricsExporter,
                               MetricSample, MetricsExporter,
                               MetricsExporterManager,
                               PrometheusMetricsExporter,
                               get_metrics_exporter_manager)
# Optimization Extensions
from .performance_optimizer import (CachingOptimizer, ParallelizationOptimizer,
                                    PerformanceMetrics, PerformanceOptimizer,
                                    PerformanceOptimizerManager,
                                    ResourceOptimizer,
                                    get_performance_optimizer_manager)
from .placement_strategy import (AffinityPlacementStrategy,
                                 LeastLoadedPlacementStrategy,
                                 PlacementDecision, PlacementRequest,
                                 PlacementStrategy, PlacementStrategyManager,
                                 RoundRobinPlacementStrategy,
                                 get_placement_strategy_manager)
# Security Extensions
from .security_policy import (ABACSecurityPolicy, CapabilitySecurityPolicy,
                              RBACSecurityPolicy, SecurityContext,
                              SecurityPolicy, SecurityPolicyManager,
                              SecurityViolation, get_security_policy_manager)
# Storage Extensions
from .storage_tier import (ColdStorageTier, HotStorageTier, StorageObject,
                           StorageTier, StorageTierManager, WarmStorageTier,
                           get_storage_tier_manager)
# Thermal Extensions
from .thermal_policy import (ActiveThermalPolicy, AdaptiveThermalPolicy,
                             PassiveThermalPolicy, ThermalAction,
                             ThermalPolicy, ThermalPolicyManager,
                             ThermalReading, get_thermal_policy_manager)
from .trace_exporter import (FileTraceExporter, JaegerTraceExporter,
                             OpenTelemetryTraceExporter, TraceBatch,
                             TraceExporter, TraceExporterManager, TraceSpan,
                             get_trace_exporter_manager)

__all__ = [
    # Extension Registry (Core)
    "ExtensionState",
    "Extension",
    "ExtensionPointDefinition",
    "ExtensionMetadata",
    "ExtensionRegistryError",
    "ExtensionPointNotFoundError",
    "InterfaceComplianceError",
    "DuplicateExtensionError",
    "ExtensionNotFoundError",
    "ActivationError",
    "UnresolvedDependencyError",
    "CircularDependencyError",
    "ExtensionRegistry",
    "get_extension_registry",

    # Configuration
    "ConfigurationProvider",
    "FileConfigurationProvider",
    "EnvironmentConfigurationProvider",
    "K0ConfigurationProvider",
    "ConfigurationManager",
    "get_config_manager",

    # Resilience
    "CircuitState",
    "CircuitBreakerStrategy",
    "CountBasedCircuitBreaker",
    "TimeBasedCircuitBreaker",
    "AdaptiveCircuitBreaker",
    "CircuitBreakerManager",
    "get_circuit_breaker_manager",

    # Observability - Logging
    "LogHandler",
    "ConsoleLogHandler",
    "FileLogHandler",
    "K0LogHandler",
    "LogHandlerManager",
    "get_log_handler_manager",

    # Observability - Metrics
    "MetricSample",
    "MetricsExporter",
    "PrometheusMetricsExporter",
    "FileMetricsExporter",
    "K0MetricsExporter",
    "MetricsExporterManager",
    "get_metrics_exporter_manager",

    # Observability - Tracing
    "TraceSpan",
    "TraceBatch",
    "TraceExporter",
    "OpenTelemetryTraceExporter",
    "JaegerTraceExporter",
    "FileTraceExporter",
    "TraceExporterManager",
    "get_trace_exporter_manager",

    # Optimization - Performance
    "PerformanceMetrics",
    "PerformanceOptimizer",
    "CachingOptimizer",
    "ResourceOptimizer",
    "ParallelizationOptimizer",
    "PerformanceOptimizerManager",
    "get_performance_optimizer_manager",

    # Optimization - Placement
    "PlacementRequest",
    "PlacementDecision",
    "PlacementStrategy",
    "RoundRobinPlacementStrategy",
    "LeastLoadedPlacementStrategy",
    "AffinityPlacementStrategy",
    "PlacementStrategyManager",
    "get_placement_strategy_manager",

    # Security
    "SecurityContext",
    "SecurityViolation",
    "SecurityPolicy",
    "RBACSecurityPolicy",
    "ABACSecurityPolicy",
    "CapabilitySecurityPolicy",
    "SecurityPolicyManager",
    "get_security_policy_manager",

    # Storage
    "StorageObject",
    "StorageTier",
    "HotStorageTier",
    "WarmStorageTier",
    "ColdStorageTier",
    "StorageTierManager",
    "get_storage_tier_manager",

    # Thermal
    "ThermalReading",
    "ThermalAction",
    "ThermalPolicy",
    "PassiveThermalPolicy",
    "ActiveThermalPolicy",
    "AdaptiveThermalPolicy",
    "ThermalPolicyManager",
    "get_thermal_policy_manager",
]
