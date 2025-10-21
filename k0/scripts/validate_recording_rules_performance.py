"""
Validate Recording Rules Performance Improvement

Compares query execution time between:
1. Raw histogram_quantile() queries (OLD)
2. Pre-aggregated recording rule queries (NEW)

Expected: 50-80% reduction in query latency
"""

import time
from typing import Any, Dict

import requests

PROMETHEUS_URL = "http://localhost:9090"

# Define query pairs: (description, old_query, new_query)
QUERY_PAIRS = [
    (
        "Command Latency p95",
        'histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket{route="/k0/command.submit"}[5m])) by (le))',
        "job:k0_command_latency_seconds:p95:5m",
    ),
    (
        "Query Latency p95",
        'histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket{route="/k0/query.execute"}[5m])) by (le))',
        "job:k0_query_latency_seconds:p95:5m",
    ),
    (
        "API Availability",
        '1 - (sum(rate(k0_kernel_http_requests_total{status=~"5.."}[5m])) / sum(rate(k0_kernel_http_requests_total[5m])))',
        "job:k0_api_availability:ratio5m",
    ),
    (
        "Command Submission Rate",
        'sum(rate(k0_kernel_http_requests_total{route="/k0/command.submit"}[5m]))',
        "job:k0_command_submissions:rate5m",
    ),
]


def execute_query(query: str, runs: int = 5) -> Dict[str, Any]:
    """Execute Prometheus query and measure performance."""
    times = []

    for _ in range(runs):
        start = time.perf_counter()
        try:
            response = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=10,
            )
            end = time.perf_counter()

            if response.status_code != 200:
                return {
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "query_time_ms": None,
                }

            data = response.json()
            if data["status"] != "success":
                return {
                    "error": f"Query failed: {data.get('error', 'Unknown error')}",
                    "query_time_ms": None,
                }

            times.append((end - start) * 1000)  # Convert to ms

        except Exception as e:
            return {"error": str(e), "query_time_ms": None}

    return {
        "error": None,
        "query_time_ms": sum(times) / len(times),  # Average
        "min_ms": min(times),
        "max_ms": max(times),
        "runs": runs,
    }


def main():
    """Run performance comparison."""
    print("🔬 Recording Rules Performance Validation")
    print("=" * 80)
    print()

    results = []

    for description, old_query, new_query in QUERY_PAIRS:
        print(f"📊 Testing: {description}")
        print(f"   OLD: {old_query[:80]}...")
        print(f"   NEW: {new_query}")
        print()

        # Execute old query
        print("   Running OLD query (5 iterations)...", end=" ")
        old_result = execute_query(old_query)
        if old_result["error"]:
            print(f"❌ FAILED: {old_result['error']}")
            continue
        print(f"✅ Avg: {old_result['query_time_ms']:.2f}ms")

        # Execute new query
        print("   Running NEW query (5 iterations)...", end=" ")
        new_result = execute_query(new_query)
        if new_result["error"]:
            print(f"❌ FAILED: {new_result['error']}")
            continue
        print(f"✅ Avg: {new_result['query_time_ms']:.2f}ms")

        # Calculate improvement
        improvement_pct = (
            (old_result["query_time_ms"] - new_result["query_time_ms"])
            / old_result["query_time_ms"]
            * 100
        )
        speedup = old_result["query_time_ms"] / new_result["query_time_ms"]

        print(
            f"   📈 Improvement: {improvement_pct:.1f}% faster ({speedup:.2f}x speedup)"
        )
        print()

        results.append(
            {
                "description": description,
                "old_ms": old_result["query_time_ms"],
                "new_ms": new_result["query_time_ms"],
                "improvement_pct": improvement_pct,
                "speedup": speedup,
            }
        )

    # Summary
    print("=" * 80)
    print("📈 SUMMARY")
    print("=" * 80)
    print()

    if not results:
        print("❌ No successful comparisons")
        return

    avg_improvement = sum(r["improvement_pct"] for r in results) / len(results)
    avg_speedup = sum(r["speedup"] for r in results) / len(results)

    print(f"Queries Tested: {len(results)}")
    print(f"Average Improvement: {avg_improvement:.1f}% faster")
    print(f"Average Speedup: {avg_speedup:.2f}x")
    print()

    # Detailed table
    print("Detailed Results:")
    print(f"{'Metric':<30} {'OLD (ms)':<12} {'NEW (ms)':<12} {'Improvement':<15}")
    print("-" * 80)
    for r in results:
        print(
            f"{r['description']:<30} "
            f"{r['old_ms']:>10.2f}   "
            f"{r['new_ms']:>10.2f}   "
            f"{r['improvement_pct']:>10.1f}%"
        )

    print()

    # Success criteria
    if avg_improvement >= 50:
        print("✅ SUCCESS: Recording rules achieved >50% query latency reduction!")
    elif avg_improvement >= 25:
        print("⚠️  PARTIAL: Recording rules achieved 25-50% improvement (target: >50%)")
    else:
        print("❌ BELOW TARGET: Recording rules <25% improvement (target: >50%)")

    print()


if __name__ == "__main__":
    main()
