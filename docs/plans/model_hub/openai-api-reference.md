# OpenAI API Reference — Verified from Documentation

> **Source**: All information fetched from `developers.openai.com` on 2026-03-31.
> **Note**: OpenAI's latest flagship models are the GPT-5.4 family. The models below (gpt-4o, o3, etc.) remain available but are predecessors.

---

## 1. Authentication

**Header format:**

```
Authorization: Bearer $OPENAI_API_KEY
```

**Optional org/project headers:**

```
OpenAI-Organization: $ORGANIZATION_ID
OpenAI-Project: $PROJECT_ID
```

HTTP Bearer authentication. API keys managed at <https://developers.openai.com/settings/organization/api-keys>

---

## 2. Chat Completions Endpoint

**`POST /v1/chat/completions`**

### Request Body (JSON)

| Field | Type | Required | Notes |
|---|---|---|---|
| `messages` | `array` | **Yes** | Array of message objects (see message format below) |
| `model` | `string` | **Yes** | e.g. `"gpt-4o"`, `"o3"`, `"o4-mini"` |
| `temperature` | `number` | No | 0–2, default varies by model |
| `max_completion_tokens` | `number` | No | **Preferred field.** Upper bound for generated tokens including reasoning tokens |
| `max_tokens` | `number` | No | **DEPRECATED** — use `max_completion_tokens`. Not compatible with o-series models |
| `stream` | `boolean` | No | Enable SSE streaming |
| `stream_options` | `object` | No | `{"include_usage": true}` to get usage in stream. Only when `stream: true` |
| `tools` | `array` | No | Array of tool definitions (function or custom tools) |
| `tool_choice` | `string\|object` | No | `"none"`, `"auto"`, `"required"`, or `{"type": "function", "function": {"name": "my_fn"}}` |
| `response_format` | `object` | No | `{"type": "text"}`, `{"type": "json_object"}`, or `{"type": "json_schema", "json_schema": {...}}` |
| `reasoning_effort` | `string` | No | `"none"`, `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`. For reasoning models. Default `"medium"` for o-series (pre-gpt-5.1). `"none"` = no reasoning for gpt-5.1+ |
| `n` | `number` | No | Number of choices to generate (1–128) |
| `stop` | `string\|array` | No | Up to 4 stop sequences. **Not supported with o3/o4-mini** |
| `frequency_penalty` | `number` | No | -2.0 to 2.0 |
| `presence_penalty` | `number` | No | -2.0 to 2.0 |
| `top_p` | `number` | No | 0–1, nucleus sampling |
| `logprobs` | `boolean` | No | Return log probabilities |
| `top_logprobs` | `number` | No | 0–20, requires `logprobs: true` |
| `seed` | `number` | No | Deprecated. Best-effort determinism |
| `user` | `string` | No | Deprecated — use `safety_identifier` and `prompt_cache_key` |
| `service_tier` | `string` | No | `"auto"`, `"default"`, `"flex"`, `"priority"` |
| `store` | `boolean` | No | Store output for distillation/evals |
| `metadata` | `object` | No | Up to 16 key-value pairs |
| `parallel_tool_calls` | `boolean` | No | Enable parallel function calling |
| `verbosity` | `string` | No | `"low"`, `"medium"`, `"high"` |
| `web_search_options` | `object` | No | `{"search_context_size": ..., "user_location": ...}` |

### Message Format

```jsonc
// Developer/System message (use "developer" for o1+ models)
{"role": "developer", "content": "You are a helpful assistant.", "name": "optional"}
{"role": "system", "content": "You are a helpful assistant."}  // older models

// User message
{"role": "user", "content": "Hello!"}
// Or multimodal:
{"role": "user", "content": [
  {"type": "text", "text": "What's in this image?"},
  {"type": "image_url", "image_url": {"url": "https://..."}}
]}

// Assistant message
{"role": "assistant", "content": "Hi there!"}

// Tool result message
{"role": "tool", "tool_call_id": "call_abc123", "content": "{\"result\": 42}"}
```

### `max_tokens` vs `max_completion_tokens`

- **`max_completion_tokens`** is the **current/preferred** field. It includes both visible output tokens AND reasoning tokens.
- **`max_tokens`** is **DEPRECATED**. Not compatible with o-series (reasoning) models.
- For a provider plugin: send `max_completion_tokens`. Fall back to `max_tokens` only for legacy callers.

### Response Body (non-streaming)

```json
{
  "id": "chatcmpl-B9MBs8CjcvOU2jLn4n570S5qMJKcT",
  "object": "chat.completion",
  "created": 1741569952,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I assist you today?",
        "refusal": null,
        "annotations": [],
        "tool_calls": null
      },
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 19,
    "completion_tokens": 10,
    "total_tokens": 29,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "audio_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "service_tier": "default"
}
```

**Key response fields:**

- `choices[].message.content` — text response
- `choices[].message.tool_calls` — array of `{id, type, function: {name, arguments}}` when model calls tools
- `choices[].message.refusal` — refusal text if model refuses
- `choices[].finish_reason` — `"stop"`, `"length"`, `"tool_calls"`, `"content_filter"`
- `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens`
- `usage.completion_tokens_details.reasoning_tokens` — tokens used for reasoning (o-series)

### Tool Calls in Response

```json
{
  "message": {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"location\": \"Boston\"}"
        }
      }
    ]
  },
  "finish_reason": "tool_calls"
}
```

---

## 3. Embeddings Endpoint

**`POST /v1/embeddings`**

### Request Body (JSON)

| Field | Type | Required | Notes |
|---|---|---|---|
| `input` | `string\|array` | **Yes** | Text or array of strings/token arrays. Max 8192 tokens per input. Max 300K tokens total per request. Max 2048 array items |
| `model` | `string` | **Yes** | e.g. `"text-embedding-3-small"`, `"text-embedding-3-large"` |
| `dimensions` | `number` | No | Override output dimensions. Only for `text-embedding-3` models. Min: 1 |
| `encoding_format` | `string` | No | `"float"` (default) or `"base64"` |
| `user` | `string` | No | End-user identifier |

### Response Body

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [0.0023064255, -0.009327292, ...],
      "index": 0
    }
  ],
  "model": "text-embedding-3-small",
  "usage": {
    "prompt_tokens": 8,
    "total_tokens": 8
  }
}
```

**Key fields:**

- `data[].embedding` — float array (or base64 string if `encoding_format: "base64"`)
- `data[].index` — position in input array
- `usage.prompt_tokens`, `usage.total_tokens`

---

## 4. Images Endpoint

**`POST /v1/images/generations`**

### Request Body (JSON)

| Field | Type | Required | Notes |
|---|---|---|---|
| `prompt` | `string` | **Yes** | Max 32000 chars (GPT image models), 4000 (dall-e-3), 1000 (dall-e-2) |
| `model` | `string` | No | `"dall-e-2"` (default), `"dall-e-3"`, `"gpt-image-1"`, `"gpt-image-1-mini"`, `"gpt-image-1.5"` |
| `n` | `number` | No | 1–10. dall-e-3 only supports `n=1` |
| `size` | `string` | No | GPT image: `"1024x1024"`, `"1536x1024"`, `"1024x1536"`, `"auto"`. dall-e-3: `"1024x1024"`, `"1792x1024"`, `"1024x1792"`. dall-e-2: `"256x256"`, `"512x512"`, `"1024x1024"` |
| `quality` | `string` | No | GPT image: `"auto"`, `"high"`, `"medium"`, `"low"`. dall-e-3: `"standard"`, `"hd"`. dall-e-2: `"standard"` only |
| `response_format` | `string` | No | `"url"` or `"b64_json"`. **Only for dall-e-2/3**. GPT image models always return base64 |
| `output_format` | `string` | No | GPT image models only: `"png"`, `"jpeg"`, `"webp"` |
| `background` | `string` | No | GPT image models only: `"transparent"`, `"opaque"`, `"auto"` |
| `style` | `string` | No | dall-e-3 only: `"vivid"` or `"natural"` |
| `user` | `string` | No | End-user identifier |

### Response Body

```json
{
  "created": 1234567890,
  "data": [
    {
      "b64_json": "<base64-encoded-image>",
      "revised_prompt": "A cute baby sea otter swimming...",
      "url": "https://..."
    }
  ],
  "background": "transparent",
  "output_format": "png",
  "quality": "low",
  "size": "1024x1024",
  "usage": {
    "input_tokens": 0,
    "input_tokens_details": {"image_tokens": 0, "text_tokens": 0},
    "output_tokens": 0,
    "total_tokens": 0,
    "output_tokens_details": {"image_tokens": 0, "text_tokens": 0}
  }
}
```

**Key fields:**

- `data[].url` — temporary URL (60 min, dall-e only)
- `data[].b64_json` — base64 image data (GPT image models always use this)
- `data[].revised_prompt` — the prompt actually used

---

## 5. Audio Endpoints

### 5a. Transcription (Speech-to-Text)

**`POST /v1/audio/transcriptions`** (multipart/form-data)

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | `file` | **Yes** | Audio file: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm |
| `model` | `string` | **Yes** | `"whisper-1"`, `"gpt-4o-transcribe"`, `"gpt-4o-mini-transcribe"`, `"gpt-4o-transcribe-diarize"` |
| `language` | `string` | No | ISO-639-1 code (e.g. `"en"`) |
| `prompt` | `string` | No | Guide model style |
| `response_format` | `string` | No | `"json"`, `"text"`, `"srt"`, `"verbose_json"`, `"vtt"`, `"diarized_json"`. For gpt-4o-transcribe: only `"json"` |
| `temperature` | `number` | No | 0–1 |
| `timestamp_granularities` | `array` | No | `["word"]`, `["segment"]`, or both. Requires `verbose_json` |
| `stream` | `boolean` | No | SSE streaming. **Not supported for whisper-1** |

**Response (JSON format):**

```json
{
  "text": "Imagine the wildest idea...",
  "usage": {
    "type": "tokens",
    "input_tokens": 14,
    "input_token_details": {"text_tokens": 0, "audio_tokens": 14},
    "output_tokens": 45,
    "total_tokens": 59
  }
}
```

### 5b. Speech (Text-to-Speech)

**`POST /v1/audio/speech`** (JSON body, returns audio binary)

| Field | Type | Required | Notes |
|---|---|---|---|
| `input` | `string` | **Yes** | Text to speak. Max 4096 characters |
| `model` | `string` | **Yes** | `"tts-1"`, `"tts-1-hd"`, `"gpt-4o-mini-tts"` |
| `voice` | `string\|object` | **Yes** | Built-in: `"alloy"`, `"ash"`, `"ballad"`, `"coral"`, `"echo"`, `"fable"`, `"onyx"`, `"nova"`, `"sage"`, `"shimmer"`, `"verse"`, `"marin"`, `"cedar"`. Or custom: `{"id": "voice_1234"}` |
| `response_format` | `string` | No | `"mp3"` (default), `"opus"`, `"aac"`, `"flac"`, `"wav"`, `"pcm"` |
| `speed` | `number` | No | 0.25–4.0, default 1.0 |
| `instructions` | `string` | No | Voice control instructions. Max 4096 chars. **Not supported for tts-1 or tts-1-hd** |

**Response:** Raw audio binary in the requested format. No JSON wrapper.

**Example:**

```bash
curl https://api.openai.com/v1/audio/speech \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini-tts", "input": "Hello world.", "voice": "alloy"}' \
  --output speech.mp3
```

---

## 6. Moderations Endpoint

**`POST /v1/moderations`**

### Request Body (JSON)

| Field | Type | Required | Notes |
|---|---|---|---|
| `input` | `string\|array` | **Yes** | Text/array of strings/multi-modal input |
| `model` | `string` | No | Moderation model ID |

### Response Body

```json
{
  "id": "modr-abc123",
  "model": "text-moderation-007",
  "results": [
    {
      "categories": {
        "harassment": false,
        "harassment/threatening": false,
        "hate": false,
        "hate/threatening": false,
        "illicit": false,
        "illicit/violent": false,
        "self-harm": false,
        "self-harm/instructions": false,
        "self-harm/intent": false,
        "sexual": false,
        "sexual/minors": false,
        "violence": true,
        "violence/graphic": false
      },
      "category_scores": {
        "harassment": 0.001,
        "violence": 0.95
      },
      "flagged": true
    }
  ]
}
```

---

## 7. Models — Verified Specs

| Model | Type | Context Window | Max Output Tokens | Notes |
|---|---|---|---|---|
| **gpt-4o** | GPT (non-reasoning) | 128,000 | 16,384 | Alias → `gpt-4o-2024-08-06`. Knowledge cutoff Oct 2023. $2.50/$10 per 1M tokens |
| **gpt-4o-mini** | GPT (non-reasoning) | 128,000 | 16,384 | Alias → `gpt-4o-mini-2024-07-18`. Knowledge cutoff Oct 2023. $0.15/$0.60 per 1M tokens |
| **o3** | Reasoning model | 200,000 | 100,000 | Alias → `o3-2025-04-16`. Knowledge cutoff Jun 2024. $2.00/$8.00 per 1M tokens. Reasoning token support. Succeeded by GPT-5 |
| **o4-mini** | Reasoning model | 200,000 | 100,000 | Alias → `o4-mini-2025-04-16`. Knowledge cutoff Jun 2024. $1.10/$4.40 per 1M tokens. Reasoning token support. Succeeded by GPT-5 mini |
| **text-embedding-3-small** | Embedding | 8,192 tokens | N/A | Default 1536 dimensions. Supports `dimensions` param to reduce. $0.02 per 1M tokens |
| **text-embedding-3-large** | Embedding | 8,192 tokens | N/A | Default 3072 dimensions. Supports `dimensions` param to reduce. $0.13 per 1M tokens |
| **dall-e-3** | Image generation | N/A | N/A | Sizes: 1024x1024, 1792x1024, 1024x1792. n=1 only. **Deprecated snapshot** |
| **gpt-image-1** | Image generation | N/A | N/A | Sizes: 1024x1024, 1536x1024, 1024x1536. Always returns b64_json. Quality: low/medium/high |
| **gpt-image-1.5** | Image generation | N/A | N/A | Latest image model. Supports streaming |
| **whisper-1** | Transcription (STT) | N/A | N/A | Powered by Whisper V2. No streaming support |
| **gpt-4o-transcribe** | Transcription (STT) | N/A | N/A | Newer transcription model. Supports streaming |
| **tts-1** | Speech (TTS) | N/A | N/A | Optimized for speed. Max 4096 chars input. No `instructions` support |
| **tts-1-hd** | Speech (TTS) | N/A | N/A | Higher quality. Max 4096 chars input. No `instructions` support |
| **gpt-4o-mini-tts** | Speech (TTS) | N/A | N/A | Supports `instructions` param for voice control |

### Reasoning Models Key Differences

- o3 and o4-mini use `max_completion_tokens` (NOT `max_tokens`)
- `stop` parameter is **not supported** with o3 and o4-mini
- Use `"developer"` role instead of `"system"` for o1+ models
- `reasoning_effort` controls thinking depth: `"low"`, `"medium"` (default), `"high"`
- `usage.completion_tokens_details.reasoning_tokens` shows internal reasoning cost

---

## 8. Rate Limit Headers

Returned with every API response:

| Header | Description |
|---|---|
| `x-ratelimit-limit-requests` | Max requests allowed in the time window |
| `x-ratelimit-limit-tokens` | Max tokens allowed in the time window |
| `x-ratelimit-remaining-requests` | Remaining requests in current window |
| `x-ratelimit-remaining-tokens` | Remaining tokens in current window |
| `x-ratelimit-reset-requests` | Time until request limit resets |
| `x-ratelimit-reset-tokens` | Time until token limit resets |

**Other useful response headers:**

| Header | Description |
|---|---|
| `x-request-id` | Unique ID for troubleshooting |
| `openai-organization` | Org associated with request |
| `openai-processing-ms` | Processing time in ms |
| `openai-version` | REST API version (currently `2020-10-01`) |

**Client-sent debug header:**

```
X-Client-Request-Id: <your-trace-id>
```

ASCII only, max 512 chars. Logged by OpenAI for support troubleshooting.

---

## 9. Error Response Format

**HTTP error response body:**

```json
{
  "error": {
    "message": "Incorrect API key provided: sk-1234...5678.",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_api_key"
  }
}
```

**Common HTTP status codes:**

| Code | Meaning |
|---|---|
| 400 | Bad request / malformed parameters |
| 401 | Invalid authentication / incorrect API key |
| 403 | Country/region not supported |
| 404 | Resource not found |
| 429 | Rate limit exceeded OR quota exceeded |
| 500 | Internal server error |
| 503 | Server overloaded / slow down |

**Error `type` values:** `invalid_request_error`, `authentication_error`, `permission_error`, `not_found_error`, `rate_limit_error`, `server_error`

---

## 10. Streaming Format (Chat Completions)

**Protocol:** Server-Sent Events (SSE)

Each event is prefixed with `data:` and separated by double newlines. Stream ends with `data: [DONE]`.

### Wire Format

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694268190,"model":"gpt-4o-mini","system_fingerprint":"fp_44709d6fcb","choices":[{"index":0,"delta":{"role":"assistant","content":""},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694268190,"model":"gpt-4o-mini","system_fingerprint":"fp_44709d6fcb","choices":[{"index":0,"delta":{"content":"Hello"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694268190,"model":"gpt-4o-mini","system_fingerprint":"fp_44709d6fcb","choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"stop"}]}

data: [DONE]
```

### Chunk Object Structure

```jsonc
{
  "id": "chatcmpl-123",              // Same ID for all chunks
  "object": "chat.completion.chunk",  // Always this value
  "created": 1694268190,              // Same timestamp for all chunks
  "model": "gpt-4o-mini",
  "system_fingerprint": "fp_44709d6fcb",
  "choices": [
    {
      "index": 0,
      "delta": {
        "role": "assistant",    // Only in first chunk
        "content": "Hello",     // Incremental text content
        "tool_calls": [...]     // Incremental tool call data
      },
      "logprobs": null,
      "finish_reason": null     // null until final chunk → "stop", "tool_calls", "length", etc.
    }
  ],
  "service_tier": "default",
  "usage": null  // null unless stream_options.include_usage=true AND it's the final chunk
}
```

### Delta Fields

- **First chunk:** `delta` contains `{"role": "assistant", "content": ""}` (or `"content": null`)
- **Content chunks:** `delta` contains `{"content": "token text"}`
- **Tool call chunks:** `delta` contains `{"tool_calls": [{"index": 0, "id": "call_...", "type": "function", "function": {"name": "get_weather", "arguments": ""}}]}`
  - Subsequent chunks append to `arguments`: `{"tool_calls": [{"index": 0, "function": {"arguments": "{\"lo"}}]}`
- **Final chunk:** `delta` is `{}`, `finish_reason` is set
- **Usage chunk** (if `stream_options.include_usage: true`): `choices` is `[]`, `usage` contains full token counts

### Streaming Usage (opt-in)

Request with:

```json
{"stream": true, "stream_options": {"include_usage": true}}
```

The final chunk before `[DONE]` will have:

```json
{"choices": [], "usage": {"prompt_tokens": 19, "completion_tokens": 10, "total_tokens": 29, ...}}
```

---

## Quick Reference: Provider Plugin Implementation Checklist

1. **Auth**: `Authorization: Bearer {key}` header on every request
2. **Chat**: POST to `/v1/chat/completions`, use `max_completion_tokens` (not `max_tokens`)
3. **Streaming**: Parse SSE lines starting with `data:`, accumulate `delta.content`, detect `[DONE]`
4. **Embeddings**: POST to `/v1/embeddings`, response in `data[].embedding`
5. **Images**: POST to `/v1/images/generations`, GPT image models return `data[].b64_json`
6. **TTS**: POST to `/v1/audio/speech`, response is raw binary audio
7. **STT**: POST to `/v1/audio/transcriptions` as multipart/form-data
8. **Rate limits**: Read `x-ratelimit-remaining-*` headers for backoff
9. **Errors**: Parse `error.message`, `error.type`, `error.code` from JSON body
10. **Reasoning models**: Use `reasoning_effort`, `max_completion_tokens`, `"developer"` role, read `reasoning_tokens` from usage
