# ADR-0043a: K0 SSE Topic Hierarchy & Naming Conventions

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0043: K0 SSE Topic Taxonomy](./0043-sse-topic-taxonomy.md)
**Authors:** K1 Architecture Team
**Priority:** ⭐⭐⭐ Critical
**Estimated Effort:** 2 weeks

---

## Context

ADR-0043 defines K0 SSE topic taxonomy for durable events. This sub-ADR specifies **hierarchical topic naming conventions** (k0.category.subcategory.event), **dot notation rules** (lowercase_with_underscores, max 4 levels), and **complete topic registry** (60+ K0 SSE topics organized into 8 major categories) to ensure consistent naming, discoverability, and K0/K1 architectural separation.

### Problem Statement

**K0 SSE topics need a hierarchical naming convention with dot notation (k0.config.hot_reload.completed), clear categorization (k0.config.*, k0.receipt.*, etc.), and naming rules (lowercase, underscores, verb tense) to prevent topic chaos, enable wildcard subscriptions, and maintain K0/K1 separation (K0 SSE = durable, K1 event bus = ephemeral per ADR-0048).**

**Current Challenge:** Without topic hierarchy:

1. **Topic Name Chaos:** No convention → 5 different patterns (config_changed, configUpdated, config.reload, k0_config_update, cfg-updated)
2. **No Categorization:** All topics flat namespace → can't group related topics (config, receipts, learning)
3. **No Wildcard Support:** Can't subscribe to "k0.config.*" → must list all config topics explicitly
4. **K0/K1 Confusion:** No clear prefix to distinguish K0 SSE (durable) from K1 internal (ephemeral)
5. **Poor Discoverability:** Can't grep for "k0.learning.*" → developers duplicate topics unknowingly

**Desired Behavior:**

```
Hierarchical Topic Structure:

k0.config.changed                  ← Config updated by admin
k0.config.hot_reload.initiated     ← Hot reload started
k0.config.hot_reload.completed     ← Hot reload completed
k0.config.validated                ← Config validation passed
k0.receipt.created                 ← Receipt written to K0 WAL
k0.receipt.finalized               ← Receipt persisted
k0.learning.feedback.explicit      ← User clicked thumbs up/down
k0.crdt.session_state.merged       ← SessionState CRDT merge

Benefits:
- Hierarchical structure (category → subcategory → event)
- Consistent k0.* prefix (durable K0 events)
- Wildcard support (k0.config.* matches all config)
- Self-documenting (grep "k0.receipt" shows all receipt topics)
- K0/K1 separation (k0.* = durable, k1.* = ephemeral ADR-0048)
```

---

## Decision

**We will implement hierarchical K0 SSE topic naming with dot notation (k0.category.subcategory.event), 8 major categories (config, receipt, learning, CRDT, policy, audit, family, ui), 60+ topics, and strict naming rules (lowercase, underscores for multi-word, past tense verbs, max 4 levels) to ensure consistency, discoverability, and architectural clarity.**

### Core Naming Rules

#### Rule 1: Hierarchical Dot Notation

**Format:** `k0.category.subcategory.event`

**Examples:**
```
k0.config.changed                    # 2 levels (simple)
k0.config.hot_reload.completed       # 3 levels (common)
k0.family.device.sync.initiated      # 4 levels (max)
```

**Rationale:**
- Hierarchical structure enables category grouping
- Wildcard matching: `k0.config.*` matches all config topics
- Max 4 levels prevents over-nesting (keeps topics readable)

---

#### Rule 2: K0 Prefix Mandatory

**All K0 SSE topics MUST start with `k0.`**

**Rationale:**
- Distinguishes K0 durable events from K1 ephemeral (ADR-0001 separation)
- Prevents confusion between K0 SSE and K1 event bus (ADR-0048)
- Clear architectural boundary: k0.* = cross-boundary durable, k1.* = internal ephemeral

**Examples:**
```
✅ CORRECT:
k0.config.changed           # K0 SSE (durable config event)
k0.receipt.finalized        # K0 SSE (durable receipt)
ui.session.state.updated    # UI bridge (sanitized K0 data)

❌ INCORRECT:
config.changed              # Missing k0. prefix
k1.config.changed           # Wrong: k1.* is for K1 internal (ADR-0048)
orchestrator.task.assigned  # Wrong: K1 internal, not K0 SSE
```

---

#### Rule 3: Lowercase with Underscores

**All topic segments MUST be lowercase. Multi-word segments use underscores.**

**Examples:**
```
✅ CORRECT:
k0.config.hot_reload.completed
k0.learning.feedback.explicit
k0.family.device.sync.initiated

❌ INCORRECT:
k0.config.HotReload.Completed   # Uppercase
k0.config.hot-reload.completed  # Hyphen (use underscore)
k0.config.hotReload.completed   # CamelCase (use underscore)
```

---

#### Rule 4: Verb Tense for Events

**Use past tense for completed events, present participle for in-progress.**

**Past Tense (Completed):**
```
k0.config.changed               # Config has changed
k0.config.validated             # Config was validated
k0.receipt.created              # Receipt was created
k0.learning.feedback.received   # Feedback was received
```

**Present Participle (In-Progress):**
```
k0.config.hot_reload.initiated    # Hot reload starting
k0.config.validating              # Validation in progress
k0.crdt.merging                   # CRDT merge in progress
```

---

#### Rule 5: Category-Based Organization

**8 Major Categories:**

1. **k0.config.*** — Configuration hot-reload (8 topics)
2. **k0.receipt.*** — Receipt acknowledgments (6 topics)
3. **k0.learning.*** — Learning feedback (8 topics)
4. **k0.crdt.*** — CRDT synchronization (6 topics)
5. **k0.policy.*** — Policy updates (4 topics)
6. **k0.audit.*** — Audit events (6 topics)
7. **k0.family.*** — Family coordination (12 topics)
8. **ui.*** — UI updates (11 topics, sanitized)

---

## Complete Topic Registry (60+ Topics)

### Category 1: k0.config.* — Configuration Hot-Reload (8 topics)

**Purpose:** Config changes propagate from K0 admin API → K1 instances

**Access Level:** Admin only

```yaml
topics:
  - name: "k0.config.changed"
    description: "Config value changed by admin"
    levels: 2
    example: "k0.config.changed"
    payload_schema: "ConfigChangedEvent"
    producers: ["k0.admin_api"]
    consumers: ["k1.config_manager", "ui.bridge"]
    retention_days: 30
    access_level: "admin"

  - name: "k0.config.hot_reload.initiated"
    description: "Config hot-reload started"
    levels: 3
    example: "k0.config.hot_reload.initiated"
    payload_schema: "ConfigHotReloadEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.config_manager"]
    retention_days: 7
    access_level: "admin"

  - name: "k0.config.hot_reload.completed"
    description: "Config hot-reload completed successfully"
    levels: 3
    example: "k0.config.hot_reload.completed"
    payload_schema: "ConfigReloadCompletedEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.config_manager", "k1.all_agents"]
    retention_days: 7
    access_level: "admin"

  - name: "k0.config.hot_reload.failed"
    description: "Config hot-reload failed (validation error)"
    levels: 3
    example: "k0.config.hot_reload.failed"
    payload_schema: "ConfigReloadFailedEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.config_manager", "ui.bridge"]
    retention_days: 30
    access_level: "admin"

  - name: "k0.config.validated"
    description: "Config validation completed successfully"
    levels: 2
    example: "k0.config.validated"
    payload_schema: "ConfigValidatedEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.config_manager"]
    retention_days: 7
    access_level: "admin"

  - name: "k0.config.rollback"
    description: "Config rolled back to previous version"
    levels: 2
    example: "k0.config.rollback"
    payload_schema: "ConfigRollbackEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.config_manager", "ui.bridge"]
    retention_days: 30
    access_level: "admin"

  - name: "k0.config.cache.cleared"
    description: "Config cache cleared (force reload)"
    levels: 3
    example: "k0.config.cache.cleared"
    payload_schema: "ConfigCacheClearedEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.config_manager"]
    retention_days: 7
    access_level: "admin"

  - name: "k0.config.export.completed"
    description: "Config export to backup completed"
    levels: 3
    example: "k0.config.export.completed"
    payload_schema: "ConfigExportEvent"
    producers: ["k0.backup_manager"]
    consumers: ["ui.bridge"]
    retention_days: 90
    access_level: "admin"
```

---

### Category 2: k0.receipt.* — Receipt Acknowledgments (6 topics)

**Purpose:** K0 WAL receipt finalization → K1 notification

**Access Level:** User scope (own receipts only)

```yaml
topics:
  - name: "k0.receipt.created"
    description: "Receipt created in K0 WAL"
    levels: 2
    example: "k0.receipt.created"
    payload_schema: "ReceiptCreatedEvent"
    producers: ["k0.wal_writer"]
    consumers: ["k1.receipt_tracker", "ui.bridge"]
    retention_days: 365  # Compliance
    access_level: "user"

  - name: "k0.receipt.finalized"
    description: "Receipt persisted and finalized"
    levels: 2
    example: "k0.receipt.finalized"
    payload_schema: "ReceiptFinalizedEvent"
    producers: ["k0.wal_writer"]
    consumers: ["k1.receipt_tracker", "ui.bridge"]
    retention_days: 365
    access_level: "user"

  - name: "k0.receipt.acknowledged"
    description: "User acknowledged receipt"
    levels: 2
    example: "k0.receipt.acknowledged"
    payload_schema: "ReceiptAcknowledgedEvent"
    producers: ["k0.receipt_manager"]
    consumers: ["k1.receipt_tracker", "ui.bridge"]
    retention_days: 365
    access_level: "user"

  - name: "k0.receipt.query.completed"
    description: "Receipt query completed"
    levels: 3
    example: "k0.receipt.query.completed"
    payload_schema: "ReceiptQueryEvent"
    producers: ["k0.query_engine"]
    consumers: ["ui.bridge"]
    retention_days: 30
    access_level: "user"

  - name: "k0.receipt.export.completed"
    description: "Receipt export completed"
    levels: 3
    example: "k0.receipt.export.completed"
    payload_schema: "ReceiptExportEvent"
    producers: ["k0.export_manager"]
    consumers: ["ui.bridge"]
    retention_days: 90
    access_level: "user"

  - name: "k0.receipt.purged"
    description: "Old receipts purged (retention policy)"
    levels: 2
    example: "k0.receipt.purged"
    payload_schema: "ReceiptPurgedEvent"
    producers: ["k0.retention_manager"]
    consumers: ["k1.receipt_tracker"]
    retention_days: 30
    access_level: "admin"
```

---

### Category 3: k0.learning.* — Learning Feedback (8 topics)

**Purpose:** User feedback stored in K0 → propagated to K1 learning loop

**Access Level:** User scope

```yaml
topics:
  - name: "k0.learning.feedback.explicit"
    description: "Explicit user feedback (thumbs up/down)"
    levels: 3
    example: "k0.learning.feedback.explicit"
    payload_schema: "ExplicitFeedbackEvent"
    producers: ["k0.feedback_collector"]
    consumers: ["k1.learning_loop", "k1.all_agents"]
    retention_days: 30
    access_level: "user"

  - name: "k0.learning.feedback.implicit"
    description: "Implicit feedback (usage patterns)"
    levels: 3
    example: "k0.learning.feedback.implicit"
    payload_schema: "ImplicitFeedbackEvent"
    producers: ["k0.feedback_collector"]
    consumers: ["k1.learning_loop"]
    retention_days: 30
    access_level: "user"

  - name: "k0.learning.feedback.behavioral"
    description: "Behavioral feedback (action completion)"
    levels: 3
    example: "k0.learning.feedback.behavioral"
    payload_schema: "BehavioralFeedbackEvent"
    producers: ["k0.feedback_collector"]
    consumers: ["k1.learning_loop"]
    retention_days: 30
    access_level: "user"

  - name: "k0.learning.drift.detected"
    description: "Model drift detected (performance degradation)"
    levels: 3
    example: "k0.learning.drift.detected"
    payload_schema: "DriftDetectedEvent"
    producers: ["k0.drift_monitor"]
    consumers: ["k1.learning_loop", "ui.bridge"]
    retention_days: 90
    access_level: "admin"

  - name: "k0.learning.model.updated"
    description: "Model weights updated (fine-tuning)"
    levels: 3
    example: "k0.learning.model.updated"
    payload_schema: "ModelUpdatedEvent"
    producers: ["k0.model_trainer"]
    consumers: ["k1.model_hub"]
    retention_days: 90
    access_level: "admin"

  - name: "k0.learning.score.computed"
    description: "Hiring score computed for agent"
    levels: 3
    example: "k0.learning.score.computed"
    payload_schema: "HiringScoreEvent"
    producers: ["k0.learning_loop"]
    consumers: ["k1.agent_fabric"]
    retention_days: 30
    access_level: "system"

  - name: "k0.learning.blacklist.updated"
    description: "Agent blacklist updated (crash threshold)"
    levels: 3
    example: "k0.learning.blacklist.updated"
    payload_schema: "BlacklistUpdatedEvent"
    producers: ["k0.learning_loop"]
    consumers: ["k1.agent_fabric"]
    retention_days: 90
    access_level: "system"

  - name: "k0.learning.config.reloaded"
    description: "Learning config hot-reloaded"
    levels: 3
    example: "k0.learning.config.reloaded"
    payload_schema: "LearningConfigReloadedEvent"
    producers: ["k0.config_manager"]
    consumers: ["k1.learning_loop"]
    retention_days: 30
    access_level: "admin"
```

---

### Category 4: k0.crdt.* — CRDT Synchronization (6 topics)

**Purpose:** SessionState CRDT merge operations broadcast to K1 instances

**Access Level:** User scope (own session state)

```yaml
topics:
  - name: "k0.crdt.session_state.merged"
    description: "SessionState CRDT merge completed"
    levels: 3
    example: "k0.crdt.session_state.merged"
    payload_schema: "SessionStateMergedEvent"
    producers: ["k0.crdt_manager"]
    consumers: ["k1.all_instances"]
    retention_days: 7
    access_level: "user"

  - name: "k0.crdt.session_state.conflict"
    description: "CRDT merge conflict detected (auto-resolved)"
    levels: 3
    example: "k0.crdt.session_state.conflict"
    payload_schema: "CRDTConflictEvent"
    producers: ["k0.crdt_manager"]
    consumers: ["k1.all_instances", "ui.bridge"]
    retention_days: 30
    access_level: "user"

  - name: "k0.crdt.device.synced"
    description: "Multi-device CRDT sync completed"
    levels: 3
    example: "k0.crdt.device.synced"
    payload_schema: "DeviceSyncedEvent"
    producers: ["k0.crdt_manager"]
    consumers: ["k1.all_instances"]
    retention_days: 7
    access_level: "user"

  - name: "k0.crdt.tombstone.collected"
    description: "CRDT tombstones garbage collected"
    levels: 3
    example: "k0.crdt.tombstone.collected"
    payload_schema: "TombstoneCollectedEvent"
    producers: ["k0.crdt_gc"]
    consumers: ["k1.session_state"]
    retention_days: 7
    access_level: "system"

  - name: "k0.crdt.snapshot.created"
    description: "CRDT snapshot created for backup"
    levels: 3
    example: "k0.crdt.snapshot.created"
    payload_schema: "CRDTSnapshotEvent"
    producers: ["k0.backup_manager"]
    consumers: ["ui.bridge"]
    retention_days: 90
    access_level: "user"

  - name: "k0.crdt.restore.completed"
    description: "CRDT state restored from snapshot"
    levels: 3
    example: "k0.crdt.restore.completed"
    payload_schema: "CRDTRestoreEvent"
    producers: ["k0.backup_manager"]
    consumers: ["k1.session_state"]
    retention_days: 90
    access_level: "user"
```

---

### Category 5: k0.policy.* — Policy Updates (4 topics)

**Purpose:** Governance policy changes propagated to K1 arbiter

**Access Level:** Admin only

```yaml
topics:
  - name: "k0.policy.updated"
    description: "Governance policy updated"
    levels: 2
    example: "k0.policy.updated"
    payload_schema: "PolicyUpdatedEvent"
    producers: ["k0.policy_engine"]
    consumers: ["k1.arbiter", "k1.config_manager"]
    retention_days: 90
    access_level: "admin"

  - name: "k0.policy.violated"
    description: "Policy violation detected"
    levels: 2
    example: "k0.policy.violated"
    payload_schema: "PolicyViolatedEvent"
    producers: ["k0.policy_engine"]
    consumers: ["k1.arbiter", "ui.bridge"]
    retention_days: 365  # Compliance
    access_level: "admin"

  - name: "k0.policy.approved"
    description: "Policy approval granted by arbiter"
    levels: 2
    example: "k0.policy.approved"
    payload_schema: "PolicyApprovedEvent"
    producers: ["k0.policy_engine"]
    consumers: ["k1.arbiter"]
    retention_days: 90
    access_level: "admin"

  - name: "k0.policy.audit.logged"
    description: "Policy audit event logged"
    levels: 3
    example: "k0.policy.audit.logged"
    payload_schema: "PolicyAuditEvent"
    producers: ["k0.policy_engine"]
    consumers: ["k0.audit_trail"]
    retention_days: 365
    access_level: "admin"
```

---

### Category 6: k0.audit.* — Audit Events (6 topics)

**Purpose:** Compliance logging for sensitive operations

**Access Level:** Admin only

```yaml
topics:
  - name: "k0.audit.access.logged"
    description: "Data access logged (compliance)"
    levels: 3
    example: "k0.audit.access.logged"
    payload_schema: "AccessAuditEvent"
    producers: ["k0.audit_logger"]
    consumers: ["k0.audit_trail"]
    retention_days: 365
    access_level: "admin"

  - name: "k0.audit.mutation.logged"
    description: "Data mutation logged (compliance)"
    levels: 3
    example: "k0.audit.mutation.logged"
    payload_schema: "MutationAuditEvent"
    producers: ["k0.audit_logger"]
    consumers: ["k0.audit_trail"]
    retention_days: 365
    access_level: "admin"

  - name: "k0.audit.export.logged"
    description: "Data export logged (compliance)"
    levels: 3
    example: "k0.audit.export.logged"
    payload_schema: "ExportAuditEvent"
    producers: ["k0.audit_logger"]
    consumers: ["k0.audit_trail"]
    retention_days: 365
    access_level: "admin"

  - name: "k0.audit.deletion.logged"
    description: "Data deletion logged (compliance)"
    levels: 3
    example: "k0.audit.deletion.logged"
    payload_schema: "DeletionAuditEvent"
    producers: ["k0.audit_logger"]
    consumers: ["k0.audit_trail"]
    retention_days: 365
    access_level: "admin"

  - name: "k0.audit.query.completed"
    description: "Audit log query completed"
    levels: 3
    example: "k0.audit.query.completed"
    payload_schema: "AuditQueryEvent"
    producers: ["k0.query_engine"]
    consumers: ["ui.bridge"]
    retention_days: 90
    access_level: "admin"

  - name: "k0.audit.retention.enforced"
    description: "Audit log retention policy enforced"
    levels: 3
    example: "k0.audit.retention.enforced"
    payload_schema: "AuditRetentionEvent"
    producers: ["k0.retention_manager"]
    consumers: ["ui.bridge"]
    retention_days: 365
    access_level: "admin"
```

---

### Category 7: k0.family.* — Family Coordination (12 topics)

**Purpose:** Family events (emergency alerts, device sync)

**Access Level:** Family scope

```yaml
topics:
  - name: "k0.family.emergency.alert"
    description: "Emergency alert broadcast to family"
    levels: 3
    example: "k0.family.emergency.alert"
    payload_schema: "EmergencyAlertEvent"
    producers: ["k0.family_coordinator"]
    consumers: ["k1.all_instances", "ui.bridge", "family.devices"]
    retention_days: 90
    access_level: "family"

  - name: "k0.family.device.connected"
    description: "Family device connected"
    levels: 3
    example: "k0.family.device.connected"
    payload_schema: "DeviceConnectedEvent"
    producers: ["k0.device_manager"]
    consumers: ["k1.all_instances", "ui.bridge"]
    retention_days: 7
    access_level: "family"

  - name: "k0.family.device.disconnected"
    description: "Family device disconnected"
    levels: 3
    example: "k0.family.device.disconnected"
    payload_schema: "DeviceDisconnectedEvent"
    producers: ["k0.device_manager"]
    consumers: ["k1.all_instances", "ui.bridge"]
    retention_days: 7
    access_level: "family"

  - name: "k0.family.member.added"
    description: "Family member added"
    levels: 3
    example: "k0.family.member.added"
    payload_schema: "FamilyMemberAddedEvent"
    producers: ["k0.family_coordinator"]
    consumers: ["k1.all_instances", "ui.bridge"]
    retention_days: 365
    access_level: "family"

  - name: "k0.family.member.removed"
    description: "Family member removed"
    levels: 3
    example: "k0.family.member.removed"
    payload_schema: "FamilyMemberRemovedEvent"
    producers: ["k0.family_coordinator"]
    consumers: ["k1.all_instances", "ui.bridge"]
    retention_days: 365
    access_level: "family"

  - name: "k0.family.location.shared"
    description: "Family member location shared"
    levels: 3
    example: "k0.family.location.shared"
    payload_schema: "LocationSharedEvent"
    producers: ["k0.location_manager"]
    consumers: ["ui.bridge"]
    retention_days: 7
    access_level: "family"

  - name: "k0.family.calendar.synced"
    description: "Family calendar synced"
    levels: 3
    example: "k0.family.calendar.synced"
    payload_schema: "CalendarSyncedEvent"
    producers: ["k0.calendar_sync"]
    consumers: ["ui.bridge"]
    retention_days: 30
    access_level: "family"

  - name: "k0.family.photo.shared"
    description: "Family photo shared"
    levels: 3
    example: "k0.family.photo.shared"
    payload_schema: "PhotoSharedEvent"
    producers: ["k0.media_sync"]
    consumers: ["ui.bridge"]
    retention_days: 90
    access_level: "family"

  - name: "k0.family.message.broadcast"
    description: "Family message broadcast"
    levels: 3
    example: "k0.family.message.broadcast"
    payload_schema: "FamilyMessageEvent"
    producers: ["k0.family_coordinator"]
    consumers: ["k1.all_instances", "ui.bridge"]
    retention_days: 30
    access_level: "family"

  - name: "k0.family.milestone.recorded"
    description: "Family milestone recorded"
    levels: 3
    example: "k0.family.milestone.recorded"
    payload_schema: "MilestoneEvent"
    producers: ["k0.milestone_tracker"]
    consumers: ["ui.bridge"]
    retention_days: 365
    access_level: "family"

  - name: "k0.family.reminder.created"
    description: "Family reminder created"
    levels: 3
    example: "k0.family.reminder.created"
    payload_schema: "ReminderCreatedEvent"
    producers: ["k0.reminder_manager"]
    consumers: ["ui.bridge"]
    retention_days: 30
    access_level: "family"

  - name: "k0.family.conflict.detected"
    description: "Family schedule conflict detected"
    levels: 3
    example: "k0.family.conflict.detected"
    payload_schema: "ConflictDetectedEvent"
    producers: ["k0.conflict_detector"]
    consumers: ["ui.bridge"]
    retention_days: 7
    access_level: "family"
```

---

### Category 8: ui.* — UI Updates (11 topics, sanitized)

**Purpose:** Real-time UI updates (sanitized K0 data for clients)

**Access Level:** Public (sanitized payloads)

```yaml
topics:
  - name: "ui.session.state.updated"
    description: "Session state updated (sanitized for UI)"
    levels: 3
    example: "ui.session.state.updated"
    payload_schema: "UISessionStateEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.message.received"
    description: "New chat message received"
    levels: 2
    example: "ui.message.received"
    payload_schema: "UIMessageEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.typing.indicator"
    description: "Typing indicator (agent composing response)"
    levels: 2
    example: "ui.typing.indicator"
    payload_schema: "UITypingEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.agent.status.changed"
    description: "Agent status changed (active, idle, draining)"
    levels: 3
    example: "ui.agent.status.changed"
    payload_schema: "UIAgentStatusEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.tool.executing"
    description: "Tool execution in progress"
    levels: 2
    example: "ui.tool.executing"
    payload_schema: "UIToolExecutingEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.tool.completed"
    description: "Tool execution completed"
    levels: 2
    example: "ui.tool.completed"
    payload_schema: "UIToolCompletedEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.notification.alert"
    description: "User notification alert"
    levels: 2
    example: "ui.notification.alert"
    payload_schema: "UINotificationEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 7
    access_level: "public"

  - name: "ui.presence.updated"
    description: "User presence updated (online, away, offline)"
    levels: 2
    example: "ui.presence.updated"
    payload_schema: "UIPresenceEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.family.event"
    description: "Family event notification (sanitized)"
    levels: 2
    example: "ui.family.event"
    payload_schema: "UIFamilyEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 7
    access_level: "public"

  - name: "ui.cost.updated"
    description: "Session cost updated (real-time)"
    levels: 2
    example: "ui.cost.updated"
    payload_schema: "UICostEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 1
    access_level: "public"

  - name: "ui.error.occurred"
    description: "UI error occurred (user-friendly message)"
    levels: 2
    example: "ui.error.occurred"
    payload_schema: "UIErrorEvent"
    producers: ["ui.bridge"]
    consumers: ["websocket.clients"]
    retention_days: 7
    access_level: "public"
```

---

## Topic Registry Summary

**Total Topics:** 61

| Category | Topic Count | Access Level | Retention |
|----------|-------------|--------------|-----------|
| k0.config.* | 8 | Admin | 7-30 days |
| k0.receipt.* | 6 | User | 30-365 days |
| k0.learning.* | 8 | User/Admin | 30-90 days |
| k0.crdt.* | 6 | User/System | 7-90 days |
| k0.policy.* | 4 | Admin | 90-365 days |
| k0.audit.* | 6 | Admin | 90-365 days |
| k0.family.* | 12 | Family | 7-365 days |
| ui.* | 11 | Public | 1-7 days |

---

## Implementation Roadmap

### Week 1: Topic Registry & Validation (Days 1-5)

**Deliverables:**
- Topic registry file (YAML): `k0/config/sse_topic_registry.yml`
- Topic validator: `k0/sse/topic_validator.rs`
- Topic name parser: `k0/sse/topic_parser.rs`

**Acceptance Criteria:**
- All 61 topics defined in registry
- Validator enforces naming rules (k0.* prefix, lowercase, max 4 levels)
- Parser extracts category, subcategory, event from topic name

### Week 2: Topic Discovery & Testing (Days 6-10)

**Deliverables:**
- Topic discovery API: `GET /k0/sse/topics`
- Topic search: `GET /k0/sse/topics?category=config`
- Comprehensive testing (all 61 topics)

**Acceptance Criteria:**
- Discovery API returns all topics with metadata
- Search filters by category, access level
- All tests pass

---

## Metrics & Monitoring

```rust
lazy_static! {
    // Topic usage
    pub static ref K0_SSE_TOPIC_EVENTS_TOTAL: IntCounterVec = register_int_counter_vec!(
        "k0_sse_topic_events_total",
        "Total events published per topic",
        &["topic"]
    ).unwrap();

    // Topic validation
    pub static ref K0_SSE_TOPIC_VALIDATION_FAILURES_TOTAL: IntCounter = register_int_counter!(
        "k0_sse_topic_validation_failures_total",
        "Total topic validation failures"
    ).unwrap();

    // Category distribution
    pub static ref K0_SSE_CATEGORY_EVENTS_TOTAL: IntCounterVec = register_int_counter_vec!(
        "k0_sse_category_events_total",
        "Total events per category",
        &["category"]
    ).unwrap();
}
```

---

## Testing Strategy

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_topic_name_validation() {
        // Valid topics
        assert!(validate_topic("k0.config.changed").is_ok());
        assert!(validate_topic("k0.config.hot_reload.completed").is_ok());

        // Invalid topics
        assert!(validate_topic("config.changed").is_err());  // Missing k0. prefix
        assert!(validate_topic("k0.Config.Changed").is_err());  // Uppercase
        assert!(validate_topic("k0.config.hot-reload.completed").is_err());  // Hyphen
    }

    #[test]
    fn test_topic_hierarchy_parsing() {
        let topic = TopicParser::parse("k0.config.hot_reload.completed");
        assert_eq!(topic.category, "k0.config");
        assert_eq!(topic.subcategory, "hot_reload");
        assert_eq!(topic.event, "completed");
        assert_eq!(topic.levels, 4);
    }

    #[test]
    fn test_all_registry_topics_valid() {
        let registry = load_topic_registry("k0/config/sse_topic_registry.yml");
        for topic in registry.topics {
            assert!(validate_topic(&topic.name).is_ok());
        }
    }
}
```

---

## Summary

**Status:** ✅ Approved

**Key Achievements:**
- ✅ Hierarchical Topic Structure: Dot notation (k0.category.subcategory.event)
- ✅ 8 Major Categories: config, receipt, learning, CRDT, policy, audit, family, ui
- ✅ 61 Topics Defined: Complete registry with schemas and access levels
- ✅ Naming Rules Enforced: k0.* prefix, lowercase, underscores, past tense, max 4 levels
- ✅ K0/K1 Separation: Clear boundary (k0.* = durable, k1.* = ephemeral ADR-0048)

**Next Sub-ADR:**
- 0043b: K0 SSE Topic Subscription Patterns (exact match, wildcard, filters, consumer groups)

---

**End of ADR-0043a**
