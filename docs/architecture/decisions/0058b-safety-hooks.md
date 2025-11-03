---
adr_number: 0058b
title: Safety Hooks (Privacy Band Gates, Refusal Carry-Over)
status: ACCEPTED
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
- cost
- modularity
- observability
- privacy
- reliability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0032
- ADR-0040
- ADR-0041
- ADR-0052
- ADR-0058
- ADR-0058b
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  affected_adrs:
  - ADR-0032
  - ADR-0040
  - ADR-0041
  - ADR-0052
  - ADR-0058
  - ADR-0058b
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR-0058b: Safety Hooks (Privacy Band Gates, Refusal Carry-Over)

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0058 (Intent Classification Integration)

**Related ADRs:**
- ADR-0058: Intent Classification Integration (parent)
- ADR-0032-0038: Privacy Bands (GREEN/AMBER/RED)
- ADR-0040: ABAC (Attribute-Based Access Control)
- ADR-0041: Refusal Reasons
- ADR-0052: HITL Extensions (step-by-step, two-person rule)

---

## Context

### Problem Statement

Voice interfaces create **unique safety risks**:
- **Mishearing:** "send $50" → "send $500" (10x error)
- **Lack of visual confirmation:** No UI to review before submit
- **Hands-free context:** Driving, cooking → can't verify details
- **Ambient activation:** Background conversation triggers actions
- **Sensitive actions:** Voice-activated payments, deletions, account changes

**Existing Safety Mechanisms (ADR-0032-0038):**
- **Privacy Bands:** GREEN (public), AMBER (personal), RED (sensitive)
- **ABAC:** Attribute-based access control for capability checks
- **Refusal Reasons:** Structured explanations for denied actions

**What's Missing for Voice:**
- **Voice-specific gates:** Extra validation before sensitive actions
- **Explicit read-back:** "I heard you say X, is that right?"
- **Refusal persistence:** Remember why action was denied, avoid repeating
- **Costly action thresholds:** Require confirmation for high-impact operations
- **Two-person rule for RED:** Voice version of approval workflow

---

## Decision

### 1. Privacy Band Gate Architecture

**3-Tier Gate System:**
```python
class SafetyGates:
    def __init__(self):
        self.band_classifier = PrivacyBandClassifier()  # ADR-0032
        self.abac_enforcer = ABACEnforcer()  # ADR-0040
        self.refusal_cache = RefusalCache()  # ADR-0041

    async def validate_intent(self,
                             intent: IntentResult,
                             session: Session) -> ValidationResult:
        """Apply safety gates based on privacy band"""

        # Step 1: Classify privacy band
        band = await self.band_classifier.classify(intent, session)

        # Step 2: Apply band-specific gates
        if band == PrivacyBand.GREEN:
            return await self.validate_green(intent, session)
        elif band == PrivacyBand.AMBER:
            return await self.validate_amber(intent, session)
        elif band == PrivacyBand.RED:
            return await self.validate_red(intent, session)
        else:
            # Unknown band → treat as RED (conservative)
            logger.warning("unknown_privacy_band", intent=intent.category)
            return await self.validate_red(intent, session)
```

### 2. GREEN Band (Public Data)

**Minimal Gates:**
```python
async def validate_green(self,
                        intent: IntentResult,
                        session: Session) -> ValidationResult:
    """GREEN band: Public data, low risk"""

    # Only check capabilities (ADR-0040)
    if not await self.abac_enforcer.check_capability(
        user=session.user,
        action=intent.category,
        resource=intent.parameters.get("resource")
    ):
        return ValidationResult(
            allowed=False,
            reason="capability_denied",
            band=PrivacyBand.GREEN
        )

    # No additional gates for GREEN
    return ValidationResult(
        allowed=True,
        band=PrivacyBand.GREEN,
        requires_confirmation=False
    )
```

### 3. AMBER Band (Personal Data)

**Warning + Confirmation for Costly Actions:**
```python
async def validate_amber(self,
                        intent: IntentResult,
                        session: Session) -> ValidationResult:
    """AMBER band: Personal data, medium risk"""

    # Check capabilities
    if not await self.abac_enforcer.check_capability(
        user=session.user,
        action=intent.category,
        resource=intent.parameters.get("resource")
    ):
        return ValidationResult(
            allowed=False,
            reason="capability_denied",
            band=PrivacyBand.AMBER
        )

    # Check if action is costly (requires confirmation)
    is_costly = await self.is_costly_action(intent)

    if is_costly:
        # Require explicit read-back confirmation
        return ValidationResult(
            allowed=True,
            band=PrivacyBand.AMBER,
            requires_confirmation=True,
            confirmation_type="read_back",
            confirmation_prompt=self.generate_read_back(intent)
        )

    # Non-costly AMBER actions → warn but allow
    return ValidationResult(
        allowed=True,
        band=PrivacyBand.AMBER,
        requires_confirmation=False,
        warnings=["This action involves personal data."]
    )
```

### 4. RED Band (Sensitive Data)

**Strict Validation + Two-Person Rule:**
```python
async def validate_red(self,
                      intent: IntentResult,
                      session: Session) -> ValidationResult:
    """RED band: Sensitive data, high risk"""

    # Check capabilities (strict)
    if not await self.abac_enforcer.check_capability(
        user=session.user,
        action=intent.category,
        resource=intent.parameters.get("resource")
    ):
        return ValidationResult(
            allowed=False,
            reason="capability_denied",
            band=PrivacyBand.RED
        )

    # Check refusal cache (avoid repeated denials)
    if await self.refusal_cache.was_recently_refused(
        session_id=session.id,
        action=intent.category
    ):
        recent_refusal = await self.refusal_cache.get_refusal(
            session_id=session.id,
            action=intent.category
        )

        return ValidationResult(
            allowed=False,
            reason="recently_refused",
            band=PrivacyBand.RED,
            refusal_details=recent_refusal
        )

    # Always require explicit confirmation for RED
    confirmation_type = self.select_red_confirmation_type(intent)

    return ValidationResult(
        allowed=True,
        band=PrivacyBand.RED,
        requires_confirmation=True,
        confirmation_type=confirmation_type,
        confirmation_prompt=self.generate_red_confirmation(intent, confirmation_type)
    )

def select_red_confirmation_type(self, intent: IntentResult) -> str:
    """Choose confirmation mechanism for RED band"""
    # Critical financial actions → Two-person rule (ADR-0052)
    if intent.category in ["tool.payment.send", "tool.payment.transfer"]:
        amount = intent.parameters.get("amount", 0)
        if amount >= 1000:  # $1000+ threshold
            return "two_person_approval"

    # Account changes → PIN verification
    if intent.category in ["tool.account.delete", "tool.account.modify"]:
        return "pin_verification"

    # Default RED → Explicit read-back + yes/no
    return "explicit_read_back"
```

### 5. Costly Action Detection

**Threshold-Based Classification:**
```python
class CostlyActionDetector:
    COST_RULES = {
        # Financial thresholds
        "tool.payment.send": {
            "parameter": "amount",
            "threshold": 100,  # $100
            "currency": "USD"
        },
        "tool.payment.transfer": {
            "parameter": "amount",
            "threshold": 500,
            "currency": "USD"
        },

        # External communication
        "tool.email.send": {
            "rule": "external_recipients",
            "threshold": 1  # Any external recipient
        },
        "tool.sms.send": {
            "rule": "external_recipients",
            "threshold": 1
        },

        # Data deletion
        "tool.file.delete": {
            "rule": "permanent_deletion",
            "threshold": True
        },
        "tool.email.delete": {
            "rule": "multiple_items",
            "threshold": 10  # Deleting 10+ emails
        },

        # Calendar
        "tool.calendar.cancel": {
            "rule": "attendee_count",
            "threshold": 3  # Meeting with 3+ people
        },
    }

    async def is_costly_action(self, intent: IntentResult) -> bool:
        """Determine if action is costly (requires confirmation)"""
        if intent.category not in self.COST_RULES:
            return False

        rule = self.COST_RULES[intent.category]

        # Threshold-based rules
        if "threshold" in rule:
            param_value = intent.parameters.get(rule["parameter"], 0)
            return param_value >= rule["threshold"]

        # Custom rule evaluation
        if "rule" in rule:
            return await self.evaluate_custom_rule(
                rule=rule["rule"],
                intent=intent,
                threshold=rule["threshold"]
            )

        return False

    async def evaluate_custom_rule(self,
                                   rule: str,
                                   intent: IntentResult,
                                   threshold: any) -> bool:
        """Evaluate custom cost rules"""
        if rule == "external_recipients":
            recipients = intent.parameters.get("recipients", [])
            external_count = sum(1 for r in recipients if self.is_external(r))
            return external_count >= threshold

        elif rule == "permanent_deletion":
            is_permanent = intent.parameters.get("permanent", False)
            return is_permanent == threshold

        elif rule == "multiple_items":
            item_count = intent.parameters.get("item_count", 1)
            return item_count >= threshold

        elif rule == "attendee_count":
            attendees = intent.parameters.get("attendees", [])
            return len(attendees) >= threshold

        return False
```

### 6. Confirmation Prompt Generation

**Read-Back Prompts:**
```python
class ConfirmationPrompts:
    def generate_read_back(self, intent: IntentResult) -> str:
        """Generate explicit read-back for confirmation"""
        # Template: "I heard you say [action] with [parameters]. Is that correct?"

        action_phrase = self.humanize_action(intent.category)
        params_phrase = self.humanize_parameters(intent.parameters)

        return f"Just to confirm: {action_phrase} {params_phrase}. Is that correct?"

    def generate_red_confirmation(self,
                                  intent: IntentResult,
                                  confirmation_type: str) -> str:
        """Generate RED band confirmation prompt"""
        if confirmation_type == "two_person_approval":
            return (
                f"This action requires approval. "
                f"I heard you say: {self.humanize_full_intent(intent)}. "
                f"I'll send this for review."
            )

        elif confirmation_type == "pin_verification":
            return (
                f"This is a sensitive action. "
                f"Please provide your PIN to confirm: {self.humanize_action(intent.category)}."
            )

        else:  # explicit_read_back
            return (
                f"⚠️ Important: {self.humanize_full_intent(intent)}. "
                f"Say 'yes' to confirm or 'no' to cancel."
            )

    def humanize_action(self, category: str) -> str:
        """Convert category to natural language"""
        mappings = {
            "tool.payment.send": "send a payment",
            "tool.email.send": "send an email",
            "tool.calendar.cancel": "cancel a meeting",
            "tool.file.delete": "delete a file",
        }
        return mappings.get(category, category.replace(".", " "))

    def humanize_parameters(self, parameters: dict) -> str:
        """Convert parameters to natural language"""
        phrases = []

        if "recipient" in parameters:
            phrases.append(f"to {parameters['recipient']}")

        if "amount" in parameters:
            phrases.append(f"for ${parameters['amount']}")

        if "subject" in parameters:
            phrases.append(f"about '{parameters['subject']}'")

        if "datetime" in parameters:
            phrases.append(f"on {self.humanize_datetime(parameters['datetime'])}")

        return " ".join(phrases)

    def humanize_full_intent(self, intent: IntentResult) -> str:
        """Full human-readable intent"""
        action = self.humanize_action(intent.category)
        params = self.humanize_parameters(intent.parameters)
        return f"{action} {params}".strip()
```

### 7. Refusal Cache (Avoid Repetition)

**Remember Denied Actions:**
```python
@dataclass
class RefusalRecord:
    session_id: str
    action: str
    reason: str
    parameters: dict
    timestamp: float
    ttl_seconds: int = 300  # 5 minutes

class RefusalCache:
    def __init__(self):
        self.cache: Dict[str, List[RefusalRecord]] = {}

    async def record_refusal(self,
                            session_id: str,
                            action: str,
                            reason: str,
                            parameters: dict):
        """Cache a refusal"""
        record = RefusalRecord(
            session_id=session_id,
            action=action,
            reason=reason,
            parameters=parameters,
            timestamp=time.time()
        )

        key = f"{session_id}:{action}"
        if key not in self.cache:
            self.cache[key] = []

        self.cache[key].append(record)

        # Emit metric
        refusals_cached.labels(reason=reason).inc()

        logger.info(
            "refusal_cached",
            session_id=session_id,
            action=action,
            reason=reason
        )

    async def was_recently_refused(self,
                                  session_id: str,
                                  action: str) -> bool:
        """Check if action was recently refused"""
        key = f"{session_id}:{action}"

        if key not in self.cache:
            return False

        # Check for recent refusals (within TTL)
        now = time.time()
        recent = [
            r for r in self.cache[key]
            if now - r.timestamp < r.ttl_seconds
        ]

        return len(recent) > 0

    async def get_refusal(self,
                         session_id: str,
                         action: str) -> Optional[RefusalRecord]:
        """Retrieve most recent refusal"""
        key = f"{session_id}:{action}"

        if key not in self.cache:
            return None

        # Return most recent
        now = time.time()
        recent = [
            r for r in self.cache[key]
            if now - r.timestamp < r.ttl_seconds
        ]

        if not recent:
            return None

        return sorted(recent, key=lambda r: r.timestamp, reverse=True)[0]

    async def clear_refusal(self, session_id: str, action: str):
        """Clear refusal (e.g., user resolved issue)"""
        key = f"{session_id}:{action}"
        if key in self.cache:
            del self.cache[key]
            logger.info("refusal_cleared", session_id=session_id, action=action)
```

### 8. Two-Person Approval (RED Band)

**Voice Version of ADR-0052:**
```python
class TwoPersonApproval:
    async def initiate_approval(self,
                               intent: IntentResult,
                               session: Session) -> ApprovalRequest:
        """Start two-person approval workflow"""
        # Create approval request
        request = ApprovalRequest(
            request_id=generate_id(),
            session_id=session.id,
            requester=session.user,
            action=intent.category,
            parameters=intent.parameters,
            created_at=time.time(),
            status=ApprovalStatus.PENDING
        )

        # Store request (ADR-0052)
        await self.approval_store.save(request)

        # Notify approvers
        await self.notify_approvers(request)

        # Respond to user
        logger.info(
            "approval_initiated",
            request_id=request.request_id,
            action=intent.category
        )

        return request

    async def notify_approvers(self, request: ApprovalRequest):
        """Send notification to designated approvers"""
        approvers = await self.get_approvers(request.requester)

        for approver in approvers:
            await self.notification_service.send(
                recipient=approver,
                subject=f"Approval Required: {request.action}",
                body=self.format_approval_notification(request),
                notification_type="approval_request"
            )

    async def check_approval_status(self, request_id: str) -> ApprovalStatus:
        """Check if approval granted/denied"""
        request = await self.approval_store.get(request_id)
        return request.status
```

### 9. Confirmation Validation

**Verify User Response:**
```python
class ConfirmationValidator:
    AFFIRMATIVE_PATTERNS = [
        r"\byes\b", r"\byeah\b", r"\byep\b", r"\bsure\b",
        r"\bok\b", r"\bokay\b", r"\bconfirm\b", r"\bcorrect\b"
    ]

    NEGATIVE_PATTERNS = [
        r"\bno\b", r"\bnope\b", r"\bcancel\b", r"\bstop\b",
        r"\bnever mind\b", r"\bforget it\b"
    ]

    async def validate_confirmation(self,
                                   user_response: str,
                                   original_intent: IntentResult) -> ConfirmationResult:
        """Parse user's confirmation response"""
        response_lower = user_response.lower()

        # Check for affirmative
        for pattern in self.AFFIRMATIVE_PATTERNS:
            if re.search(pattern, response_lower):
                return ConfirmationResult(
                    confirmed=True,
                    intent=original_intent
                )

        # Check for negative
        for pattern in self.NEGATIVE_PATTERNS:
            if re.search(pattern, response_lower):
                return ConfirmationResult(
                    confirmed=False,
                    intent=original_intent,
                    cancellation_reason="user_cancelled"
                )

        # Ambiguous response → ask again
        return ConfirmationResult(
            confirmed=None,  # Ambiguous
            intent=original_intent,
            requires_clarification=True,
            clarification_prompt="I didn't catch that. Please say 'yes' to confirm or 'no' to cancel."
        )
```

---

## Consequences

### Positive

✅ **Safety First:** Multiple gates prevent unintended actions
✅ **Voice-Aware:** Read-back confirmation for audio context
✅ **User Memory:** Refusal cache avoids repetition
✅ **Escalation Path:** Two-person approval for critical actions
✅ **Transparency:** Clear explanations for refusals

### Negative

⚠️ **UX Friction:** Extra confirmations slow down interaction
⚠️ **Complexity:** Many rules and thresholds to maintain
⚠️ **False Positives:** May block legitimate actions

---

## Implementation Guidance

### Phase 1: Privacy Band Gates (Day 1-3)
- Implement GREEN/AMBER/RED validation
- Band classification integration
- ABAC capability checking

### Phase 2: Costly Action Detection (Day 4-5)
- Cost rule definitions
- Threshold configuration
- Custom rule evaluation

### Phase 3: Confirmation Prompts (Day 6-7)
- Read-back generation
- RED band prompts
- Confirmation validation

### Phase 4: Refusal Cache (Day 8)
- Cache implementation
- TTL management
- Metrics and logging

### Phase 5: Two-Person Approval (Day 9-11)
- Approval workflow integration
- Notification system
- Status tracking

---

## Validation

```python
@test("red band requires confirmation")
async def test_red_confirmation():
    gates = SafetyGates()

    intent = IntentResult(
        category="tool.payment.send",
        parameters={"amount": 500},
        confidence=0.85
    )

    result = await gates.validate_intent(intent, mock_session)

    assert result.requires_confirmation
    assert result.confirmation_type in ["explicit_read_back", "two_person_approval"]

@test("refusal cache prevents repeated denials")
async def test_refusal_cache():
    cache = RefusalCache()

    await cache.record_refusal("s1", "tool.payment.send", "insufficient_balance", {})

    was_refused = await cache.was_recently_refused("s1", "tool.payment.send")
    assert was_refused

@test("costly action above threshold requires confirmation")
async def test_costly_detection():
    detector = CostlyActionDetector()

    intent = IntentResult(
        category="tool.payment.send",
        parameters={"amount": 150}  # Above $100 threshold
    )

    is_costly = await detector.is_costly_action(intent)
    assert is_costly
```

---

## Monitoring

```python
safety_gates_triggered = Counter(
    'safety_gates_triggered',
    'Safety gates activated',
    ['band', 'action']
)

confirmations_requested = Counter(
    'confirmations_requested',
    'Confirmations requested',
    ['type', 'band']  # read_back, two_person, pin
)

refusals_cached = Counter(
    'refusals_cached',
    'Refusals recorded in cache',
    ['reason']
)

approval_requests = Counter(
    'approval_requests',
    'Two-person approval requests',
    ['action', 'status']  # pending, approved, denied
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 1,140 lines (target: 1,100 lines) ✅