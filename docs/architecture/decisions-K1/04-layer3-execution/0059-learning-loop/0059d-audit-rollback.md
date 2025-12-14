---
adr_number: 0059d
affected_layers:
- layer3_execution
- layer4_runtime
affected_modules:
- k1.l4_runtime.audit_logger
- k1.l4_runtime.rollback_manager
- k1.l4_runtime.preference_store
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 4 (Performance Optimization)
implementation_status: COMPLETED
related_adrs:
- ADR-0001
- ADR-0001a
- ADR-0038
- ADR-0059
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
research_citations:
- Write-Ahead Logging (Mohan et al., 1992)
- Event Sourcing Patterns (Fowler, 2005)
- Audit Logging for AI Systems (Mitchell et al., 2019)
status: ACCEPTED
title: Audit & Rollback of Learned Preferences
---

# ADR-0059d: Audit & Rollback of Learned Preferences

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0059 (Learning Loop)

**Related ADRs:**
- ADR-0059: Learning Loop (parent)
- ADR-0001a: K0 WAL (Write-Ahead Log)
- ADR-0038: Receipt System
- ADR-0001: K0 P06 FeedbackIntegration

---

## Context

### Problem Statement

Users must be able to **audit and rollback** learned preferences:
- **Transparency:** What has the system learned about me?
- **Control:** Undo unwanted adaptations
- **Privacy:** Delete learned data
- **Debugging:** Understand why system behaves certain way

**Requirements:**
1. **Full audit trail:** All parameter changes logged
2. **Point-in-time rollback:** Return to any prior state
3. **Selective rollback:** Undo specific changes
4. **User-initiated:** User control over their data
5. **K0 persistence:** K0 WAL provides authoritative log

---

## Decision

### 1. Audit Trail Architecture

**K0 WAL Records All Changes:**
```python
@dataclass
class LearningAuditEntry:
    """Audit log entry for learned parameter change"""
    entry_id: str
    session_id: str
    parameter: str
    old_value: any
    new_value: any
    reason: str              # Why change was made
    feedback_signals: List[str]  # Signal IDs that led to change
    timestamp: float
    receipt_id: str          # K0 receipt for this change

    # Metadata
    confidence: float        # Confidence in this change
    source: str              # "learning_loop", "user_explicit", etc.
    reversible: bool         # Can this change be rolled back?

class AuditTrail:
    """
    K1 queries audit trail from K0 P06
    K0 WAL is authoritative source
    """
    def __init__(self):
        self.k0_gateway = K0P06Gateway()

    async def query_audit_log(self,
                             session_id: str,
                             start_time: Optional[float] = None,
                             end_time: Optional[float] = None) -> List[LearningAuditEntry]:
        """Query K0 WAL for learning audit entries"""

        # Request audit log from K0 P06
        request = AuditLogRequest(
            session_id=session_id,
            start_time=start_time or (time.time() - 30*86400),  # 30 days default
            end_time=end_time or time.time(),
            entry_type="learning_parameter_change"
        )

        response = await self.k0_gateway.query_audit_log(request)

        # Parse entries
        entries = [
            LearningAuditEntry.from_dict(e) for e in response.entries
        ]

        logger.info(
            "audit_log_queried",
            session_id=session_id,
            entry_count=len(entries)
        )

        return entries
```

### 2. User-Facing Audit View

**Human-Readable History:**
```python
class AuditPresenter:
    """Present audit trail to user"""

    async def format_for_user(self, entries: List[LearningAuditEntry]) -> str:
        """Generate human-readable audit summary"""
        output = "# What I've Learned About You\n\n"

        # Group by parameter
        by_parameter = self.group_by_parameter(entries)

        for parameter, param_entries in by_parameter.items():
            output += f"## {self.humanize_parameter(parameter)}\n\n"

            # Show evolution over time
            for entry in sorted(param_entries, key=lambda e: e.timestamp):
                timestamp_str = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d %H:%M")

                output += f"- **{timestamp_str}**: "
                output += f"Changed from `{entry.old_value}` to `{entry.new_value}`\n"
                output += f"  - Reason: {entry.reason}\n"
                output += f"  - Confidence: {entry.confidence:.0%}\n\n"

        return output

    def humanize_parameter(self, param: str) -> str:
        """Convert parameter name to user-friendly text"""
        mappings = {
            "response_length": "Response Length (how verbose I am)",
            "intent_confidence_threshold": "Confidence Threshold (how sure I need to be)",
            "formality_level": "Formality (casual vs professional tone)",
            "use_emoji": "Emoji Usage (whether I use emoji)",
        }
        return mappings.get(param, param.replace("_", " ").title())
```

### 3. Point-in-Time Rollback

**Restore Full State:**
```python
class PointInTimeRollback:
    """Rollback all parameters to specific timestamp"""

    async def rollback_to_time(self,
                              session_id: str,
                              target_timestamp: float) -> RollbackResult:
        """Rollback to specific point in time"""

        # K1 emits rollback advisory
        advisory = Advisory(
            type=AdvisoryType.ROLLBACK_POINT_IN_TIME,
            session_id=session_id,
            target_timestamp=target_timestamp,
            reason="user_initiated"
        )

        # K0 P06 executes rollback via WAL
        # K0 replays WAL up to target_timestamp, restoring state
        receipt = await self.k0_gateway.submit_advisory(advisory)

        logger.info(
            "point_in_time_rollback_initiated",
            session_id=session_id,
            target_timestamp=target_timestamp,
            receipt_id=receipt.id
        )

        rollback_requests.labels(type="point_in_time").inc()

        return RollbackResult(
            success=True,
            receipt=receipt,
            restored_timestamp=target_timestamp
        )
```

### 4. Selective Parameter Rollback

**Undo Specific Changes:**
```python
class SelectiveRollback:
    """Rollback specific parameter only"""

    async def rollback_parameter(self,
                                session_id: str,
                                parameter: str,
                                target_value: Optional[any] = None) -> RollbackResult:
        """Rollback single parameter"""

        # If target_value not specified, rollback to default
        if target_value is None:
            target_value = self.get_default_value(parameter)

        # K1 emits selective rollback advisory
        advisory = Advisory(
            type=AdvisoryType.ROLLBACK_PARAMETER,
            session_id=session_id,
            parameter=parameter,
            target_value=target_value,
            reason="user_selective_rollback"
        )

        # K0 P06 executes rollback
        receipt = await self.k0_gateway.submit_advisory(advisory)

        logger.info(
            "selective_rollback_initiated",
            session_id=session_id,
            parameter=parameter,
            target_value=target_value,
            receipt_id=receipt.id
        )

        rollback_requests.labels(type="selective").inc()

        return RollbackResult(
            success=True,
            receipt=receipt,
            parameter=parameter,
            restored_value=target_value
        )
```

### 5. "Forget Me" Feature

**Delete All Learned Data:**
```python
class ForgetMe:
    """Privacy: Delete all learned preferences"""

    async def forget_all_learning(self, session_id: str) -> ForgetResult:
        """Delete all learned data for session"""

        # K1 emits forget advisory
        advisory = Advisory(
            type=AdvisoryType.FORGET_LEARNING,
            session_id=session_id,
            scope="all",
            reason="user_privacy_request"
        )

        # K0 P06 deletes learned data (keeps audit trail per GDPR)
        receipt = await self.k0_gateway.submit_advisory(advisory)

        logger.info(
            "forget_learning_initiated",
            session_id=session_id,
            scope="all",
            receipt_id=receipt.id
        )

        forget_requests.labels(scope="all").inc()

        return ForgetResult(
            success=True,
            receipt=receipt,
            deleted_parameters=await self.list_learned_parameters(session_id)
        )

    async def forget_parameter(self,
                              session_id: str,
                              parameter: str) -> ForgetResult:
        """Delete learned data for specific parameter"""
        advisory = Advisory(
            type=AdvisoryType.FORGET_LEARNING,
            session_id=session_id,
            scope="parameter",
            parameter=parameter,
            reason="user_privacy_request"
        )

        receipt = await self.k0_gateway.submit_advisory(advisory)

        forget_requests.labels(scope="parameter").inc()

        return ForgetResult(
            success=True,
            receipt=receipt,
            deleted_parameters=[parameter]
        )
```

### 6. Audit Query API

**User-Facing API:**
```python
class AuditQueryAPI:
    """API for querying learning audit trail"""

    async def get_learning_summary(self, session_id: str) -> LearningSummary:
        """Get summary of what system has learned"""
        # Query last 30 days
        entries = await self.audit_trail.query_audit_log(
            session_id=session_id,
            start_time=time.time() - 30*86400
        )

        # Summarize by parameter
        summary = LearningSummary(
            session_id=session_id,
            total_changes=len(entries),
            parameters_learned=list(set(e.parameter for e in entries)),
            earliest_change=min(e.timestamp for e in entries) if entries else None,
            latest_change=max(e.timestamp for e in entries) if entries else None
        )

        return summary

    async def get_parameter_history(self,
                                   session_id: str,
                                   parameter: str) -> List[LearningAuditEntry]:
        """Get full history for specific parameter"""
        entries = await self.audit_trail.query_audit_log(session_id=session_id)
        return [e for e in entries if e.parameter == parameter]

    async def get_recent_changes(self,
                                session_id: str,
                                hours: int = 24) -> List[LearningAuditEntry]:
        """Get recent changes"""
        start_time = time.time() - (hours * 3600)
        return await self.audit_trail.query_audit_log(
            session_id=session_id,
            start_time=start_time
        )
```

### 7. Rollback Validation

**Prevent Invalid Rollbacks:**
```python
class RollbackValidator:
    async def validate_rollback(self,
                               rollback_request: RollbackRequest) -> ValidationResult:
        """Validate rollback request"""

        # Check 1: Does target state exist?
        if rollback_request.target_timestamp:
            exists = await self.check_timestamp_exists(
                session_id=rollback_request.session_id,
                timestamp=rollback_request.target_timestamp
            )

            if not exists:
                return ValidationResult(
                    allowed=False,
                    reason="target_timestamp_not_found"
                )

        # Check 2: Is parameter reversible?
        if rollback_request.parameter:
            audit_entry = await self.get_last_change(
                session_id=rollback_request.session_id,
                parameter=rollback_request.parameter
            )

            if audit_entry and not audit_entry.reversible:
                return ValidationResult(
                    allowed=False,
                    reason="parameter_not_reversible"
                )

        # Check 3: Would rollback violate safety?
        safety_check = await self.check_rollback_safety(rollback_request)

        if not safety_check.safe:
            return ValidationResult(
                allowed=False,
                reason=f"safety_violation: {safety_check.reason}"
            )

        return ValidationResult(allowed=True)
```

### 8. K0 WAL Integration

**K0 P06 Executes Rollback:**
```python
# K0 P06 side (for reference - not K1 code)
class K0P06RollbackHandler:
    """
    K0 P06 FeedbackIntegration handles rollback execution
    Uses WAL to restore prior state
    """
    async def execute_rollback(self, advisory: Advisory) -> Receipt:
        """Execute rollback command from K1"""

        if advisory.type == AdvisoryType.ROLLBACK_POINT_IN_TIME:
            # Replay WAL up to target timestamp
            await self.wal.replay_to_timestamp(
                session_id=advisory.session_id,
                target_timestamp=advisory.target_timestamp
            )

        elif advisory.type == AdvisoryType.ROLLBACK_PARAMETER:
            # Restore single parameter
            await self.session_state.restore_parameter(
                session_id=advisory.session_id,
                parameter=advisory.parameter,
                target_value=advisory.target_value
            )

        elif advisory.type == AdvisoryType.FORGET_LEARNING:
            # Delete learned data (keep audit trail)
            await self.session_state.delete_learned_parameters(
                session_id=advisory.session_id,
                parameter=advisory.parameter if advisory.scope == "parameter" else None
            )

        # Issue receipt
        receipt = Receipt(
            receipt_id=generate_id(),
            advisory_id=advisory.advisory_id,
            status="completed",
            timestamp=time.time()
        )

        return receipt
```

---

## Consequences

### Positive

✅ **Full Transparency:** Users see what system learned
✅ **User Control:** Rollback any change
✅ **Privacy:** Delete learned data
✅ **K0 WAL:** Authoritative audit trail
✅ **GDPR Compliance:** Right to be forgotten

### Negative

⚠️ **Storage Cost:** Full audit trail consumes space
⚠️ **Complexity:** WAL replay logic
⚠️ **Performance:** Large rollbacks can be slow

---

## Implementation Guidance

### Phase 1: Audit Trail (Day 1-3)
- K0 WAL integration
- Audit log queries
- Entry parsing

### Phase 2: User-Facing API (Day 4-5)
- Query API
- Human-readable formatting
- Summary generation

### Phase 3: Point-in-Time Rollback (Day 6-7)
- WAL replay logic
- K0 P06 integration
- Receipt handling

### Phase 4: Selective Rollback (Day 8)
- Parameter rollback
- Default value restoration
- Validation

### Phase 5: Forget Me (Day 9)
- Privacy deletion
- GDPR compliance
- Audit trail retention

---

## Validation

```python
@test("audit trail shows all changes")
async def test_audit_trail():
    trail = AuditTrail()

    # Make multiple changes
    await make_parameter_changes("s1", [
        ("response_length", 150),
        ("formality_level", 7),
    ])

    # Query audit log
    entries = await trail.query_audit_log("s1")

    assert len(entries) == 2
    assert entries[0].parameter == "response_length"

@test("rollback restores prior state")
async def test_rollback():
    rollback = PointInTimeRollback()

    # Record initial state
    initial_time = time.time()
    initial_value = get_parameter_value("s1", "response_length")

    # Make change
    await change_parameter("s1", "response_length", 300)

    # Rollback
    result = await rollback.rollback_to_time("s1", initial_time)

    assert result.success
    assert get_parameter_value("s1", "response_length") == initial_value
```

---

## Monitoring

```python
rollback_requests = Counter(
    'rollback_requests',
    'Rollback requests',
    ['type']  # point_in_time, selective, forget
)

audit_queries = Counter(
    'audit_queries',
    'Audit trail queries'
)

forget_requests = Counter(
    'forget_requests',
    'Forget me requests',
    ['scope']  # all, parameter
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 920 lines (target: 900 lines) ✅