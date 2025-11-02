# PoC: Local LLM Inference via Lemonade Server (Streaming + TTFT)

**Status:** ✅ Implementation Ready

## Overview

Tests local SLM (Small Language Model) inference performance using **streaming** with **TTFT measurement** (Time To First Token).
Model: Qwen-2.5-1.5B-Instruct-NPU on AMD Ryzen AI NPU via Lemonade Server.

**Target SLO:** P95 TTFT < 150ms (streaming first token latency)
**Model:** Qwen-2.5-1.5B-Instruct-NPU (1.5B parameters, optimized for Ryzen AI NPU)
**Execution Provider:** AMD Ryzen AI NPU (via Lemonade Server)

## Key Differences from Total Latency

- **Total Latency:** Time to complete entire generation (10-15s for long responses)
- **TTFT (Time To First Token):** Time to receive first token from streaming API (100-300ms)
- **Why TTFT matters:** User perceives latency from first character, not last
- **Streaming:** Enables incremental display, better UX, measurable TTFT

## Architecture

```
User Request
    ↓
LocalLLMInferencePOC (OpenAI Client)
    ↓
Lemonade Server (localhost:8000/api/v1)
    ↓
ONNX Runtime + AMD Ryzen AI EP
    ↓
Model Inference
    ↓
Response + Metrics
```

## Components

### LocalLLMInferencePOC
- **Single Inference:** `inference_single(prompt)` - Synchronous inference
- **Async Inference:** `inference_async(prompt)` - Async wrapper for concurrency
- **Batch Inference:** `inference_batch_async(prompts)` - Parallel batch execution
- **Connectivity Test:** `test_connectivity()` - Verify Lemonade Server is reachable
- **Metrics:** `compute_metrics()` - Latency percentiles (p50, p95, p99)
- **SLO Validation:** `validate_slo()` - Check against performance budget

### InferenceResult
- `prompt`: User input
- `response`: Model output
- `latency_ms`: Inference time
- `model`: Model identifier
- `timestamp`: Unix timestamp

## Performance Target

| Metric | Target | Status |
|--------|--------|--------|
| P95 TTFT | < 150ms | ⏳ Testing |
| P99 TTFT | < 200ms | ⏳ Testing |
| Mean TTFT | < 100ms | ⏳ Testing |
| Throughput | 10+ req/sec | ⏳ Testing |

## Setup

### Prerequisites
1. **Lemonade Server** running on `localhost:8000`
2. **Llama-3.2-1B-Instruct-Hybrid** model loaded
3. **AMD Ryzen AI drivers + ONNX Runtime** configured

### Installation
```bash
pip install -r requirements.txt
```

### Run PoC
```bash
# Single run
python poc_local_llm_inference.py

# Run with pytest
python -m pytest test_local_llm_inference.py -v
```

## Expected Output

```
======================================================================
PoC: Local LLM Inference via Lemonade Server
======================================================================
[INFO] Testing connectivity to http://localhost:8000/api/v1...
[OK] Lemonade Server is reachable

[TEST] Single Inference...
  Response: Paris is the capital of France...
  Latency: 245.67ms

[TEST] Batch Inference (5 parallel)...
  Completed: 5/5 inferences

[TEST] Sequential Inference (10 samples for metrics)...
  [1/10] What is AI?... (240.12ms)
  [2/10] Explain machine learning... (256.34ms)
  ...

======================================================================
Performance Metrics
======================================================================
  count           :        10.000
  mean_ms         :       250.156
  p50_ms          :       248.230
  p95_ms          :       267.450
  p99_ms          :       289.123
  min_ms          :       235.670
  max_ms          :       312.456
  stddev_ms       :        24.320

[SLO] P95: 267.45ms vs Target: 500ms - ✅ PASSED
```

## Test Cases

### Unit Tests (14 tests)
1. **Connectivity**: Server reachability tests
2. **Single Inference**: Success/failure handling, result storage
3. **Batch Inference**: Parallel execution, partial failures
4. **Metrics Computation**: Empty/single/multiple results
5. **SLO Validation**: Pass/fail/edge cases
6. **Edge Cases**: Empty prompts, large prompts, special characters

### Run Tests
```bash
python -m pytest test_local_llm_inference.py -v --tb=short
```

## Integration with ADR-0006

**Future Integration Points:**
- **Phase 1 (Negotiation):** Use inference for agent capability scoring
- **Phase 2 (Selection):** Rank proposals based on model confidence scores
- **Phase 3 (DAG Execution):** Agent planning with local LLM

## Next Steps

1. **Start Lemonade Server** with Llama-3.2-1B-Instruct-Hybrid
2. **Run PoC** to validate latency SLO
3. **Integrate** inference engine into Phase 3 DAG orchestrator
4. **Optimize** quantization/batching if needed
5. **Move** to `k1/l4_runtime/llm_inference/` for production

## References

- **Lemonade Server:** Local LLM API compatible with OpenAI SDK
- **ONNX Runtime:** Cross-platform inference engine
- **AMD Ryzen AI:** NPU support for efficient inference
- **ADR-0006:** Contract Net 3-Phase Orchestration
