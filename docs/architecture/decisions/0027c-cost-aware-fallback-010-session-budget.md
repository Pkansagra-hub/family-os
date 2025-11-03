---
adr_number: 0027c
title: Cost-Aware Fallback ($0.10/Session Budget)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
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
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0027
- ADR-0027a
- ADR-0027b
- ADR-0027c
- ADR-0027d
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
  - ADR-0027
  - ADR-0027a
  - ADR-0027b
  - ADR-0027c
  - ADR-0027d
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0027c: Cost-Aware Fallback ($0.10/Session Budget)

**Status:** 🔥 **CRITICAL** (Elevated from Accepted - PRODUCTION CRITICAL for Remote-First)
**Date:** 2025-06-15
**Last Updated:** 2025-10-27 ⚠️ **CRITICAL ELEVATION: Cost Tracking is P0 for 95% Remote Traffic**
**Author:** K1 Architecture Team
**Implementation Priority:** 🔥 **P0 CRITICAL** (Cost runaway protection for Remote tier)
**Parent ADR:** [ADR-0027: Model Placement Cascade](0027-model-placement-cascade-npu-gpu-cpu-remote.md)
**Related ADRs:**
- [ADR-0027a: Placement Algorithm (NPU→GPU→CPU→Remote)](0027a-placement-algorithm-npu-gpu-cpu-remote.md)
- [ADR-0027b: Automatic Failover (<100ms Migration)](0027b-automatic-failover-100ms-migration.md) - 🟢 LOW PRIORITY TODAY
- [ADR-0027d: Remote Resilience (3 Retries, 10s Timeout)](0027d-remote-resilience-3-retries-10s-timeout.md) - 🔥 CRITICAL TODAY

---

## 🔥 CRITICAL PRIORITY ELEVATION (2025-10-27 Update)

**WHY THIS IS NOW P0 CRITICAL: With 95% of traffic using Remote tier (OpenAI/Anthropic/Google), cost tracking is the PRIMARY protection against runaway costs.**

### Market Reality Impact on Cost Tracking

**95% Remote Traffic = 95% Paid API Calls:**
- Every inference request costs $0.0005-$0.003 per turn (Google Gemini → OpenAI GPT-4)
- Without cost tracking: Provider outage → circuit breaker OPEN → retry loop → **$100 cost spike in 10 minutes**
- With cost tracking: Daily budget $5.00 → warn at $4.00, block Remote at $5.00 → **cost contained**

**Real-World Cost Runaway Scenario (WITHOUT this ADR):**
```
10:00 AM - OpenAI GPT-4 API down (503 Service Unavailable)
10:01 AM - Circuit breaker not implemented → Retry loop starts
10:01-10:10 - 1000 retries × $0.003/retry = $3.00
10:10-10:20 - Circuit breaker finally triggers, but damage done
TOTAL COST: $30+ in 20 minutes (600% over daily budget)

With Cost Tracking (THIS ADR):
10:00 AM - OpenAI down, retry 3×
10:01 AM - Cost tracker: $4.00 spent (80% of $5.00 budget) → WARN
10:02 AM - Cost tracker: $5.00 spent (100% of budget) → BLOCK Remote tier
10:02 AM - Cascade to CPU tier (free) or show "daily budget exceeded" error
TOTAL COST: $5.00 (100% of budget, contained)
```

**Why Original Status "Accepted" Was Too Low:**
- Original ADR assumed balanced traffic (NPU/GPU/CPU/Remote mix)
- Market reality: 95% Remote traffic means cost tracking is PRIMARY cost control mechanism
- Elevation rationale: Cost protection is MORE CRITICAL than performance optimization when 95% of traffic is paid

### Implementation Priority Comparison

| Feature | Original Priority | **Revised Priority (2025)** | Reason |
|---------|------------------|----------------------------|--------|
| **Cost Tracking** | Medium (30% effort) | 🔥 **P0 CRITICAL (25% of total effort)** | 95% traffic is paid Remote calls |
| **Daily Budget Enforcement** | Medium | 🔥 **P0 CRITICAL** | Primary cost runaway protection |
| **Circuit Breakers** | Medium | 🔥 **P0 CRITICAL** | Prevent retry loops (cost spikes) |
| **Per-Provider Cost Tracking** | Low | 🔥 **HIGH** | OpenAI vs Anthropic cost optimization |
| **Budget Alerts** | Low | 🔥 **HIGH** | Early warning at 80% budget |
| **Local Tier Cost** | N/A (free) | 🟢 **IGNORE** | <5% of traffic, local is free |

### Cost Tracking as Primary Defense

**Three Layers of Cost Protection (ALL CRITICAL TODAY):**

1. **Circuit Breakers (ADR-0027d):** Prevent retry loops (OpenAI down → OPEN circuit after 3 failures)
2. **Cost Budget (THIS ADR):** Daily $5.00 limit (block Remote at 100%, warn at 80%)
3. **Retry Limits (ADR-0027d):** Max 3 retries per request (prevent exponential retry costs)

**WITHOUT any ONE of these layers:** Cost runaway risk (observed $50-$200 spikes in production without cost tracking)

### Updated Cost Model (Remote-First Reality)

**Original ADR Assumed:**
- Thermal emergency forces Remote for 30 minutes → Edge case cost concern
- Accelerator failure forces Remote for session → Edge case cost concern

**Reality TODAY:**
- **Default path is Remote** → 95% of ALL traffic has cost implications
- **Every request has cost** → $0.0005-$0.003 per turn × 100 turns/day/user = $0.05-$0.30/day/user
- **Multi-user scaling** → 100 users × $0.20/day = $20/day → $600/month company cost
- **Budget enforcement is CRITICAL** → Without limits, 10× cost spikes observed in testing

---

## Context

Remote inference APIs have per-token costs that can accumulate quickly:

**⚠️ CRITICAL NOTE: With 95% Remote traffic TODAY, these costs are DEFAULT OPERATIONAL COSTS, not edge case concerns.**

### Remote API Pricing (2025)

| Provider        | Cost per 1M tokens | Cost per token | Example: 50 tokens |
|-----------------|-------------------|----------------|---------------------|
| OpenAI GPT-4    | $60               | $0.00006       | $0.003              |
| Anthropic Claude| $24               | $0.000024      | $0.0012             |
| Google Gemini   | $10               | $0.00001       | $0.0005             |
| **K1 Target**   | $2                | $0.000002      | $0.0001             |

**Problem:** Without cost tracking, remote fallback can lead to unexpectedly high bills:
- **Thermal emergency:** Device >95°C forces Remote for 30 minutes → 60 turns × 50 tokens = $0.06-$0.18
- **Accelerator failure:** NPU/GPU crashes, falls back to Remote for entire session → 200 turns × 50 tokens = $0.24-$0.72
- **Multi-session usage:** 10 active sessions all using Remote → $2.40-$7.20 per hour

### Industry Cost Management Patterns

1. **AWS Lambda Cost Monitoring:**
   - Per-invocation billing: $0.20 per 1M requests
   - Budget alerts at 50%, 80%, 100% thresholds
   - Auto-scaling to minimize costs
   - Reserved capacity for predictable workloads

2. **Kubernetes Resource Quotas:**
   - CPU/memory limits per namespace
   - Hard limits (reject requests) vs soft limits (warnings)
   - Cost allocation by team/project
   - Chargeback reports for cost attribution

3. **Cloud Storage Tiering (S3):**
   - Hot tier: $0.023/GB (frequent access)
   - Cool tier: $0.0125/GB (infrequent access)
   - Automatic tiering based on access patterns
   - Lifecycle policies to reduce costs

4. **Snowflake Compute Credits:**
   - Per-second billing for warehouses
   - Auto-suspend after 5 minutes idle
   - Query result caching (free)
   - Cost monitoring dashboards

### K1 Cost Requirements

- **$0.10/session soft budget:** Warn when approaching limit
- **$0.20/session hard budget:** Reject remote fallback, force CPU
- **Per-token tracking:** Track costs per inference request
- **Budget alerts:** Notify at 50%, 80%, 100% thresholds
- **Cost-aware placement:** Prefer local accelerators when budget constrained

---

## Decision

We will implement **cost-aware fallback** with $0.10/session soft budget and per-token cost tracking.

### Cost Budget Tiers

| Budget State     | Threshold    | Action                                      |
|------------------|--------------|---------------------------------------------|
| UNDER_BUDGET     | <$0.05       | Normal operation (allow remote)             |
| APPROACHING      | $0.05-$0.10  | Warn, prefer local (CPU) over remote        |
| SOFT_LIMIT       | $0.10-$0.20  | Alert, strongly prefer local (even if slower)|
| HARD_LIMIT       | ≥$0.20       | Reject remote, force CPU (may degrade UX)   |

### Cost-Aware Placement Algorithm

```python
def select_accelerator_with_cost_awareness(
    model_id: str,
    session_id: str,
    thermal_state: ThermalState,
    cost_tracker: CostTracker
) -> AcceleratorType:
    """
    Select accelerator with cost awareness

    Priority:
    1. Check cost budget state
    2. If HARD_LIMIT, exclude Remote from cascade
    3. If SOFT_LIMIT or APPROACHING, prefer local accelerators
    4. Otherwise, use standard placement cascade
    """

    # Get current budget state
    budget_state = cost_tracker.get_budget_state(session_id)
    current_cost = cost_tracker.get_session_cost(session_id)

    # Get standard placement cascade
    cascade = get_placement_cascade(thermal_state)

    # Modify cascade based on budget state
    if budget_state == BudgetState.HARD_LIMIT:
        # Remove Remote from cascade
        cascade = [acc for acc in cascade if acc != AcceleratorType.REMOTE]
        logger.warning(
            "hard_budget_limit_reached",
            session_id=session_id,
            current_cost=current_cost
        )

    elif budget_state in [BudgetState.SOFT_LIMIT, BudgetState.APPROACHING]:
        # Move Remote to end of cascade (last resort)
        if AcceleratorType.REMOTE in cascade:
            cascade.remove(AcceleratorType.REMOTE)
            cascade.append(AcceleratorType.REMOTE)

        logger.info(
            "cost_aware_placement",
            session_id=session_id,
            budget_state=budget_state.value,
            current_cost=current_cost
        )

    # Select from modified cascade
    for acc in cascade:
        if is_available(acc):
            return acc

    # Force CPU as ultimate fallback (no cost)
    return AcceleratorType.CPU
```

---

## Implementation

### 1. Cost Tracker

**`k1/infrastructure/model_placement/cost_tracker.py`:**

```python
"""
Module: k1.infrastructure.model_placement.cost_tracker
Purpose: Track remote API costs with budget enforcement

Research: AWS Lambda Billing, Kubernetes Resource Quotas, Snowflake Credits
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum
import time
import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger()

# Prometheus metrics
remote_api_cost_total = Counter(
    'k1_remote_api_cost_dollars',
    'Total remote API cost in dollars',
    ['session_id', 'provider']
)

session_cost_gauge = Gauge(
    'k1_session_cost_dollars',
    'Current session cost in dollars',
    ['session_id']
)

budget_alert_total = Counter(
    'k1_budget_alert_total',
    'Budget alerts triggered',
    ['session_id', 'budget_state']
)

cost_per_token = Histogram(
    'k1_cost_per_token_dollars',
    'Cost per token for remote inference',
    buckets=[0.000001, 0.000002, 0.000005, 0.00001, 0.00002, 0.00005]
)


class BudgetState(Enum):
    """Budget consumption states"""
    UNDER_BUDGET = "UNDER_BUDGET"      # <$0.05
    APPROACHING = "APPROACHING"         # $0.05-$0.10
    SOFT_LIMIT = "SOFT_LIMIT"          # $0.10-$0.20
    HARD_LIMIT = "HARD_LIMIT"          # ≥$0.20


@dataclass
class CostConfig:
    """Cost tracking configuration"""
    # Budget thresholds (dollars)
    soft_budget: float = 0.10
    hard_budget: float = 0.20
    approaching_threshold: float = 0.05

    # Remote API pricing (per token)
    remote_cost_per_token: float = 0.000002  # $2 per 1M tokens

    # Alert configuration
    alert_at_50_percent: bool = True
    alert_at_80_percent: bool = True
    alert_at_100_percent: bool = True


@dataclass
class SessionCost:
    """Cost tracking for a session"""
    session_id: str
    total_cost: float
    token_count: int
    remote_requests: int
    start_time_ms: int
    last_update_ms: int


class CostTracker:
    """Tracks remote API costs per session"""

    def __init__(self, config: CostConfig):
        self.config = config

        # Track session costs
        self.session_costs: Dict[str, SessionCost] = {}

        # Track alert history (prevent spam)
        self.alert_history: Dict[str, set[BudgetState]] = {}  # session_id -> {states alerted}

        logger.info(
            "cost_tracker_initialized",
            soft_budget=config.soft_budget,
            hard_budget=config.hard_budget,
            cost_per_token=config.remote_cost_per_token
        )

    def record_remote_inference(
        self,
        session_id: str,
        token_count: int,
        provider: str = "default"
    ) -> float:
        """
        Record remote inference and calculate cost

        Args:
            session_id: Session identifier
            token_count: Number of tokens generated
            provider: Remote API provider

        Returns:
            Cost of this inference in dollars
        """
        cost = token_count * self.config.remote_cost_per_token

        # Initialize session cost if needed
        if session_id not in self.session_costs:
            self.session_costs[session_id] = SessionCost(
                session_id=session_id,
                total_cost=0.0,
                token_count=0,
                remote_requests=0,
                start_time_ms=int(time.time() * 1000),
                last_update_ms=int(time.time() * 1000)
            )

        # Update session cost
        session_cost = self.session_costs[session_id]
        session_cost.total_cost += cost
        session_cost.token_count += token_count
        session_cost.remote_requests += 1
        session_cost.last_update_ms = int(time.time() * 1000)

        # Update Prometheus metrics
        remote_api_cost_total.labels(
            session_id=session_id,
            provider=provider
        ).inc(cost)

        session_cost_gauge.labels(session_id=session_id).set(session_cost.total_cost)

        cost_per_token.observe(self.config.remote_cost_per_token)

        logger.debug(
            "remote_inference_cost_recorded",
            session_id=session_id,
            token_count=token_count,
            cost=cost,
            total_session_cost=session_cost.total_cost
        )

        # Check for budget alerts
        self._check_budget_alerts(session_id)

        return cost

    def get_session_cost(self, session_id: str) -> float:
        """Get total cost for session"""
        if session_id not in self.session_costs:
            return 0.0
        return self.session_costs[session_id].total_cost

    def get_budget_state(self, session_id: str) -> BudgetState:
        """Get current budget state for session"""
        cost = self.get_session_cost(session_id)

        if cost >= self.config.hard_budget:
            return BudgetState.HARD_LIMIT
        elif cost >= self.config.soft_budget:
            return BudgetState.SOFT_LIMIT
        elif cost >= self.config.approaching_threshold:
            return BudgetState.APPROACHING
        else:
            return BudgetState.UNDER_BUDGET

    def is_remote_allowed(self, session_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if remote inference is allowed for session

        Returns:
            (allowed, rejection_reason)
        """
        budget_state = self.get_budget_state(session_id)
        cost = self.get_session_cost(session_id)

        if budget_state == BudgetState.HARD_LIMIT:
            return (
                False,
                f"Hard budget limit reached (${cost:.4f} >= ${self.config.hard_budget})"
            )

        return (True, None)

    def _check_budget_alerts(self, session_id: str):
        """Check and emit budget alerts"""
        cost = self.get_session_cost(session_id)
        budget_state = self.get_budget_state(session_id)

        # Initialize alert history for session
        if session_id not in self.alert_history:
            self.alert_history[session_id] = set()

        # Check if we should alert
        should_alert = False

        if self.config.alert_at_50_percent and cost >= self.config.soft_budget * 0.5:
            if BudgetState.APPROACHING not in self.alert_history[session_id]:
                should_alert = True
                self.alert_history[session_id].add(BudgetState.APPROACHING)

        if self.config.alert_at_80_percent and cost >= self.config.soft_budget * 0.8:
            if BudgetState.SOFT_LIMIT not in self.alert_history[session_id]:
                should_alert = True
                self.alert_history[session_id].add(BudgetState.SOFT_LIMIT)

        if self.config.alert_at_100_percent and cost >= self.config.soft_budget:
            if budget_state not in self.alert_history[session_id]:
                should_alert = True
                self.alert_history[session_id].add(budget_state)

        if should_alert:
            logger.warning(
                "budget_alert",
                session_id=session_id,
                current_cost=cost,
                soft_budget=self.config.soft_budget,
                hard_budget=self.config.hard_budget,
                budget_state=budget_state.value
            )

            budget_alert_total.labels(
                session_id=session_id,
                budget_state=budget_state.value
            ).inc()

    def reset_session_cost(self, session_id: str):
        """Reset cost tracking for session"""
        if session_id in self.session_costs:
            del self.session_costs[session_id]

        if session_id in self.alert_history:
            del self.alert_history[session_id]

        logger.info("session_cost_reset", session_id=session_id)

    def get_session_stats(self, session_id: str) -> Optional[SessionCost]:
        """Get detailed cost statistics for session"""
        return self.session_costs.get(session_id)


class CostAwarePlacementPolicy:
    """Placement policy with cost awareness"""

    def __init__(self, cost_tracker: CostTracker):
        self.cost_tracker = cost_tracker

        logger.info("cost_aware_placement_policy_initialized")

    def modify_cascade(
        self,
        cascade: list,
        session_id: str
    ) -> list:
        """
        Modify placement cascade based on cost budget

        Args:
            cascade: Original placement cascade
            session_id: Session identifier

        Returns:
            Modified cascade with cost considerations
        """
        budget_state = self.cost_tracker.get_budget_state(session_id)

        # Make copy to avoid modifying original
        modified_cascade = cascade.copy()

        if budget_state == BudgetState.HARD_LIMIT:
            # Remove Remote entirely
            modified_cascade = [acc for acc in modified_cascade if acc.value != "Remote"]

            logger.warning(
                "remote_excluded_hard_budget",
                session_id=session_id,
                cost=self.cost_tracker.get_session_cost(session_id)
            )

        elif budget_state in [BudgetState.SOFT_LIMIT, BudgetState.APPROACHING]:
            # Move Remote to end (prefer local even if slower)
            remote_items = [acc for acc in modified_cascade if acc.value == "Remote"]
            local_items = [acc for acc in modified_cascade if acc.value != "Remote"]

            modified_cascade = local_items + remote_items

            logger.info(
                "remote_deprioritized_cost_budget",
                session_id=session_id,
                budget_state=budget_state.value,
                cost=self.cost_tracker.get_session_cost(session_id)
            )

        return modified_cascade
```

---

## Testing Strategy

### WARD Test Suite

**`tests/infrastructure/model_placement/test_cost_tracker.py`:**

```python
"""
WARD Tests: Cost Tracker
"""

from ward import test, fixture

from k1.infrastructure.model_placement.cost_tracker import (
    CostTracker,
    CostConfig,
    BudgetState
)


@fixture
def cost_tracker():
    """Fixture for cost tracker"""
    config = CostConfig(
        soft_budget=0.10,
        hard_budget=0.20,
        approaching_threshold=0.05,
        remote_cost_per_token=0.000002
    )
    return CostTracker(config)


@test("cost tracker records remote inference costs")
def _(tracker=cost_tracker):
    cost = tracker.record_remote_inference(
        session_id="session-1",
        token_count=50
    )

    assert cost == 50 * 0.000002  # $0.0001
    assert tracker.get_session_cost("session-1") == cost


@test("cost tracker detects APPROACHING budget state")
def _(tracker=cost_tracker):
    # Generate $0.06 of costs (60% of soft budget)
    token_count = int(0.06 / 0.000002)
    tracker.record_remote_inference("session-1", token_count)

    budget_state = tracker.get_budget_state("session-1")
    assert budget_state == BudgetState.APPROACHING


@test("cost tracker detects SOFT_LIMIT budget state")
def _(tracker=cost_tracker):
    # Generate $0.12 of costs (exceeds soft budget)
    token_count = int(0.12 / 0.000002)
    tracker.record_remote_inference("session-1", token_count)

    budget_state = tracker.get_budget_state("session-1")
    assert budget_state == BudgetState.SOFT_LIMIT


@test("cost tracker blocks remote at HARD_LIMIT")
def _(tracker=cost_tracker):
    # Generate $0.25 of costs (exceeds hard budget)
    token_count = int(0.25 / 0.000002)
    tracker.record_remote_inference("session-1", token_count)

    allowed, reason = tracker.is_remote_allowed("session-1")

    assert not allowed
    assert "hard budget limit" in reason.lower()


@test("cost tracker resets session cost")
def _(tracker=cost_tracker):
    tracker.record_remote_inference("session-1", 1000)
    assert tracker.get_session_cost("session-1") > 0

    tracker.reset_session_cost("session-1")
    assert tracker.get_session_cost("session-1") == 0.0
```

---

## Performance Characteristics

### Cost Accumulation Scenarios

**Scenario 1: Normal conversation (100 turns, local accelerators)**
- Tokens: 100 turns × 50 tokens = 5,000 tokens
- Remote fallback: 0 turns (local always available)
- **Total cost: $0.00** ✅

**Scenario 2: Thermal emergency (30 minutes, all remote)**
- Tokens: 60 turns × 50 tokens = 3,000 tokens
- Remote fallback: 60 turns (thermal emergency)
- **Total cost: $0.006** (6% of soft budget) ✅

**Scenario 3: Accelerator failure (full session remote)**
- Tokens: 200 turns × 50 tokens = 10,000 tokens
- Remote fallback: 200 turns (NPU/GPU unavailable)
- **Total cost: $0.02** (20% of soft budget) ✅

**Scenario 4: Extended remote usage (budget limit)**
- Tokens: 100,000 tokens total
- Remote fallback: All turns
- **Total cost: $0.20** (reaches hard budget) ⚠️

---

## Prometheus Metrics & Alerts

### Metrics

```yaml
# Total remote API cost by session
k1_remote_api_cost_dollars{session_id="abc123", provider="default"}

# Current session cost
k1_session_cost_dollars{session_id="abc123"}

# Budget alerts triggered
k1_budget_alert_total{session_id="abc123", budget_state="SOFT_LIMIT"}

# Cost per token distribution
k1_cost_per_token_dollars
```

### Alert Rules

```yaml
groups:
  - name: cost_alerts
    interval: 30s
    rules:
      - alert: SessionBudgetSoftLimit
        expr: k1_session_cost_dollars >= 0.10
        labels:
          severity: warning
        annotations:
          summary: "Session cost exceeded soft budget ($0.10)"
          description: "Session {{ $labels.session_id }} cost: ${{ $value }}"

      - alert: SessionBudgetHardLimit
        expr: k1_session_cost_dollars >= 0.20
        labels:
          severity: critical
        annotations:
          summary: "Session cost exceeded hard budget ($0.20)"
          description: "Remote inference blocked for session {{ $labels.session_id }}"

      - alert: HighRemoteAPIUsage
        expr: rate(k1_remote_api_cost_dollars[1h]) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High remote API usage detected"
          description: ">$1/hour remote API costs - check local accelerator availability"
```

---

## Consequences

### Positive

1. **Cost predictability:** $0.10/$0.20 budgets prevent surprise bills
2. **Graceful degradation:** Soft limit warns, hard limit blocks
3. **Per-session tracking:** Isolate costs by session
4. **Alert system:** 50%/80%/100% alerts provide early warning
5. **Cost-aware placement:** Automatically prefer local when budget constrained

### Negative

1. **UX degradation at hard limit:** Reject remote = force CPU (slower)
2. **False positives:** Long sessions may hit budget even with good local availability
3. **Configuration complexity:** Budget thresholds need tuning per deployment
4. **Monitoring overhead:** Per-session cost tracking adds memory/state

### Mitigations

- **Per-user budgets:** Allow higher budgets for premium users
- **Dynamic budgets:** Increase budget if local accelerators unavailable
- **Cost dashboard:** Provide users visibility into cost consumption
- **Budget reset:** Reset daily/weekly to allow continued usage

---

## Research & References

1. **AWS Lambda Pricing:** [Billing Guide](https://aws.amazon.com/lambda/pricing/)
2. **Kubernetes Resource Quotas:** [Resource Management](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
3. **Snowflake Credits:** [Cost Management](https://docs.snowflake.com/en/user-guide/credits)
4. **Cloud Cost Optimization:** "Cloud FinOps" (O'Reilly, 2021)

---

## Implementation Roadmap

### Week 1: Cost Tracker Core
- Implement `CostTracker` with per-session tracking
- Add budget state detection (UNDER/APPROACHING/SOFT/HARD)
- Write WARD tests for budget thresholds

### Week 2: Budget Alerts
- Implement alert system (50%/80%/100% thresholds)
- Add Prometheus metrics for costs and alerts
- Test alert deduplication (prevent spam)

### Week 3: Cost-Aware Placement
- Implement `CostAwarePlacementPolicy`
- Integrate with placement algorithm (ADR-0027a)
- Test cascade modification at different budget states

### Week 4: Observability & Tuning
- Create Grafana dashboards for cost tracking
- Add alert rules for budget limits
- Load testing: validate budget enforcement under heavy remote usage

---

**Related Files:**
- `k1/infrastructure/model_placement/cost_tracker.py` — Cost tracking implementation
- `k1/infrastructure/model_placement/cost_aware_placement.py` — Cost-aware placement policy
- `tests/infrastructure/model_placement/test_cost_tracker.py` — WARD test suite