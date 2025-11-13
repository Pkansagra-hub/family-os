---
adr_number: 0031a
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l2_orchestration.budget_enforcer
- k1.l4_runtime.governance
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- usability
date_created: 2025-11-03
date_updated: 2025-11-03
implementation_date: 2025-11-03
implementation_phase: Phase 1 (Foundation)
implementation_status: COMPLETED
parent_adr: ADR-0031
propagation:
  affected_adrs:
  - ADR-0027
  - ADR-0029
  - ADR-0031
  - ADR-0031b
  - ADR-0031c
  - ADR-0031d
  - ADR-0038
  affected_contracts: []
  affected_tests:
  - tests/k1/l2_orchestration/test_budget_enforcer.py
  triggers:
  - Adding new budget hierarchy levels (org/dept/team/user)
  - Modifying budget enforcement policies
  - Changing budget rollover rules
related_adrs:
- ADR-0027
- ADR-0029
- ADR-0031
- ADR-0031b
- ADR-0031c
- ADR-0031d
- ADR-0038
related_contracts: []
related_diagrams: []
research_citations:
- AWS Organizations - Consolidated Billing & Budget Controls
- Google Cloud Resource Hierarchy - Folder/Project Budget Inheritance
- Azure Resource Management - RBAC & Cost Management Scopes
- Corporate IT Governance - Chargeback & Showback Models
status: PROPOSED
superseded_by: []
supersedes: []
title: Hierarchical Budget Enforcement (Corporate Governance)
---

# ADR-0031a: Hierarchical Budget Enforcement (Corporate Governance)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
**Authors:** K1 Architecture Team
**Category:** Corporate Governance & Compliance
**Related ADRs:** ADR-0027 (Model Placement), ADR-0029 (Prometheus Metrics), ADR-0038 (Audit Trail)

---

## Context

### Problem Statement

**In corporate environments using K1 with BYOK (Bring Your Own Key), IT departments need hierarchical budget controls to prevent unauthorized spending on employee-owned LLM provider accounts.**

**Corporate BYOK Model:**
- Users bring their own API keys (OpenAI, Anthropic, Google, etc.)
- K1 runs on corporate infrastructure (not SaaS billing)
- IT sets budget limits per department/team/user
- Finance requires chargeback reports (which department spent what)
- Compliance requires audit trails (who used what, when)

**Without Hierarchical Budget Enforcement:**
```
Corporate Scenario (No Enforcement):
- Engineering department: 50 engineers
- Each engineer has OpenAI API key ($100/month personal limit)
- No K1 budget controls

Day 1:
- Engineer A: 20 sessions × $0.24 = $4.80
- Engineer B: 30 sessions × $0.24 = $7.20
- ... (48 more engineers)
- Total: $2,160/day department spend

Month end:
- Department total: $64,800/month (50 engineers × $1,296/month avg)
- IT budget: $5,000/month ❌
- Overspend: $59,800 (1196% over budget)

Problems:
- No per-user limits (power users drain budget)
- No per-session limits (long sessions expensive)
- No department rollup (finance cannot chargeback)
- No audit trail (compliance violation)
```

**With This Sub-ADR (Hierarchical Enforcement):**
```
Corporate Scenario (With Enforcement):
- Department budget: $5,000/month
- Per-user daily budget: $5/day (50 users × $5 = $250/day = $7,500/month capacity)
- Per-session budget: $0.10/session

Day 1:
- Engineer A: 10 sessions × $0.10 = $1.00 (20% of daily budget)
- Session 11: $0.095 → Warning: "Approaching daily limit"
- Session 12: Blocked, fallback to on-device ✅
- Engineer B: 5 sessions × $0.10 = $0.50 (10% of daily budget)
- Department total: $125/day (50 users avg $2.50/day)

Month end:
- Department total: $3,750/month (50 engineers × $75/month avg)
- IT budget: $5,000/month ✅
- Under budget: $1,250 (25% savings)

Benefits:
- Per-session limits prevent long expensive sessions ✅
- Per-user daily limits prevent power user drain ✅
- Department monthly rollup for finance chargeback ✅
- Audit trail for compliance ✅
```

### System Constraints

1. **Performance Requirements:**
   - Budget check: <1ms per operation (hot path)
   - Budget aggregation: <5ms (session → user → department)
   - Budget override check: <0.5ms (admin/power user bypass)

2. **Hierarchy Levels:**
   - **Level 1 (Session):** $0.10 default per conversation
   - **Level 2 (User Daily):** $5.00 per user per day
   - **Level 3 (Department Monthly):** $5,000 default per department per month

3. **Storage Requirements:**
   - Budget state: 100KB per department (1K users × 100 bytes)
   - Budget history: 10MB/month (audit trail, 90 days retention)

4. **Corporate Use Cases:**
   - **IT Admin:** Set department/team budgets via config
   - **Finance:** Monthly chargeback reports by department
   - **Compliance:** Audit trail of budget overrides
   - **End User:** Transparent budget notifications

---

## Decision

### Hierarchical Budget Structure

**3-Tier Hierarchy: Session → User Daily → Department Monthly**

```
Department Budget (Monthly)
├── Team A Budget (Monthly)
│   ├── User A1 (Daily Budget)
│   │   ├── Session 1 ($0.10 limit)
│   │   ├── Session 2 ($0.10 limit)
│   │   └── Daily Total: $5.00 limit
│   └── User A2 (Daily Budget)
│       └── ... (similar structure)
└── Team B Budget (Monthly)
    └── ... (similar structure)
```

**Budget Configuration Schema (`budgets.yml`):**
```yaml
# Corporate budget hierarchy configuration
hierarchical_budgets:
  # Level 3: Department/Organization (Monthly)
  departments:
    - department_id: "engineering"
      monthly_budget_usd: 5000.00
      alert_thresholds: [0.50, 0.80, 0.95]  # 50%, 80%, 95%
      teams:
        - team_id: "backend"
          monthly_budget_usd: 2000.00
          users: ["user_1", "user_2", "user_3"]
        - team_id: "frontend"
          monthly_budget_usd: 1500.00
          users: ["user_4", "user_5"]

    - department_id: "product"
      monthly_budget_usd: 2000.00
      alert_thresholds: [0.50, 0.80, 0.95]
      users: ["user_10", "user_11"]

  # Level 2: User Daily Budgets (Default + Overrides)
  user_daily_budgets:
    default_usd: 5.00
    alert_thresholds: [0.50, 0.80, 0.95]
    overrides:
      - user_id: "power_user_1"
        daily_budget_usd: 20.00  # Power user exception
        reason: "Research team lead"
        approved_by: "cto@company.com"
      - user_id: "demo_account"
        daily_budget_usd: 1.00  # Demo account lower limit
        reason: "Demo/training account"

  # Level 1: Session Budgets (Default + Per-Intent)
  session_budgets:
    default_usd: 0.10
    alert_thresholds: [0.50, 0.80, 0.95]
    per_intent_overrides:
      - intent: "code_generation"
        budget_usd: 0.25  # Code tasks more expensive
      - intent: "quick_qa"
        budget_usd: 0.05  # Q&A cheaper
```

### Budget Enforcement Logic

**Level 1: Session Budget Check (Per Turn)**
```python
@dataclass
class SessionBudget:
    """Per-session budget tracking"""
    session_id: str
    user_id: str
    budget_usd: float = 0.10  # Default $0.10/session
    spent_usd: float = 0.0
    alert_thresholds: List[float] = field(default_factory=lambda: [0.50, 0.80, 0.95])
    alerts_fired: Set[float] = field(default_factory=set)

    def check_budget(self, cost_usd: float) -> BudgetCheckResult:
        """Check if operation within budget (<1ms)"""
        projected_total = self.spent_usd + cost_usd
        utilization = projected_total / self.budget_usd

        # Hard limit check
        if projected_total > self.budget_usd:
            return BudgetCheckResult(
                allowed=False,
                reason="Session budget exceeded",
                utilization=utilization,
                action="fallback_to_on_device"
            )

        # Threshold alert check
        for threshold in self.alert_thresholds:
            if utilization >= threshold and threshold not in self.alerts_fired:
                self.alerts_fired.add(threshold)
                return BudgetCheckResult(
                    allowed=True,
                    alert=f"{int(threshold*100)}% session budget reached",
                    utilization=utilization,
                    action="notify_user"
                )

        return BudgetCheckResult(allowed=True, utilization=utilization)
```

**Level 2: User Daily Budget Check**
```python
@dataclass
class UserDailyBudget:
    """Per-user daily budget tracking"""
    user_id: str
    daily_budget_usd: float = 5.00  # Default $5/day
    spent_today_usd: float = 0.0
    session_costs: Dict[str, float] = field(default_factory=dict)
    last_reset: datetime = field(default_factory=datetime.now)

    def check_budget(self, session_id: str, cost_usd: float) -> BudgetCheckResult:
        """Check daily budget with session aggregation (<1ms)"""
        # Auto-reset at midnight UTC
        if datetime.now().date() > self.last_reset.date():
            self.reset_daily()

        projected_total = self.spent_today_usd + cost_usd
        utilization = projected_total / self.daily_budget_usd

        if projected_total > self.daily_budget_usd:
            return BudgetCheckResult(
                allowed=False,
                reason="Daily user budget exceeded",
                utilization=utilization,
                action="block_remote_llm_today",
                reset_time=self._next_midnight_utc()
            )

        # Threshold alerts (50%, 80%, 95%)
        return self._check_thresholds(utilization)

    def record_session_cost(self, session_id: str, cost_usd: float):
        """Record session cost for daily aggregation"""
        self.session_costs[session_id] = cost_usd
        self.spent_today_usd = sum(self.session_costs.values())
```

**Level 3: Department Monthly Budget Check**
```python
@dataclass
class DepartmentMonthlyBudget:
    """Per-department monthly budget tracking"""
    department_id: str
    monthly_budget_usd: float = 5000.00
    spent_this_month_usd: float = 0.0
    user_costs: Dict[str, float] = field(default_factory=dict)
    team_costs: Dict[str, float] = field(default_factory=dict)
    last_reset: datetime = field(default_factory=datetime.now)

    def check_budget(self, user_id: str, cost_usd: float) -> BudgetCheckResult:
        """Check department budget with user/team aggregation (<5ms)"""
        # Auto-reset at month start
        if datetime.now().month != self.last_reset.month:
            self.reset_monthly()

        projected_total = self.spent_this_month_usd + cost_usd
        utilization = projected_total / self.monthly_budget_usd

        if projected_total > self.monthly_budget_usd:
            # Department over budget - notify IT admin
            return BudgetCheckResult(
                allowed=False,
                reason="Department monthly budget exceeded",
                utilization=utilization,
                action="notify_it_admin",
                notify_emails=["it-admin@company.com", "cfo@company.com"]
            )

        # Threshold alerts for CFO/CTO
        return self._check_thresholds_with_notifications(utilization)

    def generate_chargeback_report(self) -> ChargebackReport:
        """Generate monthly chargeback report for finance"""
        return ChargebackReport(
            department_id=self.department_id,
            month=datetime.now().strftime("%Y-%m"),
            total_spent_usd=self.spent_this_month_usd,
            budget_usd=self.monthly_budget_usd,
            utilization=self.spent_this_month_usd / self.monthly_budget_usd,
            user_breakdown=self.user_costs,
            team_breakdown=self.team_costs,
            top_spenders=self._get_top_spenders(limit=10),
            cost_by_model=self._get_cost_by_model(),
            cost_by_tool=self._get_cost_by_tool()
        )
```

### Budget Aggregation Flow

**Turn-Level Budget Check (Hot Path <1ms):**
```python
class HierarchicalBudgetEnforcer:
    """3-tier budget enforcement engine"""

    def __init__(self, config: BudgetConfig):
        self.config = config
        self.session_budgets: Dict[str, SessionBudget] = {}
        self.user_daily_budgets: Dict[str, UserDailyBudget] = {}
        self.dept_monthly_budgets: Dict[str, DepartmentMonthlyBudget] = {}

    async def check_before_turn(
        self,
        session_id: str,
        user_id: str,
        dept_id: str,
        estimated_cost_usd: float
    ) -> BudgetCheckResult:
        """
        Check all 3 budget tiers before allowing turn (<1ms)
        Cascade: Session → User Daily → Department Monthly
        """
        # Level 1: Session budget check
        session_budget = self._get_or_create_session_budget(session_id, user_id)
        session_result = session_budget.check_budget(estimated_cost_usd)
        if not session_result.allowed:
            return session_result  # Block at session level

        # Level 2: User daily budget check
        user_budget = self._get_or_create_user_budget(user_id, dept_id)
        user_result = user_budget.check_budget(session_id, estimated_cost_usd)
        if not user_result.allowed:
            return user_result  # Block at user level

        # Level 3: Department monthly budget check (async, soft limit)
        dept_budget = self._get_or_create_dept_budget(dept_id)
        dept_result = dept_budget.check_budget(user_id, estimated_cost_usd)
        if not dept_result.allowed:
            # Department limit is soft - notify but allow (IT can override)
            await self._notify_it_admin(dept_result)
            # Allow operation but log warning
            return BudgetCheckResult(
                allowed=True,
                warning="Department budget exceeded - IT notified",
                utilization=dept_result.utilization
            )

        # All checks passed
        return BudgetCheckResult(allowed=True, utilization=session_result.utilization)

    async def record_actual_cost(
        self,
        session_id: str,
        user_id: str,
        dept_id: str,
        actual_cost_usd: float,
        cost_breakdown: CostBreakdown
    ):
        """
        Record actual cost after turn completes
        Update all 3 tiers + audit trail
        """
        # Level 1: Update session
        session_budget = self.session_budgets[session_id]
        session_budget.spent_usd += actual_cost_usd

        # Level 2: Update user daily
        user_budget = self.user_daily_budgets[user_id]
        user_budget.record_session_cost(session_id, actual_cost_usd)

        # Level 3: Update department monthly
        dept_budget = self.dept_monthly_budgets[dept_id]
        dept_budget.record_user_cost(user_id, actual_cost_usd)

        # Audit trail (ADR-0038 integration)
        await self._write_audit_log(
            session_id=session_id,
            user_id=user_id,
            dept_id=dept_id,
            cost_usd=actual_cost_usd,
            breakdown=cost_breakdown,
            timestamp=datetime.now()
        )
```

### Budget Override System

**Power User / Admin Overrides:**
```python
@dataclass
class BudgetOverride:
    """Admin-approved budget exceptions"""
    user_id: str
    override_type: str  # "daily", "session", "unlimited"
    override_value_usd: Optional[float]  # None = unlimited
    reason: str
    approved_by: str  # Admin email
    valid_until: datetime
    audit_trail: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Check if override still valid"""
        return datetime.now() < self.valid_until

    def apply_to_budget(self, budget: UserDailyBudget) -> UserDailyBudget:
        """Apply override to user budget"""
        if self.override_type == "unlimited":
            budget.daily_budget_usd = float('inf')
        elif self.override_type == "daily":
            budget.daily_budget_usd = self.override_value_usd

        self.audit_trail.append(
            f"Applied at {datetime.now()}: "
            f"User {self.user_id} override {self.override_type} "
            f"by {self.approved_by}"
        )
        return budget

class BudgetOverrideManager:
    """Manage admin-approved budget exceptions"""

    def __init__(self, config: BudgetConfig):
        self.overrides: Dict[str, BudgetOverride] = {}
        self._load_overrides_from_config(config)

    def check_override(self, user_id: str) -> Optional[BudgetOverride]:
        """Check if user has active override"""
        override = self.overrides.get(user_id)
        if override and override.is_valid():
            return override
        return None

    async def request_override(
        self,
        user_id: str,
        requested_by: str,
        reason: str,
        override_type: str,
        override_value_usd: float,
        duration_days: int = 30
    ) -> BudgetOverride:
        """Request budget override (requires admin approval)"""
        override = BudgetOverride(
            user_id=user_id,
            override_type=override_type,
            override_value_usd=override_value_usd,
            reason=reason,
            approved_by="pending",
            valid_until=datetime.now() + timedelta(days=duration_days)
        )

        # Send approval request to IT admin
        await self._send_approval_request(override, requested_by)
        return override
```

---

## Implementation

### Phase 1: Core Budget Tracking (Weeks 1-3)

**Week 1: Session-Level Budget Enforcement**
```python
# File: k1/cost_tracking/session_budget.py

@dataclass
class CostBreakdown:
    """Detailed cost breakdown for audit trail"""
    inference_cost_usd: float = 0.0  # LLM token costs
    tool_cost_usd: float = 0.0       # Tool call costs
    compute_cost_usd: float = 0.0    # Compute placement costs
    model_name: str = ""
    token_count: int = 0
    tool_calls: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

class SessionBudgetTracker:
    """Track per-session costs with budget enforcement"""

    def __init__(self, session_id: str, user_id: str, budget_usd: float = 0.10):
        self.session_id = session_id
        self.user_id = user_id
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.operations: List[CostBreakdown] = []
        self.created_at = datetime.now()

    def record_operation(self, breakdown: CostBreakdown) -> bool:
        """Record operation cost, return True if within budget"""
        total_cost = (
            breakdown.inference_cost_usd +
            breakdown.tool_cost_usd +
            breakdown.compute_cost_usd
        )

        projected_total = self.spent_usd + total_cost
        if projected_total > self.budget_usd:
            logger.warning(
                f"Session {self.session_id} budget exceeded",
                spent=self.spent_usd,
                budget=self.budget_usd,
                attempted=total_cost
            )
            return False

        self.spent_usd = projected_total
        self.operations.append(breakdown)
        return True

    def get_utilization(self) -> float:
        """Get budget utilization percentage"""
        return (self.spent_usd / self.budget_usd) * 100
```

**Week 2: User Daily Budget Aggregation**
```python
# File: k1/cost_tracking/user_daily_budget.py

class UserDailyBudgetTracker:
    """Track per-user daily costs with session aggregation"""

    def __init__(self, user_id: str, daily_budget_usd: float = 5.00):
        self.user_id = user_id
        self.daily_budget_usd = daily_budget_usd
        self.sessions_today: Dict[str, SessionBudgetTracker] = {}
        self.last_reset = datetime.now()

    def add_session(self, session_id: str, session_budget: float = 0.10):
        """Add new session to daily tracking"""
        if self._needs_reset():
            self.reset_daily()

        self.sessions_today[session_id] = SessionBudgetTracker(
            session_id=session_id,
            user_id=self.user_id,
            budget_usd=session_budget
        )

    def get_daily_spent(self) -> float:
        """Aggregate spending across all sessions today"""
        return sum(
            session.spent_usd
            for session in self.sessions_today.values()
        )

    def check_daily_budget(self, additional_cost: float) -> bool:
        """Check if additional cost within daily budget"""
        projected = self.get_daily_spent() + additional_cost
        return projected <= self.daily_budget_usd

    def _needs_reset(self) -> bool:
        """Check if midnight passed (UTC)"""
        return datetime.now().date() > self.last_reset.date()

    def reset_daily(self):
        """Reset at midnight UTC"""
        self.sessions_today.clear()
        self.last_reset = datetime.now()
        logger.info(f"Reset daily budget for user {self.user_id}")
```

**Week 3: Department Monthly Budget Rollup**
```python
# File: k1/cost_tracking/department_monthly_budget.py

class DepartmentMonthlyBudgetTracker:
    """Track per-department monthly costs with user/team rollup"""

    def __init__(self, dept_id: str, monthly_budget_usd: float = 5000.00):
        self.dept_id = dept_id
        self.monthly_budget_usd = monthly_budget_usd
        self.user_budgets: Dict[str, UserDailyBudgetTracker] = {}
        self.team_rollups: Dict[str, float] = {}
        self.last_reset = datetime.now()

    def add_user(self, user_id: str, team_id: str, daily_budget: float = 5.00):
        """Add user to department tracking"""
        self.user_budgets[user_id] = UserDailyBudgetTracker(
            user_id=user_id,
            daily_budget_usd=daily_budget
        )
        self.team_rollups.setdefault(team_id, 0.0)

    def get_monthly_spent(self) -> float:
        """Aggregate all users for month total"""
        return sum(
            user.get_daily_spent()
            for user in self.user_budgets.values()
        )

    def get_team_spent(self, team_id: str) -> float:
        """Get team-level spending"""
        return self.team_rollups.get(team_id, 0.0)

    def generate_monthly_report(self) -> Dict:
        """Generate finance chargeback report"""
        return {
            "department_id": self.dept_id,
            "month": datetime.now().strftime("%Y-%m"),
            "budget_usd": self.monthly_budget_usd,
            "spent_usd": self.get_monthly_spent(),
            "utilization": self.get_monthly_spent() / self.monthly_budget_usd,
            "user_breakdown": {
                user_id: user.get_daily_spent()
                for user_id, user in self.user_budgets.items()
            },
            "team_breakdown": self.team_rollups
        }
```

### Phase 2: Configuration & Overrides (Weeks 4-5)

**Week 4: Budget Configuration System**
```python
# File: k1/cost_tracking/budget_config.py

@dataclass
class BudgetTierConfig:
    """Configuration for single budget tier"""
    default_budget_usd: float
    alert_thresholds: List[float] = field(default_factory=lambda: [0.50, 0.80, 0.95])
    overrides: Dict[str, float] = field(default_factory=dict)

class BudgetConfigManager:
    """Load and manage budget configuration"""

    def __init__(self, config_path: str = "config/budgets.yml"):
        self.config_path = config_path
        self.session_config: BudgetTierConfig = None
        self.daily_config: BudgetTierConfig = None
        self.monthly_config: Dict[str, BudgetTierConfig] = {}
        self._load_config()

    def _load_config(self):
        """Load budget config from YAML"""
        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        # Session tier
        session = config['hierarchical_budgets']['session_budgets']
        self.session_config = BudgetTierConfig(
            default_budget_usd=session['default_usd'],
            alert_thresholds=session['alert_thresholds']
        )

        # Daily tier
        daily = config['hierarchical_budgets']['user_daily_budgets']
        self.daily_config = BudgetTierConfig(
            default_budget_usd=daily['default_usd'],
            alert_thresholds=daily['alert_thresholds'],
            overrides={
                o['user_id']: o['daily_budget_usd']
                for o in daily.get('overrides', [])
            }
        )

        # Monthly tier (per department)
        for dept in config['hierarchical_budgets']['departments']:
            self.monthly_config[dept['department_id']] = BudgetTierConfig(
                default_budget_usd=dept['monthly_budget_usd'],
                alert_thresholds=dept['alert_thresholds']
            )

    def get_user_daily_budget(self, user_id: str) -> float:
        """Get user daily budget (with overrides)"""
        return self.daily_config.overrides.get(
            user_id,
            self.daily_config.default_budget_usd
        )

    def hot_reload(self):
        """Reload config without restart"""
        logger.info("Hot-reloading budget configuration")
        self._load_config()
```

**Week 5: Override Management System**
```python
# File: k1/cost_tracking/budget_overrides.py

class BudgetOverrideManager:
    """Manage admin-approved budget exceptions"""

    def __init__(self, db_path: str = "data/budget_overrides.db"):
        self.db_path = db_path
        self.overrides: Dict[str, BudgetOverride] = {}
        self._load_overrides()

    def create_override(
        self,
        user_id: str,
        override_type: str,
        override_value: float,
        reason: str,
        approved_by: str,
        valid_days: int = 30
    ) -> BudgetOverride:
        """Create new budget override"""
        override = BudgetOverride(
            user_id=user_id,
            override_type=override_type,
            override_value_usd=override_value,
            reason=reason,
            approved_by=approved_by,
            valid_until=datetime.now() + timedelta(days=valid_days),
            audit_trail=[]
        )

        self.overrides[user_id] = override
        self._persist_override(override)

        logger.info(
            f"Budget override created",
            user_id=user_id,
            type=override_type,
            value=override_value,
            approved_by=approved_by
        )

        return override

    def get_active_override(self, user_id: str) -> Optional[BudgetOverride]:
        """Get active override for user"""
        override = self.overrides.get(user_id)
        if override and override.is_valid():
            return override
        return None

    def revoke_override(self, user_id: str, revoked_by: str):
        """Revoke budget override"""
        if user_id in self.overrides:
            del self.overrides[user_id]
            self._delete_override(user_id)
            logger.info(
                f"Budget override revoked",
                user_id=user_id,
                revoked_by=revoked_by
            )
```

### Phase 3: Integration & Testing (Weeks 6-8)

**Week 6: Integration with K1 Orchestrator**
```python
# File: k1/orchestrator/budget_integration.py

class OrchestratorWithBudgetEnforcement:
    """Orchestrator with hierarchical budget checks"""

    def __init__(self, budget_enforcer: HierarchicalBudgetEnforcer):
        self.budget_enforcer = budget_enforcer

    async def coordinate_turn(
        self,
        session: Session,
        user_message: str
    ) -> TurnResult:
        """Coordinate turn with budget enforcement"""

        # Estimate cost before execution
        estimated_cost = self._estimate_turn_cost(session, user_message)

        # Check budget (all 3 tiers)
        budget_check = await self.budget_enforcer.check_before_turn(
            session_id=session.id,
            user_id=session.user_id,
            dept_id=session.department_id,
            estimated_cost_usd=estimated_cost
        )

        if not budget_check.allowed:
            # Budget exceeded - fallback to on-device
            logger.warning(
                f"Budget limit reached, falling back to on-device",
                reason=budget_check.reason,
                utilization=budget_check.utilization
            )
            return await self._execute_with_fallback(session, user_message)

        # Budget OK - execute normally
        result = await self._execute_turn(session, user_message)

        # Record actual cost
        await self.budget_enforcer.record_actual_cost(
            session_id=session.id,
            user_id=session.user_id,
            dept_id=session.department_id,
            actual_cost_usd=result.cost_breakdown.total_usd,
            cost_breakdown=result.cost_breakdown
        )

        return result
```

**Week 7-8: WARD Integration Tests**
```python
# File: tests/cost_tracking/test_hierarchical_budget.py

from ward import test, fixture
import asyncio

@fixture
async def budget_enforcer():
    """Budget enforcer with test config"""
    config = BudgetConfig(
        session_default_usd=0.10,
        daily_default_usd=5.00,
        dept_default_usd=5000.00
    )
    enforcer = HierarchicalBudgetEnforcer(config)
    yield enforcer
    await enforcer.shutdown()

@test("session budget blocks when exceeded")
async def _(enforcer=budget_enforcer):
    """Test session-level budget enforcement"""

    # Create session with $0.10 budget
    session_id = "test_session_1"
    user_id = "test_user_1"
    dept_id = "test_dept"

    # Turn 1: $0.05 (50% budget) - Should pass
    result1 = await enforcer.check_before_turn(
        session_id, user_id, dept_id, estimated_cost_usd=0.05
    )
    assert result1.allowed == True
    assert result1.utilization == 0.50

    # Turn 2: $0.04 (90% budget) - Should pass with warning
    result2 = await enforcer.check_before_turn(
        session_id, user_id, dept_id, estimated_cost_usd=0.04
    )
    assert result2.allowed == True
    assert result2.alert is not None  # 80% threshold alert

    # Turn 3: $0.02 (110% budget) - Should block
    result3 = await enforcer.check_before_turn(
        session_id, user_id, dept_id, estimated_cost_usd=0.02
    )
    assert result3.allowed == False
    assert result3.reason == "Session budget exceeded"
    assert result3.action == "fallback_to_on_device"

@test("daily budget aggregates multiple sessions")
async def _(enforcer=budget_enforcer):
    """Test daily budget with multiple sessions"""

    user_id = "test_user_2"
    dept_id = "test_dept"

    # Session 1: $0.08
    await enforcer.check_before_turn("session_1", user_id, dept_id, 0.08)
    await enforcer.record_actual_cost("session_1", user_id, dept_id, 0.08, None)

    # Session 2: $0.07
    await enforcer.check_before_turn("session_2", user_id, dept_id, 0.07)
    await enforcer.record_actual_cost("session_2", user_id, dept_id, 0.07, None)

    # Session 3: $0.09 (total $0.24, within daily $5.00)
    result = await enforcer.check_before_turn("session_3", user_id, dept_id, 0.09)
    assert result.allowed == True

    # Get daily total
    user_budget = enforcer.user_daily_budgets[user_id]
    assert user_budget.get_daily_spent() == 0.24

@test("department budget generates chargeback report")
async def _(enforcer=budget_enforcer):
    """Test department-level chargeback reporting"""

    dept_id = "engineering"

    # Simulate multiple users
    users = ["user_1", "user_2", "user_3"]
    for user_id in users:
        await enforcer.check_before_turn(
            f"session_{user_id}", user_id, dept_id, estimated_cost_usd=0.10
        )
        await enforcer.record_actual_cost(
            f"session_{user_id}", user_id, dept_id, actual_cost_usd=0.10, cost_breakdown=None
        )

    # Generate chargeback report
    dept_budget = enforcer.dept_monthly_budgets[dept_id]
    report = dept_budget.generate_chargeback_report()

    assert report.total_spent_usd == 0.30
    assert len(report.user_breakdown) == 3
    assert report.utilization < 0.01  # < 1% of $5000 budget
```

---

## Consequences

### Positive

1. **Corporate Governance:** IT can enforce budget limits at department/team/user levels
2. **Audit Trail:** Full visibility into who spent what, when, for compliance
3. **Chargeback Reporting:** Finance can attribute costs to departments accurately
4. **Fair Allocation:** Prevents power users from exhausting shared budgets
5. **Graceful Degradation:** Automatic fallback to on-device keeps UX working
6. **Zero Configuration:** Sensible defaults work out-of-box, overrides for exceptions

### Negative

1. **Configuration Complexity:** 3-tier budget hierarchy requires careful planning
2. **Storage Overhead:** 90-day audit trail requires ~900MB storage
3. **Override Management:** Admin approval workflow adds operational overhead

### Risks

1. **Budget Gaming:** Users might create multiple sessions to bypass limits
   - **Mitigation:** Daily aggregation prevents session splitting

2. **Override Abuse:** Unlimited overrides bypass all controls
   - **Mitigation:** All overrides require admin approval + audit trail

3. **Cost Estimation Errors:** Pre-turn estimation might be inaccurate
   - **Mitigation:** Conservative estimates + post-turn adjustment

---

## Success Metrics

| **Metric** | **Target** | **Measurement** |
|------------|------------|----------------|
| Budget Enforcement Accuracy | >95% adherence | Actual spend vs budget |
| False Positive Rate | <5% | Blocked turns that shouldn't be |
| Performance Impact | <1ms per turn | Budget check latency |
| Chargeback Report Accuracy | 100% | Finance audit validation |
| Override Approval Time | <24 hours | Request to approval time |

---

## Related Documents

- **[ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)** - Parent ADR
- **[ADR-0031b: Cost Model & Pricing Configuration](0031b-cost-model-pricing-configuration.md)** - Pricing calculation
- **[ADR-0031c: Automatic Cost-Based Fallback](0031c-automatic-cost-based-fallback.md)** - Fallback logic
- **[ADR-0031d: Cost Observability & Metrics](0031d-cost-observability-metrics.md)** - Monitoring
- **[ADR-0038: Audit Trail to K0 Receipts](0038-audit-trail-k0-receipts.md)** - Compliance integration

---

**Status:** ✅ Ready for implementation (Corporate BYOK governance model)
**Timeline:** 8 weeks (3 weeks core + 2 weeks config + 3 weeks integration/testing)
**Priority:** ⭐⭐⭐ Critical (Corporate compliance requirement)