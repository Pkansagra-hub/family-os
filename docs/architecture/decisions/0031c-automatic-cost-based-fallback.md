# ADR-0031c: Automatic Cost-Based Fallback (Graceful Degradation)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
**Authors:** K1 Architecture Team
**Category:** Corporate Governance & Compliance
**Related ADRs:** ADR-0027 (Model Placement Cascade), ADR-0031a (Budget Enforcement), ADR-0031b (Cost Model)

---

## Context

### Problem Statement

**When corporate users approach budget limits, the system needs to automatically switch to cost-effective alternatives WITHOUT breaking the user experience.**

**Corporate BYOK Scenario:**
- User has $5/day budget from IT
- Currently at $4.80 spent (96% of budget)
- Next query estimated at $0.30
- Without fallback: Query blocked, user frustrated ❌
- With fallback: Switch to local model, user continues working ✅

**Without Automatic Fallback:**
```
User Experience (Hard Budget Limit):
9:00 AM - User starts session with GPT-4o ($0.015/turn)
10:00 AM - $2.50 spent (50% of daily budget) - No warning
11:00 AM - $4.00 spent (80% of daily budget) - No warning
11:30 AM - $4.95 spent (99% of daily budget)
11:31 AM - User: "Help me write this function"
           System: ❌ "Daily budget exceeded. Try again tomorrow."
           User: 😡 "I can't work until tomorrow?!"

Problems:
- Hard cutoff breaks workflow
- User loses productivity
- No warning before limit
- Bad user experience
```

**With This Sub-ADR:**
```
User Experience (Graceful Fallback):
9:00 AM - User starts session with GPT-4o ($0.015/turn)
10:00 AM - $2.50 spent (50% of daily budget)
11:00 AM - $4.00 spent (80% of daily budget)
           ⚠️ Warning: "80% budget reached. Switching to local models soon."
11:30 AM - $4.85 spent (97% of daily budget)
11:31 AM - User: "Help me write this function"
           System: ✅ Automatically switches to Gemma-2-9B (local)
           Response generated, cost: $0.0001 (vs $0.015)
           User: 😊 Continues working without interruption

Benefits:
- No hard cutoff - continuous workflow ✅
- Proactive warnings at 80% threshold ✅
- Automatic fallback to cost-effective models ✅
- User stays productive ✅
```

### System Constraints

1. **Performance Requirements:**
   - Fallback decision: <5ms (check threshold + select model)
   - Model switch latency: <500ms (load local model if needed)
   - User notification: <100ms (display warning)

2. **Fallback Tiers:**
   - **Tier 1 (50-80%):** Warning only, continue remote
   - **Tier 2 (80-95%):** Automatic switch to cheaper remote (GPT-4o-mini)
   - **Tier 3 (95-100%):** Switch to local models (Gemma-2-9B, Phi-3)
   - **Tier 4 (100%+):** Block expensive tools, local-only mode

3. **Quality Requirements:**
   - Local models must handle 80% of tasks adequately
   - Critical tasks can override (with admin approval)
   - User can manually select models (within budget)

---

## Decision

### Fallback Strategy Architecture

**4-Tier Progressive Fallback:**

```python
# File: k1/cost_tracking/fallback_strategy.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional

class FallbackTier(Enum):
    """Progressive fallback tiers based on budget utilization"""
    NORMAL = "normal"              # 0-50%: Normal operation
    WARNING = "warning"            # 50-80%: Warning, continue
    COST_OPTIMIZED = "optimized"   # 80-95%: Cheaper remote models
    LOCAL_ONLY = "local"           # 95-100%: Local models only
    BLOCKED = "blocked"            # 100%+: Block expensive operations

@dataclass
class FallbackDecision:
    """Fallback decision result"""
    tier: FallbackTier
    model_to_use: str
    reason: str
    user_notification: Optional[str] = None
    estimated_cost: float = 0.0

class CostBasedFallbackStrategy:
    """
    Automatic fallback based on budget utilization
    Integrates with ADR-0027 PlacementCascade
    """

    def __init__(
        self,
        budget_enforcer,
        model_router,
        config: dict
    ):
        self.budget_enforcer = budget_enforcer
        self.model_router = model_router
        self.config = config
        self.tier_thresholds = {
            FallbackTier.NORMAL: 0.50,
            FallbackTier.WARNING: 0.80,
            FallbackTier.COST_OPTIMIZED: 0.95,
            FallbackTier.LOCAL_ONLY: 0.98,
            FallbackTier.BLOCKED: 1.00
        }

    async def decide_fallback(
        self,
        session_id: str,
        user_id: str,
        requested_model: str,
        intent: str
    ) -> FallbackDecision:
        """
        Decide fallback strategy based on budget utilization (<5ms)
        """
        # Get current budget utilization
        utilization = await self.budget_enforcer.get_utilization(
            session_id, user_id
        )

        # Determine tier
        tier = self._get_fallback_tier(utilization)

        if tier == FallbackTier.NORMAL:
            # Normal operation - use requested model
            return FallbackDecision(
                tier=tier,
                model_to_use=requested_model,
                reason="Budget OK, using requested model"
            )

        elif tier == FallbackTier.WARNING:
            # Warning - continue but notify user
            return FallbackDecision(
                tier=tier,
                model_to_use=requested_model,
                reason="Approaching budget limit",
                user_notification=(
                    f"⚠️ You've used {utilization*100:.0f}% of your daily budget. "
                    f"We'll switch to cost-effective models soon."
                )
            )

        elif tier == FallbackTier.COST_OPTIMIZED:
            # Switch to cheaper remote model
            cheaper_model = self._get_cheaper_alternative(requested_model)
            return FallbackDecision(
                tier=tier,
                model_to_use=cheaper_model,
                reason="Budget optimization - using cheaper model",
                user_notification=(
                    f"💰 Switched to {cheaper_model} to stay within budget. "
                    f"Quality remains high for most tasks."
                )
            )

        elif tier == FallbackTier.LOCAL_ONLY:
            # Switch to local models
            local_model = self._get_local_model_for_intent(intent)
            return FallbackDecision(
                tier=tier,
                model_to_use=local_model,
                reason="Budget limit reached - using local model",
                user_notification=(
                    f"🏠 Switched to local {local_model} to preserve budget. "
                    f"Resets tomorrow at midnight."
                )
            )

        else:  # BLOCKED
            # Block expensive operations
            return FallbackDecision(
                tier=tier,
                model_to_use="blocked",
                reason="Budget exhausted - contact IT for override",
                user_notification=(
                    "❌ Daily budget exhausted. Using local models only. "
                    "Contact IT admin for budget extension if needed."
                )
            )

    def _get_fallback_tier(self, utilization: float) -> FallbackTier:
        """Determine fallback tier based on utilization"""
        if utilization < 0.50:
            return FallbackTier.NORMAL
        elif utilization < 0.80:
            return FallbackTier.WARNING
        elif utilization < 0.95:
            return FallbackTier.COST_OPTIMIZED
        elif utilization < 1.00:
            return FallbackTier.LOCAL_ONLY
        else:
            return FallbackTier.BLOCKED

    def _get_cheaper_alternative(self, requested_model: str) -> str:
        """Get cheaper alternative model"""
        alternatives = {
            "gpt-4o": "gpt-4o-mini",       # 97% cheaper
            "claude-3-5-sonnet": "claude-3-haiku",  # 90% cheaper
            "gemini-1.5-pro": "gemini-1.5-flash"    # 80% cheaper
        }
        return alternatives.get(requested_model, "gpt-4o-mini")

    def _get_local_model_for_intent(self, intent: str) -> str:
        """Select best local model for intent"""
        intent_models = {
            "code_generation": "gemma-2-9b",    # Best code model
            "qa": "phi-3-mini",                  # Fast Q&A
            "summarization": "gemma-2-9b",       # Good comprehension
            "general": "gemma-2-9b"              # Default
        }
        return intent_models.get(intent, "gemma-2-9b")
```

### Integration with Orchestrator

```python
# File: k1/orchestrator/budget_aware_coordinator.py

class BudgetAwareOrchestrator:
    """Orchestrator with automatic cost-based fallback"""

    def __init__(
        self,
        fallback_strategy: CostBasedFallbackStrategy,
        model_hub,
        tool_runner
    ):
        self.fallback = fallback_strategy
        self.model_hub = model_hub
        self.tool_runner = tool_runner

    async def coordinate_turn(
        self,
        session: Session,
        user_message: str,
        intent: str
    ) -> TurnResult:
        """
        Coordinate turn with automatic fallback
        """
        # Check budget and decide fallback
        fallback_decision = await self.fallback.decide_fallback(
            session_id=session.id,
            user_id=session.user_id,
            requested_model=session.preferred_model,
            intent=intent
        )

        # Notify user if needed
        if fallback_decision.user_notification:
            await self._send_user_notification(
                session.id,
                fallback_decision.user_notification
            )

        # Check if blocked
        if fallback_decision.tier == FallbackTier.BLOCKED:
            return TurnResult(
                status="budget_exceeded",
                message=fallback_decision.user_notification,
                cost_usd=0.0
            )

        # Execute with selected model
        result = await self._execute_with_model(
            session=session,
            message=user_message,
            model=fallback_decision.model_to_use,
            intent=intent
        )

        # Log fallback decision
        logger.info(
            f"Turn completed with fallback",
            tier=fallback_decision.tier.value,
            model=fallback_decision.model_to_use,
            cost_usd=result.cost_usd
        )

        return result

    async def _execute_with_model(
        self,
        session: Session,
        message: str,
        model: str,
        intent: str
    ) -> TurnResult:
        """Execute turn with specified model"""

        # Route to model
        if model.startswith("gpt") or model.startswith("claude"):
            # Remote inference
            response = await self.model_hub.infer_remote(
                model=model,
                messages=session.history + [{"role": "user", "content": message}]
            )
        else:
            # Local inference
            response = await self.model_hub.infer_local(
                model=model,
                messages=session.history + [{"role": "user", "content": message}]
            )

        return TurnResult(
            status="success",
            response=response.text,
            model_used=model,
            cost_usd=response.cost_usd
        )
```

### Fallback Configuration

```yaml
# File: k1/config/fallback_strategy.yml

fallback_strategy:
  # Tier thresholds
  thresholds:
    warning: 0.50    # 50% - start warning
    optimized: 0.80  # 80% - switch to cheaper
    local: 0.95      # 95% - switch to local
    blocked: 1.00    # 100% - block expensive

  # Model alternatives (cheaper options)
  cheaper_alternatives:
    gpt-4o: gpt-4o-mini           # 97% cost reduction
    claude-3-5-sonnet: claude-3-haiku  # 90% cost reduction
    gemini-1.5-pro: gemini-1.5-flash   # 80% cost reduction

  # Local model selection (by intent)
  local_models:
    code_generation: gemma-2-9b
    qa: phi-3-mini
    summarization: gemma-2-9b
    general: gemma-2-9b
    creative_writing: llama-3-8b

  # Tool restrictions by tier
  tool_restrictions:
    normal:  # 0-50%
      allowed_tools: ["all"]

    warning:  # 50-80%
      allowed_tools: ["all"]

    optimized:  # 80-95%
      allowed_tools: ["all"]
      warnings: ["image_generation", "web_search"]

    local:  # 95-100%
      allowed_tools: ["code_execution", "file_operations"]
      blocked_tools: ["image_generation", "web_search", "api_calls"]

    blocked:  # 100%+
      allowed_tools: ["code_execution"]
      blocked_tools: ["all_external"]

  # User notifications
  notifications:
    warning_50:
      message: "⚠️ You've used 50% of your daily budget."
      action: "none"

    warning_80:
      message: "💰 Approaching budget limit. Switching to cost-effective models."
      action: "switch_to_cheaper"

    warning_95:
      message: "🏠 Budget limit reached. Using local models to stay productive."
      action: "switch_to_local"

    exhausted_100:
      message: "❌ Daily budget exhausted. Contact IT for extension if needed."
      action: "block_expensive"
```

### Override Mechanism

```python
# File: k1/cost_tracking/fallback_override.py

class FallbackOverrideManager:
    """Allow critical operations to bypass fallback"""

    async def request_override(
        self,
        user_id: str,
        session_id: str,
        reason: str,
        requested_by: str
    ) -> OverrideResult:
        """
        Request budget override for critical task
        Requires admin approval
        """
        override = Override(
            user_id=user_id,
            session_id=session_id,
            reason=reason,
            requested_by=requested_by,
            requested_at=datetime.now(),
            status="pending"
        )

        # Send approval request to IT admin
        await self._send_approval_request(override)

        return OverrideResult(
            override_id=override.id,
            status="pending_approval",
            message="Override request sent to IT admin"
        )

    async def approve_override(
        self,
        override_id: str,
        approved_by: str,
        additional_budget_usd: float
    ):
        """Admin approves budget override"""
        override = self.overrides[override_id]
        override.status = "approved"
        override.approved_by = approved_by
        override.additional_budget = additional_budget_usd

        # Extend user budget
        await self.budget_enforcer.extend_budget(
            user_id=override.user_id,
            additional_usd=additional_budget_usd
        )

        # Audit log
        logger.info(
            f"Budget override approved",
            override_id=override_id,
            user_id=override.user_id,
            additional_budget=additional_budget_usd,
            approved_by=approved_by
        )
```

---

## Implementation Timeline

### Phase 1: Core Fallback Logic (Weeks 1-3)
- **Week 1:** Tier detection + threshold logic
- **Week 2:** Model selection (cheaper alternatives, local models)
- **Week 3:** User notifications

### Phase 2: Integration (Weeks 4-6)
- **Week 4:** Orchestrator integration
- **Week 5:** Tool restriction enforcement
- **Week 6:** Override mechanism

### Phase 3: Testing (Weeks 7-8)
- **Week 7:** WARD integration tests
- **Week 8:** User acceptance testing

---

## Consequences

### Positive
1. **No Hard Cutoff:** Users stay productive even at budget limit
2. **Graceful Degradation:** Quality reduces gradually, not abruptly
3. **Proactive Warnings:** Users informed before impact
4. **Cost Control:** Budget respected automatically

### Negative
1. **Quality Variance:** Local models less capable than remote
2. **User Confusion:** Model switching might confuse users
3. **Override Requests:** Critical tasks need admin approval

### Risks
1. **Local Model Quality:** Users dissatisfied with local responses
   - Mitigation: Clear notifications, easy override request
2. **Override Abuse:** Users request overrides too frequently
   - Mitigation: Audit trail, manager approval required

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Hard Cutoff Rate | <5% | Sessions blocked at 100% |
| User Satisfaction | >80% | User survey post-fallback |
| Budget Adherence | >95% | Actual vs budget |
| Override Requests | <10% | Override/total sessions |

---

## Related Documents

- [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
- [ADR-0031a: Hierarchical Budget Enforcement](0031a-hierarchical-budget-enforcement-corporate-governance.md)
- [ADR-0031b: Cost Model & Pricing](0031b-cost-model-pricing-configuration.md)
- [ADR-0031d: Cost Observability](0031d-cost-observability-metrics.md)
- [ADR-0027: Model Placement Cascade](0027-model-placement-cascade.md)

---

**Status:** ✅ Ready for implementation
**Timeline:** 8 weeks
**Priority:** ⭐⭐⭐ Critical (User experience + budget control)
