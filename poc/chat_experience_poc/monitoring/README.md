# Integration Health Dashboard

Real-time monitoring dashboard for K1 Intelligence Module components.

## Overview

The Integration Health Dashboard provides comprehensive visibility into all system components, displaying:
- Component health status (✅ Healthy, ⚠️ Degraded, ❌ Failed)
- P95 latency metrics
- Operational details (request counts, queue depths, connection status)
- Overall system health summary
- Alerting for unhealthy components and performance degradation

## Quick Start

### Basic Usage

```python
from monitoring.integration_dashboard import get_integration_dashboard

dashboard = get_integration_dashboard()

# Single snapshot
status = await dashboard.display_status()
print(status)

# Auto-refresh mode (updates every 5s)
await dashboard.display_status(refresh=True)
```

### Demo Script

```bash
# Single snapshot
python scripts/demo_integration_dashboard.py

# Auto-refresh mode (Ctrl+C to exit)
python scripts/demo_integration_dashboard.py --refresh
```

### CLI Integration

Add `/dashboard` command to your CLI interface:

```python
async def handle_dashboard_command():
    """Handle /dashboard CLI command."""
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()
    status = await dashboard.display_status()
    print(status)
```

## Components Monitored

### Layer 1 - Input
- **Intent Router**: User message ingress and routing

### Layer 3 - Agents
- **Concierge Agent**: Tier 1 master coordinator
- **Orchestrator**: 3-phase task coordination
- **MemoryWriterAgent**: Memory formation background service
- **ProactiveAgent**: SSE-based proactive notifications

### Layer 4 - Runtime
- **SessionState Manager**: Conversation state management
- **DeltaBus**: Event pub/sub system
- **Temporal Module**: Trigger scheduler

### Layer 5 - Infrastructure
- **K0 Bridge (Query)**: K0 query client (P01)
- **K0 Bridge (Batch)**: K0 batch client (P02/P05/P06)
- **User KG Database**: User knowledge graph (SQLite)
- **Mock MCP Server**: External tool validation (mock)

## Status Indicators

### Status Values
- ✅ **HEALTHY/ACTIVE/READY/RUNNING/UP**: Component operational
- ⚠️ **DEGRADED/WARNING**: Component functional but impaired
- ❌ **ERROR/DOWN/FAILED**: Component not operational
- ❓ **UNKNOWN**: Component not initialized or unreachable

### Status Colors
- **Green (✅)**: All systems operational
- **Yellow (⚠️)**: Some degradation, system functional
- **Red (❌)**: Critical failures, system impaired

## Alerting

The dashboard automatically monitors and alerts on:

### Unhealthy Component Alert
- **Condition**: Component unhealthy for >30 seconds
- **Action**: Log ERROR with component name and duration
- **Example**: `component_unhealthy_too_long component=Concierge_Agent duration_seconds=45`

### Multiple Failures Alert
- **Condition**: 2+ components unhealthy simultaneously
- **Action**: Log ERROR recommending system shutdown
- **Example**: `multiple_components_unhealthy_shutdown_recommended count=3`

### Performance Degradation Alert
- **Condition**: P95 latency >2x performance budget
- **Action**: Log WARNING with latency and budget
- **Example**: `component_performance_degraded component=Orchestrator latency_p95_ms=110.0 budget_ms=50.0`

## Performance Budgets

Default P95 latency budgets (from `config/perf.yml`):

| Component | Budget | Critical |
|-----------|--------|----------|
| Intent Router | 5ms | ✅ |
| DeltaBus | 1ms | ✅ |
| SessionState Manager | 1ms | ✅ |
| Temporal Module | 5ms | ✅ |
| ProactiveAgent | 5ms | ✅ |
| MemoryWriterAgent | 15ms | ⚠️ |
| K0 Bridge (Query) | 50ms | ⚠️ |
| K0 Bridge (Batch) | 50ms | ⚠️ |
| Orchestrator | 50ms | ⚠️ |
| Concierge Agent | 150ms | ❌ |

## Example Output

```
╔══════════════════════════════════════════════════════════════════╗
║            K1 Intelligence Module - System Status                ║
╠══════════════════════════════════════════════════════════════════╣
║ Component                │ Status    │ Latency (P95) │ Details   ║
╠══════════════════════════╪═══════════╪═══════════════╪═══════════╣
║ Intent Router            │ ✅ HEALTHY │ 3.2ms         │ 1247 req  ║
║ Concierge Agent          │ ✅ ACTIVE  │ 145ms         │ Turn 42   ║
║ Orchestrator             │ ✅ READY   │ 48ms          │ 23 tasks  ║
║ SessionState Manager     │ ✅ HEALTHY │ 0.8ms         │ 5 sessions║
║ DeltaBus                 │ ✅ RUNNING │ 0.4ms         │ 3542 evt  ║
║ MemoryWriterAgent        │ ✅ ACTIVE  │ 12ms          │ Queue: 2  ║
║ K0 Bridge (Query)        │ ✅ HEALTHY │ 42ms          │ Hit: 78%  ║
║ K0 Bridge (Batch)        │ ✅ HEALTHY │ 38ms          │ 156 batch ║
║ Temporal Module          │ ✅ RUNNING │ 2ms           │ 7 triggers║
║ ProactiveAgent (SSE)     │ ✅ ACTIVE  │ 1ms           │ Connected ║
║ User KG Database         │ ✅ HEALTHY │ 6ms           │ 1247 nodes║
║ Mock MCP Server (8001)   │ ✅ UP      │ 5ms           │ Mock svc  ║
╠══════════════════════════╧═══════════╧═══════════════╧═══════════╣
║ Overall System Health: ✅ ALL SYSTEMS OPERATIONAL                ║
╚══════════════════════════════════════════════════════════════════╝
```

## Component Details Format

Each component shows operational details in the "Details" column:

- **Request counts**: `1247 req`, `89 calls`
- **Turn/task counts**: `Turn 42`, `23 tasks`
- **Queue depths**: `Queue: 2`, `Q: 5`
- **Session counts**: `5 sessions`, `5 sess`
- **Event counts**: `3542 evt`
- **Cache hit rates**: `Hit: 78%`
- **Connection status**: `Connected`, `Disconn`
- **Database nodes**: `1247 nodes`
- **Triggers**: `7 triggers`, `7 trig`
- **Batches**: `156 batch`

## Implementation Notes

### Health Check Methods

Each component has a dedicated health check method:
- `_check_intent_router()`
- `_check_concierge_agent()`
- `_check_orchestrator()`
- `_check_session_state_manager()`
- `_check_deltabus()`
- `_check_memory_writer_agent()`
- `_check_temporal_module()`
- `_check_proactive_agent()`
- `_check_k0_bridge_query()`
- `_check_k0_bridge_batch()`
- `_check_user_kg()`
- `_check_mock_mcp_server()`

### Singleton Pattern

The dashboard uses a singleton pattern for global access:

```python
from monitoring.integration_dashboard import get_integration_dashboard

# Always returns the same instance
dashboard = get_integration_dashboard()
```

### Graceful Degradation

The dashboard handles missing/unavailable components gracefully:
- Components not initialized show as `UNKNOWN`
- Import errors are logged at DEBUG level
- Missing stats methods default to 0.0ms latency
- HTTP timeouts (2s) for external services

## Testing

Run dashboard tests:

```bash
# All dashboard tests
python -m pytest tests/monitoring/test_integration_dashboard.py -v

# Specific test
python -m pytest tests/monitoring/test_integration_dashboard.py::test_dashboard_display_status -v
```

## References

- **Issue 6.5.5.2**: Integration Health Dashboard
- **docs/whiteboard/chat_experience.md**: Observability requirements
- **config/perf.yml**: Performance budgets
- **ADR-0073**: DRAINING state and shutdown

## Future Enhancements

Planned improvements for production:
1. **Metrics Export**: Export to Prometheus/Grafana
2. **Historical Trends**: Track component health over time
3. **Predictive Alerts**: ML-based anomaly detection
4. **Custom Thresholds**: Per-component alert configuration
5. **Webhook Integration**: Slack/PagerDuty alerting
6. **Web UI**: React-based dashboard with real-time updates
