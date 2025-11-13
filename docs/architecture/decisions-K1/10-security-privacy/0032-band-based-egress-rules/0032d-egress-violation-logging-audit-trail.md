---
adr_number: "0032d"
parent_adr: "ADR-0032"
affected_layers:
- layer3_execution
- layer4_runtime
affected_modules:
  - k1.l5_infrastructure.egress_control.violation_logger
  - k1.l5_infrastructure.egress_control.audit_trail
authors:
- K1 Architecture Team
concerns:
- architecture
- compliance
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: "Phase 2 (Security & Privacy)"
implementation_status: UNKNOWN
propagation:
  triggers:
    - Changing audit trail retention policies
    - Modifying egress violation thresholds
    - Updating compliance reporting requirements
  affected_adrs:
  - ADR-0032
  - ADR-0032a
  - ADR-0032b
  - ADR-0032c
  - ADR-0032d
  - ADR-0038
  affected_contracts:
    - k1/contracts/flatbuffers/layer3_execution/egress_violation_log.fbs
    - k1/contracts/flatbuffers/layer5_infrastructure/audit_trail.fbs
  affected_tests:
    - tests/k1/l5_infrastructure/test_violation_logger.py
    - tests/k1/l5_infrastructure/test_audit_trail.py
related_adrs:
- ADR-0032
- ADR-0032a
- ADR-0032b
- ADR-0032c
- ADR-0032d
- ADR-0033
- ADR-0033c
- ADR-0038
related_contracts: []
related_diagrams: []
research_citations: []
status: PROPOSED
superseded_by: []
supersedes: []
parent_adr: "ADR-0032"
parent_adr: "ADR-0032"
title: "0032D: Egress Violation Logging & Audit Trail""0032D: Egress Violation Logging & Audit Trail"Egress Violation Logging & Audit Trail
---

# ADR-0032d: Egress Violation Logging & Audit Trail

**Status:** Ã¢Å“â€¦ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0032: Band-Based Egress Rules](0032-band-based-egress-rules.md)
**Authors:** K1 Architecture Team
**Category:** Security & Privacy
**Related ADRs:** ADR-0032a (Network Egress), ADR-0032b (Filesystem Egress), ADR-0032c (Resource Egress), ADR-0038 (ToolReceipt System)

---

## Context

### Problem Statement

**Egress violations (network, filesystem, resource abuse) must be logged for compliance, forensics, and threat detection. Without comprehensive audit trails, security incidents cannot be investigated or proven for SOC2/ISO27001 compliance.**

**Compliance Requirements:**
- **SOC2 CC6.1:** Security events must be logged and retained
- **ISO27001 A.12.4.1:** Event logging for compliance audit
- **GDPR Article 33:** Data breach notification within 72 hours
- **PCI-DSS 10.2:** Audit logs for access control violations

**Without Violation Logging:**
```
Security Incident (Undetected):
1. Tool "pdf_converter" (GREEN band) compromised by attacker
2. Tool POSTs PII to attacker.com Ã¢ÂÅ’ (blocked by iptables)
3. Tool reads /home/user/.ssh/id_rsa Ã¢ÂÅ’ (blocked by chroot)
4. Tool spawns 1000 processes Ã¢ÂÅ’ (blocked by cgroups)

Result: Attacks blocked Ã¢Å“â€¦ BUT:
- No evidence of compromise
- No alert to security team
- No compliance audit trail
- Attacker tries again with different tool

Impact: Compliance failure, undetected breach, repeat attacks
```

**With This Sub-ADR:**
```
Security Incident (Logged & Alerted):
1. Tool "pdf_converter" (GREEN band) compromised
2. Tool POSTs to attacker.com Ã¢ÂÅ’ (LOGGED to K0 ToolReceipt)
3. Tool reads /home/user/.ssh/id_rsa Ã¢ÂÅ’ (LOGGED)
4. Tool spawns 1000 processes Ã¢ÂÅ’ (LOGGED + ALERT sent)

Audit Trail:
{
  "timestamp": "2025-10-13T14:23:45.123Z",
  "tool_name": "pdf_converter",
  "tool_pid": 12345,
  "violations": [
    {
      "type": "network_egress",
      "attempted_destination": "attacker.com:443",
      "blocked_by": "iptables",
      "severity": "high"
    },
    {
      "type": "filesystem_egress",
      "attempted_path": "/home/user/.ssh/id_rsa",
      "blocked_by": "chroot",
      "severity": "critical"
    },
    {
      "type": "resource_abuse",
      "attempted_pids": 1000,
      "blocked_by": "cgroups",
      "severity": "high"
    }
  ]
}

Result: Security team alerted, tool blacklisted, compliance audit satisfied Ã¢Å“â€¦
```

### System Constraints

1. **Performance Requirements:**
   - Logging overhead: <1ms per violation
   - Batch writes: 100 events/sec
   - K0 forward latency: <10ms

2. **Compliance Requirements:**
   - 7-year retention (ISO27001, SOC2)
   - Tamper-proof logs (append-only)
   - Real-time alerting (<1 second)

3. **Storage:**
   - Violation logs: ~500 bytes/event
   - Estimated 1,000 violations/day = 500KB/day = 180MB/year
   - 7-year retention = 1.3GB total

---

## Decision

### Violation Logging Architecture

**3-Layer Logging System:**
1. **Violation Detector** Ã¢â€ â€™ Captures egress violations in real-time
2. **ToolReceipt Writer** Ã¢â€ â€™ Forwards to K0 audit trail
3. **Alert Manager** Ã¢â€ â€™ Real-time notifications to security team

### Violation Event Schema

```python
# File: k1/security/violation_schema.py

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

class ViolationType(Enum):
    """Types of egress violations"""
    NETWORK_EGRESS = "network_egress"
    FILESYSTEM_EGRESS = "filesystem_egress"
    RESOURCE_ABUSE = "resource_abuse"
    SYSCALL_BLOCKED = "syscall_blocked"

class ViolationSeverity(Enum):
    """Severity levels for violations"""
    LOW = "low"           # Expected behavior (RED band blocked remote)
    MEDIUM = "medium"     # Suspicious (GREEN band blocked private IP)
    HIGH = "high"         # Attack likely (repeated violations)
    CRITICAL = "critical" # Active breach (credential access attempt)

@dataclass
class EgressViolation:
    """
    Egress violation event
    Logged to K0 ToolReceipt for compliance audit
    """
    # Metadata
    timestamp: datetime
    violation_id: str           # UUID
    trace_id: str               # Cognitive trace ID

    # Tool context
    tool_name: str
    tool_pid: int
    tool_band: str              # GREEN/AMBER/RED/BLACK
    session_id: str
    user_id: str

    # Violation details
    violation_type: ViolationType
    severity: ViolationSeverity
    blocked_by: str             # "iptables", "chroot", "seccomp", "cgroups"

    # Type-specific fields
    network_destination: Optional[str] = None      # IP:port or domain
    filesystem_path: Optional[str] = None          # Attempted path
    syscall_name: Optional[str] = None             # Blocked syscall
    resource_type: Optional[str] = None            # "cpu", "memory", "pids", "io"
    resource_attempted: Optional[int] = None       # Attempted value
    resource_limit: Optional[int] = None           # Configured limit

    # Forensics
    process_command: Optional[str] = None          # Full command line
    parent_pid: Optional[int] = None               # Parent process
    environment_vars: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "violation_id": self.violation_id,
            "trace_id": self.trace_id,
            "tool_name": self.tool_name,
            "tool_pid": self.tool_pid,
            "tool_band": self.tool_band,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "blocked_by": self.blocked_by,
            "network_destination": self.network_destination,
            "filesystem_path": self.filesystem_path,
            "syscall_name": self.syscall_name,
            "resource_type": self.resource_type,
            "resource_attempted": self.resource_attempted,
            "resource_limit": self.resource_limit,
            "process_command": self.process_command,
            "parent_pid": self.parent_pid
        }
```

### Violation Detector Integration

```python
# File: k1/security/violation_logger.py

import asyncio
import uuid
from datetime import datetime
from typing import List
from collections import defaultdict

class ViolationLogger:
    """
    Centralized violation logging system
    Integrates with network/filesystem/resource controllers
    """

    def __init__(self, k0_receipt_writer, alert_manager):
        self.k0_writer = k0_receipt_writer
        self.alert_manager = alert_manager

        # Violation tracking (for pattern detection)
        self.violation_counts: Dict[str, int] = defaultdict(int)  # tool_name Ã¢â€ â€™ count
        self.violation_buffer: List[EgressViolation] = []

        # Start background flush
        asyncio.create_task(self._flush_loop())

    async def log_violation(
        self,
        tool_name: str,
        tool_pid: int,
        tool_band: str,
        session_id: str,
        user_id: str,
        violation_type: ViolationType,
        severity: ViolationSeverity,
        blocked_by: str,
        trace_id: str,
        **kwargs  # Type-specific fields
    ):
        """
        Log egress violation (<1ms)
        Buffers events and flushes to K0 in batches
        """
        violation = EgressViolation(
            timestamp=datetime.utcnow(),
            violation_id=str(uuid.uuid4()),
            trace_id=trace_id,
            tool_name=tool_name,
            tool_pid=tool_pid,
            tool_band=tool_band,
            session_id=session_id,
            user_id=user_id,
            violation_type=violation_type,
            severity=severity,
            blocked_by=blocked_by,
            **kwargs
        )

        # Add to buffer
        self.violation_buffer.append(violation)

        # Track violation count
        self.violation_counts[tool_name] += 1

        # Check for repeated violations (attack pattern)
        if self.violation_counts[tool_name] >= 5:
            await self._escalate_to_critical(violation)

        # Log locally
        logger.warning(
            f"Egress violation",
            tool_name=tool_name,
            type=violation_type.value,
            severity=severity.value,
            blocked_by=blocked_by
        )

        # Alert if critical
        if severity == ViolationSeverity.CRITICAL:
            await self.alert_manager.send_alert(violation)

    async def _flush_loop(self):
        """Flush violation buffer to K0 every 100ms"""
        while True:
            await asyncio.sleep(0.1)

            if self.violation_buffer:
                await self._flush_to_k0()

    async def _flush_to_k0(self):
        """Batch write violations to K0 ToolReceipt"""
        if not self.violation_buffer:
            return

        # Take current buffer
        violations = self.violation_buffer[:]
        self.violation_buffer.clear()

        # Write to K0 in batch
        receipts = [
            {
                "type": "egress_violation",
                "data": v.to_dict()
            }
            for v in violations
        ]

        await self.k0_writer.write_receipts_batch(receipts)

        logger.info(f"Flushed {len(violations)} violations to K0")

    async def _escalate_to_critical(self, violation: EgressViolation):
        """Escalate repeated violations to CRITICAL"""
        violation.severity = ViolationSeverity.CRITICAL

        logger.error(
            f"Repeated violations detected (escalating to CRITICAL)",
            tool_name=violation.tool_name,
            count=self.violation_counts[violation.tool_name]
        )

        # Send immediate alert
        await self.alert_manager.send_alert(violation)
```

### ToolReceipt Integration (K0 Audit Trail)

```python
# File: k1/security/k0_receipt_writer.py

import aiohttp
from typing import List, Dict, Any

class K0ReceiptWriter:
    """
    Write egress violations to K0 ToolReceipt system
    Provides tamper-proof audit trail
    """

    def __init__(self, k0_url: str = "http://localhost:9100"):
        self.k0_url = k0_url
        self.session = None

    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def write_receipt(self, receipt: Dict[str, Any]) -> bool:
        """Write single receipt to K0"""
        try:
            async with self.session.post(
                f"{self.k0_url}/receipts",
                json=receipt,
                timeout=aiohttp.ClientTimeout(total=1.0)
            ) as resp:
                if resp.status == 200:
                    return True
                else:
                    logger.error(f"K0 receipt write failed: {resp.status}")
                    return False

        except Exception as e:
            logger.error(f"Failed to write receipt to K0: {e}")
            return False

    async def write_receipts_batch(self, receipts: List[Dict[str, Any]]) -> bool:
        """Write batch of receipts to K0 (<10ms)"""
        try:
            async with self.session.post(
                f"{self.k0_url}/receipts/batch",
                json={"receipts": receipts},
                timeout=aiohttp.ClientTimeout(total=1.0)
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Wrote {len(receipts)} receipts to K0")
                    return True
                else:
                    logger.error(f"K0 batch write failed: {resp.status}")
                    return False

        except Exception as e:
            logger.error(f"Failed to write batch to K0: {e}")
            return False

    async def close(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
```

### Real-Time Alert Manager

```python
# File: k1/security/alert_manager.py

import aiohttp
from datetime import datetime

class AlertManager:
    """
    Send real-time alerts for critical violations
    Integrates with Slack, PagerDuty, email, etc.
    """

    def __init__(self, slack_webhook: str = None, pagerduty_key: str = None):
        self.slack_webhook = slack_webhook
        self.pagerduty_key = pagerduty_key
        self.session = None

    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def send_alert(self, violation: EgressViolation):
        """
        Send real-time alert for critical violation (<1s)
        """
        if violation.severity != ViolationSeverity.CRITICAL:
            return  # Only alert on CRITICAL

        # Send to Slack
        if self.slack_webhook:
            await self._send_slack_alert(violation)

        # Send to PagerDuty
        if self.pagerduty_key:
            await self._send_pagerduty_alert(violation)

        logger.info(f"Alert sent for violation {violation.violation_id}")

    async def _send_slack_alert(self, violation: EgressViolation):
        """Send Slack notification"""
        message = {
            "text": f"Ã°Å¸Å¡Â¨ *CRITICAL SECURITY VIOLATION* Ã°Å¸Å¡Â¨",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Ã°Å¸Å¡Â¨ Critical Egress Violation Detected"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Tool:* {violation.tool_name}"},
                        {"type": "mrkdwn", "text": f"*Band:* {violation.tool_band}"},
                        {"type": "mrkdwn", "text": f"*Type:* {violation.violation_type.value}"},
                        {"type": "mrkdwn", "text": f"*Severity:* {violation.severity.value}"},
                        {"type": "mrkdwn", "text": f"*Blocked By:* {violation.blocked_by}"},
                        {"type": "mrkdwn", "text": f"*Time:* {violation.timestamp.isoformat()}"}
                    ]
                }
            ]
        }

        try:
            async with self.session.post(
                self.slack_webhook,
                json=message,
                timeout=aiohttp.ClientTimeout(total=2.0)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Slack alert failed: {resp.status}")

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    async def _send_pagerduty_alert(self, violation: EgressViolation):
        """Send PagerDuty incident"""
        event = {
            "routing_key": self.pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": f"Critical egress violation: {violation.tool_name}",
                "severity": "critical",
                "source": "K1 Security",
                "timestamp": violation.timestamp.isoformat(),
                "custom_details": violation.to_dict()
            }
        }

        try:
            async with self.session.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=event,
                timeout=aiohttp.ClientTimeout(total=2.0)
            ) as resp:
                if resp.status != 202:
                    logger.error(f"PagerDuty alert failed: {resp.status}")

        except Exception as e:
            logger.error(f"Failed to send PagerDuty alert: {e}")

    async def close(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
```

### Prometheus Metrics

```python
# File: k1/security/violation_metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Violation counters
egress_violations_total = Counter(
    'k1_egress_violations_total',
    'Total egress violations',
    ['tool_name', 'band', 'violation_type', 'severity', 'blocked_by']
)

egress_alerts_sent_total = Counter(
    'k1_egress_alerts_sent_total',
    'Total critical alerts sent',
    ['tool_name', 'band', 'violation_type']
)

# Logging latency
violation_log_latency_ms = Histogram(
    'k1_violation_log_latency_ms',
    'Violation logging latency',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# K0 receipt write latency
k0_receipt_write_latency_ms = Histogram(
    'k1_k0_receipt_write_latency_ms',
    'K0 receipt write latency',
    buckets=[1, 5, 10, 20, 50, 100]
)

# Active violations
active_violations = Gauge(
    'k1_active_violations',
    'Number of violations in buffer',
)
```

---

## Implementation Timeline

### Phase 1: Core Logging (Weeks 1-3)
- **Week 1:** Violation schema and event structure
- **Week 2:** ViolationLogger with buffering
- **Week 3:** K0 ToolReceipt integration

### Phase 2: Alerting (Weeks 4-6)
- **Week 4:** AlertManager with Slack integration
- **Week 5:** PagerDuty integration
- **Week 6:** Pattern detection (repeated violations)

### Phase 3: Integration (Weeks 7-8)
- **Week 7:** Network/Filesystem/Resource controller integration
- **Week 8:** WARD tests + compliance validation

---

## Consequences

### Positive
1. **Compliance-Ready:** SOC2/ISO27001/GDPR audit trail (7-year retention)
2. **Real-Time Detection:** Critical violations alerted within 1 second
3. **Forensics Support:** Full context logged (command, environment, parent)
4. **Attack Pattern Detection:** Repeated violations escalated automatically

### Negative
1. **Storage Overhead:** 1.3GB for 7 years of violations
2. **K0 Dependency:** Requires K0 ToolReceipt system operational
3. **Alert Fatigue:** Risk of too many alerts

### Risks
1. **Log Tampering:** Attacker deletes violation logs
   - Mitigation: K0 append-only receipts, off-system backup
2. **Alert Storm:** Burst of violations floods Slack/PagerDuty
   - Mitigation: Rate limiting, deduplication

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Logging Latency | <1ms | Per-violation log time |
| K0 Forward Latency | <10ms | Batch write to K0 |
| Alert Latency | <1s | CRITICAL alert delivery |
| Compliance Retention | 7 years | Audit log storage |

---

## Related Documents

- [ADR-0032: Band-Based Egress Rules](0032-band-based-egress-rules.md)
- [ADR-0032a: Network Egress Control](0032a-network-egress-control-iptables-privacy-bands.md)
- [ADR-0032b: Filesystem Egress Control](0032b-filesystem-egress-control-chroot-seccomp.md)
- [ADR-0032c: Resource Egress Control](0032c-resource-egress-control-cgroups.md)
- [ADR-0038: ToolReceipt System](0038-tool-receipt-audit-system.md)

---

**Status:** Ã¢Å“â€¦ Ready for implementation
**Timeline:** 8 weeks
**Priority:** Ã¢Â­ÂÃ¢Â­ÂÃ¢Â­Â Critical (Compliance requirement)
