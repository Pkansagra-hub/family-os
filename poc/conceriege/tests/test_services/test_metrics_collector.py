"""
Unit tests for MetricsCollector service.

Tests:
- LLM call tracking: operation, model, latency, tokens, cost, cache hits
- Specialist duration tracking: type, duration, P95
- Turn latency tracking: E2E latency, P50/P95/P99, budget exceeded
- Proactive prompt tracking: sent, responses, response rate
- Statistical calculations: averages, percentiles
- Summary and Prometheus export
"""

from backend.services.metrics_collector import (
    MetricsCollector,
    get_metrics_collector,
    reset_metrics_collector,
)


class TestLLMMetrics:
    """Test LLM call metrics tracking."""

    def test_record_single_llm_call(self):
        """Test recording single LLM call."""
        collector = MetricsCollector()

        collector.record_llm_call(
            operation="intent_classification",
            model="gpt-4o-mini",
            latency_ms=45.0,
            tokens=50,
            cost_usd=0.0001,
            cache_hit=False,
        )

        metrics = collector.get_metrics()
        intent_metrics = metrics["llm"]["intent_classification"]

        assert intent_metrics["total_calls"] == 1
        assert intent_metrics["total_tokens"] == 50
        assert intent_metrics["total_cost_usd"] == 0.0001
        assert intent_metrics["cache_hits"] == 0
        assert intent_metrics["cache_misses"] == 1
        assert intent_metrics["avg_latency_ms"] == 45.0
        assert intent_metrics["cache_hit_rate"] == 0.0

    def test_record_multiple_llm_calls_same_operation(self):
        """Test recording multiple calls for same operation."""
        collector = MetricsCollector()

        # Record 3 calls
        for i in range(3):
            collector.record_llm_call(
                operation="empathy_generation",
                model="gpt-4o-mini",
                latency_ms=50.0 + i * 10,  # 50, 60, 70
                tokens=100,
                cost_usd=0.0002,
                cache_hit=False,
            )

        metrics = collector.get_metrics()
        empathy_metrics = metrics["llm"]["empathy_generation"]

        assert empathy_metrics["total_calls"] == 3
        assert empathy_metrics["total_tokens"] == 300
        assert empathy_metrics["total_cost_usd"] == 0.0006
        assert empathy_metrics["avg_latency_ms"] == 60.0  # Average of 50, 60, 70

    def test_record_llm_calls_different_operations(self):
        """Test recording calls for different operations."""
        collector = MetricsCollector()

        collector.record_llm_call("intent_classification", "gpt-4o-mini", 30.0, 50, 0.0001, False)
        collector.record_llm_call("empathy_generation", "gpt-4o-mini", 60.0, 80, 0.0002, False)
        collector.record_llm_call("synthesis", "gpt-4o-mini", 150.0, 200, 0.0005, False)

        metrics = collector.get_metrics()
        llm_metrics = metrics["llm"]

        assert len(llm_metrics) == 3
        assert "intent_classification" in llm_metrics
        assert "empathy_generation" in llm_metrics
        assert "synthesis" in llm_metrics

    def test_cache_hit_tracking(self):
        """Test cache hit/miss tracking."""
        collector = MetricsCollector()

        # 7 cache misses, 3 cache hits
        for i in range(10):
            collector.record_llm_call(
                "intent_classification",
                "gpt-4o-mini",
                20.0,
                50,
                0.0001,
                cache_hit=(i >= 7),  # Last 3 are hits
            )

        metrics = collector.get_metrics()
        intent_metrics = metrics["llm"]["intent_classification"]

        assert intent_metrics["cache_hits"] == 3
        assert intent_metrics["cache_misses"] == 7
        assert intent_metrics["cache_hit_rate"] == 30.0  # 3/10 * 100


class TestSpecialistMetrics:
    """Test specialist duration metrics tracking."""

    def test_record_single_specialist_call(self):
        """Test recording single specialist operation."""
        collector = MetricsCollector()

        collector.record_specialist_duration("nutritionist", 800.0)

        metrics = collector.get_metrics()
        nutritionist_metrics = metrics["specialist"]["nutritionist"]

        assert nutritionist_metrics["total_calls"] == 1
        assert nutritionist_metrics["avg_duration_ms"] == 800.0
        assert nutritionist_metrics["p95_duration_ms"] == 800.0

    def test_record_multiple_specialist_calls(self):
        """Test recording multiple specialist operations."""
        collector = MetricsCollector()

        # Record 5 calls with different durations
        durations = [500, 700, 800, 900, 1000]
        for duration in durations:
            collector.record_specialist_duration("nutritionist", float(duration))

        metrics = collector.get_metrics()
        nutritionist_metrics = metrics["specialist"]["nutritionist"]

        assert nutritionist_metrics["total_calls"] == 5
        assert nutritionist_metrics["avg_duration_ms"] == 780.0  # Average
        # P95 with 5 samples: index = int(5 * 0.95) = 4, so durations[4] = 1000
        assert nutritionist_metrics["p95_duration_ms"] == 1000.0

    def test_different_specialist_types(self):
        """Test tracking different specialist types."""
        collector = MetricsCollector()

        collector.record_specialist_duration("nutritionist", 800.0)
        collector.record_specialist_duration("psychiatrist", 600.0)
        collector.record_specialist_duration("nutritionist", 900.0)

        metrics = collector.get_metrics()
        specialist_metrics = metrics["specialist"]

        assert len(specialist_metrics) == 2
        assert specialist_metrics["nutritionist"]["total_calls"] == 2
        assert specialist_metrics["psychiatrist"]["total_calls"] == 1

    def test_p95_calculation_with_many_samples(self):
        """Test P95 calculation with 20 samples."""
        collector = MetricsCollector()

        # Record 20 calls: 100ms to 2000ms in 100ms increments
        for i in range(20):
            collector.record_specialist_duration("nutritionist", 100.0 + i * 100)

        metrics = collector.get_metrics()
        nutritionist_metrics = metrics["specialist"]["nutritionist"]

        # P95 with 20 samples: index = int(20 * 0.95) = 19, so durations[19] = 2000
        assert nutritionist_metrics["p95_duration_ms"] == 2000.0


class TestTurnMetrics:
    """Test conversation turn metrics tracking."""

    def test_record_single_turn(self):
        """Test recording single turn."""
        collector = MetricsCollector(latency_budget_ms=1500)

        collector.record_turn_latency(1200.0)

        metrics = collector.get_metrics()
        turn_metrics = metrics["turns"]

        assert turn_metrics["total_turns"] == 1
        assert turn_metrics["avg_latency_ms"] == 1200.0
        assert turn_metrics["p50_latency_ms"] == 1200.0
        assert turn_metrics["p95_latency_ms"] == 1200.0
        assert turn_metrics["p99_latency_ms"] == 1200.0
        assert turn_metrics["budget_exceeded_count"] == 0

    def test_record_multiple_turns(self):
        """Test recording multiple turns."""
        collector = MetricsCollector()

        # Record 10 turns: 1000ms to 1900ms
        latencies = [1000 + i * 100 for i in range(10)]
        for latency in latencies:
            collector.record_turn_latency(float(latency))

        metrics = collector.get_metrics()
        turn_metrics = metrics["turns"]

        assert turn_metrics["total_turns"] == 10
        assert turn_metrics["avg_latency_ms"] == 1450.0  # Average
        assert turn_metrics["p50_latency_ms"] == 1450.0  # Median
        # P95: index = int(10 * 0.95) = 9, so latencies[9] = 1900
        assert turn_metrics["p95_latency_ms"] == 1900.0
        # P99: index = int(10 * 0.99) = 9, so latencies[9] = 1900
        assert turn_metrics["p99_latency_ms"] == 1900.0

    def test_budget_exceeded_tracking(self):
        """Test budget exceeded tracking."""
        collector = MetricsCollector(latency_budget_ms=1500)

        # Record 5 turns: 3 under budget, 2 over budget
        latencies = [1000, 1200, 1400, 1600, 1800]  # Under, under, under, OVER, OVER
        for latency in latencies:
            collector.record_turn_latency(float(latency))

        metrics = collector.get_metrics()
        turn_metrics = metrics["turns"]

        assert turn_metrics["total_turns"] == 5
        assert turn_metrics["budget_exceeded_count"] == 2

    def test_percentile_calculations_with_many_samples(self):
        """Test P50/P95/P99 with 100 samples."""
        collector = MetricsCollector()

        # Record 100 turns: 100ms to 10000ms
        for i in range(100):
            collector.record_turn_latency(100.0 + i * 100)

        metrics = collector.get_metrics()
        turn_metrics = metrics["turns"]

        # P50 (median): average of 50th and 51st values = (5000 + 5100) / 2 = 5050
        assert turn_metrics["p50_latency_ms"] == 5050.0
        # P95: index = int(100 * 0.95) = 95, so latencies[95] = 9600
        assert turn_metrics["p95_latency_ms"] == 9600.0
        # P99: index = int(100 * 0.99) = 99, so latencies[99] = 10000
        assert turn_metrics["p99_latency_ms"] == 10000.0


class TestProactiveMetrics:
    """Test proactive prompt metrics tracking."""

    def test_record_proactive_prompt_no_response(self):
        """Test recording proactive prompt without response."""
        collector = MetricsCollector()

        collector.record_proactive_prompt(user_responded=False)

        metrics = collector.get_metrics()
        proactive_metrics = metrics["proactive"]

        assert proactive_metrics["prompts_sent"] == 1
        assert proactive_metrics["user_responses"] == 0
        assert proactive_metrics["response_rate"] == 0.0

    def test_record_proactive_prompt_with_response(self):
        """Test recording proactive prompt with response."""
        collector = MetricsCollector()

        collector.record_proactive_prompt(user_responded=True)

        metrics = collector.get_metrics()
        proactive_metrics = metrics["proactive"]

        assert proactive_metrics["prompts_sent"] == 1
        assert proactive_metrics["user_responses"] == 1
        assert proactive_metrics["response_rate"] == 100.0

    def test_response_rate_calculation(self):
        """Test response rate calculation."""
        collector = MetricsCollector()

        # Send 10 prompts, 6 with responses
        for i in range(10):
            collector.record_proactive_prompt(user_responded=(i < 6))

        metrics = collector.get_metrics()
        proactive_metrics = metrics["proactive"]

        assert proactive_metrics["prompts_sent"] == 10
        assert proactive_metrics["user_responses"] == 6
        assert proactive_metrics["response_rate"] == 60.0


class TestSummary:
    """Test summary statistics."""

    def test_get_summary_with_data(self):
        """Test summary with collected data."""
        collector = MetricsCollector(latency_budget_ms=1500)

        # LLM calls
        collector.record_llm_call("intent", "gpt-4o-mini", 30.0, 50, 0.0001, cache_hit=False)
        collector.record_llm_call("intent", "gpt-4o-mini", 20.0, 50, 0.0001, cache_hit=True)
        collector.record_llm_call("empathy", "gpt-4o-mini", 50.0, 80, 0.0002, cache_hit=False)

        # Specialist calls
        collector.record_specialist_duration("nutritionist", 800.0)
        collector.record_specialist_duration("psychiatrist", 600.0)

        # Turns
        collector.record_turn_latency(1200.0)
        collector.record_turn_latency(1600.0)  # Over budget
        collector.record_turn_latency(1400.0)

        # Proactive prompts
        collector.record_proactive_prompt(user_responded=True)
        collector.record_proactive_prompt(user_responded=False)

        summary = collector.get_summary()

        # LLM summary
        assert summary["llm_summary"]["total_calls"] == 3
        assert summary["llm_summary"]["total_tokens"] == 180
        assert summary["llm_summary"]["total_cost_usd"] == 0.0004
        assert summary["llm_summary"]["cache_hit_rate"] == 33.33  # 1/3

        # Specialist summary
        assert summary["specialist_summary"]["total_calls"] == 2

        # Turn summary
        assert summary["turn_summary"]["total_turns"] == 3
        assert summary["turn_summary"]["p50_latency_ms"] == 1400.0
        assert summary["turn_summary"]["budget_exceeded_count"] == 1
        assert summary["turn_summary"]["budget_exceeded_rate"] == 33.33  # 1/3

        # Proactive summary
        assert summary["proactive_summary"]["prompts_sent"] == 2
        assert summary["proactive_summary"]["response_rate"] == 50.0  # 1/2

    def test_get_summary_empty(self):
        """Test summary with no data."""
        collector = MetricsCollector()

        summary = collector.get_summary()

        assert summary["llm_summary"]["total_calls"] == 0
        assert summary["llm_summary"]["cache_hit_rate"] == 0.0
        assert summary["specialist_summary"]["total_calls"] == 0
        assert summary["turn_summary"]["total_turns"] == 0
        assert summary["proactive_summary"]["prompts_sent"] == 0


class TestPrometheusExport:
    """Test Prometheus format export."""

    def test_export_prometheus_with_data(self):
        """Test Prometheus export format."""
        collector = MetricsCollector()

        # Add some data
        collector.record_llm_call("intent", "gpt-4o-mini", 30.0, 50, 0.0001, cache_hit=False)
        collector.record_specialist_duration("nutritionist", 800.0)
        collector.record_turn_latency(1200.0)
        collector.record_proactive_prompt(user_responded=True)

        output = collector.export_prometheus()

        # Check format
        assert "# HELP llm_calls_total" in output
        assert "# TYPE llm_calls_total" in output
        assert 'llm_calls_total{operation="intent"} 1' in output

        assert "# HELP specialist_calls_total" in output
        assert 'specialist_calls_total{specialist="nutritionist"} 1' in output

        assert "# HELP turn_total" in output
        assert "turn_total 1" in output

        assert "# HELP proactive_prompts_sent_total" in output
        assert "proactive_prompts_sent_total 1" in output

    def test_export_prometheus_empty(self):
        """Test Prometheus export with no data."""
        collector = MetricsCollector()

        output = collector.export_prometheus()

        # Should have basic structure but zeros
        assert "turn_total 0" in output
        assert "proactive_prompts_sent_total 0" in output


class TestReset:
    """Test metrics reset."""

    def test_reset_clears_all_metrics(self):
        """Test that reset clears all collected metrics."""
        collector = MetricsCollector()

        # Add data
        collector.record_llm_call("intent", "gpt-4o-mini", 30.0, 50, 0.0001, False)
        collector.record_specialist_duration("nutritionist", 800.0)
        collector.record_turn_latency(1200.0)
        collector.record_proactive_prompt(user_responded=True)

        # Reset
        collector.reset()

        # Verify empty
        metrics = collector.get_metrics()
        assert len(metrics["llm"]) == 0
        assert len(metrics["specialist"]) == 0
        assert metrics["turns"]["total_turns"] == 0
        assert metrics["proactive"]["prompts_sent"] == 0


class TestSingletonPattern:
    """Test singleton instance management."""

    def test_get_metrics_collector_singleton(self):
        """Test singleton returns same instance."""
        reset_metrics_collector()

        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_reset_metrics_collector(self):
        """Test resetting singleton."""
        reset_metrics_collector()

        collector1 = get_metrics_collector()
        collector1.record_turn_latency(1200.0)

        reset_metrics_collector()
        collector2 = get_metrics_collector()

        # Should be different instance
        assert collector2 is not collector1
        # Should be empty
        metrics = collector2.get_metrics()
        assert metrics["turns"]["total_turns"] == 0

    def test_custom_latency_budget(self):
        """Test custom latency budget on first call."""
        reset_metrics_collector()

        collector = get_metrics_collector(latency_budget_ms=2000)

        assert collector.latency_budget_ms == 2000


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_tokens_and_cost(self):
        """Test recording LLM call with zero tokens/cost."""
        collector = MetricsCollector()

        collector.record_llm_call("intent", "gpt-4o-mini", 30.0, 0, 0.0, False)

        metrics = collector.get_metrics()
        intent_metrics = metrics["llm"]["intent"]

        assert intent_metrics["total_tokens"] == 0
        assert intent_metrics["total_cost_usd"] == 0.0

    def test_very_high_latency(self):
        """Test recording very high latency values."""
        collector = MetricsCollector(latency_budget_ms=1500)

        collector.record_turn_latency(10000.0)  # 10 seconds

        metrics = collector.get_metrics()
        turn_metrics = metrics["turns"]

        assert turn_metrics["avg_latency_ms"] == 10000.0
        assert turn_metrics["budget_exceeded_count"] == 1

    def test_single_sample_percentiles(self):
        """Test percentile calculations with single sample."""
        collector = MetricsCollector()

        collector.record_turn_latency(1200.0)

        metrics = collector.get_metrics()
        turn_metrics = metrics["turns"]

        # All percentiles should be same with one sample
        assert turn_metrics["p50_latency_ms"] == 1200.0
        assert turn_metrics["p95_latency_ms"] == 1200.0
        assert turn_metrics["p99_latency_ms"] == 1200.0

    def test_mixed_operations_comprehensive(self):
        """Test comprehensive scenario with all metric types."""
        collector = MetricsCollector(latency_budget_ms=1500)

        # Simulate GERD query flow
        # 1. Intent classification (cache miss)
        collector.record_llm_call("intent_classification", "gpt-4o-mini", 28.0, 45, 0.00009, False)

        # 2. Emotion detection (cache miss)
        collector.record_llm_call("emotion_detection", "gpt-4o-mini", 22.0, 35, 0.00007, False)

        # 3. Empathy generation (cache hit)
        collector.record_llm_call("empathy_generation", "gpt-4o-mini", 5.0, 50, 0.0, True)

        # 4. Nutritionist specialist
        collector.record_specialist_duration("nutritionist", 850.0)

        # 5. Proactive prompt
        collector.record_proactive_prompt(user_responded=True)

        # 6. Synthesis
        collector.record_llm_call("synthesis", "gpt-4o-mini", 180.0, 150, 0.0003, False)

        # 7. Total turn latency
        collector.record_turn_latency(1300.0)  # Under budget

        # Verify comprehensive summary
        summary = collector.get_summary()

        assert summary["llm_summary"]["total_calls"] == 4
        assert summary["llm_summary"]["cache_hit_rate"] == 25.0  # 1/4
        assert summary["specialist_summary"]["total_calls"] == 1
        assert summary["turn_summary"]["total_turns"] == 1
        assert summary["turn_summary"]["budget_exceeded_count"] == 0
        assert summary["proactive_summary"]["prompts_sent"] == 1
        assert summary["proactive_summary"]["response_rate"] == 100.0
