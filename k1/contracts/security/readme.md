# Security Contracts

**Source ADRs:** ADR-0007, ADR-0007a-d, ADR-0008, ADR-0008a-c

## Overview

This directory contains security contracts for K1, including capability-based access control, privacy bands, arbiter approval, and cryptographic policies.

## Research Foundation

- **Capabilities (Dennis & Van Horn 1966):** Fine-grained access control without ambient authority
- **Least Privilege Principle:** Minimal permissions required for operation
- **Zero Trust Architecture:** Never trust, always verify

## Contracts Included

### 1. Capability System Contract (`capabilities.yaml`)
- **Source:** ADR-0007a
- Capability types (TOOL_CALL, PLANNING, K0_READ, K0_WRITE, etc.)
- Capability attestation and verification
- Capability revocation

### 2. Privacy Bands Contract (`privacy_bands.yaml`)
- **Source:** ADR-0007b
- GREEN: Public data (no restrictions)
- AMBER: Sensitive data (logging required)
- RED: Highly sensitive (arbiter approval required)

### 3. Arbiter Approval Contract (`arbiter.yaml`)
- **Source:** ADR-0007c
- Human-in-the-loop approval for RED operations
- Approval request format
- Timeout and fallback handling

### 4. Audit Logging Contract (`audit_logging.yaml`)
- **Source:** ADR-0007d
- Comprehensive audit trail
- PII redaction
- Retention policies

### 5. Cryptographic Policies Contract (`cryptography.yaml`)
- **Source:** ADR-0008, ADR-0008a-c
- Encryption at rest and in transit
- Key management
- Hashing and signing policies

## Capability System

**Source:** ADR-0007a

```yaml
capability_system:
  principle: |
    Capabilities grant specific permissions.
    Actors have NO ambient authority.
    All operations require explicit capabilities.

  capability_types:
    TOOL_CALL:
      description: Permission to invoke external tools
      scope: specific_tool_id or wildcard

    PLANNING:
      description: Permission to generate plans
      scope: null

    K0_READ:
      description: Permission to read from K0
      scope: specific_store or wildcard

    K0_WRITE:
      description: Permission to write to K0
      scope: specific_store or wildcard

    ORCHESTRATE:
      description: Permission to orchestrate other agents
      scope: null

    BARGE_IN:
      description: Permission to interrupt ongoing operations
      scope: session_id

    ARBITER_BYPASS:
      description: Permission to bypass arbiter approval (admin only)
      scope: null

  capability_structure:
    capability_id: string
    capability_type: CapabilityType
    scope: string | null
    granted_to: actor_id
    granted_by: issuer_id
    granted_at: timestamp
    expires_at: timestamp | null
    revoked: boolean
```

### Capability Verification

```yaml
capability_verification:
  before_operation:
    - Extract required capabilities for operation
    - Retrieve actor's granted capabilities
    - Check if required ⊆ granted
    - Check capability not expired
    - Check capability not revoked
    - Check scope matches (if applicable)

  verification_latency_p95_ms: 1

  failure_handling:
    missing_capability:
      error: PermissionDenied
      log: capability_denied{actor_id, operation, required_cap}
      alert: unauthorized_access_attempt{actor_id}

    expired_capability:
      error: CapabilityExpired
      action: request_renewal

    revoked_capability:
      error: CapabilityRevoked
      action: deny_operation
```

### Capability Attestation

```yaml
capability_attestation:
  description: Prove actor possesses capability

  challenge_response:
    - Verifier sends challenge
    - Actor signs challenge with capability token
    - Verifier validates signature

  token_format:
    capability_id: string
    capability_type: CapabilityType
    scope: string | null
    signature: base64

  cryptographic_binding:
    algorithm: Ed25519
    key_derivation: actor_id + capability_id
```

## Privacy Bands

**Source:** ADR-0007b

```yaml
privacy_bands:
  GREEN:
    description: Public or non-sensitive data
    restrictions: None
    logging: Optional
    examples:
      - Public website content
      - General knowledge queries
      - Non-PII metadata

  AMBER:
    description: Sensitive but not highly restricted
    restrictions: Logging required
    logging: Mandatory
    examples:
      - User preferences
      - Session history (anonymized)
      - Tool usage patterns

  RED:
    description: Highly sensitive, requires approval
    restrictions: Arbiter approval + comprehensive logging
    logging: Mandatory with full audit trail
    examples:
      - PII (name, email, address)
      - Financial data
      - Health information
      - Authentication credentials

classification_rules:
  default_band: AMBER

  automatic_classification:
    - PII detected: RED
    - External tool call: AMBER
    - K0 write: AMBER
    - Plan modification: AMBER
    - User profile access: RED

  declassification:
    - Requires explicit approval
    - Only downgrade (RED→AMBER→GREEN), never upgrade
    - Logged with justification
```

### Privacy Band Enforcement

```yaml
privacy_enforcement:
  GREEN:
    checks: none
    approval: not_required
    logging: optional

  AMBER:
    checks:
      - Verify operation is logged
      - Check SessionState tracking enabled
    approval: not_required
    logging: required

  RED:
    checks:
      - Verify arbiter approval obtained
      - Verify comprehensive logging enabled
      - Check PII redaction configured
    approval: required
    logging: required_with_full_context
    timeout_ms: 30000

    fallback:
      - If no approval within 30s: deny operation
      - Alert: arbiter_timeout{operation, actor_id}
```

## Arbiter Approval

**Source:** ADR-0007c

```yaml
arbiter_approval:
  trigger_conditions:
    - Operation privacy_band == RED
    - Plan contains RED steps
    - Direct PII access requested
    - Irreversible operation (e.g., delete data)

  approval_request:
    operation: string
    actor_id: string
    justification: string
    risk_level: LOW | MEDIUM | HIGH | CRITICAL
    data_accessed: [string]
    alternatives: [string]
    timeout_ms: 30000

  approval_response:
    approved: boolean
    conditions: [string]
    rejection_reason: string | null
    expires_at: timestamp | null

  arbiter_types:
    human:
      latency: 5000-30000ms
      availability: business_hours
      use_case: HIGH and CRITICAL risk

    automated:
      latency: <100ms
      availability: 24/7
      use_case: LOW and MEDIUM risk with clear rules

  timeout_handling:
    - Default: deny operation
    - Optional: allow with elevated logging (configurable)
    - Alert: arbiter_approval_timeout{operation}
```

## Audit Logging

**Source:** ADR-0007d

```yaml
audit_logging:
  log_events:
    - All RED operations (approved or denied)
    - All AMBER operations
    - Capability grants and revocations
    - Arbiter approval requests and responses
    - Authentication and authorization events
    - Data access (K0 reads/writes)
    - Tool invocations
    - Plan generations and executions

  log_format:
    timestamp: iso8601
    event_type: string
    actor_id: string
    operation: string
    privacy_band: GREEN | AMBER | RED
    outcome: SUCCESS | FAILURE | DENIED
    trace_id: string
    metadata: object
    pii_redacted: boolean

  pii_redaction:
    enabled: true
    patterns:
      - email: "[EMAIL_REDACTED]"
      - phone: "[PHONE_REDACTED]"
      - ssn: "[SSN_REDACTED]"
      - credit_card: "[CC_REDACTED]"
      - ip_address: "[IP_REDACTED]"

  retention_policy:
    GREEN: 30 days
    AMBER: 90 days
    RED: 365 days (1 year)

  storage:
    location: Secure audit log store (immutable)
    encryption: AES-256-GCM
    integrity: Hash chain for tamper detection

  access_control:
    read: Admin + Security Auditor roles only
    write: System only (no manual edits)
    delete: Not allowed (immutable)
```

## Cryptographic Policies

**Source:** ADR-0008, ADR-0008a-c

```yaml
cryptography:
  encryption_at_rest:
    algorithm: AES-256-GCM
    key_rotation: 90 days
    key_storage: Hardware Security Module (HSM) or secure key vault
    scope:
      - SessionState in K0
      - Audit logs
      - PII fields
      - Tool credentials

  encryption_in_transit:
    protocol: TLS 1.3
    cipher_suites:
      - TLS_AES_256_GCM_SHA384
      - TLS_CHACHA20_POLY1305_SHA256
    certificate_validation: Required
    scope:
      - K0-K1 Bridge (all ports)
      - WebSocket connections
      - SSE connections
      - External tool calls

  key_management:
    key_derivation: HKDF-SHA256
    key_hierarchy:
      - Master key (HSM-stored)
      - Session keys (ephemeral)
      - Capability tokens (Ed25519)

    key_rotation:
      master_key: 365 days
      session_keys: per_session
      capability_tokens: 30 days

  hashing:
    algorithm: SHA-256
    use_cases:
      - Content addressable storage
      - Integrity verification
      - Deduplication

  signing:
    algorithm: Ed25519
    use_cases:
      - Capability attestation
      - Audit log integrity
      - Message authentication
```

## Threat Model

```yaml
threat_model:
  threats:
    unauthorized_access:
      mitigation: Capability-based access control
      residual_risk: LOW

    privilege_escalation:
      mitigation: Least privilege + capability verification
      residual_risk: LOW

    data_exfiltration:
      mitigation: Privacy bands + audit logging
      residual_risk: MEDIUM

    replay_attacks:
      mitigation: Nonce + timestamp in messages
      residual_risk: LOW

    man_in_the_middle:
      mitigation: TLS 1.3 + certificate pinning
      residual_risk: LOW

    insider_threat:
      mitigation: Comprehensive audit logging + arbiter approval
      residual_risk: MEDIUM
```

## Performance Requirements

```yaml
performance:
  capability_verification_latency_p95_ms: 1
  arbiter_approval_latency_p95_ms: 5000
  audit_log_write_latency_p95_ms: 10
  encryption_overhead_percent: <5
```

## Observability

```yaml
observability:
  metrics:
    - capability_verification_total{actor_id, outcome}
    - arbiter_approval_total{operation, outcome}
    - audit_log_write_total
    - unauthorized_access_total{actor_id}
    - privacy_band_violation_total{band}

  alerts:
    - UnauthorizedAccessAttempt: rate > 5/min
    - ArbiterApprovalDenied: rate > 10% for 5 min
    - CapabilityVerificationFailure: rate > 1% for 5 min
    - AuditLogWriteFailure: any failure
```

## Related Contracts

- Agent Lifecycle: `../agent_lifecycle/`
- Planning: `../planning/`
- Tools: `../tools/`
- Observability: `../observability/`

---

**Last Updated:** 2025-10-13
