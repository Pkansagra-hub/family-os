# K1 Family Tools - CONTRACT

## Purpose

`k1/tools/family` is the K1-native tool foundation for family-owned domains such as calendar, tasks, reminders, chores, and settings. A family tool is declared by a `ToolDefinition`, implemented by a `BaseToolService`, registered in the family `ToolRegistry`, and published into Fabric as one `CapabilityContract` per `ActionSpec`.

## Public Contract Surface

### `ToolDefinition`

`ToolDefinition` is the adapter-level manifest. It declares adapter identity, persistent table DDL, UI/manifest hints, cross-reference metadata, and action list.

M1 prompt/profile fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `activity_profile` | `str or None` | Default activity profile inherited by actions that do not declare their own profile. |
| `domain_tags` | `list[str]` | Extra Fabric discovery/ranking domain tags folded into generated `CapabilityContract.domain`. |

### `ActionSpec`

`ActionSpec` is the action-level contract. It declares action name, kind, params, result, roles, safety band, LLM hints, SSE/audit topics, and idempotency.

M1 prompt/profile fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `prompt_template` | `str or None` | Optional PromptContract name for this action. |
| `activity_profile` | `str or None` | Optional action-specific profile overriding `ToolDefinition.activity_profile`. |
| `tool_instructions` | `str or None` | Inline operating guidance for LLM-backed execution. |
| `social_act` | `str or None` | Constitution/social act id for conscience policy. |
| `side_effects` | `list[dict[str, Any]]` | Structured side effects for policy, HIL, and audit. |

## M8 Concrete Profiles

Initial reviewed activity profiles are attached directly to declarations:

| Adapter | `ToolDefinition.activity_profile` | Back execution profile |
| --- | --- | --- |
| `calendar` | `calendar.v1` | Backed (`back_execution_profile=True`); guidance from `guide_cards`. |
| `tasks` | `tasks.v1` | Backed; guidance from `guide_cards`. |
| `reminders` | `reminders.v1` | Backed; `fire_reminder` is scheduler-only with no profile. |
| `chores` | `chores.v1` | Unbacked — generic discovery fallback. |
| `shopping` | `shopping.v1` | Unbacked; child-added items require parent/guardian approval. |

Family settings and future family adapters must stay on generic discovery behavior until they have reviewed prompt assets and explicit metadata. Do not infer profiles from free text, action names, or capability-name prefixes.

## Invariants

- Prompt/profile metadata is guidance only; it never grants tools, bypasses HIL, or changes role/safety checks.
- Business parameters stay in `params`. Prompt/profile metadata must not be mixed into service params.
- Native family services must pass without prompt inventory present.
- `ActionSpec.activity_profile` wins over `ToolDefinition.activity_profile`.
- `ActionSpec.llm.examples` may become `CapabilityContract.tool_instructions` only when explicit `tool_instructions` is absent.
