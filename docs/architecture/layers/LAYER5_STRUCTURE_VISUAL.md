# Layer 5 Folder Structure - Visual Overview

```
d:\familyos\
└── k1/
    ├── bridge_k0/                          # K0 Communication Bridge (P0)
    │   ├── command_client.py
    │   ├── protocol.py
    │   ├── lanes.py
    │   ├── retrieval.py
    │   ├── batch_client.py
    │   ├── ports/
    │   │   ├── command_port.py
    │   │   ├── query_port.py
    │   │   └── sse_port.py
    │   └── http2_client.py
    │
    ├── l5_infrastructure/                  # Main L5 Hub
    │   ├── __init__.py
    │   │
    │   ├── event_bus/                      # Pub/Sub (P0)
    │   │   ├── event_bus.py
    │   │   └── schemas.py
    │   │
    │   ├── serialization/                  # FlatBuffers (P0)
    │   │   ├── serializer.py
    │   │   ├── deserializer.py
    │   │   ├── buffer_pool.py
    │   │   └── alignment.py
    │   │
    │   ├── resilience/                     # Circuit Breaker (P1)
    │   │   ├── circuit_breaker_manager.py
    │   │   ├── circuit_fsm.py
    │   │   ├── call_wrapper.py
    │   │   ├── config_manager.py
    │   │   ├── states/
    │   │   │   ├── closed.py
    │   │   │   ├── open.py
    │   │   │   └── half_open.py
    │   │   ├── fallbacks/
    │   │   │   ├── default_value.py
    │   │   │   ├── cached_result.py
    │   │   │   ├── alternate_service.py
    │   │   │   └── raise_error.py
    │   │   └── redis/                      # Caching Backend (P1)
    │   │       ├── client.py
    │   │       └── connection_pool.py
    │   │
    │   ├── storage/                        # Multi-Tier Manager (P1)
    │   │   ├── tier_manager.py
    │   │   └── lifecycle_manager.py
    │   │
    │   ├── thermal/                        # Thermal Management (M1)
    │   │   ├── placement_manager.py
    │   │   ├── device_capability.py
    │   │   ├── sensors.py
    │   │   └── metrics.py
    │   │
    │   ├── placement/                      # Model Placement Cascade (M1)
    │   │   ├── cascade_engine.py
    │   │   ├── circuit_breaker.py
    │   │   ├── capability_matcher.py
    │   │   └── cost_tracker.py
    │   │
    │   ├── backpressure/                   # Backpressure Coordination (M1)
    │   │   ├── watermark_checker.py
    │   │   ├── voice_pipeline_monitor.py
    │   │   ├── global_limits_enforcer.py
    │   │   └── cascade_coordinator.py
    │   │
    │   ├── rate_limiting/                  # Rate Limiting (P2)
    │   │   ├── limiter.py
    │   │   └── config.yml
    │   │
    │   ├── scheduler/                      # Task Scheduling (P2)
    │   │   ├── wfq.py
    │   │   └── task_queue.py
    │   │
    │   ├── admission/                      # Admission Control (P2)
    │   │   ├── controller.py
    │   │   └── policies.py
    │   │
    │   └── extensions/                     # Extensibility Framework (M2)
    │       ├── config_provider.py
    │       ├── metrics_exporter.py
    │       ├── trace_exporter.py
    │       ├── log_handler.py
    │       ├── thermal_policy.py
    │       ├── placement_strategy.py
    │       ├── storage_tier.py
    │       ├── circuit_breaker_strategy.py
    │       ├── security_policy.py
    │       └── performance_optimizer.py
    │
    ├── config/                             # Shared Configuration (P0)
    │   ├── circuit_breakers.yml
    │   ├── rate_limits.yml
    │   ├── thermal_profiles.yml
    │   ├── placement_cascade.yml
    │   ├── backpressure_tiers.yml
    │   └── performance_budgets.yml
    │
    ├── l4_runtime/                         # Storage Implementations (L4)
    │   └── storage/
    │       ├── hot_tier.py                 # In-memory (<1ms)
    │       ├── warm_tier.py                # SSD (<50ms)
    │       └── cold_tier.py                # Cloud (<500ms)
    │
    ├── l3_execution/                       # KV Cache (L3)
    │   └── model_hub/
    │       └── kv_cache_broker.py          # 128MB global pool
    │
    └── modules/                            # Plugin System (M2)
        └── example_module/
            └── metadata.yml

k0/                                         # Shared Observability (P0)
├── metrics/
│   └── prometheus.yml
├── traces/
│   └── tempo.yml
└── logs/
    └── loki.yml
```

---

## Layer 5 Component Map

| Component | Location | Purpose | Priority |
|-----------|----------|---------|----------|
| **K0 Bridge** | `k1/bridge_k0/` | HTTP/2 communication, FlatBuffers, batching | P0 |
| **Event Bus** | `k1/l5_infrastructure/event_bus/` | L1-L2 async messaging (<5ms) | P0 |
| **Serialization** | `k1/l5_infrastructure/serialization/` | FlatBuffers (150× faster) | P0 |
| **Observability** | `k0/` | Shared Prometheus/Grafana/Tempo | P0 |
| **Circuit Breaker** | `k1/l5_infrastructure/resilience/` | 3-state FSM, fail-fast | P1 |
| **Multi-Tier Storage** | `k1/l5_infrastructure/storage/` | Hot/Warm/Cold lifecycle | P1 |
| **Caching** | `k1/l5_infrastructure/resilience/redis/` | <1ms revocation checks | P1 |
| **Thermal Mgmt** | `k1/l5_infrastructure/thermal/` | 4-tier placement cascade | M1 |
| **Model Placement** | `k1/l5_infrastructure/placement/` | NPU→GPU→CPU→Remote | M1 |
| **Backpressure** | `k1/l5_infrastructure/backpressure/` | 3-tier cascading coordination | M1 |
| **Rate Limiting** | `k1/l5_infrastructure/rate_limiting/` | Token bucket per-service | P2 |
| **Scheduler** | `k1/l5_infrastructure/scheduler/` | 4-tier WFQ | P2 |
| **Admission** | `k1/l5_infrastructure/admission/` | Anti-starvation | P2 |
| **Extensibility** | `k1/l5_infrastructure/extensions/` | Plugin framework (10 points) | M2 |
| **Config** | `k1/config/` | YAML-based all-L5-config | P0 |

---

## Total Structure

- **15 Primary L5 Folders** (under `k1/l5_infrastructure/` + `k1/bridge_k0/` + `k1/config/`)
- **3 Supporting Folders** (L4 storage, L3 KV cache, K0 observability)
- **18 Total** including shared dependencies
- **Status:** 🚧 ALL NEED IMPLEMENTATION

---

## Quick Deploy Checklist

```bash
# Create folder structure
mkdir -p k1/bridge_k0/ports
mkdir -p k1/l5_infrastructure/{event_bus,serialization,resilience,storage,thermal,placement,backpressure,rate_limiting,scheduler,admission,extensions}
mkdir -p k1/l5_infrastructure/resilience/{states,fallbacks,redis}
mkdir -p k1/config/
mkdir -p k1/modules/
mkdir -p k1/l4_runtime/storage/
mkdir -p k1/l3_execution/model_hub/

# Create __init__.py files
find k1/l5_infrastructure -type d -exec touch {}/__init__.py \;
```
