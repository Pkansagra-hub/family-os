---
adr_number: '0075'
title: Layer 5 Extensibility Framework (Extension Points, Hook System, Capability
  Binding)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0004
- ADR-0010
- ADR-0010c
- ADR-0026
- ADR-0027
- ADR-0028
- ADR-0029
- ADR-0074
- ADR-0075
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0004
  - ADR-0010
  - ADR-0010c
  - ADR-0026
  - ADR-0027
  - ADR-0028
  - ADR-0029
  - ADR-0074
  - ADR-0075
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0075: Layer 5 Extensibility Framework (Extension Points, Hook System, Capability Binding)

**Status:** ✅ Accepted
**Date:** 2025-10-17
**Authors:** K1 Architecture Team
**Milestone:** M2 - Pluggable Module System & Extensibility
**Category:** Layer 5 - Infrastructure (Extensibility & Hooks)

**Related ADRs:**
- [ADR-0004 (52-Module 5-Layer Architecture)](0004-52-module-5-layer-architecture.md)
- [ADR-0010 (Capability-Based Security)](0010-capability-based-security.md)
- [ADR-0010c (Capability Enforcement Runtime)](0010c-capability-enforcement-runtime.md)
- [ADR-0026 (Thermal Hysteresis Matrix)](0026-thermal-hysteresis-matrix.md)
- [ADR-0027 (Model Placement Cascade)](0027-model-placement-cascade.md)
- [ADR-0028 (Weighted Fair Queuing Scheduler)](0028-weighted-fair-queuing-scheduler.md)
- [ADR-0029 (Prometheus Metrics RED Method)](0029-prometheus-metrics-red-method.md)
- [ADR-0074 (Pluggable Module System - Parent)](0074-pluggable-module-system.md)

---

## Context: Why Layer 5 Extensibility?

**Problem Statement:**

K1's Layer 5 Infrastructure (Config Manager, Observability, Thermal Manager, Scheduler, Backpressure) is hardcoded with single implementations:

- ❌ Config: Only file-based (can't use Consul, etcd, AWS Parameter Store)
- ❌ Metrics: Only Prometheus (can't use Datadog, InfluxDB, CloudWatch)
- ❌ Tracing: Only OpenTelemetry file export (can't use Jaeger, Lightstep, New Relic)
- ❌ Logs: Only file-based (can't use CloudLogging, Loki, Splunk)
- ❌ Thermal: Single algorithm (can't customize for mobile, edge, cloud)
- ❌ Placement: Single strategy (can't optimize for cost, latency, power)
- ❌ Cache: Single eviction policy (can't use ML-guided, cost-aware, workload-specific)
- ❌ Backpressure: Single handler (can't retry, queue, or custom drop strategy)
- ❌ Error Handling: Single strategy (can't integrate circuit breaker, custom recovery)
- ❌ Health Checks: Single implementation (can't add application-specific checks)

**Real-World Scenarios ADR-0075 Enables:**

```
Scenario 1: Cloud Deployment
- Deploy K1 with cloud-native services:
  - Consul for config (auto-reload on change)
  - Datadog for metrics (time-series analysis)
  - Jaeger for tracing (distributed trace visualization)
  - CloudLogging for logs (centralized log analysis)
- All without K1 recompilation

Scenario 2: Edge Device Deployment
- Deploy K1 on mobile/edge with custom:
  - FileSystemConfig for offline operation
  - PrometheusMetricsExporter for local metrics
  - FileSystemHealthCheck for device-specific checks
- Low memory, no cloud connectivity

Scenario 3: Custom Thermal Management
- Deploy K1 on heterogeneous device (NPU + GPU + CPU)
- Use ML-guided placement strategy based on past performance
- Thermal policy considers battery state, time-to-idle, user expectations
- All via extension without K1 source code changes
```

---

## Decision: Implement 3-Part Layer 5 Extensibility

We implement **three coordinated systems** for Layer 5 extensibility:

### Part 1: 10 Extension Points (Issue 2.2.1)

**Purpose:** Define 10 pluggable extension points covering Layer 5 infrastructure

#### Extension Point 1: ConfigProvider

```python
class ConfigProvider(ExtensionPoint):
    """Custom configuration source"""

    @abstractmethod
    async def get_config(self, key: str) -> Dict[str, Any]:
        """Get configuration value"""
        pass

    @abstractmethod
    async def watch_config(self, key: str, callback: Callable) -> None:
        """Watch for config changes (hot-reload)"""
        pass
```

**Use Cases:**
- Consul: Service discovery + config management
- etcd: Distributed config with watch support
- AWS Parameter Store: Cloud-native config with versioning
- Spring Cloud Config: Microservices config server

**Integration Point:** Config Manager calls `get_config()` on startup and `watch_config()` for hot-reload

---

#### Extension Point 2: MetricsExporter

```python
class MetricsExporter(ExtensionPoint):
    """Custom metrics sink"""

    @abstractmethod
    async def export_metrics(self, metrics: Dict[str, Any], timestamp_ms: int) -> None:
        """Export metrics to sink"""
        pass
```

**Use Cases:**
- Prometheus: Pull-based metrics scraping
- Datadog: Push-based cloud metrics
- InfluxDB: Time-series database
- CloudWatch: AWS native metrics

**Integration Point:** Metrics Collector calls `export_metrics()` every 60s with batch of metrics

**Sample Implementation:**

```python
@register_extension_point("metrics_exporter")
class PrometheusMetricsExporter(MetricsExporter):
    async def initialize(self, config: Dict[str, Any]) -> None:
        from prometheus_client import CollectorRegistry
        self.registry = CollectorRegistry()
        logger.info("Prometheus exporter initialized")

    async def export_metrics(self, metrics: Dict[str, Any], timestamp_ms: int) -> None:
        for metric_name, value in metrics.items():
            # Push to Prometheus
            logger.debug(f"Exported {metric_name}={value}")
```

---

#### Extension Point 3: TraceExporter

```python
class TraceExporter(ExtensionPoint):
    """Custom trace sink"""

    @abstractmethod
    async def export_traces(self, traces: List[Dict[str, Any]]) -> None:
        """Export traces to sink"""
        pass
```

**Use Cases:**
- Jaeger: Distributed tracing with UI
- Lightstep: SaaS tracing platform
- New Relic: APM + tracing
- Cloud Trace: GCP tracing service

**Integration Point:** OpenTelemetry tracer calls `export_traces()` for trace batches

---

#### Extension Point 4: LogHandler

```python
class LogHandler(ExtensionPoint):
    """Custom log sink"""

    @abstractmethod
    async def handle_log(self, level: str, message: str, context: Dict[str, Any], timestamp_ms: int) -> None:
        """Handle log message"""
        pass
```

**Use Cases:**
- Cloud Logging: GCP centralized logging
- CloudWatch Logs: AWS centralized logging
- Loki: Open-source log aggregation
- Splunk: Enterprise log analytics

**Integration Point:** Logger calls `handle_log()` for each log message

---

#### Extension Point 5: ThermalPolicy

```python
class ThermalPolicy(ExtensionPoint):
    """Custom device thermal management"""

    @abstractmethod
    async def compute_placement_score(
        self,
        agent_spec: AgentSpec,
        devices: List[Device],
        thermal_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """Compute placement score per device (0.0-1.0)"""
        pass

    @abstractmethod
    async def on_thermal_overheat(self) -> str:
        """Return action: THROTTLE, PAUSE, SHUTDOWN"""
        pass
```

**Use Cases:**
- Mobile Thermal Policy: Consider battery temp, thermal limits
- Edge Thermal Policy: Passive cooling constraints
- Cloud Thermal Policy: Active cooling, no thermal limits
- AI-Guided Thermal: ML-predicted thermal impact

**Integration Point:** Thermal Manager calls `compute_placement_score()` for agent placement, `on_thermal_overheat()` when hot

---

#### Extension Point 6: PlacementStrategy

```python
class PlacementStrategy(ExtensionPoint):
    """Custom agent placement algorithm"""

    @abstractmethod
    async def place_agent(
        self,
        agent_spec: AgentSpec,
        available_devices: List[Device],
        placement_hints: Dict[str, Any]
    ) -> Device:
        """Select device for agent placement"""
        pass
```

**Use Cases:**
- Cost-Aware Placement: Minimize cloud compute cost
- Latency-Aware Placement: Minimize inference latency
- Power-Aware Placement: Minimize device power consumption
- ML-Guided Placement: Learn from past performance

**Integration Point:** Orchestrator calls `place_agent()` when hiring new agent

---

#### Extension Point 7: CachePolicy

```python
class CachePolicy(ExtensionPoint):
    """Custom KV cache eviction policy"""

    @abstractmethod
    async def compute_eviction_priority(
        self,
        cache_items: List[CacheItem],
        cache_stats: Dict[str, Any]
    ) -> Dict[str, float]:
        """Compute eviction priority per item (0.0=keep, 1.0=evict first)"""
        pass

    @abstractmethod
    async def on_cache_full(self) -> str:
        """Return action: EVICT_LRU, EVICT_LFU, EVICT_COST_AWARE"""
        pass
```

**Use Cases:**
- LRU Cache: Evict least recently used
- LFU Cache: Evict least frequently used
- Cost-Aware Cache: Evict based on cost to reload
- Workload-Specific Cache: Custom scoring per workload

**Integration Point:** KV Cache Manager calls `compute_eviction_priority()` when cache full

---

#### Extension Point 8: BackpressureHandler

```python
class BackpressureHandler(ExtensionPoint):
    """Custom backpressure response"""

    @abstractmethod
    async def on_backpressure(
        self,
        queue_depth: int,
        threshold: int,
        backpressure_reason: str
    ) -> str:
        """Return action: DROP, QUEUE, REJECT, THROTTLE"""
        pass
```

**Use Cases:**
- Drop Strategy: Shed load by dropping low-priority tasks
- Queue Strategy: Buffer in external queue (K0 fallback)
- Reject Strategy: Reject new requests with backpressure error
- Throttle Strategy: Rate-limit new requests

**Integration Point:** Backpressure system calls `on_backpressure()` when queue overloaded

---

#### Extension Point 9: ErrorInterceptor

```python
class ErrorInterceptor(ExtensionPoint):
    """Custom error handling and recovery"""

    @abstractmethod
    async def on_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Return recovery action: RETRY, FALLBACK, SKIP, or None"""
        pass
```

**Use Cases:**
- Retry Strategy: Exponential backoff + circuit breaker
- Fallback Strategy: Use degraded service
- Skip Strategy: Continue with partial results
- Custom Recovery: Application-specific logic

**Integration Point:** Error handler calls `on_error()` for each error, returns recovery action

---

#### Extension Point 10: HealthCheckProvider

```python
class HealthCheckProvider(ExtensionPoint):
    """Custom health check logic"""

    @abstractmethod
    async def perform_health_check(self) -> HealthStatus:
        """Perform health check, return HEALTHY/DEGRADED/UNHEALTHY"""
        pass
```

**Use Cases:**
- Device Health: Battery%, storage space, temperature
- Network Health: Connectivity, latency, bandwidth
- Application Health: Memory pressure, task queue depth
- Custom Health: Business-specific health signals

**Integration Point:** Health Monitor calls `perform_health_check()` every 10s

---

### Part 2: Hook System

**Purpose:** Allow extensions to hook into K1 lifecycle events

```python
class ExtensionRegistry:
    """Manages extension points and hooks"""

    def __init__(self):
        self.extension_points: Dict[str, List[ExtensionPoint]] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self.hook_order: Dict[str, List[int]] = {}

    def register_extension(
        self,
        point_name: str,
        extension: ExtensionPoint
    ) -> None:
        """Register extension for point"""
        if point_name not in self.extension_points:
            self.extension_points[point_name] = []

        self.extension_points[point_name].append(extension)
        logger.info(f"Registered extension: {point_name}={extension.get_name()}")

    def register_hook(
        self,
        event_name: str,
        callback: Callable,
        order: int = 100
    ) -> None:
        """Register before/after hook with order"""
        if event_name not in self.hooks:
            self.hooks[event_name] = []
            self.hook_order[event_name] = []

        self.hooks[event_name].append(callback)
        self.hook_order[event_name].append(order)

        # Sort by order (ascending = execute first)
        sorted_pairs = sorted(
            zip(self.hook_order[event_name], self.hooks[event_name])
        )
        self.hook_order[event_name], self.hooks[event_name] = zip(*sorted_pairs)

    async def emit_hook(
        self,
        event_name: str,
        **kwargs
    ) -> None:
        """Emit hook event to all registered callbacks"""
        if event_name not in self.hooks:
            return

        for callback in self.hooks[event_name]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(**kwargs)
                else:
                    callback(**kwargs)
            except Exception as e:
                # Error isolation: extension failures don't crash K1
                logger.error(f"Hook error for {event_name}: {e}")
                # Continue with next hook

    def get_extensions(self, point_name: str) -> List[ExtensionPoint]:
        """Get all extensions for point"""
        return self.extension_points.get(point_name, [])

# Global extension registry
_extension_registry = ExtensionRegistry()

def register_extension_point(point_name: str):
    """Decorator to register extension"""
    def decorator(cls):
        instance = cls()
        _extension_registry.register_extension(point_name, instance)
        return cls
    return decorator

def register_hook(event_name: str, order: int = 100):
    """Decorator to register hook"""
    def decorator(func):
        _extension_registry.register_hook(event_name, func, order)
        return func
    return decorator

```

**Hook Events (Examples):**
- `on_k1_startup` (order: 0) - Called at K1 startup
- `on_session_created` (order: 100) - Called for each session
- `on_agent_created` (order: 100) - Called when agent created
- `on_agent_terminated` (order: 100) - Called when agent terminates
- `on_turn_completed` (order: 100) - Called at end of user turn
- `on_error_occurred` (order: 100) - Called on error
- `on_k1_shutdown` (order: 900) - Called at K1 shutdown

---

### Part 3: Extension Capability Binding (Issue 2.2.2)

**Purpose:** Bind capabilities to extensions at load time

```python
@dataclass
class ExtensionCapabilitySpec:
    """Capability requirements for extension"""
    extension_id: str
    required_capabilities: List[str]  # List of capability names
    resource_limits: Dict[str, Any]  # Memory, CPU, rate limits
    scope: str  # SESSION, GLOBAL, PER_AGENT
    audit_enabled: bool = True

class ExtensionCapabilityBinder:
    """Bind capabilities to extensions"""

    def __init__(self, capability_manager, logger_instance):
        self.capability_manager = capability_manager
        self.logger = logger_instance
        self.bound_capabilities: Dict[str, List[str]] = {}  # extension_id -> capabilities

    async def bind_capabilities(
        self,
        extension_id: str,
        spec: ExtensionCapabilitySpec
    ) -> None:
        """Bind capabilities to extension"""
        bound = []

        for cap_name in spec.required_capabilities:
            try:
                cap_token = await self.capability_manager.issue_capability(
                    subject=f"extension:{extension_id}",
                    resource=cap_name,
                    rights=["execute"],
                    ttl_seconds=3600,
                    constraints={
                        "extension_id": extension_id,
                        "resource_limit": spec.resource_limits.get(cap_name),
                        "scope": spec.scope,
                    }
                )
                bound.append(cap_name)
                self.logger.debug(f"Bound capability {cap_name} to {extension_id}")
            except Exception as e:
                self.logger.error(f"Failed to bind capability {cap_name}: {e}")

        self.bound_capabilities[extension_id] = bound

        if spec.audit_enabled:
            self.logger.audit(
                "extension_capabilities_bound",
                extension_id=extension_id,
                capabilities=bound,
                resource_limits=spec.resource_limits
            )

    async def revoke_capabilities(self, extension_id: str) -> None:
        """Revoke all capabilities for extension"""
        if extension_id in self.bound_capabilities:
            await self.capability_manager.revoke_extension_capabilities(extension_id)
            del self.bound_capabilities[extension_id]
            self.logger.info(f"Revoked all capabilities for {extension_id}")

```

**Capability Types for Extensions:**
- `CONFIG_READ` - Read K1 configuration
- `CONFIG_WRITE` - Modify K1 configuration
- `METRICS_WRITE` - Export metrics to external sink
- `TRACE_WRITE` - Export traces to external sink
- `LOG_WRITE` - Write logs to external sink
- `SYSTEM_ADMIN` - System-level access (thermal, placement)
- `AGENT_OBSERVE` - Observe agent state (for health checks)
- `DEVICE_OBSERVE` - Observe device state
- `ERROR_INTERCEPT` - Intercept and handle errors

**Resource Limits per Extension:**
- Memory limit (e.g., 64MB for extension process)
- CPU quota (e.g., 10% of K1 CPU)
- Metric export rate (e.g., 1000 metrics/sec)
- Log output rate (e.g., 1MB/sec)
- Trace export rate (e.g., 100 traces/sec)

**Scope Types:**
- `SESSION` - Extension active for single user session
- `GLOBAL` - Extension active for entire K1 process
- `PER_AGENT` - Extension instance per agent

---

## Extension Implementation Example

**Sample: Custom Cost-Aware Placement Strategy**

```python
@register_extension_point("placement_strategy")
class CostAwarePlacementStrategy(PlacementStrategy):
    """Place agents to minimize cloud compute cost"""

    def __init__(self):
        self.device_costs = {}  # device_id -> cost per minute

    async def initialize(self, config: Dict[str, Any]) -> None:
        """Load device cost pricing"""
        self.device_costs = config.get("device_costs", {})
        logger.info(f"Cost-aware placement initialized with {len(self.device_costs)} devices")

    async def place_agent(
        self,
        agent_spec: AgentSpec,
        available_devices: List[Device],
        placement_hints: Dict[str, Any]
    ) -> Device:
        """Place agent on lowest-cost device"""
        best_device = None
        best_cost = float('inf')

        for device in available_devices:
            cost = self.device_costs.get(device.device_id, 0)
            if device.available_memory_mb >= agent_spec.memory_budget_mb and cost < best_cost:
                best_cost = cost
                best_device = device

        if best_device:
            logger.info(f"Placed agent on {best_device.device_id} (cost: ${best_cost}/min)")
            return best_device

        raise PlacementError(f"No suitable device for cost {best_cost}")

    async def shutdown(self) -> None:
        logger.info("Cost-aware placement strategy shutdown")

    def get_name(self) -> str:
        return "CostAwarePlacementStrategy"

@register_hook("on_session_created", order=50)
async def log_session_creation(**kwargs):
    session_id = kwargs.get("session_id")
    logger.info(f"Session created: {session_id}")

```

---

## Consequences

### Positive

✅ **True Extensibility:** Customize all Layer 5 infrastructure without recompiling K1

✅ **Multi-Deployment:** Same K1 binary runs on cloud (with Datadog), edge (with local exporters), mobile (with battery-aware policy)

✅ **Error Isolation:** Extension failures don't crash K1 (async error boundaries)

✅ **Capability Control:** Extensions get only required permissions (least privilege)

✅ **Audit Trail:** All extension capability usage logged

✅ **Hook System:** Extensions can hook into K1 lifecycle without modifying core

### Negative

❌ **Complexity:** 10 extension points + hook system adds documentation burden

❌ **Testing:** Must test all extension combinations (combinatorial explosion)

❌ **Debugging:** Extension failures may be hard to diagnose (cross-process)

### Mitigations

- Comprehensive extension documentation with examples
- Extension test harness in WARD framework
- Detailed error logging with trace_id for debugging
- Extension capabilities tracked in audit logs

---

## Integration Points (M2 Implementation Roadmap)

### Issue 2.2.1: Layer 5 Extension Points (1 week)

**Deliverables:**
- `k1/infrastructure/extensions.py` - All 10 extension point base classes
- `docs/layer5_extensions.md` - Extension point documentation
- 3 sample extensions (ConfigProvider, MetricsExporter, HealthCheckProvider)
- `tests/infrastructure/test_extensions.py` - WARD tests

**Success Criteria:**
- All 10 extension points defined ✓
- Decorator-based registration working ✓
- Hook system functional ✓
- 3 sample extensions implemented ✓
- Extension failures isolated (don't crash K1) ✓

### Issue 2.2.2: Extension Capability Binding (1 week)

**Deliverables:**
- `k1/infrastructure/extension_capabilities.py` - Capability binding for extensions
- Capability types defined (CONFIG_READ, METRICS_WRITE, etc.)
- Resource limits enforced (memory, CPU, rate limits)
- Audit logging of all capability usage
- `tests/infrastructure/test_extension_capabilities.py` - WARD tests

**Success Criteria:**
- Capabilities bound at extension load time ✓
- Only bound capabilities usable ✓
- Resource limits enforced ✓
- Capability revocation on unload ✓
- Audit logs complete and queryable ✓

---

## References

**Related Research:**
- Plugin Architectures (Gamma et al. Design Patterns)
- Hook Systems (WordPress, Django plugin systems)
- Capability-Based Security (Dennis & Van Horn 1966)
- Microservices Extension Points (Martin Fowler)

**K1 Architecture:**
- `k1_architecture_diagram.mmd` - Layer 5 infrastructure components
- ADR-0004 (52-Module 5-Layer Architecture)
- ADR-0026 (Thermal Hysteresis Matrix) - Uses ThermalPolicy extension
- ADR-0027 (Model Placement Cascade) - Uses PlacementStrategy extension
- ADR-0028 (Weighted Fair Queuing Scheduler)
- ADR-0029 (Prometheus Metrics RED Method) - Uses MetricsExporter extension

**Performance Targets (M2):**
- Extension registration: <50ms per extension
- Hook emission: <10ms total for all hooks
- Extension point lookup: <5ms P95
- Capability binding: <100ms per extension
- Resource limit enforcement: <1ms P95

---

## Appendix: Extension Point Integration Map

| Extension Point | Integrates With | Calls | Metrics | Hooks |
|-----------------|-----------------|-------|---------|-------|
| ConfigProvider | Config Manager | `get_config()`, `watch_config()` | `config_reads_total` | `on_config_changed` |
| MetricsExporter | Metrics Collector | `export_metrics()` | `metrics_exported_total` | `on_metrics_batch` |
| TraceExporter | OpenTelemetry | `export_traces()` | `traces_exported_total` | `on_trace_batch` |
| LogHandler | Logger | `handle_log()` | `logs_exported_total` | `on_log_write` |
| ThermalPolicy | Thermal Manager | `compute_placement_score()`, `on_thermal_overheat()` | `thermal_decisions_total` | `on_overheat` |
| PlacementStrategy | Orchestrator | `place_agent()` | `placement_decisions_total` | `on_agent_placed` |
| CachePolicy | KV Cache Manager | `compute_eviction_priority()`, `on_cache_full()` | `cache_evictions_total` | `on_cache_full` |
| BackpressureHandler | Backpressure System | `on_backpressure()` | `backpressure_decisions_total` | `on_backpressure_event` |
| ErrorInterceptor | Error Handler | `on_error()` | `error_intercepts_total` | `on_error_intercepted` |
| HealthCheckProvider | Health Monitor | `perform_health_check()` | `health_checks_total` | `on_health_check_complete` |