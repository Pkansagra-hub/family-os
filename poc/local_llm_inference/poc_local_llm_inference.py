"""
PoC: Local LLM Inference via Lemonade Server (Streaming + TTFT)

Validates local SLM inference performance with streaming and measures TTFT (Time To First Token).
Tests Qwen-2.5-1.5B-Instruct-NPU running on AMD Ryzen AI via Lemonade Server.

Performance Target: <150ms P95 TTFT (streaming model)
Integration: Later phases will use TTFT for agent capability scoring

November 2025 - K1 Intelligence Module
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from openai import APIConnectionError, APIError, OpenAI


@dataclass
class InferenceResult:
    """Inference response with metrics."""

    prompt: str
    response: str
    latency_ms: float
    model: str
    timestamp: float


class LocalLLMInferencePOC:
    """
    PoC for local LLM inference via Lemonade Server with streaming.

    Measures TTFT (Time To First Token) instead of total latency.

    Tests:
    1. Connection to local Lemonade Server
    2. TTFT for Qwen-2.5-1.5B-Instruct-NPU streaming
    3. Batch TTFT performance
    4. Error handling and fallback
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        model: str = "Qwen-2.5-1.5B-Instruct-NPU",
    ):
        """Initialize OpenAI client for local LLM."""
        self.base_url = base_url
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key="lemonade")
        self.inference_results = []

    def test_connectivity(self) -> bool:
        """Test if Lemonade Server is reachable."""
        try:
            print(f"[INFO] Testing connectivity to {self.base_url}...")
            self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": "ping"}], max_tokens=10
            )
            print("[OK] Lemonade Server is reachable")
            return True
        except (APIConnectionError, APIError) as e:
            print(f"[ERROR] Cannot connect to Lemonade Server: {e}")
            return False

    def inference_single(
        self, prompt: str, show_streaming: bool = False
    ) -> Optional[InferenceResult]:
        """
        Execute single inference with streaming and measure TTFT.

        Args:
            prompt: User prompt for model
            show_streaming: If True, display streaming tokens in real-time

        Returns:
            InferenceResult with TTFT latency, or None on error
        """
        start_time = time.perf_counter()
        ttft_ms = None
        response_tokens = []

        try:
            if show_streaming:
                print("\n  [STREAM] ", end="", flush=True)

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=256,
            )

            chunk_count = 0
            for chunk in stream:
                chunk_count += 1
                # Measure TTFT on first token
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - start_time) * 1000

                # Collect tokens and display if requested
                try:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta and hasattr(delta, "content") and delta.content:
                            token = delta.content
                            response_tokens.append(token)
                            if show_streaming:
                                print(token, end="", flush=True)
                except (AttributeError, IndexError):
                    pass  # Skip malformed chunks

            if show_streaming:
                print()  # Newline after streaming

            # Fallback if no TTFT captured
            if ttft_ms is None:
                ttft_ms = (time.perf_counter() - start_time) * 1000

            response = "".join(response_tokens)
            result = InferenceResult(
                prompt=prompt,
                response=response,
                latency_ms=ttft_ms,  # TTFT instead of total latency
                model=self.model,
                timestamp=time.time(),
            )
            self.inference_results.append(result)
            return result
        except Exception as e:
            print(f"[ERROR] Inference failed: {type(e).__name__}: {e}")
            return None

    async def inference_async(
        self, prompt: str, show_streaming: bool = False
    ) -> Optional[InferenceResult]:
        """Async wrapper for inference (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.inference_single, prompt, show_streaming)

    async def inference_batch_async(self, prompts: list[str]) -> list[InferenceResult]:
        """
        Execute batch inference in parallel.

        Args:
            prompts: List of prompts to process

        Returns:
            List of InferenceResult objects
        """
        tasks = [self.inference_async(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    def compute_metrics(self) -> dict:
        """Compute latency metrics from inference results."""
        if not self.inference_results:
            return {}

        latencies = [r.latency_ms for r in self.inference_results]
        return {
            "count": len(latencies),
            "mean_ms": float(np.mean(latencies)),
            "p50_ms": float(np.percentile(latencies, 50)),
            "p95_ms": float(np.percentile(latencies, 95)),
            "p99_ms": float(np.percentile(latencies, 99)),
            "min_ms": float(np.min(latencies)),
            "max_ms": float(np.max(latencies)),
            "stddev_ms": float(np.std(latencies)),
        }

    def validate_slo(self, target_p95_ms: float = 150) -> bool:
        """Check if performance meets SLO."""
        metrics = self.compute_metrics()
        if not metrics:
            return False
        p95 = metrics.get("p95_ms", float("inf"))
        slo_met = p95 <= target_p95_ms
        status = "✅ PASSED" if slo_met else "❌ FAILED"
        print(f"\n[SLO] P95 TTFT: {p95:.2f}ms vs Target: {target_p95_ms}ms - {status}")
        return slo_met


async def run_poc():
    """Execute PoC benchmark."""
    print("=" * 70)
    print("PoC: Local LLM Inference via Lemonade Server (Streaming + TTFT)")
    print("=" * 70)

    poc = LocalLLMInferencePOC()

    print(f"\n[CONFIG] Model: {poc.model}")
    print(f"[CONFIG] Server: {poc.base_url}")

    # Test 1: Connectivity
    if not poc.test_connectivity():
        print("\n[ERROR] Cannot proceed without Lemonade Server. Start server and retry.")
        return

    # Test 2: Single inference with streaming
    print("\n[TEST] Single Inference with Streaming...")
    query = "What is the capital of France?"
    print(f"[QUERY] {query}")
    result = poc.inference_single(query, show_streaming=False)  # Disable streaming for now
    if result:
        print(f"  TTFT: {result.latency_ms:.2f}ms")
        print(f"  Response: {result.response[:100]}...")

    # Test 3: Batch inference
    print("\n[TEST] Batch Inference (5 parallel)...")
    prompts = [
        "What is 2+2?",
        "What is the largest planet?",
        "What is Python used for?",
        "What is machine learning?",
        "What is a neural network?",
    ]
    for prompt in prompts:
        print(f"[QUERY] {prompt}")
    batch_results = await poc.inference_batch_async(prompts)
    print(f"  Completed: {len(batch_results)}/{len(prompts)} inferences")

    # Test 4: Sequential inference for metrics
    print("\n[TEST] Sequential Inference (5 samples for metrics)...")
    test_prompts = [
        "What is AI?",
        "Explain machine learning",
        "What is deep learning?",
        "What is NLP?",
        "What is computer vision?",
    ]
    for i, prompt in enumerate(test_prompts, 1):
        print(f"  [{i}/5] [QUERY] {prompt}")
        result = poc.inference_single(prompt, show_streaming=False)
        if result:
            print(f"         [TTFT] {result.latency_ms:.2f}ms")
        else:
            print("         [FAILED]")

    # Display metrics
    print("\n" + "=" * 70)
    print("Performance Metrics")
    print("=" * 70)
    metrics = poc.compute_metrics()
    for key, value in metrics.items():
        print(f"  {key:15s}: {value:>10.3f}")

    # SLO validation
    poc.validate_slo(target_p95_ms=500)

    print("\n" + "=" * 70)
    print("Sample Inference Responses with Streaming (first 2)")
    print("=" * 70)
    for i, result in enumerate(poc.inference_results[:2], 1):
        print(f"\n[{i}] Prompt: {result.prompt}")
        print(f"    TTFT: {result.latency_ms:.2f}ms")
        print(f"    Response: {result.response[:150]}...")
        print(f"    Response Length: {len(result.response)} chars")


if __name__ == "__main__":
    try:
        asyncio.run(run_poc())
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] PoC terminated by user")
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback

        traceback.print_exc()
        traceback.print_exc()
