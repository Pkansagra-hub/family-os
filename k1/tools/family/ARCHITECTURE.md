# K1 Family Tools - ARCHITECTURE

## Responsibility

The family-tool layer is the K1-native foundation for household tools. It owns declarative tool definitions, service dispatch, ACL/policy helpers, persistence primitives, audit/event emission, and Fabric registration for native family capabilities.

## Component Boundaries

| Component | Responsibility |
| --- | --- |
| `definition.py` | `ToolDefinition`, `ActionSpec`, `FieldSpec`, `LLMHints`, `SSESpec` declarations. |
| `base_service.py` | Uniform service dispatch, role/safety checks, idempotency, audit emission. |
| `registry.py` | Live service registry and Fabric publication. |
| `bootstrap.py` | Kernel-facing composition root for store, registry, services, and provider registration. |
| `manifest_translator.py` | Fabric-side conversion from family definitions to `CapabilityContract`. |
| `NativeToolProvider` | Fabric provider that dispatches exact capability names into registered services. |

## Prompt/Profile Architecture

Prompt/profile metadata stays in the contract plane:

```text
Family adapter author
  -> ToolDefinition default activity_profile/domain_tags
  -> ActionSpec prompt_template/activity_profile/tool_instructions
  -> Fabric CapabilityContract metadata
  -> Discovery, audit, and prompt/context plumbing
```

M8 attaches reviewed concrete profiles to real family definitions: calendar,
tasks, user-invokable reminders, chores, and shopping. Other family adapters
continue through generic system-of-record guidance until they have reviewed
prompt assets.

Profiles are procedure, not authority. The service layer continues to trust only explicit params, policy, role, safety band, and schema validation.
