"""
Layer 5 - Infrastructure

K1's infrastructure layer providing cross-cutting services for all layers:
K0 bridge, resilience, thermal management, event bus, observability, configuration,
connectors, and extensibility.

Architecture:
- Leaf layer: L5 imports nothing from L1-L4 (dependency inversion)
- Cross-cutting: All layers depend on L5 infrastructure
- External dependency: L5 depends on K0 (dual-kernel architecture)

Primary ADRs:
- ADR-0004: 52-Module 5-Layer Architecture (Layer 5 definition)
- ADR-0001a: K0 Bridge Architecture (dual-protocol, lane processing)
- ADR-0029: Prometheus Metrics (50+ metrics, RED method)
- ADR-0030: Trace Sampling (cognitive_trace_id, adaptive sampling)
- ADR-0009: Circuit Breaker (3-state FSM, resilience)
- ADR-0026: Thermal Management (hysteresis, 4-tier placement)

Module Structure (7 categories, 19 modules):

1. bridge_k0/ - K0 Bridge (6 modules)
   - command_client.py: K0 Command Port client (<50ms GREEN, <200ms AMBER/RED)
   - query_client.py: K0 Query Port client (<100ms, multi-store retrieval)
   - sse_client.py: K0 SSE Port client (<5ms delivery, event streaming)
   - batch_client.py: SessionState delta batching (250ms interval)
   - observability_client.py: Metrics/logs push to K0 (<20ms)
   - http2/: HTTP/2 transport layer (<10ms latency)

2. resilience/ - Resilience (3 modules)
   - circuit_breaker_manager.py: 3-state FSM circuit breaker (<10ms check)
   - retry_policy.py: Exponential backoff retry (<5ms decision)
   - hot_reload.py: Config hot-reload (<100ms, zero-downtime)

3. thermal/ - Thermal Management (2 modules)
   - placement_planner.py: 4-tier placement (NPU→GPU→CPU→Remote, <10ms)
   - monitor.py: Temperature monitoring (1 Hz polling, <5ms read)

4. event_bus/ - Internal Event Bus (2 modules)
   - event_bus.py: Pub/sub event bus (<5ms delivery, zero-copy)
   - schemas.py: Event schema definitions (IntentDetected, UserInput, etc.)

5. observability/ - Observability (4 modules)
   - metrics.py: Prometheus metrics (50+ metrics, RED method, <10ms emission)
   - tracing.py: OpenTelemetry tracing (1% sampling, adaptive, <5ms span)
   - logging.py: Structured JSON logging (6 event types, <5ms write)
   - dashboards/: Grafana dashboards (7 dashboards, SLO alerts)

6. config/ - Configuration (2 modules)
   - loader.py: YAML config loader (hot-reload <100ms, zero-downtime)
   - schema_validator.py: JSON Schema Draft 7 validator (<10ms)

7. connectors/ - Connectors (1 module)
   - k0_connector.py: K0 connection lifecycle (HTTP/2 pooling, health checks)

8. extensions/ - Extensibility (10 extension points)
   - Extension points: ConfigProvider, MetricsExporter, TraceExporter, LogHandler,
     ThermalPolicy, PlacementStrategy, CachePolicy, BackpressureHandler,
     ErrorInterceptor, HealthCheckProvider

Performance Budgets (ADR-0024):
- K0 Command (GREEN): <50ms P95
- K0 Command (AMBER/RED): <200ms P95
- K0 Query: <100ms P95
- SSE event delivery: <5ms P95
- Circuit breaker check: <10ms P95
- Thermal placement: <10ms P95
- Event bus delivery: <5ms P95
- Metric emission: <10ms P95
- Trace span creation: <5ms P95
- Log write: <5ms P95
- Config reload: <100ms P95

Integration Points:
- L5 → K0: Command Port (:5200), Query Port (:5201), SSE Port (:5202), Observability Port (:5203)
- L1/L2/L3/L4 → L5: Metrics, tracing, logging, config, event bus, circuit breaker, thermal

Research Foundation:
- K0 Bridge: Dual-kernel architecture (K0 memory + K1 intelligence)
- Resilience: Circuit breaker (Nygard), exponential backoff (Ethernet collision avoidance)
- Thermal: Hysteresis FSM (HVAC systems), DVFS (Intel SpeedStep)
- Event Bus: Pub/sub pattern (observer pattern), zero-copy (shared memory)
- Observability: RED method (Grafana), OpenTelemetry (CNCF), structured logging
- Configuration: Hot-reload (zero-downtime updates), JSON Schema validation

Total ADRs: 165 ADRs covering Layer 5
Coverage: 100% of Layer 5 modules (19/19 modules)
"""

# __all__ = [
#     # K0 Bridge
#     "CommandClient",
#     "QueryClient",
#     "SSEClient",
#     "BatchClient",
#     "ObservabilityClient",

#     # Resilience
#     "CircuitBreakerManager",
#     "RetryPolicy",
#     "HotReload",

#     # Thermal
#     "PlacementPlanner",
#     "ThermalMonitor",

#     # Event Bus
#     "EventBus",
#     "IntentDetected",
#     "UserInput",
#     "VoiceCommand",
#     "BargeIn",

#     # Observability
#     "MetricsExporter",
#     "TracingManager",
#     "StructuredLogger",

#     # Config
#     "ConfigLoader",
#     "SchemaValidator",

#     # Connectors
#     "K0Connector",

#     # Extensions
#     "ExtensionManager",
#     "ConfigProvider",
#     "MetricsExporter",
#     "TraceExporter",
#     "LogHandler",
#     "ThermalPolicy",
#     "PlacementStrategy",
#     "CachePolicy",
#     "BackpressureHandler",
#     "ErrorInterceptor",
#     "HealthCheckProvider",
# ]
