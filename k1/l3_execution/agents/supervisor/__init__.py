"""
K1 Layer 3 Execution — agents/supervisor/

PURPOSE:
========
Health monitoring & crash detection for all 58 K1 agents (4 AI + 54 pure actors).
Implements supervisor tree pattern with <100ms crash detection.

RESPONSIBILITIES:
=================
1. Heartbeat Monitoring: 1s interval ping, 3s timeout, event-loop heartbeat (200ms)
2. Crash Detection: <100ms detection, crash logging, replacement spawning
3. Blacklist Manager: 3 crashes in 10 min threshold, 1 hour duration, 88% reduction repeated crashes
4. State Tracking: FSM transition logging, state validation, metrics emission

PRIMARY ADRs:
=============
- ADR-0005d: Supervisor (heartbeat monitoring, crash detection, blacklist)
  * Heartbeat protocol: 1s interval PING, expect PONG within 3s
  * Event-loop heartbeat: 200ms max blocking detection
  * Crash detection: <100ms from last heartbeat miss
  * Blacklist policy: 3 crashes in 10 min → 1 hour blacklist → 88% reduction

- ADR-0002b: Actor Fabric Supervisor
  * Supervisor is pure actor (deterministic logic, no LLM)
  * Monitors ALL 58 agents via heartbeat protocol
  * Supervisor tree: single-level hierarchy (all agents report to one supervisor)
  * Failure escalation: supervisor crash → K1 restart (critical component)

RELATED ADRs:
=============
- ADR-0029: Prometheus Metrics (crash rate, blacklist)

HEARTBEAT PROTOCOL:
===================
**Supervisor → Agent (PING):**
- Interval: 1000ms (configurable)
- Message: HeartbeatPing{supervisor_id, timestamp, sequence_number}

**Agent → Supervisor (PONG):**
- Timeout: 3000ms (3 missed heartbeats → crash detection)
- Message: HeartbeatPong{agent_id, timestamp, sequence_number, event_loop_latency_ms}

**Event-Loop Heartbeat:**
- Agent reports event-loop latency (time since last message processed)
- Warning threshold: 200ms (agent slow, not crashed)
- Critical threshold: 3000ms (agent hung → crash)

CRASH DETECTION:
================
**Detection Logic:**
```python
async def check_heartbeat(agent_id: str) -> None:
    \"\"\"Check agent heartbeat, detect crashes.\"\"\"
    last_pong_time = self.last_pong[agent_id]
    now = time.monotonic() * 1000
    elapsed_ms = now - last_pong_time

    if elapsed_ms > 3000:  # 3 missed heartbeats
        await handle_agent_crash(agent_id, reason="heartbeat_timeout")
```

**Crash Handling:**
1. Log crash event (structured log + Prometheus metric)
2. Update blacklist (increment crash count, check threshold)
3. Notify orchestrator (agent unavailable, need replacement)
4. Cleanup resources (mailbox, KV cache, leases)
5. Spawn replacement (if not blacklisted)

BLACKLIST MANAGER:
==================
**Policy (ADR-0005d):**
- **Threshold:** 3 crashes in 10 min window
- **Duration:** 1 hour blacklist (no hiring during blacklist)
- **Impact:** 88% reduction in repeated crashes (prevents crash loops)

**Algorithm:**
```python
class BlacklistManager:
    def __init__(self):
        self.crash_history = {}  # agent_type → list[(timestamp, reason)]
        self.blacklist = {}  # agent_type → blacklist_until_timestamp

    def record_crash(self, agent_type: str, reason: str) -> bool:
        \"\"\"Record crash, check if blacklist threshold exceeded.\"\"\"
        now = time.monotonic() * 1000
        # Add crash to history
        self.crash_history[agent_type].append((now, reason))

        # Count crashes in last 10 min
        recent_crashes = [
            (ts, r) for (ts, r) in self.crash_history[agent_type]
            if now - ts < 600_000  # 10 min window
        ]

        if len(recent_crashes) >= 3:
            # Blacklist for 1 hour
            self.blacklist[agent_type] = now + 3_600_000
            return True  # Blacklisted
        return False  # Not blacklisted

    def is_blacklisted(self, agent_type: str) -> bool:
        \"\"\"Check if agent type is blacklisted.\"\"\"
        if agent_type not in self.blacklist:
            return False
        now = time.monotonic() * 1000
        return now < self.blacklist[agent_type]
```

PERFORMANCE METRICS:
====================
- Heartbeat overhead: <1% CPU (58 agents × 1s interval)
- Crash detection latency: <100ms (from last heartbeat miss)
- Blacklist enforcement: <1ms lookup (hash table)
- Supervisor overhead: <5ms per agent per second

INTEGRATION POINTS:
===================
Supervisor → Agent (Heartbeat):
```python
# Send PING to agent mailbox
await agent_mailbox.enqueue(
    message=HeartbeatPing(supervisor_id, timestamp, seq),
    priority=Priority.URGENT
)
```

Agent → Supervisor (PONG):
```python
# Agent responds with PONG
await supervisor_mailbox.enqueue(
    message=HeartbeatPong(agent_id, timestamp, seq, event_loop_latency_ms),
    priority=Priority.URGENT
)
```

Supervisor → Orchestrator (Crash Notification):
```python
# Notify orchestrator of agent crash
await orchestrator_mailbox.enqueue(
    message=AgentCrashEvent(agent_id, agent_type, reason, timestamp),
    priority=Priority.REALTIME
)
```

TESTING:
========
See tests/l3_execution/agents/test_supervisor.py (ADR-0004d):
- Heartbeat monitoring (1s interval, 3s timeout)
- Crash detection (<100ms latency)
- Blacklist enforcement (3 crashes → 1 hour blacklist)
- Event-loop latency detection (200ms warning, 3s critical)
- Supervisor overhead (<1% CPU)

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_supervisor_heartbeat_failures{agent_id}
- layer3_agent_crash_rate{agent_type, reason}
- layer3_blacklist_active{agent_type}
- layer3_supervisor_overhead_cpu_percent{}

Structured Logs:
```python
logger.error(
    "agent_crashed",
    agent_id=agent_id,
    agent_type=agent_type,
    reason="heartbeat_timeout",
    last_pong_ms_ago=elapsed_ms,
    crash_count=crash_count,
    blacklisted=is_blacklisted,
    trace_id=trace_id
)
```

RESEARCH FOUNDATIONS:
=====================
- Erlang OTP Supervision Trees (Armstrong 2003) — Supervisor patterns
- Akka Death Watch (Lightbend 2013) — Failure detection
- Heartbeat protocols (Chandra & Toueg 1996) — Distributed failure detection

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
