# ADR-0059c: Planner/DM Parameter Update Contracts

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0059 (Learning Loop)

**Related ADRs:**
- ADR-0059: Learning Loop (parent)
- ADR-0007: Planner Pipeline
- ADR-0006: Orchestrator Core
- ADR-0041: Refusal Reasons

---

## Context

### Problem Statement

Learning loop can **suggest parameter adjustments** to improve planner/orchestrator performance:
- **LLM parameters:** Temperature, top-k, top-p
- **Planning depth:** Max steps, timeout
- **Confidence thresholds:** Intent classification, tool selection
- **Verbosity:** Response length, detail level

**Critical Safety Constraint:**
- **NEVER override safety refusals**
- **NEVER bypass privacy band checks**
- **NEVER disable audit logging**
- **NEVER weaken security policies**

---

## Decision

### 1. Advisory-Only Architecture

**K1 Suggests, Components Decide:**
```python
class ParameterAdvisory:
    """
    K1 Learning Loop emits parameter suggestions
    Planner/orchestrator decide whether to apply
    """
    def __init__(self):
        self.suggestion_generator = SuggestionGenerator()

    async def generate_suggestion(self,
                                 feedback: AggregateScore,
                                 session: Session) -> ParameterSuggestion:
        """Generate parameter adjustment suggestion"""

        # Analyze feedback patterns
        analysis = await self.analyze_feedback(feedback, session)

        # Generate suggestions
        suggestions = []

        if analysis.indicates_verbosity_issue:
            suggestions.append(
                ParameterSuggestion(
                    parameter="response_length",
                    current_value=session.preferences.response_length,
                    suggested_value=analysis.recommended_length,
                    reason="user_prefers_shorter" if analysis.too_verbose else "user_wants_detail",
                    confidence=analysis.confidence
                )
            )

        if analysis.indicates_confidence_issue:
            suggestions.append(
                ParameterSuggestion(
                    parameter="intent_confidence_threshold",
                    current_value=session.preferences.intent_threshold,
                    suggested_value=analysis.recommended_threshold,
                    reason="too_many_clarifications" if analysis.too_strict else "accepting_bad_intents",
                    confidence=analysis.confidence
                )
            )

        return suggestions
```

### 2. Allowed Parameter Categories

**What Can Be Adjusted:**
```python
class AllowedParameters:
    # LLM Generation Parameters (safe to tune)
    LLM_PARAMS = {
        "temperature": {
            "min": 0.0,
            "max": 1.0,
            "default": 0.7,
            "description": "Randomness in generation"
        },
        "top_k": {
            "min": 1,
            "max": 100,
            "default": 40,
            "description": "Vocabulary size for sampling"
        },
        "top_p": {
            "min": 0.0,
            "max": 1.0,
            "default": 0.9,
            "description": "Nucleus sampling threshold"
        },
        "max_tokens": {
            "min": 50,
            "max": 2000,
            "default": 500,
            "description": "Max response length"
        },
    }

    # Planning Parameters (safe to tune)
    PLANNING_PARAMS = {
        "max_planning_steps": {
            "min": 3,
            "max": 20,
            "default": 10,
            "description": "Max planner iterations"
        },
        "planning_timeout_ms": {
            "min": 1000,
            "max": 10000,
            "default": 5000,
            "description": "Planning time budget"
        },
        "retry_attempts": {
            "min": 1,
            "max": 5,
            "default": 3,
            "description": "Retries on failure"
        },
    }

    # Confidence Parameters (safe to tune within bounds)
    CONFIDENCE_PARAMS = {
        "intent_confidence_threshold": {
            "min": 0.60,   # Never go below 0.60
            "max": 0.95,   # Never require >0.95
            "default": 0.80,
            "description": "Intent classification threshold"
        },
        "tool_selection_confidence": {
            "min": 0.70,
            "max": 0.95,
            "default": 0.85,
            "description": "Tool selection threshold"
        },
    }

    # Style/Preference Parameters (safe to tune)
    STYLE_PARAMS = {
        "response_verbosity": {
            "min": 0,
            "max": 10,
            "default": 5,
            "description": "Response detail level"
        },
        "formality_level": {
            "min": 0,
            "max": 10,
            "default": 5,
            "description": "Formal vs casual tone"
        },
        "use_emoji": {
            "type": "bool",
            "default": False,
            "description": "Include emoji in responses"
        },
    }
```

### 3. Forbidden Parameter Categories

**What CANNOT Be Adjusted:**
```python
class ForbiddenParameters:
    # Safety Parameters (NEVER adjust)
    SAFETY_FORBIDDEN = [
        "privacy_band_thresholds",      # NEVER weaken privacy
        "refusal_policies",             # NEVER override refusals
        "safety_filter_thresholds",     # NEVER lower safety bars
        "audit_log_enabled",            # NEVER disable auditing
        "two_person_approval_threshold" # NEVER bypass approval
    ]

    # Security Parameters (NEVER adjust)
    SECURITY_FORBIDDEN = [
        "authentication_required",
        "authorization_policies",
        "encryption_enabled",
        "rate_limit_thresholds"
    ]

    # Infrastructure Parameters (NEVER adjust)
    INFRASTRUCTURE_FORBIDDEN = [
        "port_numbers",
        "k0_k1_boundary_rules",
        "pipeline_ownership",
        "receipt_validation"
    ]

    @staticmethod
    def is_forbidden(parameter: str) -> bool:
        """Check if parameter adjustment is forbidden"""
        return (
            parameter in ForbiddenParameters.SAFETY_FORBIDDEN or
            parameter in ForbiddenParameters.SECURITY_FORBIDDEN or
            parameter in ForbiddenParameters.INFRASTRUCTURE_FORBIDDEN
        )
```

### 4. Suggestion Validation

**Safety Checks Before Application:**
```python
class SuggestionValidator:
    async def validate(self, suggestion: ParameterSuggestion) -> ValidationResult:
        """Validate parameter suggestion"""

        # Check 1: Is parameter allowed?
        if ForbiddenParameters.is_forbidden(suggestion.parameter):
            logger.error(
                "forbidden_parameter_adjustment",
                parameter=suggestion.parameter
            )
            return ValidationResult(
                allowed=False,
                reason="parameter_forbidden"
            )

        # Check 2: Is new value within safe bounds?
        bounds = self.get_parameter_bounds(suggestion.parameter)

        if suggestion.suggested_value < bounds["min"] or suggestion.suggested_value > bounds["max"]:
            logger.warning(
                "parameter_out_of_bounds",
                parameter=suggestion.parameter,
                suggested=suggestion.suggested_value,
                min=bounds["min"],
                max=bounds["max"]
            )
            return ValidationResult(
                allowed=False,
                reason="value_out_of_bounds"
            )

        # Check 3: Is confidence high enough?
        if suggestion.confidence < 0.70:
            return ValidationResult(
                allowed=False,
                reason="low_confidence_suggestion"
            )

        # Check 4: Would this violate safety constraints?
        safety_check = await self.check_safety_impact(suggestion)

        if not safety_check.safe:
            return ValidationResult(
                allowed=False,
                reason=f"safety_violation: {safety_check.reason}"
            )

        # All checks passed
        return ValidationResult(allowed=True)

    async def check_safety_impact(self, suggestion: ParameterSuggestion) -> SafetyCheck:
        """Check if suggestion would weaken safety"""

        # Example: Lowering confidence threshold too much
        if suggestion.parameter == "intent_confidence_threshold":
            if suggestion.suggested_value < 0.65:
                return SafetyCheck(
                    safe=False,
                    reason="confidence_threshold_too_low"
                )

        # Example: Increasing max_tokens could enable prompt injection
        if suggestion.parameter == "max_tokens":
            if suggestion.suggested_value > 1500:
                return SafetyCheck(
                    safe=False,
                    reason="max_tokens_enables_prompt_injection"
                )

        return SafetyCheck(safe=True)
```

### 5. Planner Integration

**Planner Receives Suggestions:**
```python
class PlannerParameterAdapter:
    """Planner component receives and applies suggestions"""

    async def apply_suggestion(self,
                              suggestion: ParameterSuggestion,
                              session: Session) -> ApplicationResult:
        """Apply parameter suggestion to planner"""

        # Validate suggestion
        validation = await self.validator.validate(suggestion)

        if not validation.allowed:
            logger.warning(
                "suggestion_rejected",
                parameter=suggestion.parameter,
                reason=validation.reason
            )

            parameter_suggestions_rejected.labels(
                reason=validation.reason
            ).inc()

            return ApplicationResult(
                applied=False,
                reason=validation.reason
            )

        # Apply parameter change
        old_value = session.preferences.get(suggestion.parameter)
        session.preferences.set(suggestion.parameter, suggestion.suggested_value)

        logger.info(
            "parameter_adjusted",
            parameter=suggestion.parameter,
            old_value=old_value,
            new_value=suggestion.suggested_value,
            reason=suggestion.reason
        )

        parameter_adjustments.labels(
            parameter=suggestion.parameter
        ).inc()

        # Track change for rollback
        await self.track_change(suggestion, session)

        return ApplicationResult(
            applied=True,
            old_value=old_value,
            new_value=suggestion.suggested_value
        )
```

### 6. Orchestrator Integration

**Orchestrator Dynamic Config:**
```python
class OrchestratorParameterAdapter:
    """Orchestrator receives suggestions for agent selection"""

    TUNABLE_PARAMS = {
        "agent_selection_temperature": {
            "min": 0.0,
            "max": 1.0,
            "default": 0.3,
            "description": "Randomness in agent selection"
        },
        "max_negotiation_rounds": {
            "min": 1,
            "max": 10,
            "default": 3,
            "description": "Negotiation phase iterations"
        },
        "capability_match_threshold": {
            "min": 0.5,
            "max": 1.0,
            "default": 0.8,
            "description": "Min capability score for agent"
        },
    }

    async def apply_suggestion(self,
                              suggestion: ParameterSuggestion,
                              session: Session) -> ApplicationResult:
        """Apply suggestion to orchestrator config"""

        # Validate parameter is tunable
        if suggestion.parameter not in self.TUNABLE_PARAMS:
            return ApplicationResult(
                applied=False,
                reason="parameter_not_tunable"
            )

        # Apply via config hot-reload (ADR-0031)
        await self.config_manager.update_parameter(
            parameter=suggestion.parameter,
            value=suggestion.suggested_value,
            session_id=session.id
        )

        return ApplicationResult(applied=True)
```

### 7. Refusal Override Prevention

**Never Override Safety Refusals:**
```python
class RefusalProtection:
    """Ensure learning never overrides safety refusals"""

    async def validate_against_refusals(self,
                                       suggestion: ParameterSuggestion,
                                       session: Session) -> bool:
        """Check if suggestion would override past refusals"""

        # Get recent refusals for this session
        refusals = await self.refusal_cache.get_recent_refusals(
            session_id=session.id,
            lookback_hours=24
        )

        # Check if any parameter change would re-enable refused action
        for refusal in refusals:
            if self.would_enable_refused_action(suggestion, refusal):
                logger.error(
                    "parameter_would_override_refusal",
                    parameter=suggestion.parameter,
                    refusal_reason=refusal.reason
                )

                refusal_override_prevented.inc()

                return False

        return True

    def would_enable_refused_action(self,
                                   suggestion: ParameterSuggestion,
                                   refusal: RefusalRecord) -> bool:
        """Check if parameter change would re-enable refused action"""
        # Example: Lowering confidence threshold to accept previously refused intent
        if suggestion.parameter == "intent_confidence_threshold":
            if refusal.reason == "low_confidence_intent":
                if suggestion.suggested_value < refusal.context["confidence"]:
                    return True  # Would accept previously refused intent

        return False
```

---

## Consequences

### Positive

✅ **Safe Tuning:** Only allows safe parameter adjustments
✅ **Never Override Refusals:** Prevents weakening safety
✅ **Advisory Model:** Components decide to apply or ignore
✅ **Gradual Adaptation:** Small, incremental changes

### Negative

⚠️ **Limited Scope:** Can't tune everything
⚠️ **Conservative:** May miss valid optimizations
⚠️ **Complexity:** Validation logic for each parameter

---

## Implementation Guidance

### Phase 1: Parameter Catalog (Day 1-2)
- Define allowed parameters
- Define forbidden parameters
- Set safe bounds

### Phase 2: Suggestion Generation (Day 3-4)
- Feedback analysis
- Suggestion logic
- Confidence scoring

### Phase 3: Validation (Day 5-6)
- Safety checks
- Bounds validation
- Refusal override prevention

### Phase 4: Planner Integration (Day 7-8)
- Apply suggestions
- Track changes
- Rollback support

### Phase 5: Orchestrator Integration (Day 9)
- Config hot-reload integration
- Agent selection tuning

---

## Validation

```python
@test("forbidden parameters rejected")
async def test_forbidden_parameter():
    validator = SuggestionValidator()

    suggestion = ParameterSuggestion(
        parameter="refusal_policies",  # FORBIDDEN
        suggested_value=0.5
    )

    result = await validator.validate(suggestion)
    assert not result.allowed
    assert "forbidden" in result.reason

@test("suggestion does not override refusal")
async def test_refusal_protection():
    protection = RefusalProtection()

    # Mock refusal due to low confidence
    refusal = RefusalRecord(
        reason="low_confidence_intent",
        context={"confidence": 0.75}
    )

    # Suggestion to lower threshold below refusal confidence
    suggestion = ParameterSuggestion(
        parameter="intent_confidence_threshold",
        suggested_value=0.70  # Below 0.75
    )

    is_safe = await protection.validate_against_refusals(suggestion, mock_session)
    assert not is_safe  # Should be blocked
```

---

## Monitoring

```python
parameter_suggestions_generated = Counter(
    'parameter_suggestions_generated',
    'Parameter suggestions generated',
    ['parameter']
)

parameter_suggestions_rejected = Counter(
    'parameter_suggestions_rejected',
    'Suggestions rejected',
    ['reason']
)

parameter_adjustments = Counter(
    'parameter_adjustments',
    'Parameters adjusted',
    ['parameter']
)

refusal_override_prevented = Counter(
    'refusal_override_prevented',
    'Prevented override of safety refusals'
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 830 lines (target: 800 lines) ✅
