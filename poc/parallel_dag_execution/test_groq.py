"""
Test Groq API integration directly
"""

import asyncio
import os

# Set Groq API key
os.environ["GROQ_API_KEY"] = "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"


async def test_groq():
    """Test Groq API with comprehensive test."""
    print("=" * 90)
    print("GROQ API TEST - Force Groq Backend")
    print("=" * 90)

    # Import after env is set
    from comprehensive_test import DAGExecutor

    print("\n[PROVIDER INITIALIZATION]")
    # Create provider without local LLM
    from poc.llm_provider import LLMProvider

    provider = LLMProvider(prefer_local=False, max_workers=5)
    print(f"Backend: {provider.get_backend()}")
    print(f"API Key: {provider.groq_api_key[:20]}...")
    print("-" * 90)

    if provider.backend.value != "groq":
        print("[WARN] Groq not initialized - checking error...")
        if not provider.groq_api_key:
            print("[ERROR] GROQ_API_KEY not set")
        return

    # Test 5 parallel API requests
    print("\n[5 PARALLEL API REQUESTS VIA GROQ]")
    exec_par = DAGExecutor(provider)
    exec_par.add_task("R1", "Req1", "What is Python? (max 10 words)")
    exec_par.add_task("R2", "Req2", "Explain async/await (max 10 words)")
    exec_par.add_task("R3", "Req3", "What is DAG? (max 10 words)")
    exec_par.add_task("R4", "Req4", "Define parallelism (max 10 words)")
    exec_par.add_task("R5", "Req5", "What is Groq? (max 10 words)")

    try:
        par_metrics = await exec_par.execute_parallel_dag()
        print("\nGroq Parallel Results:")
        print(f"  Total:       {par_metrics.total_latency_ms:.0f}ms")
        print(f"  Completed:   {par_metrics.tasks_completed}/5")
        print(
            f"  Throughput:  {par_metrics.tasks_completed / (par_metrics.total_latency_ms / 1000):.2f} req/sec"
        )

        print("\n[RESPONSE SAMPLES]")
        for task_id, task in sorted(exec_par.tasks.items()):
            if task.result:
                print(f"  {task_id}: {task.result[:70]}")

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)[:100]}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 90)


if __name__ == "__main__":
    asyncio.run(test_groq())
