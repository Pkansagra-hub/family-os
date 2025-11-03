---
adr_number: 0031d
title: Cost Observability & Metrics (Corporate Dashboards)
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
- cost
- observability
- performance
- privacy
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0029
- ADR-0031
- ADR-0031a
- ADR-0031b
- ADR-0031c
- ADR-0031d
- ADR-0038
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
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0029
  - ADR-0031
  - ADR-0031a
  - ADR-0031b
  - ADR-0031c
  - ADR-0031d
  - ADR-0038
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


# ADR-0031d: Cost Observability & Metrics (Corporate Dashboards)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
**Authors:** K1 Architecture Team
**Category:** Corporate Governance & Compliance
**Related ADRs:** ADR-0029 (Prometheus Metrics), ADR-0031a (Budget Enforcement), ADR-0031b (Cost Model), ADR-0038 (Audit Trail)

---

## Context

### Problem Statement

**Corporate IT, finance, and compliance teams need real-time visibility into K1 usage costs for budget monitoring, chargeback reporting, and audit compliance.**

**Corporate BYOK Stakeholders:**
- **IT Admins:** Need real-time budget monitoring, anomaly detection
- **Finance:** Need monthly chargeback reports, cost attribution
- **Compliance:** Need audit trails, usage reports for SOC2/ISO27001
- **Department Managers:** Need team usage visibility, cost optimization insights
- **CTO/CFO:** Need executive dashboards, forecasting, ROI analysis

**Without Cost Observability:**
```
End of Month Chaos:
- Finance: "How much did Engineering spend?"
- IT Admin: "Let me check... I think around $5K?"
- Finance: "Need exact breakdown by team, model, user"
- IT Admin: "We don't track that level of detail"
- Finance: "How do we chargeback to departments?"
- IT Admin: "Manual spreadsheet from user estimates?"
- Compliance: "Where's the audit trail for SOC2?"
- IT Admin: "We don't have that..."

Problems:
- No real-time visibility ❌
- No cost attribution ❌
- No audit trail ❌
- Manual chargeback process ❌
```

**With This Sub-ADR:**
```
Real-Time Observability:
- IT Admin dashboard: Live budget utilization, alerts at 80%
- Finance dashboard: MTD spending by department, forecast Q4
- Compliance portal: Full audit trail, exportable reports
- Manager dashboard: Team usage, cost optimization tips

Benefits:
- Real-time cost monitoring ✅
- Automated chargeback reports ✅
- Compliance-ready audit trails ✅
- Proactive cost optimization ✅
```

### System Constraints

1. **Performance Requirements:**
   - Metrics export: <1ms overhead per operation
   - Dashboard query: <500ms response time
   - Report generation: <10s for monthly reports

2. **Data Retention:**
   - Real-time metrics: 1 hour (Prometheus)
   - Historical metrics: 90 days detailed, 2 years aggregated
   - Audit trail: 7 years (compliance requirement)

3. **Dashboard Requirements:**
   - IT Admin: Real-time monitoring, alerting
   - Finance: Monthly reports, cost attribution
   - Compliance: Audit trails, usage reports
   - Executives: High-level trends, forecasting

---

## Decision

### Metrics Architecture

**3-Layer Observability Stack:**
1. **Prometheus Metrics:** Real-time cost metrics (RED method)
2. **Grafana Dashboards:** Visual monitoring for IT/Finance
3. **Audit Trail Storage:** Compliance-grade immutable logs

### Prometheus Metrics Schema

```python
# File: k1/cost_tracking/metrics_exporter.py

from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

logger = structlog.get_logger()

# Cost Counters (cumulative)
cost_total_usd = Counter(
    'k1_cost_total_usd',
    'Total cost in USD',
    ['department', 'user_id', 'model', 'provider']
)

inference_cost_usd = Counter(
    'k1_inference_cost_usd',
    'LLM inference cost in USD',
    ['department', 'model', 'provider']
)

tool_cost_usd = Counter(
    'k1_tool_cost_usd',
    'Tool call cost in USD',
    ['department', 'tool_name']
)

# Budget Gauges (current state)
budget_utilization = Gauge(
    'k1_budget_utilization_ratio',
    'Budget utilization ratio (0.0-1.0)',
    ['department', 'user_id', 'tier']  # tier: session/daily/monthly
)

budget_remaining_usd = Gauge(
    'k1_budget_remaining_usd',
    'Remaining budget in USD',
    ['department', 'user_id', 'tier']
)

# Cost Histograms (distribution)
cost_per_turn_usd = Histogram(
    'k1_cost_per_turn_usd',
    'Cost per turn distribution',
    ['department', 'model'],
    buckets=[0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]
)

# Fallback Metrics
fallback_events = Counter(
    'k1_fallback_events_total',
    'Fallback events by tier',
    ['department', 'tier', 'from_model', 'to_model']
)

budget_violations = Counter(
    'k1_budget_violations_total',
    'Budget limit violations',
    ['department', 'user_id', 'tier']
)

class CostMetricsExporter:
    """Export cost metrics to Prometheus"""

    def __init__(self):
        self.logger = logger.bind(component="cost_metrics")

    def record_operation_cost(
        self,
        department: str,
        user_id: str,
        model: str,
        provider: str,
        cost_breakdown: dict
    ):
        """Record cost metrics for single operation (<1ms)"""

        # Total cost
        total = cost_breakdown['total_usd']
        cost_total_usd.labels(
            department=department,
            user_id=user_id,
            model=model,
            provider=provider
        ).inc(total)

        # Inference cost
        if cost_breakdown['inference_cost_usd'] > 0:
            inference_cost_usd.labels(
                department=department,
                model=model,
                provider=provider
            ).inc(cost_breakdown['inference_cost_usd'])

        # Tool costs
        for tool_name, tool_cost in cost_breakdown.get('tool_costs', {}).items():
            tool_cost_usd.labels(
                department=department,
                tool_name=tool_name
            ).inc(tool_cost)

        # Per-turn cost distribution
        cost_per_turn_usd.labels(
            department=department,
            model=model
        ).observe(total)

    def update_budget_metrics(
        self,
        department: str,
        user_id: str,
        tier: str,  # "session", "daily", "monthly"
        utilized: float,
        remaining: float
    ):
        """Update budget utilization metrics"""

        budget_utilization.labels(
            department=department,
            user_id=user_id,
            tier=tier
        ).set(utilized)

        budget_remaining_usd.labels(
            department=department,
            user_id=user_id,
            tier=tier
        ).set(remaining)

    def record_fallback_event(
        self,
        department: str,
        tier: str,
        from_model: str,
        to_model: str
    ):
        """Record cost-based fallback event"""

        fallback_events.labels(
            department=department,
            tier=tier,
            from_model=from_model,
            to_model=to_model
        ).inc()

    def record_budget_violation(
        self,
        department: str,
        user_id: str,
        tier: str
    ):
        """Record budget limit violation"""

        budget_violations.labels(
            department=department,
            user_id=user_id,
            tier=tier
        ).inc()
```

### Grafana Dashboard Configurations

**Dashboard 1: IT Admin - Real-Time Monitoring**
```json
{
  "dashboard": {
    "title": "K1 Cost Monitoring - IT Admin",
    "panels": [
      {
        "title": "Department Budget Utilization",
        "type": "gauge",
        "targets": [{
          "expr": "avg(k1_budget_utilization_ratio{tier=\"monthly\"}) by (department)"
        }],
        "thresholds": [
          {"value": 0.50, "color": "green"},
          {"value": 0.80, "color": "yellow"},
          {"value": 0.95, "color": "red"}
        ]
      },
      {
        "title": "Real-Time Spending Rate ($/hour)",
        "type": "graph",
        "targets": [{
          "expr": "rate(k1_cost_total_usd[1h]) by (department)"
        }]
      },
      {
        "title": "Top 10 Users by Spending",
        "type": "table",
        "targets": [{
          "expr": "topk(10, sum(k1_cost_total_usd) by (user_id, department))"
        }]
      },
      {
        "title": "Budget Violations (Last 24h)",
        "type": "stat",
        "targets": [{
          "expr": "sum(increase(k1_budget_violations_total[24h]))"
        }],
        "alert": {
          "condition": "> 5",
          "notification": "it-admin@company.com"
        }
      },
      {
        "title": "Fallback Events by Tier",
        "type": "pie",
        "targets": [{
          "expr": "sum(k1_fallback_events_total) by (tier)"
        }]
      }
    ]
  }
}
```

**Dashboard 2: Finance - Chargeback Reports**
```json
{
  "dashboard": {
    "title": "K1 Cost Analytics - Finance",
    "panels": [
      {
        "title": "Monthly Spending by Department",
        "type": "bar",
        "targets": [{
          "expr": "sum(k1_cost_total_usd) by (department)"
        }]
      },
      {
        "title": "Cost Breakdown by Model",
        "type": "pie",
        "targets": [{
          "expr": "sum(k1_inference_cost_usd) by (model)"
        }]
      },
      {
        "title": "Cost Trend (Last 90 Days)",
        "type": "graph",
        "targets": [{
          "expr": "sum(increase(k1_cost_total_usd[1d])) by (department)"
        }]
      },
      {
        "title": "Projected Monthly Total",
        "type": "stat",
        "targets": [{
          "expr": "sum(k1_cost_total_usd) * (30 / day_of_month())"
        }]
      },
      {
        "title": "Cost Attribution by Project",
        "type": "table",
        "targets": [{
          "expr": "sum(k1_cost_total_usd) by (project_tag, department)"
        }]
      }
    ]
  }
}
```

**Dashboard 3: Executive - High-Level Overview**
```json
{
  "dashboard": {
    "title": "K1 Executive Dashboard",
    "panels": [
      {
        "title": "Total Monthly Spending",
        "type": "stat",
        "targets": [{
          "expr": "sum(k1_cost_total_usd)"
        }],
        "format": "currency"
      },
      {
        "title": "Budget Adherence",
        "type": "gauge",
        "targets": [{
          "expr": "sum(k1_budget_utilization_ratio{tier=\"monthly\"}) / count(k1_budget_utilization_ratio{tier=\"monthly\"})"
        }]
      },
      {
        "title": "Cost Optimization Savings",
        "type": "stat",
        "targets": [{
          "expr": "sum(k1_fallback_savings_usd)"
        }],
        "format": "currency"
      },
      {
        "title": "Spending Trend",
        "type": "graph",
        "targets": [{
          "expr": "sum(increase(k1_cost_total_usd[1d]))"
        }],
        "timeRange": "90d"
      }
    ]
  }
}
```

### Audit Trail Storage

```python
# File: k1/cost_tracking/audit_trail.py

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List
import json

@dataclass
class CostAuditEntry:
    """Immutable audit trail entry for compliance"""

    # Identifiers
    audit_id: str
    timestamp: datetime

    # User/Department
    user_id: str
    department_id: str
    session_id: str

    # Operation Details
    operation_type: str  # "inference", "tool_call", "budget_override"
    model_name: str
    provider: str

    # Cost Details
    cost_usd: float
    cost_breakdown: Dict

    # Budget Context
    budget_tier: str
    budget_utilization_before: float
    budget_utilization_after: float

    # Compliance Fields
    purpose: str  # "business", "research", "demo"
    project_tag: str
    data_classification: str  # "GREEN", "AMBER", "RED"

    # Audit Trail
    created_by: str
    approved_by: str = ""
    override_reason: str = ""

class AuditTrailManager:
    """Compliance-grade audit trail storage"""

    def __init__(self, storage_path: str = "data/audit_trail"):
        self.storage_path = storage_path
        self.entries: List[CostAuditEntry] = []

    async def log_cost_operation(
        self,
        user_id: str,
        department_id: str,
        session_id: str,
        cost_breakdown: Dict,
        budget_context: Dict
    ):
        """
        Log cost operation to immutable audit trail
        Required for SOC2, ISO27001 compliance
        """
        entry = CostAuditEntry(
            audit_id=self._generate_audit_id(),
            timestamp=datetime.now(),
            user_id=user_id,
            department_id=department_id,
            session_id=session_id,
            operation_type="inference",
            model_name=cost_breakdown['model_name'],
            provider=cost_breakdown['provider'],
            cost_usd=cost_breakdown['total_usd'],
            cost_breakdown=cost_breakdown,
            budget_tier=budget_context['tier'],
            budget_utilization_before=budget_context['before'],
            budget_utilization_after=budget_context['after'],
            purpose=budget_context.get('purpose', 'business'),
            project_tag=budget_context.get('project_tag', 'untagged'),
            data_classification=budget_context.get('classification', 'GREEN'),
            created_by=user_id
        )

        # Write to append-only log (immutable)
        await self._append_to_log(entry)

        # Update in-memory cache
        self.entries.append(entry)

    async def generate_compliance_report(
        self,
        start_date: datetime,
        end_date: datetime,
        department_id: str
    ) -> Dict:
        """
        Generate compliance audit report
        Suitable for SOC2, ISO27001 auditors
        """
        # Query entries
        entries = [
            e for e in self.entries
            if e.department_id == department_id
            and start_date <= e.timestamp <= end_date
        ]

        return {
            "report_type": "cost_audit_trail",
            "department": department_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_operations": len(entries),
            "total_cost_usd": sum(e.cost_usd for e in entries),
            "operations_by_user": self._group_by(entries, 'user_id'),
            "operations_by_model": self._group_by(entries, 'model_name'),
            "operations_by_classification": self._group_by(entries, 'data_classification'),
            "budget_violations": [
                e for e in entries
                if e.budget_utilization_after > 1.0
            ],
            "overrides": [
                e for e in entries
                if e.override_reason
            ],
            "audit_trail_integrity": "verified",  # Cryptographic hash validation
            "generated_at": datetime.now().isoformat()
        }
```

### Cost API Endpoints

```python
# File: k1/api/cost_endpoints.py

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter(prefix="/k1/costs", tags=["costs"])

@router.get("/session/{session_id}")
async def get_session_costs(session_id: str):
    """Get cost breakdown for specific session"""
    session_costs = await cost_tracker.get_session_costs(session_id)
    return {
        "session_id": session_id,
        "total_cost_usd": session_costs.total_usd,
        "breakdown": session_costs.to_dict(),
        "budget_utilization": session_costs.budget_utilization
    }

@router.get("/user/{user_id}/daily")
async def get_user_daily_costs(user_id: str, date: Optional[str] = None):
    """Get user's daily cost summary"""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    daily_costs = await cost_tracker.get_user_daily_costs(user_id, target_date)
    return {
        "user_id": user_id,
        "date": target_date,
        "total_cost_usd": daily_costs.total_usd,
        "budget_usd": daily_costs.budget_usd,
        "utilization": daily_costs.utilization,
        "sessions": daily_costs.sessions
    }

@router.get("/department/{dept_id}/monthly")
async def get_department_monthly_costs(dept_id: str, month: Optional[str] = None):
    """Get department's monthly chargeback report"""
    target_month = month or datetime.now().strftime("%Y-%m")
    report = await cost_tracker.get_department_monthly_report(dept_id, target_month)
    return report.to_dict()

@router.get("/department/{dept_id}/forecast")
async def get_cost_forecast(dept_id: str, horizon_days: int = 30):
    """Get cost forecast for department"""
    forecast = await cost_forecaster.predict(dept_id, horizon_days)
    return {
        "department_id": dept_id,
        "forecast_horizon_days": horizon_days,
        "predicted_cost_usd": forecast.predicted_total,
        "confidence_interval": forecast.confidence_interval,
        "trend": forecast.trend
    }
```

---

## Implementation Timeline

### Phase 1: Metrics Export (Weeks 1-3)
- **Week 1:** Prometheus metrics schema
- **Week 2:** Metrics exporter integration
- **Week 3:** Metrics validation

### Phase 2: Dashboards (Weeks 4-6)
- **Week 4:** IT Admin dashboard (Grafana)
- **Week 5:** Finance dashboard (Grafana)
- **Week 6:** Executive dashboard

### Phase 3: Audit & API (Weeks 7-8)
- **Week 7:** Audit trail storage + compliance reports
- **Week 8:** Cost API endpoints + WARD tests

---

## Consequences

### Positive
1. **Real-Time Visibility:** IT monitors spending live
2. **Automated Chargeback:** Finance gets accurate reports
3. **Compliance Ready:** Audit trails for SOC2/ISO27001
4. **Proactive Optimization:** Identify cost-saving opportunities

### Negative
1. **Storage Overhead:** 7-year audit trail requires significant storage
2. **Dashboard Maintenance:** Grafana dashboards need periodic updates
3. **Query Performance:** Large audit trail queries can be slow

### Risks
1. **Metric Explosion:** Too many labels cause Prometheus performance issues
   - Mitigation: Limit cardinality, aggregate at query time
2. **Audit Trail Gaps:** Log failures cause compliance violations
   - Mitigation: Redundant storage, integrity validation

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Dashboard Load Time | <500ms | Grafana query latency |
| Audit Trail Completeness | 100% | No missing entries |
| Chargeback Accuracy | 100% | Finance validation |
| Cost Anomaly Detection | <1 hour | Alert to detection time |

---

## Related Documents

- [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
- [ADR-0031a: Hierarchical Budget Enforcement](0031a-hierarchical-budget-enforcement-corporate-governance.md)
- [ADR-0031b: Cost Model & Pricing](0031b-cost-model-pricing-configuration.md)
- [ADR-0031c: Automatic Fallback](0031c-automatic-cost-based-fallback.md)
- [ADR-0029: Prometheus Metrics RED Method](0029-prometheus-metrics-red-method.md)
- [ADR-0038: Audit Trail to K0 Receipts](0038-audit-trail-k0-receipts.md)

---

**Status:** ✅ Ready for implementation
**Timeline:** 8 weeks
**Priority:** ⭐⭐⭐ Critical (Corporate compliance + finance requirement)