# K1 Family Tools - WIRING

## Runtime Path

```text
KernelService startup
  -> bootstrap_family_tools(shared_fabric, service_classes=[...])
  -> K1FamilyStore opens SQLite
  -> EventEmitter attaches SSE publisher and optional sync outbox
  -> ToolRegistry registers each BaseToolService
  -> manifest_translator.register_definition(...)
  -> Fabric CapabilityRegistry receives CapabilityContract per action
  -> NativeToolProvider registers as provider_type=LOCAL, provider_id=k1_native_tools
```

## Prompt/Profile Metadata Wiring

```text
ToolDefinition.activity_profile/domain_tags
ActionSpec.prompt_template/activity_profile/tool_instructions/social_act/side_effects
  -> manifest_translator.build_contract()
  -> CapabilityContract prompt/profile/policy metadata
  -> Fabric discovery and exact registry lookup
```

M8 concrete attachments currently cover:

- `calendar.v1` / `calendar_activity_v1` for all calendar actions.
- `tasks.v1` / `tasks_activity_v1` for all task actions.
- `reminders.v1` / `reminders_activity_v1` for user-invokable reminder actions; `fire_reminder` is scheduler-only and keeps explicit no-LLM tool instructions.
- `chores.v1` / `chores_activity_v1` for all chore actions.
- `shopping.v1` / `shopping_activity_v1` for all shopping actions; child-added items stay pending until parent/guardian approval.

Native services do not receive prompt text in business params, and `NativeToolProvider` does not require prompt metadata to execute actions. Prompt/profile metadata is passed separately for audit/debug through Fabric provider metadata.

## Provider Boundary

All family capabilities use:

- `provider_type="LOCAL"`
- `provider_id="k1_native_tools"`
- `provider_endpoint="local://k1_native_tools"`

The provider dispatches by capability name shape:

```text
tool.execute.<adapter_id>.<action_name>
tool.read.<adapter_id>.<action_name>
```
