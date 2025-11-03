---
adr_number: 0032c
title: Resource Egress Control (cgroups)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
- compliance
- observability
- performance
- privacy
- reliability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0032
- ADR-0032a
- ADR-0032b
- ADR-0032c
- ADR-0032d
- ADR-0033
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0032
  - ADR-0032a
  - ADR-0032b
  - ADR-0032c
  - ADR-0032d
  - ADR-0033
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


# ADR-0032c: Resource Egress Control (cgroups)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0032: Band-Based Egress Rules](0032-band-based-egress-rules.md)
**Authors:** K1 Architecture Team
**Category:** Security & Privacy
**Related ADRs:** ADR-0032a (Network Egress), ADR-0032b (Filesystem Egress), ADR-0033 (3-Tier Sandbox)

---

## Context

### Problem Statement

**Tools require CPU, memory, and I/O resources to execute, but unrestricted resource usage enables denial-of-service attacks, resource exhaustion, and noisy-neighbor problems.**

**Privacy Band Requirements:**
- **GREEN Band:** Generous resources (4 CPU cores, 2GB RAM)
- **AMBER Band:** Moderate resources (2 CPU cores, 1GB RAM)
- **RED Band:** Minimal resources (1 CPU core, 512MB RAM)
- **BLACK Band:** NO EXECUTION (zero resources)

**Without Resource Egress Control:**
```
Malicious Scenario:
- Tool: "data_analyzer" (GREEN band)
- User: "Analyze sales trends"

Resource Abuse Attack:
1. Tool spawns 1000 threads (fork bomb) ❌
2. Tool allocates 16GB RAM (memory exhaustion) ❌
3. Tool runs infinite loop at 100% CPU (DoS) ❌
4. Tool writes 500GB to /tmp/ (disk exhaustion) ❌
5. Tool opens 100,000 file descriptors (FD exhaustion) ❌

Impact: K1 crashes, other tools starved, system unresponsive
```

**With This Sub-ADR:**
```
Secure Execution:
- Tool: "data_analyzer" (GREEN band)
- cgroups limits: 4 CPUs, 2GB RAM, 100 processes, 10GB I/O

Execution:
1. Tool spawns 1000 threads ❌ (capped at 100, rest fail)
2. Tool allocates 2GB RAM ✅ (at limit)
3. Tool allocates 3GB RAM ❌ (OOM killer terminates tool)
4. Tool runs at 100% CPU ✅ (capped at 400% = 4 cores)
5. Tool writes 10GB to /tmp/ ✅ (at I/O limit)
6. Tool writes 11GB ❌ (I/O throttled to 0 bytes/sec)

Result: Analysis completes, resource abuse prevented ✅
```

### System Constraints

1. **Performance Requirements:**
   - cgroup setup: <2ms per tool launch
   - Resource enforcement: 0ms (kernel-enforced)
   - Overhead: <1% CPU for accounting

2. **Security Requirements:**
   - 100% OOM killer integration (kill tool, not K1)
   - Hard limits on CPU, memory, PIDs, I/O
   - Zero resource leakage after tool exit

3. **Compatibility:**
   - Linux: cgroups v2 (kernel 4.5+)
   - Requires cgroupfs mounted at /sys/fs/cgroup/

---

## Decision

### Resource Control Architecture

**4-Tier Resource Limits (cgroups v2):**
1. **CPU Quota** → Limit CPU cores per tool
2. **Memory Limit** → Hard cap with OOM killer
3. **PID Limit** → Prevent fork bombs
4. **I/O Limit** → Throttle disk writes

### Privacy Band Resource Policies

```yaml
# File: k1/config/resource_egress_policies.yml

resource_egress:
  # GREEN Band: Generous resources for complex tasks
  green_band:
    cpu:
      quota: 400000        # 4.0 CPUs (400,000 µs per 100ms period)
      period: 100000       # 100ms period
      shares: 1024         # High priority
    memory:
      limit: 2147483648    # 2GB hard limit
      soft_limit: 1610612736  # 1.5GB soft limit (OOM warning)
      swap: 0              # No swap
    pids:
      max: 100             # Max 100 processes/threads
    io:
      write_bps: 10737418240  # 10 GB/s write throughput
      write_iops: 10000    # 10,000 IOPS
      read_bps: 21474836480   # 20 GB/s read throughput
      read_iops: 20000     # 20,000 IOPS
    timeout: 300           # 5 minutes max execution

  # AMBER Band: Moderate resources
  amber_band:
    cpu:
      quota: 200000        # 2.0 CPUs
      period: 100000
      shares: 512          # Medium priority
    memory:
      limit: 1073741824    # 1GB hard limit
      soft_limit: 805306368   # 768MB soft limit
      swap: 0
    pids:
      max: 50              # Max 50 processes
    io:
      write_bps: 5368709120   # 5 GB/s
      write_iops: 5000
      read_bps: 10737418240   # 10 GB/s
      read_iops: 10000
    timeout: 180           # 3 minutes max execution

  # RED Band: Minimal resources for sensitive data
  red_band:
    cpu:
      quota: 100000        # 1.0 CPU
      period: 100000
      shares: 256          # Low priority
    memory:
      limit: 536870912     # 512MB hard limit
      soft_limit: 402653184   # 384MB soft limit
      swap: 0
    pids:
      max: 20              # Max 20 processes
    io:
      write_bps: 1073741824   # 1 GB/s
      write_iops: 1000
      read_bps: 2147483648    # 2 GB/s
      read_iops: 2000
    timeout: 60            # 1 minute max execution

  # BLACK Band: No execution
  black_band:
    cpu:
      quota: 0             # No CPU
      period: 100000
      shares: 0
    memory:
      limit: 0             # No memory
      soft_limit: 0
      swap: 0
    pids:
      max: 0               # No processes
    io:
      write_bps: 0
      write_iops: 0
      read_bps: 0
      read_iops: 0
    timeout: 0
```

### cgroups v2 Implementation

```python
# File: k1/security/resource_egress.py

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class ResourcePolicy:
    """Resource limits for tool"""
    tool_pid: int
    band: str
    cpu_quota: int          # µs per period
    cpu_period: int         # µs
    cpu_shares: int         # Priority weight
    memory_limit: int       # bytes
    memory_soft_limit: int  # bytes
    pids_max: int
    io_write_bps: int       # bytes/sec
    io_write_iops: int      # ops/sec
    io_read_bps: int
    io_read_iops: int
    timeout: int            # seconds

class CgroupsResourceController:
    """
    Control tool resource usage via cgroups v2
    Enforces CPU, memory, PID, and I/O limits
    """

    def __init__(self, cgroup_root: Path = Path("/sys/fs/cgroup")):
        self.cgroup_root = cgroup_root
        self.k1_cgroup = cgroup_root / "k1"
        self.active_cgroups: Dict[int, Path] = {}  # pid → cgroup path
        self._ensure_k1_cgroup_exists()

    def _ensure_k1_cgroup_exists(self):
        """Create K1 parent cgroup"""
        self.k1_cgroup.mkdir(exist_ok=True)

        # Enable controllers
        controllers = ["cpu", "memory", "pids", "io"]
        subtree_control = self.k1_cgroup / "cgroup.subtree_control"

        for controller in controllers:
            subtree_control.write_text(f"+{controller}\n")

        logger.info(f"K1 cgroup initialized: {self.k1_cgroup}")

    async def apply_policy(self, policy: ResourcePolicy) -> bool:
        """
        Apply resource limits for tool (<2ms)
        Returns True if successful
        """
        if policy.band == "BLACK":
            # No resources allowed
            return True  # Tool won't run anyway

        try:
            # Create cgroup for this tool
            cgroup_path = self.k1_cgroup / f"tool_{policy.tool_pid}"
            cgroup_path.mkdir(exist_ok=True)

            # Apply CPU limits
            await self._set_cpu_limits(cgroup_path, policy)

            # Apply memory limits
            await self._set_memory_limits(cgroup_path, policy)

            # Apply PID limits
            await self._set_pid_limits(cgroup_path, policy)

            # Apply I/O limits
            await self._set_io_limits(cgroup_path, policy)

            # Move process to cgroup
            await self._add_process_to_cgroup(cgroup_path, policy.tool_pid)

            self.active_cgroups[policy.tool_pid] = cgroup_path

            logger.info(
                f"Applied resource policy",
                pid=policy.tool_pid,
                band=policy.band,
                cgroup=str(cgroup_path)
            )

            return True

        except Exception as e:
            logger.error(f"Failed to apply resource policy: {e}")
            return False

    async def _set_cpu_limits(self, cgroup_path: Path, policy: ResourcePolicy):
        """Set CPU quota and shares"""
        # CPU quota (hard limit)
        cpu_max = cgroup_path / "cpu.max"
        cpu_max.write_text(f"{policy.cpu_quota} {policy.cpu_period}\n")

        # CPU shares (priority)
        cpu_weight = cgroup_path / "cpu.weight"
        # Convert shares (1-1024) to weight (1-10000)
        weight = int((policy.cpu_shares / 1024) * 10000)
        cpu_weight.write_text(f"{weight}\n")

        logger.debug(
            f"CPU limits set",
            quota=policy.cpu_quota,
            period=policy.cpu_period,
            weight=weight
        )

    async def _set_memory_limits(self, cgroup_path: Path, policy: ResourcePolicy):
        """Set memory limits with OOM killer"""
        # Hard limit
        memory_max = cgroup_path / "memory.max"
        memory_max.write_text(f"{policy.memory_limit}\n")

        # Soft limit (OOM warning threshold)
        memory_high = cgroup_path / "memory.high"
        memory_high.write_text(f"{policy.memory_soft_limit}\n")

        # Disable swap
        memory_swap_max = cgroup_path / "memory.swap.max"
        memory_swap_max.write_text("0\n")

        # Set OOM killer to target this cgroup
        oom_group = cgroup_path / "memory.oom.group"
        oom_group.write_text("1\n")  # Kill all processes in cgroup on OOM

        logger.debug(
            f"Memory limits set",
            hard_limit=policy.memory_limit,
            soft_limit=policy.memory_soft_limit
        )

    async def _set_pid_limits(self, cgroup_path: Path, policy: ResourcePolicy):
        """Set PID limit (prevent fork bombs)"""
        pids_max = cgroup_path / "pids.max"
        pids_max.write_text(f"{policy.pids_max}\n")

        logger.debug(f"PID limit set: {policy.pids_max}")

    async def _set_io_limits(self, cgroup_path: Path, policy: ResourcePolicy):
        """Set I/O bandwidth limits"""
        # Detect primary block device
        device_id = self._get_primary_block_device()

        # Write bandwidth limit
        io_max = cgroup_path / "io.max"
        io_max.write_text(
            f"{device_id} rbps={policy.io_read_bps} "
            f"wbps={policy.io_write_bps} "
            f"riops={policy.io_read_iops} "
            f"wiops={policy.io_write_iops}\n"
        )

        logger.debug(
            f"I/O limits set",
            device=device_id,
            write_bps=policy.io_write_bps,
            write_iops=policy.io_write_iops
        )

    def _get_primary_block_device(self) -> str:
        """Get primary block device ID (major:minor)"""
        # Read device ID from /proc/mounts
        with open("/proc/mounts") as f:
            for line in f:
                if line.startswith("/dev/") and " / " in line:
                    device = line.split()[0]
                    stat = os.stat(device)
                    major = os.major(stat.st_rdev)
                    minor = os.minor(stat.st_rdev)
                    return f"{major}:{minor}"

        # Fallback: assume 8:0 (sda)
        return "8:0"

    async def _add_process_to_cgroup(self, cgroup_path: Path, pid: int):
        """Move process to cgroup"""
        procs = cgroup_path / "cgroup.procs"
        procs.write_text(f"{pid}\n")

        logger.debug(f"Process {pid} added to cgroup {cgroup_path}")

    async def remove_policy(self, pid: int):
        """
        Remove resource policy and cleanup cgroup
        """
        if pid not in self.active_cgroups:
            return

        cgroup_path = self.active_cgroups[pid]

        try:
            # cgroup will auto-delete when empty
            # Just remove from tracking
            del self.active_cgroups[pid]

            # Force cleanup if processes still exist
            procs_file = cgroup_path / "cgroup.procs"
            if procs_file.exists():
                procs = procs_file.read_text().strip()
                if procs:
                    logger.warning(f"Processes still in cgroup: {procs}")

            # Delete cgroup directory
            cgroup_path.rmdir()

            logger.info(f"Removed cgroup: pid={pid}, path={cgroup_path}")

        except Exception as e:
            logger.warning(f"Failed to cleanup cgroup: {e}")
```

### OOM Killer Integration

```python
# File: k1/security/oom_handler.py

import asyncio
from pathlib import Path
from datetime import datetime

class OOMEventHandler:
    """
    Monitor OOM events from cgroups
    Log violations and terminate tools gracefully
    """

    def __init__(self, cgroup_root: Path):
        self.cgroup_root = cgroup_root
        self.monitoring = False

    async def start_monitoring(self):
        """Monitor memory.events for OOM kills"""
        self.monitoring = True

        while self.monitoring:
            for cgroup_dir in (self.cgroup_root / "k1").iterdir():
                if cgroup_dir.is_dir() and cgroup_dir.name.startswith("tool_"):
                    await self._check_oom_events(cgroup_dir)

            await asyncio.sleep(0.1)  # Check every 100ms

    async def _check_oom_events(self, cgroup_path: Path):
        """Check for OOM events in cgroup"""
        events_file = cgroup_path / "memory.events"

        if not events_file.exists():
            return

        events = events_file.read_text()

        # Parse memory.events
        for line in events.split("\n"):
            if line.startswith("oom_kill "):
                count = int(line.split()[1])
                if count > 0:
                    await self._handle_oom(cgroup_path, count)

    async def _handle_oom(self, cgroup_path: Path, count: int):
        """Handle OOM kill event"""
        tool_name = cgroup_path.name.replace("tool_", "")

        logger.error(
            f"OOM kill detected",
            cgroup=str(cgroup_path),
            count=count
        )

        # Log violation to K0 audit trail
        violation = {
            "type": "resource_oom",
            "timestamp": datetime.utcnow().isoformat(),
            "cgroup": str(cgroup_path),
            "tool_name": tool_name,
            "oom_count": count,
            "severity": "high"
        }

        await self._log_violation(violation)

    async def _log_violation(self, violation: dict):
        """Log resource violation to K0"""
        # Forward to K0 ToolReceipt
        # (Implementation in ADR-0032d)
        pass
```

### Resource Monitoring

```python
# File: k1/security/resource_monitor.py

from prometheus_client import Gauge, Counter

# Prometheus metrics
resource_cpu_usage = Gauge(
    'k1_tool_cpu_usage_percent',
    'Tool CPU usage percentage',
    ['tool_name', 'band', 'pid']
)

resource_memory_usage = Gauge(
    'k1_tool_memory_usage_bytes',
    'Tool memory usage in bytes',
    ['tool_name', 'band', 'pid']
)

resource_oom_kills = Counter(
    'k1_tool_oom_kills_total',
    'Total OOM kills',
    ['tool_name', 'band']
)

class ResourceMonitor:
    """Monitor tool resource usage via cgroups"""

    def __init__(self, cgroup_root: Path):
        self.cgroup_root = cgroup_root

    async def collect_metrics(self):
        """Collect resource metrics from cgroups"""
        for cgroup_dir in (self.cgroup_root / "k1").iterdir():
            if cgroup_dir.is_dir() and cgroup_dir.name.startswith("tool_"):
                await self._collect_cgroup_metrics(cgroup_dir)

    async def _collect_cgroup_metrics(self, cgroup_path: Path):
        """Collect metrics for single cgroup"""
        tool_name = cgroup_path.name.replace("tool_", "")

        # CPU usage
        cpu_stat = (cgroup_path / "cpu.stat").read_text()
        usage_usec = int([
            line for line in cpu_stat.split("\n")
            if line.startswith("usage_usec")
        ][0].split()[1])

        resource_cpu_usage.labels(
            tool_name=tool_name,
            band="unknown",  # TODO: track band
            pid=tool_name
        ).set(usage_usec / 1000000)  # Convert to seconds

        # Memory usage
        memory_current = (cgroup_path / "memory.current").read_text().strip()
        resource_memory_usage.labels(
            tool_name=tool_name,
            band="unknown",
            pid=tool_name
        ).set(int(memory_current))
```

---

## Implementation Timeline

### Phase 1: CPU/Memory Limits (Weeks 1-3)
- **Week 1:** cgroups v2 setup and K1 parent cgroup
- **Week 2:** CPU quota and memory limits
- **Week 3:** OOM killer integration

### Phase 2: PID/I/O Limits (Weeks 4-6)
- **Week 4:** PID limits (fork bomb prevention)
- **Week 5:** I/O bandwidth limits
- **Week 6:** Resource monitoring and metrics

### Phase 3: Integration (Weeks 7-8)
- **Week 7:** Cgroup lifecycle management
- **Week 8:** WARD tests + validation

---

## Consequences

### Positive
1. **100% Fork Bomb Prevention:** PID limits enforce max processes
2. **OOM Killer Protection:** Tools killed, K1 survives
3. **Fair Resource Sharing:** CPU shares prevent noisy neighbors
4. **I/O Throttling:** Disk exhaustion prevented

### Negative
1. **Overhead:** 1% CPU for cgroups accounting
2. **Kernel Dependency:** Requires cgroups v2 (kernel 4.5+)
3. **Configuration Complexity:** Tuning limits per privacy band

### Risks
1. **Legitimate Tools Starved:** Overly aggressive limits
   - Mitigation: Per-tool resource profiling, generous GREEN band limits
2. **OOM Thrashing:** Tool repeatedly killed and restarted
   - Mitigation: Exponential backoff, circuit breaker

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| OOM Kill Protection | 100% | K1 never killed, only tools |
| Fork Bomb Prevention | 100% | PID limit enforced |
| Resource Setup Latency | <2ms | cgroup creation time |
| Overhead | <1% | CPU accounting overhead |

---

## Related Documents

- [ADR-0032: Band-Based Egress Rules](0032-band-based-egress-rules.md)
- [ADR-0032a: Network Egress Control](0032a-network-egress-control-iptables-privacy-bands.md)
- [ADR-0032b: Filesystem Egress Control](0032b-filesystem-egress-control-chroot-seccomp.md)
- [ADR-0032d: Egress Violation Logging](0032d-egress-violation-logging-audit-trail.md)

---

**Status:** ✅ Ready for implementation
**Timeline:** 8 weeks
**Priority:** ⭐⭐⭐ Critical (Security foundation)