# K1 Family Tools - STATE

## Current Runtime State

- `ToolDefinition` and `ActionSpec` are immutable Pydantic models with `extra="forbid"`.
- `ToolRegistry` holds live service instances and publishes their Fabric contracts.
- `K1FamilyStore` owns the SQLite connection used by native family services.
- `BaseToolService` applies adapter DDL, role checks, safety-band checks, idempotency replay, handler dispatch, and audit emission.

## Prompt/Profile State

Implemented:

- `ActionSpec.prompt_template`
- `ActionSpec.activity_profile`
- `ActionSpec.tool_instructions`
- `ActionSpec.social_act`
- `ActionSpec.side_effects`
- `ToolDefinition.activity_profile`
- `ToolDefinition.domain_tags`
- `manifest_translator.py` propagation into Fabric `CapabilityContract`
- M8 concrete profile attachment for Calendar, Tasks, user-invokable Reminders actions, Chores, and Shopping.
- Calendar actions expose `calendar.v1` (backed Back execution profile) with scheduling, availability, and external-calendar domain tags.
- Tasks actions expose `tasks.v1` (backed Back execution profile) with task-management, delegation, and deadline domain tags.
- Reminder user actions expose `reminders.v1` (backed Back execution profile) with alerting, notification, and scheduler domain tags. `fire_reminder` remains scheduler-only with explicit tool instructions and no Back profile.
- Chores actions expose `chores.v1` (`activity_profile` only; unbacked — generic discovery) with recurrence, gamification, and reward-tracking domain tags.
- Shopping actions expose `shopping.v1` (`activity_profile` only; unbacked) with shopping, category, and parent-approval domain tags.

Pending later milestones:

- Family settings, finance, health, and future vertical-specific profiles remain generic until reviewed prompt assets exist.
- Side-effect/social-act expansion remains separate governance work; M8 only attaches operating guidance metadata.

Operational invariant: family tools remain executable when prompt/profile metadata is absent or prompt inventory is empty.
