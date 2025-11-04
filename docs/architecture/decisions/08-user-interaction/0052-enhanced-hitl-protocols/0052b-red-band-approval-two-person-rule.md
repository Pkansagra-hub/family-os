---
adr_number: 0052b
affected_layers:
- layer3_execution
- layer4_runtime
affected_modules:
- k1.hitl.red_band_approval
- k1.security.two_person_rule
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
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 3 (User Interaction)
implementation_status: COMPLETED
related_adrs:
- ADR-0003b
- ADR-0007c
- ADR-0032
- ADR-0038
- ADR-0052
- ADR-0052a
- ADR-0052c
- ADR-0052d
- ADR-0052e
- ADR-0053
related_contracts:
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
research_citations:
- Two-Person Rule (Nuclear Safety, 1962)
- Dual Control Systems (ISO 27001)
- Critical Action Authorization (NIST SP 800-53)
status: ACCEPTED
title: RED Band Approval with Two-Person Rule
---

- ADR-0053b
- ADR-0065
- ADR-0065d
- ADR-0083
related_contracts: []
related_diagrams: []
research_citations:
- Framework (2018)
- Model (1990)
- Things (1988)
status: PROPOSED
superseded_by: []
supersedes: []
title: RED Band Approval with Two-Person Rule
---

# ADR-0052b: RED Band Approval with Two-Person Rule

**Status:** ✅ **ACCEPTED** (2025-10-14)
**Date:** 2025-10-14
**Decision Date:** 2025-10-14
**Parent ADR:** [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
**Authors:** K1 Architecture Team
**Category:** Human-in-the-Loop & Safety
**Technical Story:** [Explicit Confirmation for High-Risk Operations]

**Related ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md) - Parent umbrella ADR
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md) - Protocol 3 (Clarification) foundation
- [ADR-0032-0038: Privacy Band System](0032-band-based-egress-rules.md) - RED/AMBER/GREEN band classification
- [ADR-0038: Audit Trail to K0 Receipts](0038-audit-trail-to-k0-receipts.md) - 7-year retention for compliance
- [ADR-0007c: Arbiter Safety Validation](0007c-arbiter-safety-validation.md) - Risk scoring before approval

---

## Executive Summary

**Purpose:** Require explicit confirmation phrases for high-risk operations (RED band) to prevent accidental destructive actions, with optional two-person approval for CRITICAL operations.

**Core Functionality:**
- **Explicit Confirmation Phrases:** User must type exact phrase (e.g., "CONFIRM DELETE 1.2M RECORDS")
- **Case-Insensitive Matching:** Phrase matching ignores case but requires exact wording
- **Privacy Band Integration:** RED band operations automatically trigger approval protocol
- **Optional Two-Person Rule:** Second approver for CRITICAL operations (feature flag, disabled by default)
- **Full Audit Trail:** Log who approved, when, what phrase was typed (7-year retention for compliance)
- **Phrase Generation:** Dynamically generated phrases based on operation impact

**Key Design Decisions:**
1. **Case-insensitive matching** — User can type "confirm delete" or "CONFIRM DELETE"
2. **Two-person rule is optional** — Feature flag (disabled by default), configurable per operation
3. **Audit trail required** — Every RED band approval logged to K0 receipts
4. **60-second timeout** — Longer than basic clarification (30s), shorter than step-by-step (5min)
5. **Arbiter pre-validation** — Risk scoring before showing approval prompt

**Performance Targets:**
- Phrase validation: <100ms (case-insensitive string comparison)
- Audit log write: <50ms (async to K0)
- Two-person approval latency: <60s timeout (waiting for second approver)

---

## Context

### The Problem

**Current State:** K1 supports basic HITL clarifications (ADR-0003b Protocol 3) with 4 types:
- MULTIPLE_CHOICE, FREE_TEXT, YES_NO, **APPROVAL** (mentioned but not fully specified)

**Limitation:** Current APPROVAL type is underspecified:
- No explicit confirmation phrase requirement (just "Yes" button)
- No integration with Privacy Band system (ADR-0032-0038)
- No audit trail for high-risk approvals
- No two-person rule support for CRITICAL operations

**Real-World Risk Scenarios:**

**Scenario 1: Accidental Photo Album Deletion**
```
User: "Delete old photos from 2020"

Agent (current behavior - BAD):
  "This will delete 1,847 photos from your 2020 album. Proceed? [Yes/No]"

User: [accidentally clicks Yes while scrolling through preview]

Agent: "✅ Deleting 1,847 photos..."

[10 seconds later]
User: "WAIT NO! Those were Emma's baby photos!"
[Too late - photos deleted, no backup]
```

**Scenario 2: Large Money Transfer (Family Financial Management)**
```
User: "Transfer $8,000 to Emma's college fund"

Agent (current behavior - BAD):
  "Transfer $8,000 to College Savings account? [Yes/No]"

[Teen using parent's phone accidentally clicks Yes]

Agent: "✅ Transfer initiated..."

Problem: Single button click for $8K transfer, no secondary approval from spouse
```

**Scenario 3: Sharing Family Medical Records Externally**
```
User: "Share medical records with Dr. Smith"

Agent (current behavior - BAD):
  "Share 47 medical documents with dr.smith@clinic.com? [Yes/No]"

User: [clicks Yes without realizing it's wrong email]

Agent: "✅ Shared medical records via email..."

Problem: No confirmation for RED band (medical) data sharing
```

### Research Foundation

**1. Norman's Design of Everyday Things (1988)**
- **Principle:** Use "forcing functions" to prevent errors
- **Forcing Function:** Explicit phrase typing forces user to consciously confirm
- **Application:** RED band approval requires typing exact phrase, not just clicking button

**2. Two-Person Rule (Military/Nuclear Protocols)**
- **Principle:** Critical actions require independent approval from 2 people
- **Benefit:** Prevents single-point-of-failure errors and unauthorized actions
- **Application:** CRITICAL operations (production deploy, bulk delete >10K) require 2 approvers

**3. Reason's Swiss Cheese Model (1990)**
- **Principle:** Multiple layers of defense against errors
- **Benefit:** Single mistake doesn't cause catastrophic failure
- **Application:** RED band approval is one defense layer (others: arbiter, audit trail, rate limits)

**4. NIST Cybersecurity Framework (2018)**
- **Principle:** Identify → Protect → Detect → Respond → Recover
- **Application:** Audit trail (7-year retention) enables detection and forensic analysis

**5. SOC2 & ISO27001 Compliance**
- **Requirement:** Log all access to sensitive data, retain logs for 7 years
- **Application:** RED band approvals logged to K0 receipts with full context

---

## Decision

We implement **RED Band Approval Protocol** as a new ClarificationType in Protocol 3 (ADR-0003b), with the following design:

### 1. ClarificationType Enum Extension

**Add to existing Protocol 3 enums:**

```yaml
enum ClarificationType:
  MULTIPLE_CHOICE = 0      # Existing
  FREE_TEXT = 1            # Existing
  YES_NO = 2               # Existing
  APPROVAL = 3             # Existing (basic)
  STEP_BY_STEP = 4         # ADR-0052a

  # NEW in ADR-0052b
  RED_BAND_APPROVAL = 5    # Explicit confirmation phrase required
```

### 2. FlatBuffers Schema

**File:** `k1/schemas/websocket/clarification.fbs`

```flatbuffers
// RED band approval request (sent by agent to user)
table RedBandApprovalRequest {
  approval_id: string;                      // UUID for this approval
  operation: string;                        // "delete" | "transfer" | "deploy_prod" | "share_external"
  operation_description: string;            // Human-readable description
  impact_summary: ImpactSummary;            // Structured impact data
  privacy_band: PrivacyBand;                // RED (required) | BLACK (forbidden)
  approval_level: ApprovalLevel;            // LOW | MEDIUM | HIGH | CRITICAL
  required_phrase: string;                  // Exact phrase user must type
  two_person_required: bool;                // Whether second approver needed
  secondary_approver_role: string?;         // Required role (if two-person)
  timeout_sec: uint32;                      // 60s default (vs 30s clarification)
  arbiter_risk_score: float;                // 0.0-1.0 from arbiter
}

// Impact summary (what will happen if approved)
table ImpactSummary {
  affected_records: uint64?;                // Number of records (if applicable)
  financial_amount_usd: float?;             // Dollar amount (if applicable)
  affected_users: uint32?;                  // Number of users impacted
  is_reversible: bool;                      // Can operation be undone?
  estimated_duration_sec: uint32;           // How long operation takes
  additional_context: string?;              // Freeform context
}

enum PrivacyBand: byte {
  GREEN = 0,      // Public data, low risk
  AMBER = 1,      // Sensitive data, medium risk
  RED = 2,        // Highly sensitive, high risk (approval required)
  BLACK = 3,      // Forbidden (never allowed)
}

enum ApprovalLevel: byte {
  LOW = 0,        // Single "Yes" button (no phrase)
  MEDIUM = 1,     // Type "CONFIRM"
  HIGH = 2,       // Type exact phrase (dynamically generated)
  CRITICAL = 3,   // Two-person approval required
}

// RED band approval response (sent by user to agent)
table RedBandApprovalResponse {
  approval_id: string;                      // Which approval this is for
  action: ApprovalAction;                   // APPROVE | DENY
  confirmation_phrase_typed: string;        // What user actually typed
  timestamp: uint64;                        // Unix timestamp (ms)
  user_id: string;                          // Primary approver user ID
  secondary_approver_id: string?;           // Second approver (if two-person)
}

enum ApprovalAction: byte {
  APPROVE = 0,    // User confirmed with correct phrase
  DENY = 1,       // User cancelled or typed wrong phrase
  TIMEOUT = 2,    // User didn't respond within 60s
}

// Audit trail record (persisted to K0 receipts)
table RedBandAuditRecord {
  approval_id: string;                      // UUID for approval
  session_id: string;                       // K1 session
  operation: string;                        // "delete" | "transfer" | etc.
  operation_description: string;            // Human-readable
  impact_summary: ImpactSummary;            // What was affected
  privacy_band: PrivacyBand;                // RED
  approval_level: ApprovalLevel;            // HIGH | CRITICAL
  required_phrase: string;                  // Expected phrase
  confirmation_phrase_typed: string;        // Actual phrase typed
  phrase_match: bool;                       // true | false (case-insensitive)
  arbiter_risk_score: float;                // 0.0-1.0
  primary_approver_id: string;              // Who approved
  secondary_approver_id: string?;           // Second approver (if two-person)
  approval_timestamp: uint64;               // When approved (Unix ms)
  execution_result: string;                 // "SUCCESS" | "FAILED" | "DENIED"
  retention_years: uint8;                   // 7 years (compliance)
}
```

### 3. Approval Level Enforcement

**Approval Level Decision Logic:**

```python
class ApprovalLevelCalculator:
    """
    Determines approval level based on operation risk
    Integrated with Arbiter (ADR-0007c) and Privacy Bands (ADR-0032-0038)
    """

    def calculate_level(self, operation: Operation) -> ApprovalLevel:
        """
        LOW: Simple "Yes" button (no phrase)
        MEDIUM: Type "CONFIRM"
        HIGH: Type exact operation phrase
        CRITICAL: Two-person approval
        """
        # Rule 1: Privacy band
        if operation.privacy_band == PrivacyBand.RED:
            base_level = ApprovalLevel.HIGH
        elif operation.privacy_band == PrivacyBand.AMBER:
            base_level = ApprovalLevel.MEDIUM
        else:
            base_level = ApprovalLevel.LOW

        # Rule 2: Arbiter risk score (overrides privacy band)
        arbiter_score = arbiter.assess_risk(operation)
        if arbiter_score > 0.9:
            base_level = ApprovalLevel.CRITICAL  # Two-person rule
        elif arbiter_score > 0.7:
            base_level = max(base_level, ApprovalLevel.HIGH)

        # Rule 3: Explicit operation thresholds
        if operation.type == "delete" and operation.record_count > 10000:
            base_level = ApprovalLevel.CRITICAL

        if operation.type == "wire_transfer" and operation.amount_usd > 50000:
            base_level = ApprovalLevel.CRITICAL

        if operation.type == "deploy_production":
            base_level = ApprovalLevel.CRITICAL

        # Rule 4: Irreversibility
        if not operation.is_reversible and base_level < ApprovalLevel.HIGH:
            base_level = ApprovalLevel.HIGH

        return base_level
```

**Configuration:**

```yaml
# File: k1/config/red_band_approval.yml
red_band_approval:
  # Approval level thresholds (FamilyOS)
  thresholds:
    delete_photos: 500                 # >500 photos → HIGH approval
    delete_messages: 1000              # >1K messages → HIGH approval
    delete_contacts: 50                # >50 contacts → HIGH approval
    money_transfer: 1000               # >$1K → HIGH approval
    share_medical: 1                   # Any medical records → HIGH
    share_external: 1                  # Any external sharing → MEDIUM

  # Arbiter risk score mapping
  arbiter_risk_levels:
    low: 0.0-0.3                       # No approval needed
    medium: 0.3-0.7                    # Type "CONFIRM"
    high: 0.7-0.9                      # Type exact phrase
    critical: 0.9-1.0                  # Two-person approval

  # Two-person rule (for families)
  two_person_rule:
    enabled: false                     # Feature flag (default: disabled)
    required_for:
      - operation: "delete_photos"
        threshold: 1000                # >1K photos needs spouse approval
      - operation: "money_transfer"
        threshold: 5000                # >$5K needs spouse approval
      - operation: "share_medical"
        always: true                   # Medical always needs spouse
      - operation: "delete_messages"
        threshold: 5000                # >5K messages needs approval

    secondary_approver:
      role: "spouse"                   # Require spouse approval
      timeout_sec: 300                 # 5 minutes to approve
      notification_method: "sms"       # Text message to spouse

  # Timeout settings
  approval_timeout_sec: 60             # User must respond within 60s
  phrase_retry_limit: 3                # Max 3 wrong phrase attempts

  # Audit trail (family privacy)
  audit_trail:
    enabled: true                      # Always log RED band approvals
    retention_years: 7                 # Keep for family records
    log_phrase_typed: true             # Log what user typed
    redact_pii: true                   # Redact personal info in logs
```### 4. Phrase Generation

**Dynamic Phrase Generation:**

```python
class ConfirmationPhraseGenerator:
    """
    Generate confirmation phrases dynamically based on operation
    Balance: Explicit enough to prevent accidents, not too long to type
    """

    def generate(self, operation: Operation) -> str:
        """
        Examples (FamilyOS):
        - "CONFIRM DELETE 1847 PHOTOS"
        - "CONFIRM TRANSFER $8000 TO COLLEGE FUND"
        - "CONFIRM SHARE MEDICAL RECORDS"
        """
        if operation.type == "delete":
            if operation.data_type == "photos":
                count = self._format_number(operation.item_count)
                return f"CONFIRM DELETE {count} PHOTOS"
            elif operation.data_type == "messages":
                count = self._format_number(operation.item_count)
                return f"CONFIRM DELETE {count} MESSAGES"
            elif operation.data_type == "contacts":
                count = self._format_number(operation.item_count)
                return f"CONFIRM DELETE {count} CONTACTS"
            else:
                return f"CONFIRM DELETE {operation.data_type.upper()}"

        elif operation.type == "transfer":
            amount = self._format_currency(operation.amount_usd)
            recipient = operation.recipient_name or operation.account_name
            return f"CONFIRM TRANSFER {amount} TO {recipient}"

        elif operation.type == "share_medical":
            recipient = operation.recipient_email.split('@')[0]  # Get name part
            return f"CONFIRM SHARE MEDICAL RECORDS WITH {recipient.upper()}"

        elif operation.type == "share_external":
            recipient = operation.recipient_domain
            return f"CONFIRM SHARE TO {recipient.upper()}"

        else:
            # Generic fallback
            return f"CONFIRM {operation.type.upper()}"

    def _format_number(self, n: int) -> str:
        """1847 → '1847', 5000 → '5000', 1200000 → '1.2M'"""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        elif n >= 10_000:
            return f"{n / 1_000:.0f}K"
        else:
            return str(n)

    def _format_currency(self, amount_usd: float) -> str:
        """8000.00 → '$8000', 125.50 → '$125'"""
        return f"${int(amount_usd)}"
```**Phrase Validation (Case-Insensitive):**

```python
def validate_confirmation_phrase(typed: str, expected: str) -> bool:
    """
    Case-insensitive comparison
    User can type "confirm delete 1.2m records" or "CONFIRM DELETE 1.2M RECORDS"
    """
    typed_normalized = typed.strip().upper()
    expected_normalized = expected.strip().upper()

    # Exact match (case-insensitive)
    return typed_normalized == expected_normalized
```

### 5. Integration with Privacy Band System

**Reference:** ADR-0032-0038 (Privacy Band System)

**Automatic RED Band Detection:**

```python
async def execute_operation(operation: Operation):
    """
    All operations go through privacy band check
    RED band operations automatically trigger approval protocol
    """
    # Step 1: Classify privacy band (ADR-0032)
    privacy_band = classify_privacy_band(operation)

    # Step 2: If RED band, require approval
    if privacy_band == PrivacyBand.RED:
        approval_level = calculate_approval_level(operation)

        # Generate confirmation phrase
        phrase = generate_confirmation_phrase(operation)

        # Request approval from user
        approval = await request_red_band_approval(
            operation=operation,
            privacy_band=privacy_band,
            approval_level=approval_level,
            required_phrase=phrase,
        )

        if approval.action != ApprovalAction.APPROVE:
            raise OperationDenied("User denied RED band approval")

        # Validate phrase
        if not validate_confirmation_phrase(
            approval.confirmation_phrase_typed,
            phrase
        ):
            raise PhraseMismatch("Confirmation phrase incorrect")

    # Step 3: Execute operation
    result = await execute_unsafe(operation)

    # Step 4: Audit log (always for RED band)
    await log_red_band_audit(operation, approval, result)
```

### 6. Two-Person Rule Implementation

**Secondary Approver Flow:**

```python
async def request_two_person_approval(
    operation: Operation,
    primary_approver_id: str,
    required_phrase: str,
) -> RedBandApprovalResponse:
    """
    Two-person approval flow:
    1. Primary user types confirmation phrase
    2. System notifies secondary approver (email)
    3. Secondary approver reviews and approves/denies
    4. If both approve → execute operation
    """
    # Step 1: Primary approver types phrase
    primary_response = await request_approval_from_primary(
        operation=operation,
        required_phrase=required_phrase,
    )

    if primary_response.action != ApprovalAction.APPROVE:
        return primary_response  # Denied by primary

    # Step 2: Notify secondary approver (out-of-band)
    await notify_secondary_approver(
        operation=operation,
        primary_approver_id=primary_approver_id,
        notification_method="email",
    )

    # Step 3: Wait for secondary approval (timeout: 5 min)
    try:
        secondary_response = await wait_for_secondary_approval(
            operation=operation,
            timeout_sec=300,
        )
    except TimeoutError:
        logger.warning("secondary_approval_timeout",
                       operation=operation.type,
                       primary_approver=primary_approver_id)
        return RedBandApprovalResponse(
            approval_id=operation.approval_id,
            action=ApprovalAction.TIMEOUT,
        )

    # Step 4: Both approved → return success
    if secondary_response.action == ApprovalAction.APPROVE:
        return RedBandApprovalResponse(
            approval_id=operation.approval_id,
            action=ApprovalAction.APPROVE,
            confirmation_phrase_typed=primary_response.confirmation_phrase_typed,
            user_id=primary_approver_id,
            secondary_approver_id=secondary_response.user_id,
        )
    else:
        return secondary_response  # Denied by secondary
```

**Email Notification Template (FamilyOS - Spouse Approval):**

```
Subject: [K1 Family] Approval Needed from You

Hi Sarah,

Mike needs your approval for a high-risk action:

Operation: Delete 1,847 family photos from 2020
Requested by: Mike (Dad's phone)
Risk Level: HIGH
Privacy Band: RED (Family Photos)
Timestamp: 2025-10-14 14:32:45

Impact:
- Photos affected: 1,847
- Cannot be undone (no backup after deletion)
- Albums: "Emma's Birthday 2020", "Hawaii Vacation", "Christmas"

Mike has confirmed with phrase: "CONFIRM DELETE 1847 PHOTOS"

⚠️ These are precious family memories. Are you sure this is correct?

To approve this operation, click:
[Approve] [Deny]

Timeout: 5 minutes (auto-deny after 2:37 PM)

---
K1 Family Assistant
Security Log: audit-789xyz
```

### 7. Audit Trail to K0 Receipts

**Reference:** ADR-0038 (Audit Trail to K0 Receipts)

**Audit Log Schema:**

```python
@dataclass
class RedBandAuditRecord:
    """Full audit trail for RED band approvals (7-year retention)"""
    approval_id: str
    session_id: str
    timestamp: datetime

    # Operation details
    operation: str                        # "delete" | "transfer" | etc.
    operation_description: str
    affected_records: Optional[int]
    financial_amount_usd: Optional[float]
    affected_users: Optional[int]
    is_reversible: bool

    # Privacy & risk
    privacy_band: PrivacyBand
    approval_level: ApprovalLevel
    arbiter_risk_score: float

    # Approval details
    required_phrase: str
    confirmation_phrase_typed: str
    phrase_match: bool
    primary_approver_id: str
    secondary_approver_id: Optional[str]

    # Result
    approval_action: ApprovalAction       # APPROVE | DENY | TIMEOUT
    execution_result: str                 # "SUCCESS" | "FAILED"
    execution_duration_sec: Optional[float]
    error_message: Optional[str]

    # Metadata
    retention_years: int = 7              # Compliance requirement
    redacted_fields: List[str] = []       # PII redaction log

async def log_red_band_audit(
    operation: Operation,
    approval: RedBandApprovalResponse,
    result: OperationResult,
):
    """
    Write audit record to K0 receipts (ADR-0038)
    7-year retention for SOC2/ISO27001 compliance
    """
    audit_record = RedBandAuditRecord(
        approval_id=approval.approval_id,
        session_id=operation.session_id,
        timestamp=datetime.now(timezone.utc),
        operation=operation.type,
        operation_description=operation.description,
        affected_records=operation.record_count,
        financial_amount_usd=operation.amount_usd,
        privacy_band=operation.privacy_band,
        approval_level=operation.approval_level,
        arbiter_risk_score=operation.arbiter_risk_score,
        required_phrase=operation.required_phrase,
        confirmation_phrase_typed=approval.confirmation_phrase_typed,
        phrase_match=validate_confirmation_phrase(
            approval.confirmation_phrase_typed,
            operation.required_phrase
        ),
        primary_approver_id=approval.user_id,
        secondary_approver_id=approval.secondary_approver_id,
        approval_action=approval.action,
        execution_result=result.status,
        execution_duration_sec=result.duration_sec,
        error_message=result.error_message,
    )

    # Serialize to FlatBuffers
    fb_bytes = serialize_audit_record(audit_record)

    # Write to K0 receipts (durable, 7-year retention)
    await k0_client.write_receipt(
        event_type="red_band_approval",
        payload=fb_bytes,
        retention_years=7,
    )

    logger.info("red_band_audit_logged",
                approval_id=approval.approval_id,
                operation=operation.type,
                result=result.status)
```

### 8. User Experience Flow

**Agent-to-User Message (RED Band Approval Request):**

```json
{
  "type": "ClarificationRequest",
  "clarification_type": "RED_BAND_APPROVAL",
  "red_band_approval": {
    "approval_id": "approval-123abc",
    "operation": "delete",
    "operation_description": "Delete 1,847 family photos from 2020",
    "impact_summary": {
      "affected_items": 1847,
      "data_type": "photos",
      "albums": ["Emma's Birthday", "Hawaii Vacation", "Christmas"],
      "is_reversible": false,
      "estimated_duration_sec": 45
    },
    "privacy_band": "RED",
    "approval_level": "HIGH",
    "required_phrase": "CONFIRM DELETE 1847 PHOTOS",
    "two_person_required": false,
    "timeout_sec": 60,
    "arbiter_risk_score": 0.82
  }
}
```

**User-to-Agent Response (Approval):**

```json
{
  "type": "ClarificationResponse",
  "approval_id": "approval-123abc",
  "action": "APPROVE",
  "confirmation_phrase_typed": "confirm delete 1847 photos"
}
```

**UI Wireframe (Text-Based):**

```
┌─────────────────────────────────────────────────────┐
│ 🤖 K1 Family Assistant                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 🚨 HIGH RISK OPERATION DETECTED                    │
│                                                     │
│ This action will:                                   │
│ • Delete 1,847 family photos from 2020             │
│ • Cannot be undone (no backup)                     │
│ • Albums: Emma's Birthday, Hawaii, Christmas       │
│ • Estimated time: 45 seconds                       │
│                                                     │
│ Privacy Band: RED (Family Photos)                   │
│ Risk Score: 0.82 (HIGH)                            │
│                                                     │
│ ⚠️ To proceed, type EXACTLY:                        │
│                                                     │
│   "CONFIRM DELETE 1847 PHOTOS"                     │
│                                                     │
│ [________________________________]                  │
│                                                     │
│ Type 'cancel' to abort (timeout: 60s)              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Success Response:**

```
┌─────────────────────────────────────────────────────┐
│ 🤖 K1 Family Assistant                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ Authorization confirmed                          │
│                                                     │
│ Deleting photos...                                  │
│ [████████████████░░░░░░░░] 65% (1,200/1,847)       │
│                                                     │
│ Estimated time remaining: 15 seconds                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Phrase Mismatch (Wrong Phrase):**

```
┌─────────────────────────────────────────────────────┐
│ 🤖 K1 Family Assistant                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ❌ Incorrect confirmation phrase                    │
│                                                     │
│ You typed: "delete photos"                          │
│ Expected: "CONFIRM DELETE 1847 PHOTOS"             │
│                                                     │
│ Attempts remaining: 2/3                             │
│                                                     │
│ [________________________________]                  │
│                                                     │
│ Type 'cancel' to abort                              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Consequences

### Positive Consequences

**1. Prevents Accidental Destructive Actions:**
- ✅ **Forcing function** (typing phrase) makes user consciously confirm
- ✅ **No accidental clicks** (can't accidentally click "Yes" while reading)
- ✅ **Clear consequences** (user sees exactly what will happen)

**2. Compliance & Auditability:**
- ✅ **7-year audit trail** meets SOC2/ISO27001 requirements
- ✅ **Full forensic record** (who approved, when, what phrase, result)
- ✅ **Immutable logs** in K0 receipts (append-only)

**3. Two-Person Rule for CRITICAL Operations:**
- ✅ **Independent approval** prevents single-point-of-failure errors
- ✅ **Out-of-band notification** (email) prevents social engineering
- ✅ **Optional feature flag** (disabled by default) allows gradual rollout

**4. Integration with Existing Systems:**
- ✅ **Privacy Band integration** (ADR-0032-0038) automatic RED band detection
- ✅ **Arbiter integration** (ADR-0007c) risk scoring before approval
- ✅ **K0 Receipts integration** (ADR-0038) durable audit trail

### Negative Consequences & Mitigations

**1. User Friction for Legitimate Operations:**
- ⚠️ **Problem:** Typing exact phrase takes 10-30 seconds (slower than clicking button)
- ✅ **Mitigation:** Only for RED band operations (truly dangerous), normal operations unaffected
- ✅ **Trade-off:** Intentional friction prevents accidental harm (Norman's forcing functions)

**2. Phrase Mismatch Frustration:**
- ⚠️ **Problem:** User may mistype phrase ("delete 1.2m" vs "DELETE 1.2M RECORDS")
- ✅ **Mitigation:** Case-insensitive matching reduces errors
- ✅ **UX improvement:** Show phrase in copy-pasteable format

**3. Two-Person Rule Delays:**
- ⚠️ **Problem:** Waiting for second approver adds 1-5 minutes latency
- ✅ **Mitigation:** Optional feature flag (disabled by default), only for CRITICAL ops
- ✅ **Notification:** Email second approver immediately (5-min timeout)

**4. Audit Log Storage:**
- ⚠️ **Problem:** 7-year retention increases K0 storage (~1KB per approval)
- ✅ **Mitigation:** Compliance requirement (SOC2/ISO27001), cannot reduce retention
- ✅ **Compression:** FlatBuffers serialization reduces size

**5. Secondary Approver Unavailable:**
- ⚠️ **Problem:** Second approver on vacation/offline → operation blocked
- ✅ **Mitigation:** Configure backup approvers (fallback chain)
- ✅ **Escalation:** If no response in 5 min, notify admin

### Trade-Offs

| Aspect | Before ADR-0052b | After ADR-0052b | Trade-Off |
|--------|------------------|-----------------|-----------|
| **Safety** | Single "Yes" button | Explicit phrase typing | ✅ Higher safety, ⚠️ More friction |
| **Latency** | <1s approval | 10-30s typing phrase | ⚠️ Higher latency for RED band |
| **Compliance** | Basic event logs | 7-year audit trail | ✅ Better compliance, ⚠️ More storage |
| **Authorization** | Single user | Optional two-person | ✅ Stronger authorization, ⚠️ Delays |
| **Error Rate** | Accidental clicks common | Accidental approvals rare | ✅ Fewer errors, ⚠️ User friction |

---

## Performance Budgets

**ADR-0052b Performance Targets (P95):**

| Operation | Target Latency | Memory Budget | Notes |
|-----------|----------------|---------------|-------|
| **Phrase Validation** | <100ms | N/A | Case-insensitive string comparison |
| **Audit Log Write to K0** | <50ms | 1KB per approval | Async write, doesn't block user |
| **RED Band Approval Timeout** | 60s | N/A | User must respond within 60s |
| **Two-Person Approval Timeout** | 300s (5min) | N/A | Wait for second approver |
| **Email Notification Send** | <2s | N/A | Out-of-band, async |
| **Arbiter Risk Scoring** | <50ms | N/A | Pre-computed before approval prompt |

**Audit Trail Storage:**
- Audit record size: ~1KB per approval (FlatBuffers)
- Expected volume: 100 RED band approvals/day/user
- 7-year retention: 100 × 365 × 7 = 255K approvals = 255MB/user (manageable)

---

## Security & Privacy Considerations

**1. Audit Trail Immutability:**
- ✅ **Append-only K0 receipts** (ADR-0038) prevent tampering
- ✅ **Cryptographic hashing** ensures integrity
- ✅ **7-year retention** meets compliance requirements

**2. PII Redaction in Logs:**
- ✅ **Redact user names/accounts** in audit trail (keep user IDs)
- ✅ **Hash sensitive data** (e.g., account numbers)
- ✅ **Configurable redaction rules** per data type

**3. Two-Person Rule Security:**
- ✅ **Out-of-band notification** (email) prevents in-app social engineering
- ✅ **Role-based access** (only "manager" role can approve)
- ✅ **Timeout enforcement** (5 min max, auto-deny)
- ✅ **Audit both approvers** (log primary + secondary)

**4. Phrase Generation Security:**
- ✅ **No predictable phrases** (dynamically generated per operation)
- ✅ **Include operation-specific details** (record count, account number)
- ✅ **Case-insensitive but exact match required** (balance usability + security)

**5. Rate Limiting:**
- ✅ **Max 3 phrase attempts** per approval (prevent brute force)
- ✅ **10-second delay after 3 failures** (exponential backoff)
- ✅ **Lock account after 10 failed approvals** (suspicious activity)

---

## Metrics & Observability

**Success Metrics:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| **% RED Band Approvals Successful** | >90% | Users complete phrase correctly |
| **% Phrase Mismatch (First Try)** | <20% | Users type phrase correctly |
| **Average Approval Latency** | 15-30s | Time to type phrase |
| **Two-Person Approval Rate** | <5% | Only CRITICAL operations |
| **% Operations Denied** | 5-10% | Users change mind after seeing impact |
| **Audit Trail Coverage** | 100% | Every RED band approval logged |

**Prometheus Metrics:**

```yaml
# RED band approval metrics
red_band_approval_requests_total:
  type: counter
  labels: [operation_type, approval_level, result]
  description: "Total RED band approval requests"

red_band_approval_latency_seconds:
  type: histogram
  buckets: [10, 20, 30, 45, 60]
  labels: [operation_type]
  description: "Time user takes to approve RED band operation"

red_band_phrase_mismatch_total:
  type: counter
  labels: [operation_type, attempt_number]
  description: "Phrase mismatch count by attempt (1st, 2nd, 3rd)"

two_person_approval_latency_seconds:
  type: histogram
  buckets: [30, 60, 120, 180, 300]
  description: "Time for second approver to respond"

red_band_audit_records_written_total:
  type: counter
  labels: [operation_type, result]
  description: "Audit records written to K0"
```

**Structured Logging:**

```python
logger.info("red_band_approval_requested",
            approval_id=approval.approval_id,
            operation=operation.type,
            approval_level=approval_level.name,
            privacy_band=privacy_band.name,
            arbiter_risk_score=arbiter_score,
            required_phrase=required_phrase)

logger.info("red_band_approval_completed",
            approval_id=approval.approval_id,
            action=approval.action.name,
            phrase_match=phrase_match,
            approval_latency_sec=latency)

logger.warning("red_band_phrase_mismatch",
               approval_id=approval.approval_id,
               typed=typed_phrase,
               expected=required_phrase,
               attempt=attempt_number)
```

---

## Testing Strategy

### Unit Tests (WARD)

```python
from ward import test

@test("RED band approval: correct phrase (case-insensitive)")
async def _():
    operation = create_delete_operation(record_count=1_200_000)
    required_phrase = "CONFIRM DELETE 1.2M RECORDS"

    # User types lowercase
    typed_phrase = "confirm delete 1.2m records"

    match = validate_confirmation_phrase(typed_phrase, required_phrase)
    assert match is True

@test("RED band approval: wrong phrase")
async def _():
    required_phrase = "CONFIRM DELETE 1.2M RECORDS"
    typed_phrase = "delete records"

    match = validate_confirmation_phrase(typed_phrase, required_phrase)
    assert match is False

@test("RED band approval: timeout after 60s")
async def _():
    operation = create_delete_operation(record_count=1_000_000)

    # User doesn't respond
    with timeout(61):  # 60s + 1s buffer
        approval = await request_red_band_approval(operation)

    assert approval.action == ApprovalAction.TIMEOUT

@test("two-person approval: both approve")
async def _():
    operation = create_critical_operation()

    # Primary approves
    primary_approval = await approve_as_primary(operation, phrase="CONFIRM DEPLOY PROD")

    # Secondary approves
    secondary_approval = await approve_as_secondary(operation)

    assert primary_approval.action == ApprovalAction.APPROVE
    assert secondary_approval.action == ApprovalAction.APPROVE

@test("two-person approval: secondary denies")
async def _():
    operation = create_critical_operation()

    # Primary approves
    await approve_as_primary(operation, phrase="CONFIRM DEPLOY PROD")

    # Secondary DENIES
    secondary_approval = await deny_as_secondary(operation)

    assert secondary_approval.action == ApprovalAction.DENY
```

### Integration Tests

```python
@test("RED band approval: full flow with audit trail")
async def _():
    operation = create_delete_operation(record_count=1_200_000)

    # Request approval
    approval = await request_red_band_approval(operation)

    # User approves with correct phrase
    response = RedBandApprovalResponse(
        approval_id=approval.approval_id,
        action=ApprovalAction.APPROVE,
        confirmation_phrase_typed="confirm delete 1.2m records",
    )

    # Execute operation
    result = await execute_operation(operation, response)

    # Verify audit trail written to K0
    audit_records = await k0_client.query_receipts(
        event_type="red_band_approval",
        limit=1
    )

    assert len(audit_records) == 1
    assert audit_records[0].approval_id == approval.approval_id
    assert audit_records[0].execution_result == "SUCCESS"
```

---

## Implementation Checklist

**Phase 1: Schema & Data Structures (Week 1)**
- [ ] Add `RED_BAND_APPROVAL` enum to `ClarificationType`
- [ ] Define FlatBuffers schema for `RedBandApprovalRequest/Response`
- [ ] Create `RedBandAuditRecord` data structure
- [ ] Implement phrase generation logic

**Phase 2: Approval Level Calculation (Week 2)**
- [ ] Integrate with Privacy Band system (ADR-0032-0038)
- [ ] Integrate with Arbiter risk scoring (ADR-0007c)
- [ ] Implement approval level decision logic
- [ ] Add configuration file (`red_band_approval.yml`)

**Phase 3: Phrase Validation (Week 3)**
- [ ] Implement case-insensitive phrase matching
- [ ] Add phrase retry limit (3 attempts)
- [ ] Implement timeout handling (60s)
- [ ] Add phrase mismatch logging

**Phase 4: Two-Person Rule (Week 4)**
- [ ] Implement secondary approver notification (email)
- [ ] Add role-based access control (manager role)
- [ ] Implement 5-minute timeout for second approver
- [ ] Add fallback approver chain

**Phase 5: Audit Trail Integration (Week 5)**
- [ ] Integrate with K0 receipts (ADR-0038)
- [ ] Implement 7-year retention policy
- [ ] Add PII redaction logic
- [ ] Test audit trail integrity

**Phase 6: WebSocket Protocol & UI (Week 6)**
- [ ] Add `RedBandApprovalRequest` message to WebSocket
- [ ] Add `RedBandApprovalResponse` message handling
- [ ] Implement UI wireframes (text + visual)
- [ ] Test full approval flow end-to-end

**Phase 7: Testing & Observability (Week 7)**
- [ ] Add Prometheus metrics
- [ ] Add structured logging
- [ ] WARD unit tests (phrase validation, timeout)
- [ ] WARD integration tests (audit trail, two-person)

---

## Related Work & Research Evidence

**1. Norman's Design of Everyday Things (1988)**
- **Source:** Chapter 5 - Human Error
- **Application:** Explicit phrase typing as forcing function

**2. Two-Person Rule (Military/Nuclear)**
- **Source:** US Nuclear Launch Protocols
- **Application:** CRITICAL operations require 2 independent approvers

**3. Reason's Swiss Cheese Model (1990)**
- **Source:** "Human Error" - Cambridge University Press
- **Application:** Multiple defense layers (arbiter + approval + audit)

**4. NIST Cybersecurity Framework (2018)**
- **Source:** NIST Special Publication 800-53
- **Application:** Audit trail for compliance

**5. SOC2 Type II & ISO27001**
- **Source:** AICPA Trust Services Criteria
- **Application:** 7-year log retention requirement

---

## References

**ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md)
- [ADR-0032-0038: Privacy Band System](0032-band-based-egress-rules.md)
- [ADR-0038: Audit Trail to K0 Receipts](0038-audit-trail-to-k0-receipts.md)
- [ADR-0007c: Arbiter Safety Validation](0007c-arbiter-safety-validation.md)

**Source Documents:**
- [HITL_MESSAGE_FLOW_ANALYSIS.md](../../HITL_MESSAGE_FLOW_ANALYSIS.md) - Gap 2 (RED Band Approval)
- [whiteboard.md](../../whiteboard.md) - Privacy Band system

---

**Document Status:** ✅ **ACCEPTED** (2025-10-14)

**Next Steps:**
1. Implement FlatBuffers schema (Week 1)
2. Integrate with Privacy Band system (Week 2)
3. Add phrase validation logic (Week 3)
4. Implement two-person rule (Week 4)
5. K0 audit trail integration (Week 5)
6. WebSocket protocol & UI (Week 6)
7. WARD integration tests (Week 7)

---

**END OF ADR-0052b**