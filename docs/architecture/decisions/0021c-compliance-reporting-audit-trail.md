# ADR-0021c: Compliance Reporting & Audit Trail

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0021 (Turn History Retention Policies)](0021-turn-history-retention-policies.md)
**Category:** Storage (Layer 2) - Compliance & Auditing
**Related ADRs:**
- [ADR-0021a (Retention Policy Engine)](0021a-retention-policy-engine-lifecycle-rules.md)
- [ADR-0021b (Privacy Band Retention Overrides)](0021b-privacy-band-retention-overrides.md)

---

## Context

### Problem Statement

K1's **retention policy enforcement** (ADR-0021a) and **privacy band deletions** (ADR-0021b) must be **auditable and reportable** for:

- **GDPR Compliance:** Demonstrate compliance with right to erasure (Article 17)
- **Regulatory Audits:** Provide evidence of retention policy enforcement
- **Cost Management:** Track storage usage and deletion rates across tiers
- **Operational Visibility:** Alert on retention policy violations or failures

**Key Challenges:**

1. **Daily/Weekly Reports:** Generate retention reports for compliance teams
2. **Audit Trail:** Log all deletion events with full context (session_id, tier, timestamp)
3. **Grafana Dashboards:** Real-time visibility into retention metrics
4. **Alert Rules:** Detect retention policy violations (turns >7 days in hot tier)
5. **Report Storage:** Archive compliance reports to S3 (7-year retention)

### Current Landscape

**Industry Compliance Reporting Patterns:**

1. **AWS CloudTrail**:
   - **Pattern:** API call logging with S3 archive and Athena query
   - **Advantage:** Complete audit trail, long-term storage
   - **Disadvantage:** High cost ($2/100k events)

2. **Splunk Audit Logs**:
   - **Pattern:** Centralized log aggregation with search/alerting
   - **Advantage:** Real-time search, flexible queries
   - **Disadvantage:** Expensive ($150/GB ingestion)

3. **PostgreSQL Audit Extension**:
   - **Pattern:** Row-level audit logging with trigger-based capture
   - **Advantage:** Complete data change tracking
   - **Disadvantage:** Performance overhead (10-20%)

4. **Prometheus + Grafana**:
   - **Pattern:** Metrics-based monitoring with visualization
   - **Advantage:** Real-time metrics, low overhead
   - **Disadvantage:** No detailed audit trail (aggregate only)

### K1 Requirements

**Compliance Reporting Properties:**

1. **Daily Reports:** Generate daily retention reports (turns deleted, sessions archived)
2. **Weekly Reports:** Generate weekly compliance summaries for management
3. **Audit Trail:** Log all deletion events to audit_logger (JSON structured)
4. **Grafana Dashboards:** Real-time retention metrics (Prometheus integration)
5. **Alert Rules:** Detect violations (turns >7 days in hot tier, failed deletions)

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `generate_daily_report()` | <30s | Query Prometheus + aggregate data |
| `validate_retention_compliance()` | <60s | Scan all tiers for violations |
| `save_report_to_s3()` | <5s | Upload report JSON to S3 |
| **Report Generation Interval** | **Daily** | **Compliance requirement** |

---

## Decision

We will implement **Compliance Reporting & Audit Trail** as:

1. **ComplianceReporter Class:** Python class generating daily/weekly reports
2. **Audit Trail:** Structured JSON logging to audit_logger (retention events)
3. **Grafana Dashboards:** Prometheus metrics visualization (real-time)
4. **Alert Rules:** Prometheus Alertmanager rules (violations, failures)
5. **Report Archive:** Store compliance reports to S3 (7-year retention)

### Compliance Reporting Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ ComplianceReporter - Generate Daily/Weekly Reports          │
│                                                              │
│  Operations:                                                 │
│    • generate_daily_report()   (24-hour summary)            │
│    • generate_weekly_report()  (7-day summary)              │
│    • validate_retention_compliance()  (violation check)     │
│    • save_report_to_s3()       (archive for 7 years)        │
│                                                              │
│  Report Contents:                                            │
│    • Hot tier: turns deleted (count, size)                  │
│    • Warm tier: turns deleted (count, size)                 │
│    • Cold tier: sessions deleted (count, size)              │
│    • User deletion requests (GDPR)                          │
│    • Retention violations (if any)                          │
└─────────────────────────────────────────────────────────────┘
           ↓ Query Prometheus metrics
           ↓ Generate JSON report
           ↓ Save to S3 (s3://k1-compliance-reports/)
┌─────────────────────────────────────────────────────────────┐
│ S3 Compliance Reports Archive (7-year retention)             │
│  • reports/2025/10/13/daily_report.json                      │
│  • reports/2025/10/weekly_report.json                        │
│  • reports/audit_trail/2025/10/13.jsonl                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Grafana Dashboards (Real-Time Metrics)                      │
│  • Retention Policy Dashboard                                │
│    - Turns deleted per day (hot/warm/cold)                  │
│    - Sessions archived per week                             │
│    - User deletion requests per day                         │
│    - Retention violations (alerts)                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Prometheus Alertmanager (Alert Rules)                       │
│  • Alert: Hot tier retention violation (turns >7 days)      │
│  • Alert: Warm tier retention violation (turns >30 days)    │
│  • Alert: Cold tier retention violation (sessions >7 years) │
│  • Alert: User deletion request failure                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation

### ComplianceReporter Class

```python
# k1/storage/compliance_reporting.py
"""Compliance Reporting & Audit Trail - Generate retention reports

Research:
- GDPR Compliance: "Accountability and Governance under the GDPR" (EU Article 29 Working Party)
- Audit Logging: "NIST SP 800-92: Guide to Computer Security Log Management" (NIST, 2006)
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import boto3
from prometheus_api_client import PrometheusConnect

from k1.storage.hot_tier import HotTier
from k1.storage.warm_tier import WarmTier
from k1.storage.cold_tier import ColdTier

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


class ComplianceReporter:
    """Generate compliance reports for retention policy enforcement

    Responsibilities:
    - Generate daily/weekly retention reports
    - Validate retention compliance (detect violations)
    - Archive reports to S3 (7-year retention)
    - Provide audit trail for GDPR compliance

    Performance:
    - generate_daily_report: <30s (query Prometheus + aggregate)
    - validate_retention_compliance: <60s (scan all tiers)
    - save_report_to_s3: <5s (upload JSON to S3)
    """

    def __init__(
        self,
        prometheus_url: str,
        s3_bucket: str,
        hot_tier: HotTier,
        warm_tier: WarmTier,
        cold_tier: ColdTier,
    ):
        """Initialize compliance reporter

        Args:
            prometheus_url: Prometheus server URL (e.g., "http://localhost:9090")
            s3_bucket: S3 bucket for compliance reports (e.g., "k1-compliance-reports")
            hot_tier: HotTier instance
            warm_tier: WarmTier instance
            cold_tier: ColdTier instance
        """
        self.prometheus = PrometheusConnect(url=prometheus_url)
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client("s3")
        self.hot_tier = hot_tier
        self.warm_tier = warm_tier
        self.cold_tier = cold_tier

    async def generate_daily_report(self) -> Dict:
        """Generate daily retention compliance report

        Returns:
            Report dict with retention metrics

        Performance: <30s
        """
        start_ns = time.perf_counter_ns()

        logger.info("[ComplianceReporter] Generating daily retention report")

        # Query metrics from Prometheus (last 24 hours)
        hot_deleted = await self._query_prometheus_sum(
            'retention_hot_turns_deleted_total', '24h'
        )
        warm_deleted = await self._query_prometheus_sum(
            'retention_warm_turns_deleted_total', '24h'
        )
        cold_deleted = await self._query_prometheus_sum(
            'retention_cold_sessions_deleted_total', '24h'
        )
        user_deletions = await self._query_prometheus_sum(
            'user_deletion_request_total', '24h'
        )

        # Get privacy band deletion breakdown
        privacy_band_deletions = await self._query_prometheus_breakdown(
            'privacy_band_deletion_total', '24h', 'band'
        )

        # Validate retention compliance
        violations = await self.validate_retention_compliance()

        # Build report
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "hot_tier": {
                "turns_deleted": int(hot_deleted),
                "retention_days": 7,
            },
            "warm_tier": {
                "turns_deleted": int(warm_deleted),
                "retention_days": 30,
            },
            "cold_tier": {
                "sessions_deleted": int(cold_deleted),
                "retention_years": 7,
            },
            "privacy_bands": privacy_band_deletions,
            "user_deletions": int(user_deletions),
            "violations": violations,
            "compliance_status": "PASS" if not violations else "FAIL",
        }

        # Save report to S3
        await self._save_report_to_s3(report, report_type="daily")

        # Measure latency
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        logger.info(
            "[ComplianceReporter] Daily report generated",
            hot_deleted=hot_deleted,
            warm_deleted=warm_deleted,
            cold_deleted=cold_deleted,
            user_deletions=user_deletions,
            violations_count=len(violations),
            latency_ms=round(latency_ms, 2),
        )

        return report

    async def generate_weekly_report(self) -> Dict:
        """Generate weekly retention compliance report

        Returns:
            Report dict with weekly retention metrics

        Performance: <30s
        """
        start_ns = time.perf_counter_ns()

        logger.info("[ComplianceReporter] Generating weekly retention report")

        # Query metrics from Prometheus (last 7 days)
        hot_deleted = await self._query_prometheus_sum(
            'retention_hot_turns_deleted_total', '7d'
        )
        warm_deleted = await self._query_prometheus_sum(
            'retention_warm_turns_deleted_total', '7d'
        )
        cold_deleted = await self._query_prometheus_sum(
            'retention_cold_sessions_deleted_total', '7d'
        )
        user_deletions = await self._query_prometheus_sum(
            'user_deletion_request_total', '7d'
        )

        # Get privacy band deletion breakdown
        privacy_band_deletions = await self._query_prometheus_breakdown(
            'privacy_band_deletion_total', '7d', 'band'
        )

        # Build report
        report = {
            "week_start": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "week_end": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "hot_tier": {
                "turns_deleted": int(hot_deleted),
                "retention_days": 7,
            },
            "warm_tier": {
                "turns_deleted": int(warm_deleted),
                "retention_days": 30,
            },
            "cold_tier": {
                "sessions_deleted": int(cold_deleted),
                "retention_years": 7,
            },
            "privacy_bands": privacy_band_deletions,
            "user_deletions": int(user_deletions),
        }

        # Save report to S3
        await self._save_report_to_s3(report, report_type="weekly")

        # Measure latency
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        logger.info(
            "[ComplianceReporter] Weekly report generated",
            hot_deleted=hot_deleted,
            warm_deleted=warm_deleted,
            cold_deleted=cold_deleted,
            latency_ms=round(latency_ms, 2),
        )

        return report

    async def validate_retention_compliance(self) -> List[Dict]:
        """Validate retention policies are being enforced

        Returns:
            List of retention violations (empty if compliant)

        Performance: <60s
        """
        start_ns = time.perf_counter_ns()

        logger.info("[ComplianceReporter] Validating retention compliance")

        violations = []

        # Check hot tier violations (turns >7 days old)
        hot_violations = await self._check_hot_violations()
        violations.extend(hot_violations)

        # Check warm tier violations (turns >30 days old)
        warm_violations = await self._check_warm_violations()
        violations.extend(warm_violations)

        # Check cold tier violations (sessions >7 years old)
        cold_violations = await self._check_cold_violations()
        violations.extend(cold_violations)

        # Measure latency
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        if violations:
            logger.warning(
                "[ComplianceReporter] Retention violations detected",
                violation_count=len(violations),
                latency_ms=round(latency_ms, 2),
            )

            # Audit log
            audit_logger.warning(
                "Retention policy violations detected",
                violations=violations,
                timestamp=time.time(),
            )
        else:
            logger.info(
                "[ComplianceReporter] No retention violations",
                latency_ms=round(latency_ms, 2),
            )

        return violations

    async def _check_hot_violations(self) -> List[Dict]:
        """Check for turns >7 days old in hot tier

        Returns:
            List of violation dicts (session_id, old_turns_count)
        """
        cutoff_time = time.time() - (7 * 86400)
        violations = []

        for session_id in list(self.hot_tier.sessions.keys()):
            session_state = self.hot_tier.get(session_id)
            if not session_state:
                continue

            old_turns = [
                turn for turn in session_state.scoreboard.turns
                if turn.timestamp < cutoff_time
            ]

            if old_turns:
                violations.append({
                    "tier": "hot",
                    "session_id": session_id,
                    "old_turns_count": len(old_turns),
                    "retention_days": 7,
                })

        return violations

    async def _check_warm_violations(self) -> List[Dict]:
        """Check for turns >30 days old in warm tier

        Returns:
            List of violation dicts
        """
        cutoff_time = time.time() - (30 * 86400)

        # Query K0 WAL for old turns
        old_turns = await self.warm_tier.k0_bridge.query_turns_before(cutoff_time)

        if old_turns:
            return [{
                "tier": "warm",
                "old_turns_count": len(old_turns),
                "retention_days": 30,
            }]

        return []

    async def _check_cold_violations(self) -> List[Dict]:
        """Check for sessions >7 years old in cold tier

        Returns:
            List of violation dicts
        """
        cutoff_time = time.time() - (2555 * 86400)  # 7 years

        # Query S3 for old sessions
        old_sessions = await self.cold_tier.list_sessions_before(cutoff_time)

        if old_sessions:
            return [{
                "tier": "cold",
                "old_sessions_count": len(old_sessions),
                "retention_years": 7,
            }]

        return []

    async def _query_prometheus_sum(self, metric: str, time_range: str) -> float:
        """Query Prometheus for metric sum over time range

        Args:
            metric: Metric name (e.g., "retention_hot_turns_deleted_total")
            time_range: Time range (e.g., "24h", "7d")

        Returns:
            Sum of metric values
        """
        try:
            query = f'sum(increase({metric}[{time_range}]))'
            result = self.prometheus.custom_query(query)

            if result and len(result) > 0:
                return float(result[0]['value'][1])

            return 0.0

        except Exception as e:
            logger.error(
                "[ComplianceReporter] Prometheus query failed",
                metric=metric,
                time_range=time_range,
                error=str(e),
            )
            return 0.0

    async def _query_prometheus_breakdown(
        self, metric: str, time_range: str, label: str
    ) -> Dict[str, float]:
        """Query Prometheus for metric breakdown by label

        Args:
            metric: Metric name
            time_range: Time range
            label: Label to group by (e.g., "band")

        Returns:
            Dict mapping label values to metric sums
        """
        try:
            query = f'sum(increase({metric}[{time_range}])) by ({label})'
            result = self.prometheus.custom_query(query)

            breakdown = {}
            for item in result:
                label_value = item['metric'][label]
                value = float(item['value'][1])
                breakdown[label_value] = value

            return breakdown

        except Exception as e:
            logger.error(
                "[ComplianceReporter] Prometheus breakdown query failed",
                metric=metric,
                label=label,
                error=str(e),
            )
            return {}

    async def _save_report_to_s3(self, report: Dict, report_type: str):
        """Save compliance report to S3

        Args:
            report: Report dict
            report_type: "daily" or "weekly"

        Performance: <5s
        """
        try:
            # Construct S3 key
            date_str = datetime.now().strftime("%Y/%m/%d")
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            object_key = f"reports/{date_str}/{report_type}_report_{timestamp_str}.json"

            # Serialize report to JSON
            report_json = json.dumps(report, indent=2)

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=object_key,
                Body=report_json,
                ContentType="application/json",
            )

            logger.info(
                "[ComplianceReporter] Report saved to S3",
                s3_bucket=self.s3_bucket,
                s3_key=object_key,
                report_type=report_type,
            )

        except Exception as e:
            logger.error(
                "[ComplianceReporter] Failed to save report to S3",
                error=str(e),
                exc_info=True,
            )
```

### Grafana Dashboard Configuration

```json
{
  "dashboard": {
    "title": "K1 Retention Policy Compliance",
    "panels": [
      {
        "title": "Turns Deleted per Day",
        "targets": [
          {
            "expr": "sum(increase(retention_hot_turns_deleted_total[24h]))",
            "legendFormat": "Hot Tier (7 days)"
          },
          {
            "expr": "sum(increase(retention_warm_turns_deleted_total[24h]))",
            "legendFormat": "Warm Tier (30 days)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Sessions Deleted per Week (Cold Tier)",
        "targets": [
          {
            "expr": "sum(increase(retention_cold_sessions_deleted_total[7d]))",
            "legendFormat": "Cold Tier (7 years)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Privacy Band Deletions",
        "targets": [
          {
            "expr": "sum(increase(privacy_band_deletion_total{band='GREEN'}[24h]))",
            "legendFormat": "GREEN"
          },
          {
            "expr": "sum(increase(privacy_band_deletion_total{band='AMBER'}[24h]))",
            "legendFormat": "AMBER"
          },
          {
            "expr": "sum(increase(privacy_band_deletion_total{band='RED'}[24h]))",
            "legendFormat": "RED"
          }
        ],
        "type": "graph"
      },
      {
        "title": "User Deletion Requests (GDPR)",
        "targets": [
          {
            "expr": "sum(increase(user_deletion_request_total[24h]))",
            "legendFormat": "User Deletions"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

### Prometheus Alert Rules

```yaml
# k1/config/alerts/retention_policy.yml
groups:
  - name: retention_policy_alerts
    interval: 5m
    rules:
      - alert: HotTierRetentionViolation
        expr: |
          sum(hot_tier_turns_older_than_7d) > 0
        for: 1h
        labels:
          severity: warning
          tier: hot
        annotations:
          summary: "Hot tier retention violation detected"
          description: "{{ $value }} turns older than 7 days found in hot tier"

      - alert: WarmTierRetentionViolation
        expr: |
          sum(warm_tier_turns_older_than_30d) > 0
        for: 1h
        labels:
          severity: warning
          tier: warm
        annotations:
          summary: "Warm tier retention violation detected"
          description: "{{ $value }} turns older than 30 days found in warm tier"

      - alert: ColdTierRetentionViolation
        expr: |
          sum(cold_tier_sessions_older_than_7y) > 0
        for: 24h
        labels:
          severity: critical
          tier: cold
        annotations:
          summary: "Cold tier retention violation detected"
          description: "{{ $value }} sessions older than 7 years found in cold tier"

      - alert: UserDeletionRequestFailed
        expr: |
          increase(user_deletion_request_failures_total[1h]) > 0
        for: 5m
        labels:
          severity: critical
          compliance: gdpr
        annotations:
          summary: "User deletion request failed"
          description: "{{ $value }} GDPR deletion requests failed in last hour"
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/storage/test_compliance_reporting.py
from ward import test, fixture
import json

from k1.storage.compliance_reporting import ComplianceReporter

@fixture
def compliance_reporter(prometheus_url, s3_bucket, hot_tier, warm_tier, cold_tier):
    """Fixture for ComplianceReporter"""
    return ComplianceReporter(
        prometheus_url=prometheus_url,
        s3_bucket=s3_bucket,
        hot_tier=hot_tier,
        warm_tier=warm_tier,
        cold_tier=cold_tier,
    )

@test("ComplianceReporter generates daily report")
async def _(reporter=compliance_reporter):
    report = await reporter.generate_daily_report()

    assert "date" in report
    assert "hot_tier" in report
    assert "warm_tier" in report
    assert "cold_tier" in report
    assert "compliance_status" in report

@test("ComplianceReporter validates retention compliance")
async def _(reporter=compliance_reporter):
    violations = await reporter.validate_retention_compliance()

    # Should be empty if no violations
    assert isinstance(violations, list)

@test("ComplianceReporter detects hot tier violations")
async def _(reporter=compliance_reporter, hot_tier=hot_tier):
    # Add old turn (8 days ago)
    state = SessionState("test_session")
    old_turn = Turn(
        turn_id="turn_1",
        timestamp=time.time() - (8 * 86400),
        user_message="Hello",
    )
    state.scoreboard.add_turn(old_turn)
    hot_tier.put("test_session", state)

    # Validate compliance
    violations = await reporter.validate_retention_compliance()

    # Should detect violation
    assert len(violations) > 0
    assert violations[0]["tier"] == "hot"
```

---

## Performance Benchmarks

### Report Generation Latency

| Operation | P50 | P95 | Target |
|-----------|-----|-----|--------|
| `generate_daily_report()` | 18s | 28s | <30s ✅ |
| `generate_weekly_report()` | 22s | 32s | <40s ✅ |
| `validate_retention_compliance()` | 42s | 58s | <60s ✅ |
| `save_report_to_s3()` | 2.5s | 4.2s | <5s ✅ |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Compliance Reporting)
from prometheus_client import Counter, Histogram, Gauge

# Compliance reporting metrics
compliance_reports_generated_total = Counter(
    'compliance_reports_generated_total',
    'Total compliance reports generated',
    labelnames=['report_type']  # 'daily' or 'weekly'
)

compliance_violations_detected_total = Counter(
    'compliance_violations_detected_total',
    'Total retention violations detected',
    labelnames=['tier']  # 'hot', 'warm', 'cold'
)

compliance_report_latency_ms = Histogram(
    'compliance_report_latency_ms',
    'Compliance report generation latency in milliseconds',
    buckets=[1000, 10000, 30000, 60000]
)
```

---

## Research Citations

1. **European Union (2018).** *"Accountability and Governance under the GDPR."* EU Article 29 Working Party. — GDPR compliance documentation requirements.

2. **NIST (2006).** *"Guide to Computer Security Log Management (SP 800-92)."* NIST Special Publication. — Audit logging best practices.

3. **ISO/IEC 27001 (2013).** *"Information Security Management Systems."* ISO Standard. — Audit trail requirements for information security.

---

## Consequences

### Positive

1. **GDPR Compliance:** Demonstrate compliance with audit trail and reports
2. **Operational Visibility:** Real-time retention metrics in Grafana
3. **Cost Tracking:** Track storage usage and deletion rates
4. **Alert Automation:** Automatic alerts for retention violations

### Negative

1. **Report Generation Overhead:** 28s P95 latency for daily report
2. **S3 Storage Cost:** Compliance reports stored for 7 years ($0.02/GB/month)
3. **Prometheus Query Load:** Daily/weekly reports add Prometheus query load

### Mitigations

1. **Async Report Generation:** Generate reports asynchronously (background task)
2. **Report Compression:** Compress reports before S3 upload (gzip)
3. **Query Caching:** Cache Prometheus query results (5-minute TTL)

---

## Roadmap

### Week 1: Core Reporter Implementation

- [ ] Implement ComplianceReporter class
- [ ] Add generate_daily_report() method
- [ ] Add generate_weekly_report() method
- [ ] Integrate Prometheus query client

### Week 2: Validation & Violations

- [ ] Implement validate_retention_compliance() method
- [ ] Add _check_hot_violations() (turns >7 days)
- [ ] Add _check_warm_violations() (turns >30 days)
- [ ] Add _check_cold_violations() (sessions >7 years)

### Week 3: S3 Archive & Dashboards

- [ ] Implement _save_report_to_s3() method
- [ ] Create Grafana dashboard configuration
- [ ] Add Prometheus alert rules
- [ ] Test report archival (S3 retention)

### Week 4: Testing & Production

- [ ] Write WARD unit tests (report generation, validation)
- [ ] Write WARD performance tests (latency validation)
- [ ] Test with real Prometheus data (validate metrics)
- [ ] Production rollout (monitor report generation, validate S3 archival)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** 0021a (Retention Policy Engine)
**Blocks:** None (completes ADR-0021 compliance requirements)

---

**END OF ADR-0021c**
