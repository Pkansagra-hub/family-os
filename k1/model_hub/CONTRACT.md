# K1 Model Hub — CONTRACT

---

## 1. Purpose

`k1/model_hub/` is the **single LLM dispatch layer** for the entire K1 system.
All components that need to call a language model (planner, concierge, orchestrator)
go through `IModelHubPort`. Model Hub owns:

- Provider lifecycle (register, initialize, health-check, close)
- Capability routing and model selection
- Circuit breaking and rate limiting per provider
- Response caching
- Request normalization and response denormalization
- Audit logging and telemetry

Model Hub does **not** own:
- Session state (read-only via `IStateReadPort` — MH-01)
- Capability/fabric registry (entirely separate)
- Plan or task logic

---

## 2. Core invariants

| ID | Invariant |
|---|---|
| MH-01 | Model Hub never writes to SessionState. `IStateReadPort` has no write methods. |
| MH-02 | Credentials are injected at request time via `ICredentialPort.get_key(provider_id)` — never stored inside plugins at rest beyond initialization. |
| MH-03 | `trace_id` is REQUIRED on every `HubRequest`. Requests with empty `trace_id` are rejected with `ValidationError`. |
| MH-04 | `cost_limit` is accepted in `RequestConstraints` but is NOT enforced by this revision. Cost tracking is passive; there is no `k1.model_hub.budget.alert.v1` constant or enforcer. |
| MH-05 | `IProviderPlugin.execute()` and `stream_execute()` are isolated: all plugin exceptions are caught by `ProviderDispatcher` and trigger circuit-failure recording. They never propagate uncaught to callers. |
| MH-06 | Streaming responses are NEVER cached. `should_cache(..., streaming=True)` always returns `False`. |
| MH-07 | `TOOL_CALL`, `BATCH`, `MODERATE` capabilities are NEVER cached regardless of temperature. |
| MH-08 | Responses at `temperature > 0.9` are NEVER cached. |
| MH-09 | Response cache is bounded: `cache_max_entries=1000` entries (LRU eviction), `cache_ttl_s=300s` (lazy TTL expiry). |
| MH-10 | `ProviderManifest` is the SOLE source of truth for provider capabilities and model specs (MH-18). Hub never hardcodes provider names. |
| MH-11 | Every request is logged to the in-memory `AuditLogger` (success and failure paths). Audit records are accessible for testing and debugging. |
| MH-12 | Rate limiter applies per-provider headroom (default 80%). Actual hard limit = `floor(rpm_limit * headroom_pct)`. |
| MH-13 | Provider selection uses a 3-dimension weighted score: preference (50%), placement (20%), health (30%). |
| MH-14 | Circuit breaker per provider: 3 failures in 60s → OPEN. Cooldown 30s → HALF_OPEN (one probe). Success → CLOSED. Failure in HALF_OPEN → OPEN. |
| MH-15 | Timeout tiers: `REALTIME=10s`, `INTERACTIVE=30s`, `BACKGROUND=60s`. Enforced via `asyncio.wait_for` in `RequestRouter`. |
| MH-16 | Max fallback depth = 3 (primary + 2 alternates). Max retries per provider = 1. |
| MH-17 | `_HubCore.shutdown()` drains all plugins concurrently with a 5s per-plugin timeout. Timeout is non-fatal. |
| MH-18 | Manifest is sole source of truth. No provider is hardcoded in hub logic. |

---

## 3. Public contract — `IModelHubPort`

```python
async def execute(request: HubRequest) -> HubResponse
async def stream_execute(request: HubRequest) -> AsyncIterator[HubChunk]
async def discover_capabilities() -> Dict[CapabilityType, List[str]]
async def discover_models(capability: CapabilityType | None = None) -> List[ModelInfo]
async def health() -> HubHealthReport
```

Callers must supply a valid `HubRequest`:
- `capability: CapabilityType` — one of 15 enum values
- `payload: Any` — typed payload dataclass for the capability
- `constraints: RequestConstraints` — timeout, token budget, priority, preference
- `trace_id: str` — REQUIRED, non-empty
- `request_id: str` — auto-generated UUID4 if omitted

---

## 4. `HubRequest` and payload types (all frozen)

| Capability | Payload Type | Key fields |
|---|---|---|
| `CHAT` | `ChatPayload` | `messages: List[Message]`, `system_prompt: Optional[str]` |
| `TOOL_CALL` | `ToolCallPayload` | `messages`, `tools: List[ToolDefinition]`, `tool_choice="auto"`, `parallel_tool_calls=True` |
| `STRUCTURED` | `StructuredOutputPayload` | `messages`, `output_schema: Dict`, `strict=True` |
| `REASON` | `ReasonPayload` | `messages`, `reasoning_effort="medium"` (`low/medium/high`), `include_thinking=False` |
| `EMBED` | `EmbedPayload` | `texts: List[str]`, `dimensions: Optional[int]`, `encoding_format="float"` |
| `VISION` | `VisionPayload` | `messages`, `image_inputs: List[Dict]`, `detail="auto"` |
| `BATCH` | `BatchPayload` | `requests: List[Any]`, `callback_topic: Optional[str]` |
| `MODERATE` | `ModeratePayload` | `text: str`, `categories: Optional[List[str]]` |
| `TOKEN_COUNT` | `TokenCountPayload` | `messages`, `model_id: Optional[str]` |
| `CACHE_PROMPT` | `CachePromptPayload` | `cache_key: str`, `messages`, `ttl_s=300` |
| `AUDIO_IN` | `AudioInputPayload` | `messages`, `audio: AudioInput`, `voice_config: Optional[VoiceConfig]` |
| `TTS` | `TTSPayload` | `text: str`, `voice="alloy"`, `format="mp3"`, `speed=1.0` |
| `IMAGE_GEN` | `ImageGenPayload` | `prompt: str`, `size="1024x1024"`, `quality="standard"`, `n=1` |
| `WEB_SEARCH` | `WebSearchPayload` | `query: str`, `max_results=10` |
| `CODE_EXEC` | `CodeExecPayload` | `code: str`, `language="python"`, `timeout_s=30` |

---

## 5. `HubResponse` and result types

```python
@dataclass(frozen=True)
class HubResponse:
    result: Any                   # typed result object (see table below)
    metadata: ResponseMetadata
```

| Capability | Result Type | Key fields |
|---|---|---|
| `CHAT` | `ChatResult` | `text: str` |
| `TOOL_CALL` | `ToolCallResultSet` | `text: str`, `tool_calls: List[ToolCallResult]` |
| `STRUCTURED` | `StructuredResult` | `json_output: Dict` |
| `REASON` | `ReasonResult` | `text: str`, `thinking: str` |
| `MODERATE` | `ModerateResult` | `flagged: bool`, `categories: List[ModerationCategory]` |
| Others | raw dict or primitive | Per provider convention |

`ResponseMetadata` carries: `request_id`, `model_id`, `provider_id`, `usage: TokenUsage`,
`cost_usd`, `latency_ms`, `cache_hit: bool`, `capability`, `trace_id`, `fallback_used: bool`, `finish_reason: FinishReason`.

`HubChunk` (streaming): `content: str`, `done: bool`, `metadata: Optional[ResponseMetadata]`, `tool_calls: Optional[List[ToolCallResult]]`.
Final chunk (`done=True`) always has `metadata`. Intermediate chunks have `metadata=None`.

---

## 6. `RequestConstraints`

```python
@dataclass(frozen=True)
class RequestConstraints:
    max_tokens:          int = 65536
    timeout_ms:          int = 30000
    priority:            Priority = Priority.INTERACTIVE
    temperature:         float = 0.7
    model_preference:    Optional[ModelPreference] = None
    provider_preference: Optional[str] = None
    cost_limit:          Optional[float] = None   # carried, not enforced (MH-04)
    consumer_id:         str = ""                 # used for audit
```

`Priority` timeout tiers override `timeout_ms` if stricter (MH-15):
`REALTIME` → 10s, `INTERACTIVE` → 30s, `BACKGROUND` → 60s.

`ModelPreference`: `preferred_provider`, `preferred_model`, `preferred_tier`, `avoid_providers`.

---

## 7. Routing pipeline (7 steps)

```
HubRequest
   │
   ▼ Step 1: validate — trace_id non-empty, capability in CapabilityType
   │                     → ValidationError if fails
   │
   ▼ Step 2: metrics — active_requests +1, requests_total +1
   │
   ▼ Step 3: CapabilityRouter.route()
   │         5-step filter:
   │          (a) registry.get_providers_for_capability(cap) — O(1)
   │          (b) model-level capability filter
   │          (c) circuit breaker != OPEN
   │          (d) rate_limiter.has_capacity(pid, token_estimate)
   │          (e) health_status != UNHEALTHY
   │         → NoEligibleProviderError if list empty
   │
   ▼ Step 4: ModelSelector.select()
   │         scoring: preference×0.5 + placement×0.2 + health×0.3
   │         sorts descending; primary = top; fallbacks = next 2
   │         → NoEligibleProviderError if empty after scoring
   │
   ▼ Step 5: ResponseCache.get()
   │         key = SHA-256(capability|repr(payload)|model_id|temp:.4f)
   │         → HubResponse (cache_hit=True) if hit; skip Steps 6–7
   │
   ▼ Step 6: NormalizationLayer.normalize()
   │         → NormalizedRequest via _CAPABILITY_EXTRACTORS dispatch table
   │
   ▼ Step 7: ProviderDispatcher.dispatch()
   │         primary provider → retry once → fallback chain → fallback[0] → ... → fallback[2]
   │         CB/RL acquire before each; record_failure on error; record_success on ok
   │         → ProviderResponse
   │
   ▼ denormalize + cache put + audit log + metrics → HubResponse
```

---

## 8. Provider plugin contract (`IProviderPlugin`)

Every plugin must implement:

```python
async def initialize(manifest: ProviderManifest) -> None
def supports(capability: CapabilityType) -> bool
async def execute(request: NormalizedRequest) -> ProviderResponse
async def stream_execute(request: NormalizedRequest) -> AsyncIterator[ProviderChunk]
def estimate_tokens(messages: List[Message]) -> int    # ~4 chars/token heuristic
async def health_check() -> ProviderHealth
async def close() -> None
```

`NormalizedRequest` carries: `messages`, `model_id`, `max_tokens`, `temperature`,
`stream`, `tools`, `output_schema`, `extra`.

`ProviderResponse` carries: `content`, `tool_calls`, `finish_reason`, `usage: TokenUsage`, `raw`.

---

## 9. Supported providers and special behaviors

| Provider | Plugin | Special behaviors |
|---|---|---|
| OpenAI | `OpenAIPlugin` | Reasoning models (`o3/o4-mini/o3-mini/o1/o1-mini`): `reasoning_effort`, no `temperature`, `developer` role. `max_completion_tokens` (not `max_tokens`). SSE with `include_usage`. |
| Anthropic | `AnthropicPlugin` | `system` is top-level (not in messages). `max_tokens` required. Tools use `input_schema`. Extended thinking: `budget_tokens=max_tokens//2`. SSE event-typed streaming. Health: `count_tokens` with claude-haiku-4-5. |
| Google | `GooglePlugin` | Uses `google-genai` SDK (sync). `asyncio.run_in_executor` for all calls. Thinking budget: low=1024, medium=8192, high=24576. Web search: `GoogleSearch()` tool. Code exec: `ToolCodeExecution()`. Streaming is NOT true async — materializes all chunks. |
| Ollama | `OllamaPlugin` | Native `/api/chat` NDJSON. No auth. Tool call `arguments` returned as OBJECT (not JSON string) — differs from OpenAI convention. |
| vLLM | `VLLMPlugin` | OpenAI-compat `/v1/*`. Health: `GET /health`. Optional `--api-key`. `LOCAL_GPU` placement. |
| Stub | `StubProviderPlugin` | All 15 capabilities. Static response. Used when kernel `model_mode != 'hub'`. |
| Test | `TestProviderPlugin` | Configurable: `fail_count`, `latency_ms`, `tool_calls`, `stream_chunks`. Records all calls. |

---

## 10. Circuit breaker contract

```
Default config: failure_threshold=3, failure_window_s=60, cooldown_s=30

CLOSED  → OPEN      if ≥3 failures in last 60s
OPEN    → HALF_OPEN if cooldown_s elapsed (transition happens on get_state() call, not timer)
HALF_OPEN → CLOSED  on record_success()
HALF_OPEN → OPEN    on record_failure() (only 1 probe at a time)
```

`acquire(provider_id)` marks a HALF_OPEN probe in-flight. Providers in any non-CLOSED state
are excluded by `CapabilityRouter` (step 3c).

---

## 11. Rate limiter contract

Two token buckets per provider: RPM (requests per minute) and TPM (tokens per minute).
`effective_capacity = floor(limit * headroom_pct)` (default 80%).
`refill_rate = effective_capacity / 60.0` tokens/sec.
`has_capacity()` checks non-blocking (no consume). `acquire()` consumes from both buckets.
`retry_after_ms` available on `RateDecision` when capacity is insufficient.

---

## 12. Error surface

| Exception | When raised |
|---|---|
| `ValidationError` | Empty `trace_id`, unknown `CapabilityType` |
| `NoEligibleProviderError` | All providers filtered by CB/RL/health/capability |
| `RateLimitError` | All eligible providers rate-limited |
| `CircuitOpenError` | All eligible providers circuit-open |
| `HubTimeoutError` | Request exceeded `timeout_ms` (MH-15) |
| `ProviderError` | Plugin raised (HTTP error, auth, etc.) — may be converted to `NoEligibleProviderError` if all providers exhausted |

All inherit from `ModelHubError(request_id, trace_id, capability)`.
Plugin exceptions are caught inside `ProviderDispatcher` and never exposed directly.

---

## 13. Bus topics

Consumed:
- `k1.model_hub.execute.v1` — inbound `HubRequest` (bus transport path, via `BusEnvelopeDeserializer`)

Produced:

- `k1.model_hub.request.received.v1` — `RequestReceivedPayload`
- `k1.model_hub.response.complete.v1` — `ResponseCompletePayload` (tokens, cost, latency, cache_hit)
- `k1.model_hub.provider.failure.v1` — `ProviderFailurePayload` (from `ProviderDispatcher` when fallback is available)
- `k1.model_hub.fallback.triggered.v1` — `FallbackTriggeredPayload`
- `k1.model_hub.circuit.state.v1` — `CircuitStatePayload` (state transitions)
- `k1.model_hub.provider.registered.v1` — `ProviderRegisteredPayload` (from `ProviderLoader` when wired)
- `k1.model_hub.execute.response.v1` — JSON `HubResponse` reply (bus transport path)

Legacy topics still emitted by `RequestRouter` but not declared in `events.py`:

- `k1.model_hub.request.completed.v1`
- `k1.model_hub.request.failed.v1`

Declared but not emitted by current code: `k1.model_hub.capability.available.v1`.

Declared in `events.py` but not emitted by the current `route()` path:

- `k1.model_hub.request.routed.v1`
- `k1.model_hub.cache.hit.v1` (cache hits currently emit `response.complete.v1` with `cache_hit=True`)
- `k1.model_hub.provider.health.v1`

---

## 14. What Model Hub does NOT do

- Does not execute capabilities or tools (that is Fabric's job)
- Does not persist SessionState or plan state (MH-01)
- Does not enforce cost limits (MH-04 — passive tracking only)
- Does not implement retry logic above MH-16 bounds
- Does not collect streaming token usage (zeroes in streaming `TokenUsage`)
- Does not provide true async streaming for Google/Gemini (runs SDK in thread executor)
- Does not persist the audit log (in-memory only)
