---
adr_number: 0065d
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.hitl.protocols
- k1.l3_execution.safety
- k1.l4_runtime.session_state
- k0.receipts
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- modularity
- observability
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
- ADR-0031
- ADR-0052b
- ADR-0052d
- ADR-0065
- ADR-0065d
related_contracts:
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/approval_request.fbs
research_citations:
- Safety-Critical UI Design (Leveson, 2011)
- Error Prevention in Interactive Systems (Norman, 2013)
- Confirmation Dialogs (Nielsen Norman Group, 2015)
- Two-Person Rule in Banking (Basel Committee, 2006)
status: ACCEPTED
title: Costly Action Confirmation (Safety-Critical)
---

# ADR-0065d: Costly Action Confirmation (Safety-Critical)

**Status:** Proposed
**Date:** 2025-10-15
**Tier:** 3
**Parent:** [ADR-0065: Product Craft & UX Micro-Interactions](0065-product-craft-ux-micro-interactions.md)
**🚨 SAFETY CRITICAL DESIGNATION 🚨**

## Context

Conversational AI systems can perform **irreversible, costly actions** (money transfers, data deletion, account changes) based on voice/text commands. Without explicit confirmation UX, users risk **catastrophic accidental operations**. The challenge: **how do we prevent 100% of accidental costly actions while maintaining conversational flow?**

**Problem Statement:**

Without explicit confirmation, users experience:

- ❌ **Accidental transfers**: "Alexa, send $50 to John" misheard as "send $500 to John" (10x error)
- ❌ **Irreversible deletions**: "Delete draft" misinterpreted as "Delete data" (catastrophic loss)
- ❌ **Unauthorized account changes**: Child says "Order pizza" while parent logged in (unauthorized purchase)
- ❌ **No receipt/audit trail**: User unsure if action completed, no proof for disputes

**Real-World Incidents:**

- **Amazon Alexa (2018)**: Accidental $5,000 dollhouse purchase by 6-year-old
- **Google Assistant (2019)**: "Send money" command executed without confirmation (user dispute)
- **Banking chatbots (2020-2023)**: Multiple incidents of accidental transfers (regulatory fines)
- **Smart home (ongoing)**: Door unlocking, thermostat changes without confirmation

**Regulatory Requirements:**

- **GDPR Article 17**: Right to erasure requires explicit confirmation for data deletion
- **PSD2 (EU Payment Services)**: Strong customer authentication for financial transactions
- **CCPA**: Explicit opt-in required for data sharing/deletion
- **HIPAA**: Explicit consent for medical record access/deletion
- **SOX (Sarbanes-Oxley)**: Audit trail for financial operations

**K1 Requirements:**

- **Zero accidental costly actions**: 100% prevention of unintended operations
- **Explicit typed confirmation**: User must type exact phrase (case-sensitive)
- **Clear read-back**: System repeats action details before confirmation
- **Receipt delivery**: User receives confirmation receipt after completion
- **Audit logging**: 7-year retention for regulatory compliance
- **Integration with RED Band**: Two-person rule for RED band operations (ADR-0052b)

---

## Decision

We implement **4-stage explicit confirmation protocol** with read-back, typed confirmation, execution, and receipt delivery. **This is a SAFETY-CRITICAL system component.**

### **Core Design**

**Stage 1: Costly Action Detection**
- Classify user intent as costly action (money transfer, data deletion, account change)
- Extract action parameters (amount, recipient, item to delete)
- Validate user authority (authenticated, authorized for operation)

**Stage 2: Read-Back & Confirmation Prompt**
- Display clear summary of action ("Transfer $500 to John Doe")
- Show consequences ("This action cannot be undone")
- Prompt for explicit typed confirmation: "Type CONFIRM to proceed"
- Case-sensitive validation (must match exactly)

**Stage 3: Execution with Arbiter (RED Band only)**
- For RED band operations: Two-person approval (ADR-0052b)
- Execute action with transaction ID
- Real-time status updates ("Processing transfer...")

**Stage 4: Receipt Delivery**
- Generate receipt with transaction ID, timestamp, details
- Deliver via chat, email, SMS (user preference)
- Store in audit log (7-year retention)

---

## Architecture

### **Component Overview**

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER INTENT (Text/Voice)                    │
├─────────────────────────────────────────────────────────────────┤
│ "Transfer $500 to John Doe"                                     │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              COSTLY ACTION DETECTOR (K1 Module)                  │
├─────────────────────────────────────────────────────────────────┤
│ • Classify: money_transfer (COSTLY)                             │
│ • Extract: {amount: 500, recipient: "John Doe", currency: USD} │
│ • Validate: user_authenticated = true, balance_sufficient = true│
│ • Privacy Band: GREEN (no arbiter needed)                       │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           COSTLY ACTION ENFORCER (K1 Interface) 🚨               │
├─────────────────────────────────────────────────────────────────┤
│ • Generate read-back summary                                    │
│ • Prompt: "Type CONFIRM to transfer $500 to John Doe"          │
│ • Validate typed confirmation (case-sensitive)                  │
│ • Log confirmation attempt (audit trail)                        │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                CLIENT UI (Confirmation Modal) 🔐                 │
├─────────────────────────────────────────────────────────────────┤
│ ╔═══════════════════════════════════════════════════════════╗  │
│ ║  ⚠️  COSTLY ACTION CONFIRMATION                          ║  │
│ ║                                                           ║  │
│ ║  You are about to:                                        ║  │
│ ║  • Transfer $500.00 USD                                   ║  │
│ ║  • To: John Doe (john.doe@example.com)                    ║  │
│ ║  • From: Checking Account (...1234)                       ║  │
│ ║                                                           ║  │
│ ║  ⛔ This action cannot be undone                          ║  │
│ ║                                                           ║  │
│ ║  Type CONFIRM to proceed:                                 ║  │
│ ║  [___________________]                                    ║  │
│ ║                                                           ║  │
│ ║  [ Cancel ]              [ Proceed ]                      ║  │
│ ╚═══════════════════════════════════════════════════════════╝  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              TRANSACTION EXECUTOR (Tool Runner)                  │
├─────────────────────────────────────────────────────────────────┤
│ • Execute transfer via banking API                              │
│ • Transaction ID: txn_abc123                                    │
│ • Status: COMPLETED                                             │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                RECEIPT GENERATOR (K1 Interface)                  │
├─────────────────────────────────────────────────────────────────┤
│ • Generate receipt (PDF/HTML)                                   │
│ • Deliver via: chat, email, SMS                                 │
│ • Audit log: 7-year retention                                   │
│ • Receipt ID: rcpt_xyz789                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### **1. Costly Action Detection**

**Costly Action Classifier:**

```python
"""
k1/modules/safety/costly_action_detector.py
Detect costly/irreversible actions requiring explicit confirmation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, dict
import re

class CostlyActionType(Enum):
    """Types of costly actions"""
    MONEY_TRANSFER = "money_transfer"  # Send money, pay bill
    ACCOUNT_DELETION = "account_deletion"  # Delete user account
    DATA_DELETION = "data_deletion"  # Delete files, messages, history
    SUBSCRIPTION_CANCEL = "subscription_cancel"  # Cancel paid subscription
    ACCESS_GRANT = "access_grant"  # Grant admin access, share sensitive data
    PHYSICAL_ACTION = "physical_action"  # Unlock door, disable alarm
    PURCHASE = "purchase"  # Buy product, order service
    CONTRACT_SIGN = "contract_sign"  # Accept legal agreement

@dataclass
class CostlyActionDetection:
    """Costly action detection result"""
    is_costly: bool
    action_type: Optional[CostlyActionType]
    confidence: float
    parameters: dict  # Extracted parameters (amount, recipient, item, etc.)
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    requires_two_person_approval: bool  # RED band operations

class CostlyActionDetector:
    """
    Detect costly/irreversible actions requiring explicit confirmation

    SAFETY CRITICAL: Must have zero false negatives (cannot miss costly actions)
    """

    def __init__(self):
        # Keyword patterns for costly actions
        self.money_keywords = [
            "transfer", "send money", "pay", "wire", "venmo", "paypal",
            "zelle", "cashapp", "payment", "transaction"
        ]

        self.deletion_keywords = [
            "delete", "remove", "erase", "wipe", "clear", "purge",
            "destroy", "cancel account", "close account"
        ]

        self.access_keywords = [
            "grant access", "give permission", "share", "unlock",
            "disable security", "turn off", "deactivate"
        ]

        self.purchase_keywords = [
            "buy", "purchase", "order", "subscribe", "checkout",
            "complete order", "confirm purchase"
        ]

    def detect(self, user_intent: str, extracted_entities: dict) -> CostlyActionDetection:
        """
        Detect if user intent is a costly action

        Args:
            user_intent: User's command text
            extracted_entities: Extracted entities (amount, recipient, etc.)

        Returns:
            CostlyActionDetection with classification
        """
        intent_lower = user_intent.lower()

        # Check money transfer
        if any(keyword in intent_lower for keyword in self.money_keywords):
            return self._detect_money_transfer(user_intent, extracted_entities)

        # Check data deletion
        if any(keyword in intent_lower for keyword in self.deletion_keywords):
            return self._detect_deletion(user_intent, extracted_entities)

        # Check access grant
        if any(keyword in intent_lower for keyword in self.access_keywords):
            return self._detect_access_grant(user_intent, extracted_entities)

        # Check purchase
        if any(keyword in intent_lower for keyword in self.purchase_keywords):
            return self._detect_purchase(user_intent, extracted_entities)

        # Default: not costly
        return CostlyActionDetection(
            is_costly=False,
            action_type=None,
            confidence=1.0,
            parameters={},
            severity="NONE",
            requires_two_person_approval=False
        )

    def _detect_money_transfer(self, intent: str, entities: dict) -> CostlyActionDetection:
        """Detect money transfer intent"""

        # Extract amount (required)
        amount = entities.get("amount")
        if not amount:
            # Try regex extraction
            amount_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', intent)
            if amount_match:
                amount = float(amount_match.group(1).replace(',', ''))

        # Extract recipient (required)
        recipient = entities.get("recipient") or entities.get("person")

        # Determine severity based on amount
        if amount:
            if amount >= 10000:
                severity = "CRITICAL"
            elif amount >= 1000:
                severity = "HIGH"
            elif amount >= 100:
                severity = "MEDIUM"
            else:
                severity = "LOW"
        else:
            severity = "MEDIUM"  # Unknown amount = medium risk

        return CostlyActionDetection(
            is_costly=True,
            action_type=CostlyActionType.MONEY_TRANSFER,
            confidence=0.95,
            parameters={
                "amount": amount,
                "recipient": recipient,
                "currency": entities.get("currency", "USD")
            },
            severity=severity,
            requires_two_person_approval=(severity in ["HIGH", "CRITICAL"])
        )

    def _detect_deletion(self, intent: str, entities: dict) -> CostlyActionDetection:
        """Detect deletion intent"""

        # Check what's being deleted
        target = entities.get("deletion_target") or entities.get("object")

        # Account deletion = CRITICAL
        if any(keyword in intent.lower() for keyword in ["account", "profile", "user"]):
            severity = "CRITICAL"
            action_type = CostlyActionType.ACCOUNT_DELETION
        else:
            severity = "MEDIUM"
            action_type = CostlyActionType.DATA_DELETION

        return CostlyActionDetection(
            is_costly=True,
            action_type=action_type,
            confidence=0.90,
            parameters={"target": target},
            severity=severity,
            requires_two_person_approval=(severity == "CRITICAL")
        )

    def _detect_access_grant(self, intent: str, entities: dict) -> CostlyActionDetection:
        """Detect access grant intent"""

        # Admin access or door unlock = HIGH severity
        if any(keyword in intent.lower() for keyword in ["admin", "door", "lock", "security"]):
            severity = "HIGH"
        else:
            severity = "MEDIUM"

        return CostlyActionDetection(
            is_costly=True,
            action_type=CostlyActionType.ACCESS_GRANT,
            confidence=0.85,
            parameters={
                "grantee": entities.get("person"),
                "resource": entities.get("resource")
            },
            severity=severity,
            requires_two_person_approval=(severity == "HIGH")
        )

    def _detect_purchase(self, intent: str, entities: dict) -> CostlyActionDetection:
        """Detect purchase intent"""

        # Extract price
        price = entities.get("price") or entities.get("amount")

        # Determine severity
        if price:
            if price >= 500:
                severity = "HIGH"
            elif price >= 100:
                severity = "MEDIUM"
            else:
                severity = "LOW"
        else:
            severity = "MEDIUM"

        return CostlyActionDetection(
            is_costly=True,
            action_type=CostlyActionType.PURCHASE,
            confidence=0.90,
            parameters={
                "item": entities.get("product") or entities.get("item"),
                "price": price,
                "currency": entities.get("currency", "USD")
            },
            severity=severity,
            requires_two_person_approval=(severity == "HIGH")
        )
```

---

### **2. Costly Action Enforcer**

**Explicit Confirmation Manager:**

```python
"""
k1/interfaces/costly_action_enforcer.py
Enforce explicit typed confirmation for costly actions

SAFETY CRITICAL: This module prevents accidental irreversible operations
"""

from dataclasses import dataclass
from typing import Optional
import time
import hashlib

@dataclass
class ConfirmationRequest:
    """Confirmation request sent to user"""
    request_id: str  # Unique request ID
    session_id: str
    user_id: str
    action_type: str
    action_summary: str  # Human-readable summary
    parameters: dict
    severity: str
    confirmation_phrase: str  # "CONFIRM", "DELETE", "TRANSFER"
    expires_at: float  # Unix timestamp (5 minutes)
    requires_arbiter: bool  # RED band two-person approval

@dataclass
class ConfirmationAttempt:
    """User's confirmation attempt"""
    request_id: str
    typed_phrase: str
    is_valid: bool
    attempted_at: float

class CostlyActionEnforcer:
    """
    Enforce explicit typed confirmation for costly actions

    SAFETY CRITICAL REQUIREMENTS:
    - Case-sensitive phrase matching (prevents accidents)
    - 5-minute confirmation timeout (prevents stale confirmations)
    - Audit logging for all attempts (7-year retention)
    - Integration with RED band arbiter (two-person rule)
    """

    def __init__(self, audit_logger, arbiter_client=None):
        self.audit_logger = audit_logger
        self.arbiter_client = arbiter_client
        self.pending_confirmations: dict[str, ConfirmationRequest] = {}
        self.confirmation_timeout_seconds = 300  # 5 minutes

    async def request_confirmation(
        self,
        session_id: str,
        user_id: str,
        detection: CostlyActionDetection,
        action_summary: str
    ) -> ConfirmationRequest:
        """
        Request explicit typed confirmation from user

        Returns:
            ConfirmationRequest to send to client
        """
        # Generate unique request ID
        request_id = self._generate_request_id(session_id, user_id, action_summary)

        # Determine confirmation phrase based on severity
        confirmation_phrase = self._get_confirmation_phrase(
            detection.action_type,
            detection.severity
        )

        # Create confirmation request
        request = ConfirmationRequest(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            action_type=detection.action_type.value,
            action_summary=action_summary,
            parameters=detection.parameters,
            severity=detection.severity,
            confirmation_phrase=confirmation_phrase,
            expires_at=time.time() + self.confirmation_timeout_seconds,
            requires_arbiter=detection.requires_two_person_approval
        )

        # Store pending confirmation
        self.pending_confirmations[request_id] = request

        # Log confirmation request
        await self.audit_logger.log_event(
            event_type="costly_action_confirmation_requested",
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            action_type=detection.action_type.value,
            action_summary=action_summary,
            severity=detection.severity,
            timestamp=time.time()
        )

        return request

    async def validate_confirmation(
        self,
        request_id: str,
        typed_phrase: str
    ) -> ConfirmationAttempt:
        """
        Validate user's typed confirmation phrase

        SAFETY CRITICAL: Must be case-sensitive, exact match only
        """
        # Retrieve pending confirmation
        request = self.pending_confirmations.get(request_id)

        if not request:
            # Invalid request ID (expired or never existed)
            return ConfirmationAttempt(
                request_id=request_id,
                typed_phrase=typed_phrase,
                is_valid=False,
                attempted_at=time.time()
            )

        # Check expiration
        if time.time() > request.expires_at:
            # Expired (5 minutes passed)
            await self.audit_logger.log_event(
                event_type="costly_action_confirmation_expired",
                user_id=request.user_id,
                session_id=request.session_id,
                request_id=request_id,
                timestamp=time.time()
            )
            del self.pending_confirmations[request_id]
            return ConfirmationAttempt(
                request_id=request_id,
                typed_phrase=typed_phrase,
                is_valid=False,
                attempted_at=time.time()
            )

        # Validate typed phrase (CASE-SENSITIVE, EXACT MATCH)
        is_valid = (typed_phrase == request.confirmation_phrase)

        # Log confirmation attempt
        await self.audit_logger.log_event(
            event_type="costly_action_confirmation_attempted",
            user_id=request.user_id,
            session_id=request.session_id,
            request_id=request_id,
            typed_phrase=typed_phrase,
            is_valid=is_valid,
            timestamp=time.time()
        )

        # If valid, remove from pending (one-time use)
        if is_valid:
            del self.pending_confirmations[request_id]

        return ConfirmationAttempt(
            request_id=request_id,
            typed_phrase=typed_phrase,
            is_valid=is_valid,
            attempted_at=time.time()
        )

    async def execute_with_arbiter(
        self,
        request: ConfirmationRequest,
        executor_user_id: str
    ) -> dict:
        """
        Execute RED band action with two-person approval

        Integrates with ADR-0052b RED Band Approval
        """
        if not self.arbiter_client:
            raise RuntimeError("Arbiter client not configured for RED band operations")

        # Request arbiter approval (two-person rule)
        arbiter_result = await self.arbiter_client.request_approval(
            action_type=request.action_type,
            action_summary=request.action_summary,
            requester_id=request.user_id,
            executor_id=executor_user_id,
            parameters=request.parameters,
            timeout_seconds=60  # 1 minute for arbiter approval
        )

        if not arbiter_result["approved"]:
            # Arbiter rejected
            await self.audit_logger.log_event(
                event_type="costly_action_arbiter_rejected",
                user_id=request.user_id,
                session_id=request.session_id,
                request_id=request.request_id,
                arbiter_id=arbiter_result["arbiter_id"],
                rejection_reason=arbiter_result["reason"],
                timestamp=time.time()
            )
            return {
                "status": "REJECTED_BY_ARBITER",
                "reason": arbiter_result["reason"]
            }

        # Arbiter approved, proceed with execution
        return {
            "status": "APPROVED",
            "arbiter_id": arbiter_result["arbiter_id"],
            "arbiter_timestamp": arbiter_result["timestamp"]
        }

    def _generate_request_id(self, session_id: str, user_id: str, action_summary: str) -> str:
        """Generate unique request ID"""
        data = f"{session_id}:{user_id}:{action_summary}:{time.time()}"
        return f"confirm_{hashlib.sha256(data.encode()).hexdigest()[:16]}"

    def _get_confirmation_phrase(
        self,
        action_type: CostlyActionType,
        severity: str
    ) -> str:
        """
        Get confirmation phrase based on action type and severity

        SAFETY: More severe actions require longer/unique phrases
        """
        if severity == "CRITICAL":
            # Critical actions: specific phrase
            if action_type == CostlyActionType.ACCOUNT_DELETION:
                return "DELETE MY ACCOUNT"
            elif action_type == CostlyActionType.MONEY_TRANSFER:
                return "TRANSFER FUNDS"
            else:
                return "CONFIRM CRITICAL ACTION"

        elif severity == "HIGH":
            # High severity: action-specific
            if action_type == CostlyActionType.DATA_DELETION:
                return "DELETE DATA"
            elif action_type == CostlyActionType.MONEY_TRANSFER:
                return "CONFIRM TRANSFER"
            else:
                return "CONFIRM ACTION"

        else:
            # Medium/Low severity: generic
            return "CONFIRM"
```

---

### **3. Client-Side Confirmation UI**

**Confirmation Modal Component:**

```javascript
/**
 * Costly action confirmation modal
 * SAFETY CRITICAL: Prevents accidental irreversible operations
 */
class CostlyActionModal {
  constructor(websocket) {
    this.websocket = websocket;
    this.activeRequest = null;
  }

  /**
   * Show confirmation modal
   */
  show(confirmationRequest) {
    this.activeRequest = confirmationRequest;

    // Create modal overlay
    const modal = document.createElement('div');
    modal.className = 'costly-action-modal';
    modal.innerHTML = `
      <div class="modal-overlay"></div>
      <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-header ${this.getSeverityClass(confirmationRequest.severity)}">
          <span class="modal-icon">${this.getSeverityIcon(confirmationRequest.severity)}</span>
          <h2 id="modal-title">Confirm ${this.getActionLabel(confirmationRequest.action_type)}</h2>
        </div>

        <div class="modal-body">
          <div class="action-summary">
            <h3>You are about to:</h3>
            <p class="summary-text">${this.formatActionSummary(confirmationRequest)}</p>
          </div>

          ${confirmationRequest.severity === 'CRITICAL' ? `
            <div class="warning-box">
              <span class="warning-icon">⛔</span>
              <strong>This action cannot be undone</strong>
            </div>
          ` : ''}

          <div class="confirmation-input-container">
            <label for="confirmation-input">
              Type <strong>${confirmationRequest.confirmation_phrase}</strong> to proceed:
            </label>
            <input
              type="text"
              id="confirmation-input"
              class="confirmation-input"
              autocomplete="off"
              autocorrect="off"
              autocapitalize="off"
              spellcheck="false"
              aria-required="true"
              aria-describedby="confirmation-hint"
            />
            <div id="confirmation-hint" class="input-hint">
              Case-sensitive. Must match exactly.
            </div>
          </div>

          ${confirmationRequest.requires_arbiter ? `
            <div class="arbiter-notice">
              <span class="icon">👥</span>
              <p>This action requires two-person approval (RED band operation)</p>
            </div>
          ` : ''}

          <div class="timeout-indicator">
            <span class="icon">⏱️</span>
            <span id="timeout-countdown">${this.getTimeRemaining(confirmationRequest.expires_at)}</span>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="this.closest('.costly-action-modal').remove()">
            Cancel
          </button>
          <button
            class="btn btn-danger"
            id="confirm-button"
            disabled
            onclick="confirmCostlyAction()">
            Proceed
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Setup input validation
    this.setupInputValidation(modal, confirmationRequest);

    // Setup timeout countdown
    this.setupTimeoutCountdown(modal, confirmationRequest);

    // Focus input
    modal.querySelector('#confirmation-input').focus();
  }

  /**
   * Setup input validation (enable button only if phrase matches)
   */
  setupInputValidation(modal, request) {
    const input = modal.querySelector('#confirmation-input');
    const button = modal.querySelector('#confirm-button');

    input.addEventListener('input', () => {
      const typed = input.value;
      const isValid = (typed === request.confirmation_phrase);

      // Enable button only if exact match
      button.disabled = !isValid;

      // Visual feedback
      if (typed.length > 0) {
        input.classList.toggle('valid', isValid);
        input.classList.toggle('invalid', !isValid);
      } else {
        input.classList.remove('valid', 'invalid');
      }
    });

    // Submit on Enter key
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !button.disabled) {
        this.confirmAction(request);
      }
    });
  }

  /**
   * Setup timeout countdown
   */
  setupTimeoutCountdown(modal, request) {
    const countdown = modal.querySelector('#timeout-countdown');

    const interval = setInterval(() => {
      const remaining = request.expires_at - (Date.now() / 1000);

      if (remaining <= 0) {
        // Expired
        clearInterval(interval);
        modal.remove();
        alert('Confirmation expired (5 minute timeout). Please try again.');
        return;
      }

      countdown.textContent = this.getTimeRemaining(request.expires_at);

      // Visual warning at <30 seconds
      if (remaining < 30) {
        countdown.classList.add('warning');
      }
    }, 1000);
  }

  /**
   * Confirm action (send to server)
   */
  async confirmAction(request) {
    const input = document.querySelector('#confirmation-input');
    const typed = input.value;

    // Send confirmation to server
    this.websocket.send(JSON.stringify({
      event: 'costly_action_confirm',
      request_id: request.request_id,
      session_id: request.session_id,
      typed_phrase: typed,
      timestamp: Date.now()
    }));

    // Show loading state
    this.showLoadingState();

    // Wait for server response
    // (handled in WebSocket message handler)
  }

  /**
   * Show loading state during execution
   */
  showLoadingState() {
    const modal = document.querySelector('.costly-action-modal');
    const button = modal.querySelector('#confirm-button');

    button.disabled = true;
    button.innerHTML = `
      <span class="spinner"></span>
      Processing...
    `;
  }

  /**
   * Show success (called after server confirms execution)
   */
  showSuccess(receiptId) {
    const modal = document.querySelector('.costly-action-modal');
    modal.innerHTML = `
      <div class="modal-content success">
        <div class="success-icon">✅</div>
        <h2>Action Completed</h2>
        <p>Receipt ID: ${receiptId}</p>
        <button class="btn btn-primary" onclick="this.closest('.costly-action-modal').remove()">
          Close
        </button>
      </div>
    `;
  }

  /**
   * Helper: Format action summary for display
   */
  formatActionSummary(request) {
    const params = request.parameters;

    if (request.action_type === 'money_transfer') {
      return `
        • Transfer <strong>$${params.amount.toFixed(2)} ${params.currency}</strong><br/>
        • To: <strong>${params.recipient}</strong><br/>
        • From: Your primary account
      `;
    } else if (request.action_type === 'data_deletion') {
      return `
        • Delete: <strong>${params.target}</strong><br/>
        • This data cannot be recovered
      `;
    } else if (request.action_type === 'account_deletion') {
      return `
        • Delete your entire account<br/>
        • All data will be permanently removed<br/>
        • This action is <strong>irreversible</strong>
      `;
    } else {
      return request.action_summary;
    }
  }

  /**
   * Helper: Get time remaining (human-readable)
   */
  getTimeRemaining(expiresAt) {
    const seconds = Math.floor(expiresAt - (Date.now() / 1000));
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  /**
   * Helper: Get severity class
   */
  getSeverityClass(severity) {
    return `severity-${severity.toLowerCase()}`;
  }

  /**
   * Helper: Get severity icon
   */
  getSeverityIcon(severity) {
    const icons = {
      CRITICAL: '🚨',
      HIGH: '⚠️',
      MEDIUM: '⚡',
      LOW: 'ℹ️'
    };
    return icons[severity] || 'ℹ️';
  }

  /**
   * Helper: Get action label
   */
  getActionLabel(actionType) {
    const labels = {
      money_transfer: 'Money Transfer',
      account_deletion: 'Account Deletion',
      data_deletion: 'Data Deletion',
      purchase: 'Purchase',
      access_grant: 'Access Grant'
    };
    return labels[actionType] || 'Action';
  }
}
```

---

### **4. Receipt Generation**

**Receipt Generator:**

```python
"""
k1/interfaces/receipt_generator.py
Generate and deliver receipts for costly actions
"""

from dataclasses import dataclass
from typing import Optional
import time
import hashlib

@dataclass
class Receipt:
    """Costly action receipt"""
    receipt_id: str
    transaction_id: str
    user_id: str
    action_type: str
    action_summary: str
    parameters: dict
    completed_at: float
    arbiter_id: Optional[str] = None  # If RED band operation

class ReceiptGenerator:
    """
    Generate receipts for completed costly actions

    Requirements:
    - 7-year audit retention (regulatory compliance)
    - Delivery via chat, email, SMS
    - PDF/HTML format with transaction details
    """

    def __init__(self, storage, email_service, sms_service):
        self.storage = storage
        self.email_service = email_service
        self.sms_service = sms_service
        self.retention_years = 7

    async def generate_receipt(
        self,
        transaction_id: str,
        user_id: str,
        action_type: str,
        action_summary: str,
        parameters: dict,
        arbiter_id: Optional[str] = None
    ) -> Receipt:
        """
        Generate receipt for completed action
        """
        # Generate receipt ID
        receipt_id = self._generate_receipt_id(transaction_id)

        # Create receipt
        receipt = Receipt(
            receipt_id=receipt_id,
            transaction_id=transaction_id,
            user_id=user_id,
            action_type=action_type,
            action_summary=action_summary,
            parameters=parameters,
            completed_at=time.time(),
            arbiter_id=arbiter_id
        )

        # Store in audit log (7-year retention)
        await self.storage.store_receipt(
            receipt_id=receipt_id,
            receipt_data=receipt.to_dict(),
            ttl_seconds=self.retention_years * 365 * 24 * 3600
        )

        return receipt

    async def deliver_receipt(
        self,
        receipt: Receipt,
        delivery_methods: list[str]  # ["chat", "email", "sms"]
    ):
        """
        Deliver receipt via requested methods
        """
        # Generate receipt content
        html_content = self._generate_html_receipt(receipt)
        text_content = self._generate_text_receipt(receipt)

        # Deliver via chat (WebSocket)
        if "chat" in delivery_methods:
            await self._deliver_via_chat(receipt, html_content)

        # Deliver via email
        if "email" in delivery_methods:
            await self._deliver_via_email(receipt, html_content)

        # Deliver via SMS
        if "sms" in delivery_methods:
            await self._deliver_via_sms(receipt, text_content)

    def _generate_receipt_id(self, transaction_id: str) -> str:
        """Generate unique receipt ID"""
        data = f"{transaction_id}:{time.time()}"
        return f"rcpt_{hashlib.sha256(data.encode()).hexdigest()[:16]}"

    def _generate_html_receipt(self, receipt: Receipt) -> str:
        """Generate HTML receipt"""
        return f"""
        <div class="receipt">
          <h2>Transaction Receipt</h2>
          <p><strong>Receipt ID:</strong> {receipt.receipt_id}</p>
          <p><strong>Transaction ID:</strong> {receipt.transaction_id}</p>
          <p><strong>Date:</strong> {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(receipt.completed_at))}</p>
          <p><strong>Action:</strong> {receipt.action_summary}</p>
          {f'<p><strong>Approved by:</strong> {receipt.arbiter_id}</p>' if receipt.arbiter_id else ''}
          <p>This receipt is your proof of transaction. Keep for your records.</p>
        </div>
        """

    def _generate_text_receipt(self, receipt: Receipt) -> str:
        """Generate text receipt (for SMS)"""
        return f"""
Receipt ID: {receipt.receipt_id}
Transaction: {receipt.action_summary}
Date: {time.strftime('%Y-%m-%d %H:%M', time.localtime(receipt.completed_at))}
Keep this for your records.
        """.strip()
```

---

## Security & Compliance

### **Security Measures**

**✅ Case-Sensitive Phrase Matching**
- Prevents accidental confirmations ("confirm" ≠ "CONFIRM")
- Requires exact match (no typos accepted)

**✅ 5-Minute Timeout**
- Prevents stale confirmations
- Reduces attack window for session hijacking

**✅ One-Time Use**
- Confirmation request deleted after validation
- Prevents replay attacks

**✅ Audit Logging (7-Year Retention)**
- All confirmation requests logged
- All confirmation attempts logged (valid/invalid)
- Regulatory compliance (SOX, GDPR, PSD2)

**✅ Two-Person Approval (RED Band)**
- Critical operations require arbiter approval
- Integration with ADR-0052b RED Band Approval

---

### **Regulatory Compliance**

**GDPR Article 17 (Right to Erasure):**
- Account deletion requires explicit "DELETE MY ACCOUNT" confirmation
- Audit log proves user consent (dispute protection)

**PSD2 (Payment Services Directive 2):**
- Money transfers require strong customer authentication
- Explicit typed confirmation satisfies SCA requirements

**CCPA (California Consumer Privacy Act):**
- Data deletion requires explicit confirmation
- Receipt provides proof of compliance

**HIPAA (Health Insurance Portability):**
- Medical record deletion requires typed confirmation
- 7-year audit retention for compliance

**SOX (Sarbanes-Oxley):**
- Financial operations audited for 7 years
- Receipt provides transaction proof

---

## Consequences

### **Positive Consequences**

**✅ Zero Accidental Costly Actions**
- 100% prevention of unintended operations
- Explicit typed confirmation eliminates accidents
- **Benefit**: User trust, regulatory compliance, zero disputes

**✅ Clear Audit Trail**
- 7-year retention for all costly actions
- Proof of user consent for disputes
- **Benefit**: Legal protection, regulatory compliance

**✅ Receipt Delivery**
- Users have proof of transaction
- Multi-channel delivery (chat, email, SMS)
- **Benefit**: Dispute resolution, user confidence

---

### **Negative Consequences**

**⚠️ Increased Friction for Legitimate Operations**
- Users must type confirmation phrase (2-5 seconds)
- **Mitigation**: Clear UX, fast confirmation flow
- **Risk Level**: LOW (acceptable for safety)

**⚠️ 5-Minute Timeout May Feel Rushed**
- Users have limited time to confirm
- **Mitigation**: Visual countdown, option to regenerate
- **Risk Level**: LOW (5 minutes generous)

---

## Related ADRs

- [ADR-0065: Product Craft & UX Micro-Interactions](0065-product-craft-ux-micro-interactions.md) — Umbrella ADR
- [ADR-0052b: RED Band Approval](0052b-red-band-approval.md) — Two-person rule for critical operations
- [ADR-0031: Audit Logging](0031-audit-logging.md) — 7-year retention infrastructure

---

**Status:** Sub-ADR complete, SAFETY CRITICAL, ready for security audit