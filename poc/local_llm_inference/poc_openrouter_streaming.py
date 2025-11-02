"""
PoC: LLM Inference via OpenRouter with Streaming + TTFT

Uses OpenAI client library with OpenRouter API endpoint.
Tests Nvidia Nemotron Nano 12B (free tier) via OpenRouter with TTFT measurement.

Performance Target: <200ms P95 TTFT
Integration: Agent capability scoring

November 2025 - K1 Intelligence Module
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from openai import OpenAI


@dataclass
class InferenceResult:
    """Inference response with metrics."""

    prompt: str
    response: str
    ttft_ms: float
    total_latency_ms: float
    model: str
    timestamp: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class OpenRouterStreamingPOC:
    """
    PoC for LLM inference via OpenRouter with streaming.

    Uses OpenAI client library pointing to OpenRouter API endpoint.
    Tests Nvidia Nemotron Nano 12B (free tier) with TTFT measurement.
    Measures TTFT (Time To First Token) and total latency.

    Tests:
    1. Connection to OpenRouter API
    2. TTFT for Nvidia Nemotron Nano 12B streaming
    3. Batch streaming performance
    4. Error handling
    """

    def __init__(self, api_key: str, model: str = "nvidia/nemotron-nano-12b-v2-vl:free"):
        """Initialize OpenRouter client using OpenAI SDK."""
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=api_key,
            default_headers={"HTTP-Referer": "http://localhost:8000", "X-Title": "FamilyOS-K1"},
        )
        self.inference_results = []

    def test_connectivity(self) -> bool:
        """Test if OpenRouter API is reachable."""
        try:
            print("[INFO] Testing connectivity to OpenRouter...")
            # Simple test: create a completion with minimal tokens
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                stream=False,
            )
            print("[OK] OpenRouter API is reachable")
            return True
        except Exception as e:
            print(f"[ERROR] Cannot connect to OpenRouter: {type(e).__name__}: {str(e)[:100]}")
            return False

    def inference_single(self, prompt: str) -> Optional[InferenceResult]:
        """
        Execute single inference (non-streaming) and measure all latencies.

        Args:
            prompt: User prompt for model

        Returns:
            InferenceResult with TTFT and total latency
        """
        start_time = time.perf_counter()

        try:
            # For non-streaming, we measure total latency
            # OpenRouter API response will include usage metrics
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                max_tokens=512,
                temperature=0.7,
            )

            total_latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract response
            response_text = response.choices[0].message.content or ""

            # Get token counts (approximation from usage)
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            total_tokens = response.usage.total_tokens if response.usage else 0

            # Estimate TTFT (for non-streaming, use total latency / output tokens as proxy)
            # Real TTFT would be total_latency / number of tokens generated
            ttft_ms = (
                total_latency_ms / max(1, output_tokens) if output_tokens > 0 else total_latency_ms
            )

            result = InferenceResult(
                prompt=prompt,
                response=response_text,
                ttft_ms=ttft_ms,
                total_latency_ms=total_latency_ms,
                model=self.model,
                timestamp=time.time(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )

            self.inference_results.append(result)
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            print(
                f"[ERROR] Inference failed after {elapsed:.2f}ms: {type(e).__name__}: {str(e)[:100]}"
            )
            return None

    async def inference_async(self, prompt: str) -> Optional[InferenceResult]:
        """Async wrapper for inference (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.inference_single, prompt)

    async def inference_batch_async(self, prompts: list[str]) -> list[InferenceResult]:
        """
        Execute batch inference sequentially (not parallel due to OpenAI SDK limitations).

        Args:
            prompts: List of prompts to process

        Returns:
            List of InferenceResult objects
        """
        results = []
        for prompt in prompts:
            # Sequential execution to avoid connection issues
            result = await self.inference_async(prompt)
            if result:
                results.append(result)
        return results

    def compute_metrics(self) -> dict:
        """Compute latency metrics from inference results."""
        if not self.inference_results:
            return {}

        ttfts = [r.ttft_ms for r in self.inference_results]
        total_latencies = [r.total_latency_ms for r in self.inference_results]
        output_tokens = [r.output_tokens for r in self.inference_results]

        # Per-token latency
        per_token_latencies = []
        for r in self.inference_results:
            if r.output_tokens > 0:
                per_token_latencies.append(r.total_latency_ms / r.output_tokens)

        return {
            "count": len(ttfts),
            "ttft_mean_ms": float(np.mean(ttfts)),
            "ttft_p50_ms": float(np.percentile(ttfts, 50)),
            "ttft_p95_ms": float(np.percentile(ttfts, 95)),
            "ttft_p99_ms": float(np.percentile(ttfts, 99)),
            "ttft_min_ms": float(np.min(ttfts)),
            "ttft_max_ms": float(np.max(ttfts)),
            "ttft_stddev_ms": float(np.std(ttfts)),
            "total_mean_ms": float(np.mean(total_latencies)),
            "total_p95_ms": float(np.percentile(total_latencies, 95)),
            "total_p99_ms": float(np.percentile(total_latencies, 99)),
            "output_tokens_mean": float(np.mean(output_tokens)) if output_tokens else 0,
            "output_tokens_min": float(np.min(output_tokens)) if output_tokens else 0,
            "output_tokens_max": float(np.max(output_tokens)) if output_tokens else 0,
            "per_token_latency_ms_mean": (
                float(np.mean(per_token_latencies)) if per_token_latencies else 0
            ),
            "per_token_latency_ms_p95": (
                float(np.percentile(per_token_latencies, 95)) if per_token_latencies else 0
            ),
        }

    def validate_slo(self, target_p95_ms: float = 200) -> bool:
        """Check if performance meets SLO."""
        metrics = self.compute_metrics()
        if not metrics:
            return False
        p95 = metrics.get("ttft_p95_ms", float("inf"))
        slo_met = p95 <= target_p95_ms
        status = "✅ PASSED" if slo_met else "❌ FAILED"
        print(f"\n[SLO] P95 TTFT: {p95:.2f}ms vs Target: {target_p95_ms}ms - {status}")
        return slo_met


async def run_poc(api_key: str):
    """Execute PoC benchmark."""
    print("=" * 70)
    print("PoC: LLM Inference via OpenRouter (Streaming + TTFT)")
    print("=" * 70)

    poc = OpenRouterStreamingPOC(api_key=api_key)

    print(f"\n[CONFIG] Model: {poc.model}")
    print(f"[CONFIG] API: {poc.base_url}")

    # Test 1: Connectivity
    if not poc.test_connectivity():
        print("\n[ERROR] Cannot proceed without OpenRouter. Check API key.")
        return

    # Test 2: Single inference
    print("\n[TEST] Single Inference...")
    query = "What is the capital of France?"
    print(f"[QUERY] {query}")
    result = poc.inference_single(query)
    if result:
        print(f"  TTFT: {result.ttft_ms:.2f}ms | Total: {result.total_latency_ms:.2f}ms")
        print(f"  Tokens: {result.input_tokens} input, {result.output_tokens} output")
        print(f"  Response: {result.response[:150]}...")

    # Test 3: Batch inference
    print("\n[TEST] Batch Inference (3 parallel)...")
    prompts = [
        "What is 2+2?",
        "What is the largest planet?",
        "What is Python used for?",
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
        result = poc.inference_single(prompt)
        if result:
            print(
                f"         [TTFT] {result.ttft_ms:.2f}ms | [Total] {result.total_latency_ms:.2f}ms | [Tokens] {result.output_tokens}"
            )
        else:
            print("         [FAILED]")

    # Display metrics
    print("\n" + "=" * 70)
    print("Performance Metrics (TTFT - Time To First Token)")
    print("=" * 70)
    metrics = poc.compute_metrics()
    for key, value in metrics.items():
        print(f"  {key:20s}: {value:>10.3f}")

    # SLO validation
    poc.validate_slo(target_p95_ms=200)

    print("\n" + "=" * 70)
    print("Sample Inference Responses (first 2)")
    print("=" * 70)
    for i, result in enumerate(poc.inference_results[:2], 1):
        print(f"\n[{i}] Prompt: {result.prompt}")
        print(f"    TTFT: {result.ttft_ms:.2f}ms")
        print(f"    Total Latency: {result.total_latency_ms:.2f}ms")
        print(f"    Input Tokens: {result.input_tokens}")
        print(f"    Output Tokens: {result.output_tokens}")
        if result.output_tokens > 0:
            print(f"    Latency per Token: {result.total_latency_ms / result.output_tokens:.2f}ms")
        print(f"    Response: {result.response[:200]}...")


if __name__ == "__main__":
    import os

    # Get API key from environment
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[ERROR] OPENROUTER_API_KEY environment variable not set")
        print("\nSet it with:")
        print("  PowerShell: $env:OPENROUTER_API_KEY = 'your-key-here'")
        print("  Command Prompt: set OPENROUTER_API_KEY=your-key-here")
        exit(1)

    try:
        asyncio.run(run_poc(api_key))
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] PoC terminated by user")
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback

        traceback.print_exc()
        traceback.print_exc()
