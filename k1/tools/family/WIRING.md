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

- `calendar.v1` for all calendar actions; backed Back execution profile (`ToolDefinition.back_execution_profile=True`), guidance derived from `guide_cards`.
- `tasks.v1` for all task actions; backed Back execution profile, guidance derived from `guide_cards`.
- `reminders.v1` for user-invokable reminder actions; backed Back execution profile. `fire_reminder` is scheduler-only and keeps explicit no-LLM tool instructions.
- `chores.v1` for all chore actions; `activity_profile` only (unbacked — no Back execution profile, falls back to generic discovery).
- `shopping.v1` for all shopping actions; `activity_profile` only (unbacked). Child-added items stay pending until parent/guardian approval.

The legacy per-action `prompt_template` activity-profile YAMLs were removed; actions inherit only the definition-level `activity_profile`.

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
