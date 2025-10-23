"""
Layer 5 - Extensions Framework

This module defines 10 extension points for customizing Layer 5 infrastructure
behavior without modifying core K1 code.

Primary ADRs:
- ADR-0074: Module System (module discovery, loading)
- ADR-0075: Layer 5 Extensibility (10 extension points)

Extension Points Architecture:

Extension points allow third-party customization of Layer 5 infrastructure:
- Custom config sources
- Alternative metrics exporters
- Custom trace exporters
- Custom log handlers
- Thermal policies
- Placement strategies
- Cache policies
- Backpressure handlers
- Error interceptors
- Health check providers

Extension Point Pattern:
1. Define abstract base class (ABC) for extension point
2. Register extensions via plugin system
3. Discover extensions at runtime (entry points)
4. Load extensions on demand
5. Call extension hooks at appropriate points

Extension Discovery:
- Python entry points (setuptools/poetry)
- Plugin directory scanning
- Explicit registration via API

Extension Lifecycle:
1. Discovery: Find available extensions
2. Validation: Check compatibility (version, dependencies)
3. Loading: Import and instantiate extension
4. Registration: Register with extension manager
5. Activation: Enable extension hooks
6. Deactivation: Disable extension hooks
7. Unloading: Clean up resources

## 10 Extension Points

### 1. ConfigProvider
**Purpose:** Custom configuration sources beyond YAML files
**Use Cases:** Remote config (Consul, etcd), database config, cloud config (AWS SSM)
**Methods:** `load_config(path: str) -> Dict`, `watch_config(callback: Callable)`

### 2. MetricsExporter
**Purpose:** Export metrics to alternative backends beyond Prometheus
**Use Cases:** StatsD, CloudWatch, Datadog, New Relic
**Methods:** `export_counter(name, value, labels)`, `export_gauge(name, value, labels)`, `export_histogram(name, value, labels)`

### 3. TraceExporter
**Purpose:** Export traces to alternative backends beyond Jaeger
**Use Cases:** Zipkin, AWS X-Ray, Google Cloud Trace, Honeycomb
**Methods:** `export_span(span: Span)`, `export_batch(spans: List[Span])`

### 4. LogHandler
**Purpose:** Custom log handlers beyond stdout/file
**Use Cases:** Syslog, CloudWatch Logs, Elasticsearch, Loki
**Methods:** `emit(record: LogRecord)`, `flush()`, `close()`

### 5. ThermalPolicy
**Purpose:** Custom thermal management policies beyond default zones
**Use Cases:** Device-specific thermal curves, custom cooling strategies, external sensors
**Methods:** `classify_thermal_zone(temperature: float) -> ThermalZone`, `should_throttle(zone: ThermalZone) -> bool`

### 6. PlacementStrategy
**Purpose:** Custom model placement strategies beyond NPU→GPU→CPU→Remote
**Use Cases:** Custom accelerator selection, cost-aware placement, latency-aware placement
**Methods:** `choose_accelerator(model_config: ModelConfig, constraints: Dict) -> str`

### 7. CachePolicy
**Purpose:** Custom KV cache policies beyond LRU+LFU
**Use Cases:** Custom eviction algorithms, compression strategies, thermal-aware caching
**Methods:** `evict(cache: Cache, required_size: int) -> List[CacheEntry]`, `compress(entry: CacheEntry) -> bytes`

### 8. BackpressureHandler
**Purpose:** Custom backpressure handling beyond 3-tier cascade
**Use Cases:** Custom watermark thresholds, custom overflow policies, domain-specific backpressure
**Methods:** `check_backpressure(queue_depth: int, threshold: int) -> BackpressureLevel`, `handle_overflow(queue: Queue)`

### 9. ErrorInterceptor
**Purpose:** Custom error transformation and handling
**Use Cases:** Error aggregation, custom retry policies, error reporting to external systems
**Methods:** `intercept_error(error: Exception, context: Dict) -> Exception`, `should_retry(error: Exception) -> bool`

### 10. HealthCheckProvider
**Purpose:** Custom health check endpoints beyond K0 ping
**Use Cases:** Database health checks, dependency health checks, custom liveness/readiness probes
**Methods:** `check_health() -> HealthStatus`, `check_liveness() -> bool`, `check_readiness() -> bool`

## Extension Registration

### Entry Points (setuptools)
```python
# setup.py or pyproject.toml
entry_points = {
    "k1.l5_infrastructure.config_provider": [
        "consul = my_package.consul_provider:ConsulConfigProvider",
    ],
    "k1.l5_infrastructure.metrics_exporter": [
        "datadog = my_package.datadog_exporter:DatadogExporter",
    ],
}
```

### Programmatic Registration
```python
from k1.l5_infrastructure.extensions import ExtensionManager

manager = ExtensionManager()
manager.register_extension("config_provider", "consul", ConsulConfigProvider)
```

## Extension Interface Example

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class ConfigProvider(ABC):
    '''Extension point for custom configuration sources'''

    @abstractmethod
    def load_config(self, path: str) -> Dict[str, Any]:
        '''Load configuration from custom source'''
        pass

    @abstractmethod
    def watch_config(self, callback: Callable[[Dict], None]):
        '''Watch for configuration changes'''
        pass

class ConsulConfigProvider(ConfigProvider):
    '''Consul implementation of ConfigProvider'''

    def __init__(self, consul_host: str, consul_port: int):
        self.consul_host = consul_host
        self.consul_port = consul_port

    def load_config(self, path: str) -> Dict[str, Any]:
        # Load from Consul KV store
        return consul.kv.get(path)

    def watch_config(self, callback: Callable[[Dict], None]):
        # Watch Consul KV for changes
        consul.kv.watch(path, callback)
```

## Extension Manager

The ExtensionManager provides:
- Extension discovery (entry points, plugin directories)
- Extension validation (version compatibility, dependency checks)
- Extension loading (import, instantiate, register)
- Extension lifecycle management (activate, deactivate, reload)
- Extension isolation (separate namespaces, error handling)

## Extension Security

Extensions run with same privileges as K1, so:
- Validate extensions before loading (signature verification)
- Sandbox extensions if possible (separate process, restricted capabilities)
- Audit extension behavior (logging, monitoring)
- Limit extension access to sensitive resources

## Extension Performance

Extensions should not degrade K1 performance:
- Extension hooks have performance budgets (<10ms overhead)
- Extensions run asynchronously when possible
- Extensions use lazy loading (load on first use)
- Extensions are measured (metrics for extension overhead)

Research Foundation:
- Plugin architecture (Eclipse plugin system, VS Code extensions)
- Extension points (Martin Fowler, "Extension Object" pattern)
- Service provider interface (Java SPI, Python entry points)
- Dependency injection (inversion of control, extension composition)
"""

# __all__ = [
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
