# PoC: LLM Inference via OpenRouter (Streaming + TTFT)

**Status:** ✅ Ready to Test

## Overview

Tests LLM inference with **streaming** and **TTFT measurement** via OpenRouter API.
Model: **Nvidia Nemotron Nano 12B** (free tier) via OpenRouter with real-time token streaming.

**Target SLO:** P95 TTFT < 200ms (streaming first token latency)
**Model:** nvidia/nemotron-nano-12b-v2-vl:free (12B parameters, free tier)
**Execution:** Cloud-based via OpenRouter API (no local hardware needed)

## Key Features

- **Streaming:** Real-time token output as they arrive
- **TTFT Measurement:** Time to receive first token (what users perceive)
- **Total Latency:** Time to complete generation
- **Async Support:** Parallel batch inference
- **Error Handling:** Robust connection and parsing

## Performance Target

| Metric | Target | Status |
|--------|--------|--------|
| P95 TTFT | < 200ms | ⏳ Testing |
| P99 TTFT | < 300ms | ⏳ Testing |
| Mean TTFT | < 150ms | ⏳ Testing |
| Throughput | 5+ req/sec | ⏳ Testing |

## Setup

### Prerequisites

1. **OpenRouter API Key** - Get from https://openrouter.io/
2. **Python 3.11+**
3. **Dependencies** - httpx, numpy, pytest

### Installation

```bash
pip install -r requirements.txt
```

### Set API Key

**PowerShell:**
```powershell
$env:OPENROUTER_API_KEY = 'your-api-key-here'
```

**Command Prompt:**
```cmd
set OPENROUTER_API_KEY=your-api-key-here
```

**Linux/Mac:**
```bash
export OPENROUTER_API_KEY="your-api-key-here"
```

## Run PoC

```bash
python poc_openrouter_streaming.py
```

## Expected Output

```
======================================================================
PoC: LLM Inference via OpenRouter (Streaming + TTFT)
======================================================================

[CONFIG] Model: nvidia/nemotron-nano-12b-v2-vl:free
[CONFIG] API: https://openrouter.ai/api/v1
[INFO] Testing connectivity to OpenRouter...
[OK] OpenRouter API is reachable

[TEST] Single Inference with Streaming...
[QUERY] What is the capital of France?

  [STREAM] Paris is the capital of France, located in the north-central part...
  TTFT: 142.35ms | Total: 2156.78ms

[TEST] Batch Inference (3 parallel)...
[QUERY] What is 2+2?
[QUERY] What is the largest planet?
[QUERY] What is Python used for?
  Completed: 3/3 inferences

[TEST] Sequential Inference (5 samples for metrics)...
  [1/5] [QUERY] What is AI?
         [TTFT] 156.23ms | [Total] 2341.50ms
  ...

======================================================================
Performance Metrics (TTFT - Time To First Token)
======================================================================
  count                :        9.000
  ttft_mean_ms         :      152.340
  ttft_p50_ms          :      148.560
  ttft_p95_ms          :      178.900
  ttft_p99_ms          :      189.230
  ttft_min_ms          :      142.350
  ttft_max_ms          :      192.560
  ttft_stddev_ms       :       16.780
  total_mean_ms        :     2456.780
  total_p95_ms         :     2890.560

[SLO] P95 TTFT: 178.90ms vs Target: 200ms - ✅ PASSED
```

## Test Cases

### Unit Tests

Run tests:
```bash
python -m pytest test_openrouter_streaming.py -v
```

Tests cover:
- Result dataclass fields
- Metrics computation (empty/single/multiple)
- SLO validation (pass/fail)
- Initialization (default/custom model)

## Integration with K1

**Future Integration Points:**
- Phase 1 (Negotiation): Use TTFT for agent capability scoring
- Phase 2 (Selection): Rank proposals based on model latency
- Phase 3 (DAG Execution): Agent planning with streaming LLM

## API Details

**Endpoint:** `https://openrouter.io/api/v1/chat/completions`

**Headers:**
- `Authorization: Bearer {API_KEY}`
- `HTTP-Referer: http://localhost:8000`
- `X-Title: FamilyOS-K1`

**Request:**
```json
{
  "model": "nvidia/nemotron-nano-12b-v2-vl:free",
  "messages": [{"role": "user", "content": "..."}],
  "stream": true,
  "max_tokens": 256,
  "temperature": 0.7
}
```

**Response (streaming):**
```
data: {"choices":[{"delta":{"content":"token"}}]}
data: [DONE]
```

## Pricing

OpenRouter charges per token (input + output).
**Nvidia Nemotron Nano 12B (free tier):** $0 - completely free for testing!

For PoC testing: **FREE** - no costs for unlimited inference.

Other premium models available on OpenRouter if needed.

## Next Steps

1. Get OpenRouter API key
2. Set `OPENROUTER_API_KEY` environment variable
3. Run `python poc_openrouter_streaming.py`
4. Validate TTFT < 200ms SLO
5. Integrate streaming into K1 orchestrator phases
