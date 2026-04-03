# vLLM API Reference — Verified from Documentation

> **Source**: All information fetched from `docs.vllm.ai/en/stable/` (v0.18.1) on 2026-07-15.
> **Note**: vLLM provides an OpenAI-compatible HTTP server. The official Python `openai` client works against it.

---

## 1. API Compatibility & Supported Endpoints

vLLM implements a subset of the OpenAI API. All endpoints are prefixed under the same path structure.

### OpenAI-Compatible Endpoints

| Endpoint | Method | Notes |
|---|---|---|
| `/v1/chat/completions` | POST | Chat Completions API. Requires chat template. `user` param **ignored**. `image_url.detail` **not supported** |
| `/v1/completions` | POST | Completions API (text generation models only). `suffix` **not supported** |
| `/v1/embeddings` | POST | Embeddings API (embedding models only) |
| `/v1/models` | GET | List available models |
| `/v1/responses` | POST | Responses API (text generation models) |
| `/v1/audio/transcriptions` | POST | Transcriptions API (ASR models only) |
| `/v1/audio/translations` | POST | Translation API (ASR models only) |
| `/v1/realtime` | WebSocket | Realtime WebSocket API (ASR models only) |

### vLLM-Specific Endpoints

| Endpoint | Method | Notes |
|---|---|---|
| `/tokenize` | POST | Tokenizer API |
| `/detokenize` | POST | Detokenizer API |
| `/pooling` | POST | Pooling API |
| `/classify` | POST | Classification API |
| `/v2/embed` | POST | Cohere Embed API compatible |
| `/score` | POST | Score API |
| `/rerank` | POST | Rerank API (also `/v1/rerank`, `/v2/rerank` for Jina/Cohere compat) |
| `/health` | GET | Health check endpoint |

---

## 2. Chat Completions — `/v1/chat/completions`

Compatible with the OpenAI Chat Completions API. Uses the official `openai` Python client.

### Request Body (JSON)

| Field | Type | Required | vLLM Support |
|---|---|---|---|
| `messages` | `array` | **Yes** | Supported. Requires chat template |
| `model` | `string` | **Yes** | Must match the served model name |
| `temperature` | `number` | No | Supported |
| `max_tokens` | `number` | No | Supported (alias for `max_completion_tokens`) |
| `max_completion_tokens` | `number` | No | Supported |
| `stream` | `boolean` | No | Supported (SSE) |
| `stream_options` | `object` | No | Supported. `{"include_usage": true}` |
| `tools` | `array` | No | Supported (requires `--enable-auto-tool-choice` and `--tool-call-parser`) |
| `tool_choice` | `string\|object` | No | `"none"`, `"auto"`, `"required"` (≥v0.8.3), or named function |
| `parallel_tool_calls` | `boolean` | No | Supported. `false` = zero or one tool call. `true` (default) = allows multiple |
| `response_format` | `object` | No | Supported (structured outputs) |
| `n` | `number` | No | Supported |
| `stop` | `string\|array` | No | Supported |
| `frequency_penalty` | `number` | No | Supported |
| `presence_penalty` | `number` | No | Supported |
| `top_p` | `number` | No | Supported |
| `logprobs` | `boolean` | No | Supported |
| `top_logprobs` | `number` | No | Supported |
| `seed` | `number` | No | Supported |
| `user` | `string` | No | **Accepted but IGNORED** |

### NOT Supported vs OpenAI

| Feature | Status |
|---|---|
| `image_url.detail` param | **Not supported** |
| `suffix` (completions) | **Not supported** |
| `strict` mode on function schemas | **Accepted but has NO EFFECT** (no constrained decoding in `auto` mode) |
| `user` field | **Accepted but ignored** |

### Response Body

Same format as OpenAI. Example:

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "NousResearch/Meta-Llama-3-8B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?",
        "tool_calls": null
      },
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 19,
    "completion_tokens": 10,
    "total_tokens": 29
  }
}
```

### `finish_reason` values

- `"stop"` — natural completion or stop sequence
- `"length"` — hit `max_tokens`
- `"tool_calls"` — model generated tool calls

---

## 3. Streaming Format

**Protocol:** Server-Sent Events (SSE) — identical wire format to OpenAI.

Each event is `data: {json}\n\n`. Stream ends with `data: [DONE]\n\n`.

### Chunk Object

```jsonc
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion.chunk",
  "created": 1700000000,
  "model": "NousResearch/Meta-Llama-3-8B-Instruct",
  "choices": [
    {
      "index": 0,
      "delta": {
        "role": "assistant",   // first chunk only
        "content": "Hello"     // incremental content
      },
      "logprobs": null,
      "finish_reason": null    // null until final → "stop", "tool_calls", "length"
    }
  ]
}
```

### Streaming Usage (opt-in)

Request: `{"stream": true, "stream_options": {"include_usage": true}}`

Final chunk before `[DONE]` has `"choices": []` and `"usage": {...}`.

---

## 4. Tool Calling

### Server Requirements

Tool calling requires specific server flags:

```bash
vllm serve <model> \
    --enable-auto-tool-choice \
    --tool-call-parser <parser_name> \
    --chat-template <optional_template>
```

### `tool_choice` Modes

| Mode | Constrained Decoding | Behavior |
|---|---|---|
| Named function (`{"type": "function", "function": {"name": "..."}}`) | **Yes** (structured outputs) | Arguments guaranteed valid JSON matching schema |
| `"required"` | **Yes** (structured outputs) | Must produce ≥1 tool call. Schema-conformant. (≥v0.8.3) |
| `"auto"` | **No** | Model generates freely. Parser extracts tool calls from raw text. **Arguments may be malformed** |
| `"none"` | N/A | No tool calls produced |

### Available Tool Call Parsers

| Parser | Models | Flag |
|---|---|---|
| `hermes` | Hermes 2 Pro/Theta/3, Qwen2.5, QwQ-32B | `--tool-call-parser hermes` |
| `mistral` | Mistral-7B-Instruct-v0.3+ | `--tool-call-parser mistral` |
| `llama3_json` | Llama 3.1, 3.2 | `--tool-call-parser llama3_json` |
| `llama4_pythonic` | Llama 4 Scout/Maverick | `--tool-call-parser llama4_pythonic` |
| `granite` | Granite 3.x | `--tool-call-parser granite` |
| `granite4` | Granite 4.0 | `--tool-call-parser granite4` |
| `internlm` | InternLM 2.5 | `--tool-call-parser internlm` |
| `jamba` | AI21 Jamba 1.5 | `--tool-call-parser jamba` |
| `xlam` | Salesforce xLAM | `--tool-call-parser xlam` |
| `deepseek_v3` | DeepSeek-V3-0324, DeepSeek-R1-0528 | `--tool-call-parser deepseek_v3` |
| `deepseek_v31` | DeepSeek-V3.1 | `--tool-call-parser deepseek_v31` |
| `pythonic` | Llama 3.2 (small), ToolACE-8B | `--tool-call-parser pythonic` |
| `openai` | gpt-oss-20b, gpt-oss-120b | `--tool-call-parser openai` |
| `kimi_k2` | Kimi-K2-Instruct | `--tool-call-parser kimi_k2` |
| `minimax` | MiniMax-M1 | `--tool-call-parser minimax` |
| `hunyuan_a13b` | Hunyuan-A13B-Instruct | `--tool-call-parser hunyuan_a13b` |
| `glm45` | GLM-4.5, GLM-4.6 | `--tool-call-parser glm45` |
| `glm47` | GLM-4.7 | `--tool-call-parser glm47` |
| `olmo3` | Olmo-3-7B/32B | `--tool-call-parser olmo3` |
| `qwen3_xml` | Qwen3-Coder | `--tool-call-parser qwen3_xml` |
| `functiongemma` | FunctionGemma-270M | `--tool-call-parser functiongemma` |
| `gigachat3` | GigaChat3 | `--tool-call-parser gigachat3` |
| `longcat` | LongCat-Flash-Chat | `--tool-call-parser longcat` |

### Custom Tool Parser Plugin

You can register custom parsers via:

```bash
--tool-parser-plugin /path/to/plugin.py --tool-call-parser my_parser
```

Plugin must implement `ToolParser` similar to `vllm/tool_parsers/hermes_tool_parser.py`.

---

## 5. Embeddings — `/v1/embeddings`

### Request Body (JSON)

| Field | Type | Required | Notes |
|---|---|---|---|
| `input` | `string\|array` | **Yes** | Text or array of strings |
| `model` | `string` | **Yes** | Must be an embedding model |
| `encoding_format` | `string` | No | `"float"` or `"base64"` |

### Response Body

Same format as OpenAI:

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [0.0023, -0.0093, ...],
      "index": 0
    }
  ],
  "model": "intfloat/e5-mistral-7b-instruct",
  "usage": {
    "prompt_tokens": 8,
    "total_tokens": 8
  }
}
```

---

## 6. Authentication

### Configuration

| Method | How |
|---|---|
| `--api-key` CLI arg | `vllm serve <model> --api-key token-abc123` |
| `VLLM_API_KEY` env var | `export VLLM_API_KEY=token-abc123` |
| Multiple keys | Pass multiple values after `--api-key` for key rotation |
| No auth (default) | If neither is set, **no authentication required** |

### Client Usage

Same as OpenAI — pass the key in the `Authorization` header:

```
Authorization: Bearer token-abc123
```

Or via `openai` Python client:

```python
from openai import OpenAI
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="token-abc123",
)
```

---

## 7. Server Startup

### Basic Command

```bash
vllm serve <model_name_or_path> [options]
```

### Examples

```bash
# Minimal
vllm serve Qwen/Qwen2.5-1.5B-Instruct

# With auth and dtype
vllm serve NousResearch/Meta-Llama-3-8B-Instruct \
    --dtype auto \
    --api-key token-abc123

# With tool calling
vllm serve meta-llama/Llama-3.1-8B-Instruct \
    --enable-auto-tool-choice \
    --tool-call-parser llama3_json \
    --chat-template examples/tool_chat_template_llama3.1_json.jinja

# Custom host/port
vllm serve <model> --host 0.0.0.0 --port 8080
```

### Key Server Arguments

| Argument | Default | Description |
|---|---|---|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8000` | Bind port |
| `--dtype` | auto | Model data type (`auto`, `float16`, `bfloat16`, etc.) |
| `--api-key` | (none) | API key(s) for authentication |
| `--chat-template` | (from model) | Path to Jinja chat template, or `tool_use` for HF multi-template |
| `--chat-template-content-format` | auto | `"string"` or `"openai"` content format |
| `--enable-auto-tool-choice` | (off) | Enable model to autonomously generate tool calls |
| `--tool-call-parser` | (none) | Select tool parser (see table above) |
| `--tool-parser-plugin` | (none) | Path to custom tool parser plugin file |
| `--generation-config` | (from HF) | Override generation config. Use `vllm` for vLLM defaults |

### Configuration File

Server arguments can also be provided via a YAML/JSON config file instead of CLI args (see `https://docs.vllm.ai/en/stable/configuration/serve_args/`).

---

## 8. Base URL & Client Setup

**Default base URL:** `http://localhost:8000`

**OpenAI client setup:**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="token-abc123",  # or "EMPTY" if no auth configured
)

# Chat completion
response = client.chat.completions.create(
    model="Qwen/Qwen2.5-1.5B-Instruct",
    messages=[{"role": "user", "content": "Hello!"}],
)

# List models
models = client.models.list()
```

**curl:**

```bash
# List models
curl http://localhost:8000/v1/models

# Chat completion
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-abc123" \
  -d '{"model": "Qwen/Qwen2.5-1.5B-Instruct", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## 9. Model Support

vLLM serves **one model per server instance** (the model specified in `vllm serve`). The model name in API requests must match the served model.

### Supported Model Families (text generation — partial list)

Llama (1/2/3/3.1/3.2/4), Mistral, Mixtral, Qwen (1/2/2.5/3/3.5), DeepSeek (V2/V3/V3.1/R1), Gemma (1/2/3/3n), Phi (3/4), GPT-2, GPT-J, GPT-NeoX, Falcon, StarCoder2, Command-R, Jamba, Granite, InternLM, OLMo, DBRX, and many more.

### Supported Embedding Models

Served via the `/v1/embeddings` endpoint when an embedding model is loaded.

### Supported Audio/ASR Models

Whisper and other ASR models served via `/v1/audio/transcriptions`.

For the full list: `https://docs.vllm.ai/en/stable/models/supported_models/`

---

## 10. Health Endpoint

**`GET /health`**

Returns server readiness status. Used for load balancer health checks and startup probes.

---

## 11. Error Response Format

vLLM follows the OpenAI error format:

```json
{
  "object": "error",
  "message": "The model `nonexistent-model` does not exist.",
  "type": "NotFoundError",
  "param": null,
  "code": 404
}
```

Standard HTTP status codes apply (400, 401, 404, 500, etc.).

---

## 12. Key Differences from OpenAI API

| Aspect | OpenAI | vLLM |
|---|---|---|
| **Model selection** | Multiple models via `model` field | Single model per server instance |
| **Authentication** | Always required (API key) | Optional (off by default) |
| **`user` field** | Used for abuse tracking | **Accepted but ignored** |
| **`image_url.detail`** | Supported | **Not supported** |
| **`suffix` (completions)** | Supported | **Not supported** |
| **`strict` mode (tools)** | Enforces schema in auto mode | **Accepted, no effect** |
| **Tool calling** | Built-in for all chat models | Requires `--enable-auto-tool-choice` + `--tool-call-parser` |
| **Reasoning models** | o-series with `reasoning_effort` | No direct equivalent (model-dependent) |
| **Rate limits** | Token/request limits with headers | No built-in rate limiting |
| **Health endpoint** | N/A | `GET /health` |
| **Extra endpoints** | N/A | `/tokenize`, `/detokenize`, `/pooling`, `/classify`, `/score`, `/rerank` |
| **Streaming** | SSE, `data: [DONE]` | Identical SSE format |

---

## Quick Reference: Provider Plugin Implementation Checklist (vLLM)

1. **Auth**: `Authorization: Bearer {key}` — only if server configured with `--api-key`. If no auth, send `api_key="EMPTY"` with openai client
2. **Chat**: POST to `/v1/chat/completions` — same request/response format as OpenAI
3. **Streaming**: Identical SSE format — `data: {json}\n\n`, `data: [DONE]`
4. **Embeddings**: POST to `/v1/embeddings` — same format as OpenAI
5. **Tool calling**: Only works if server started with `--enable-auto-tool-choice` and `--tool-call-parser`. Prefer `tool_choice="required"` for guaranteed schema conformance
6. **Model name**: Must match the exact model name/path used in `vllm serve`
7. **Base URL**: Default `http://localhost:8000/v1`
8. **Health**: `GET /health` for readiness probes
9. **Errors**: Same JSON error format as OpenAI (`error.message`, `error.type`, `error.code`)
10. **No rate limit headers**: vLLM does not return `x-ratelimit-*` headers
11. **Extra params**: vLLM accepts additional sampling parameters beyond the OpenAI spec
