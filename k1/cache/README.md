# K1 Cache Module (Top-Level: Adaptive KV Cache)

## Overview

The `cache/` module implements the **Top-Level: Adaptive KV Cache** layer of the K1 Cognitive Architecture. This module provides dynamic key-value cache management for LLM inference, supporting adaptive sizing, thermal-aware placement, and hot/cold eviction strategies.

## Purpose

- **Adaptive Sizing**: Dynamic cache allocation based on workload and thermal signals
- **Thermal Integration**: Placement optimization considering NPU/GPU/CPU temperatures
- **Hot/Cold Eviction**: Intelligent eviction with rapid rewarming capabilities
- **Performance Optimization**: Minimize cache misses while respecting memory budgets

## Architecture

### Core Components

- **`size_allocator.py`**: Dynamic cache size allocation with workload adaptation
- **`evictor.py`**: Hot/cold eviction policies with thermal data integration
- **`rewarmer.py`**: Rapid reactivation mechanisms for evicted sessions
- **`thermal_integrator.py`**: Temperature-based cache adjustments

### Cache Hierarchy

Following ADR-0025 (KV Cache Management):

- **Hot Cache**: Active inference, <1ms access, thermal-optimized placement
- **Warm Cache**: Recently used, <5ms access, compressed storage
- **Cold Cache**: Evicted but recoverable, <50ms reactivation

## Key ADRs

- **ADR-0060**: Adaptive KV-Cache Management - Core adaptive management
- **ADR-0060a**: Dynamic Placement & Sizing - Runtime allocation algorithms
- **ADR-0060b**: Hot/Cold Eviction & Recovery - Eviction and rewarming strategies
- **ADR-0025**: KV Cache Management (512MB) - Global cache budget
- **ADR-0076**: KV Cache Optimization Strategy - Advanced optimization techniques
- **ADR-0024**: Performance Budgets (P95) - Latency and throughput targets
- **ADR-0026**: Thermal Hysteresis Matrix - Temperature-based throttling
- **ADR-0027**: Model Placement Cascade - Hardware placement optimization
- **ADR-0077**: Thermal Placement Algorithm v2 - ML-informed thermal management

## Interfaces

### CacheSizeAllocator Interface

```python
class CacheSizeAllocator:
    async def allocate(self, session_id: str, model_type: ModelType, requested_mb: int) -> CacheAllocation:
        """Allocate cache for session with thermal awareness"""

    async def reallocate(self, session_id: str, new_size_mb: int) -> bool:
        """Adjust cache size based on workload signals"""

    async def deallocate(self, session_id: str) -> None:
        """Release cache allocation"""
```

### Evictor Interface

```python
class HotColdEvictor:
    async def evict_if_needed(self, pressure_level: PressureLevel) -> List[EvictedSession]:
        """Evict sessions based on memory pressure and thermal signals"""

    async def should_evict(self, session_id: str) -> EvictionDecision:
        """Determine if session should be evicted"""
```

### Rewarmer Interface

```python
class RapidRewarmer:
    async def rewarm(self, session_id: str, evicted_data: EvictedData) -> RewarmResult:
        """Rapidly restore evicted session data"""

    async def prefetch(self, session_id: str, access_pattern: AccessPattern) -> None:
        """Prefetch likely-to-be-needed data"""
```

## Performance Characteristics

- **Allocation Latency**: <10ms for cache allocation decisions
- **Eviction Latency**: <5ms for hot evictions, <50ms for rewarming
- **Cache Hit Rate**: Target 75% for active conversations
- **Memory Budget**: 512MB global KV cache limit
- **Thermal Response**: <100ms adjustment to temperature changes

## Thermal Integration

Following ADR-0026 (Thermal Hysteresis Matrix):

- **Temperature Monitoring**: Continuous sensor reading with hysteresis
- **Placement Cascade**: NPU (fastest) → GPU → CPU → Remote based on thermal state
- **Throttling Policies**: Automatic cache reduction under thermal pressure
- **Recovery**: Gradual cache expansion as temperatures normalize

## Fault Tolerance

- **Graceful Degradation**: Cache size reduction under memory pressure
- **Data Persistence**: Critical session data preserved during evictions
- **Recovery Mechanisms**: Automatic rewarming on session reactivation
- **Monitoring**: Comprehensive metrics for cache health and performance

## Security

- **Access Control**: Capability-based cache access per session
- **Data Isolation**: Session-specific cache regions prevent cross-contamination
- **Audit Trail**: Cache operations logged with session and user context
- **Privacy**: Cache content respects privacy band restrictions

## Testing

- **Unit Tests**: Isolated cache components with mock thermal sensors
- **Integration Tests**: End-to-end cache lifecycle with real workloads
- **Performance Tests**: Cache hit rates and latency under various conditions
- **Thermal Tests**: Cache behavior under simulated thermal pressure

## Dependencies

- `k1.supervision`: Health monitoring and failure detection
- `k1.thermal`: Temperature monitoring and hysteresis management
- `k1.sessionstate`: Session data for cache decisions
- `k1.observability`: Metrics and tracing for cache operations

## Development Notes

- Cache management is thermal-aware and workload-adaptive
- Hot/cold eviction balances memory usage with reactivation speed
- All allocations respect the global 512MB KV cache budget
- Thermal integration prevents overheating during intensive inference
- Cache operations are observable with detailed metrics and tracing
