"""
Tests for the Scratchpad core model.

Validates:
  - to_llm_messages() keeps context bounded
  - compact_messages() reduces message count
  - findings_summary() includes all extracted facts
  - budget.exhausted triggers correctly
  - Sub-agent lifecycle tracking
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.models import (
    FailedAttempt,
    Finding,
    LoopBudget,
    Message,
    Scratchpad,
    SubAgentStatus,
    Tier,
    ToolCall,
    ToolResult,
)


class TestLoopBudget:

    def test_for_tier_low(self):
        b = LoopBudget.for_tier(Tier.LOW)
        assert b.max_tools == 6
        assert b.max_iterations == 6
        assert b.timeout_ms == 2_000

    def test_for_tier_medium(self):
        b = LoopBudget.for_tier(Tier.MEDIUM)
        assert b.max_tools == 10

    def test_for_tier_high(self):
        b = LoopBudget.for_tier(Tier.HIGH)
        assert b.max_tools == 15
        assert b.max_iterations == 15
        assert b.timeout_ms == 45_000

    def test_exhausted_false_initially(self):
        b = LoopBudget(max_tools=5, max_iterations=5)
        assert not b.exhausted

    def test_exhausted_tools(self):
        b = LoopBudget(max_tools=2, max_iterations=10)
        b.consume_tool()
        b.consume_tool()
        assert b.exhausted

    def test_exhausted_iterations(self):
        b = LoopBudget(max_tools=10, max_iterations=2)
        b.consume_iteration()
        b.consume_iteration()
        assert b.exhausted

    def test_remaining(self):
        b = LoopBudget(max_tools=5, max_iterations=5)
        b.consume_tool()
        assert b.remaining_tools == 4
        assert b.remaining_iterations == 5

    def test_slice(self):
        parent = LoopBudget(max_tools=10, max_iterations=10)
        parent.tools_used = 3
        child = parent.slice(4)
        assert child.max_tools == 4
        assert child.max_iterations == 6  # 4 + 2 headroom

    def test_slice_capped_by_remaining(self):
        parent = LoopBudget(max_tools=5, max_iterations=10)
        parent.tools_used = 3
        child = parent.slice(10)  # asking for 10 but only 2 remain
        assert child.max_tools == 2

    def test_return_unused(self):
        parent = LoopBudget(max_tools=10, max_iterations=10)
        parent.tools_used = 5
        child = LoopBudget(max_tools=3, max_iterations=5)
        child.tools_used = 1  # used 1 of 3, so 2 remaining
        parent.return_unused(child)
        assert parent.tools_used == 3  # 5 - 2 = 3


class TestScratchpad:

    def _make_scratchpad(self, **kwargs) -> Scratchpad:
        defaults = {
            "system_prompt": "You are a helpful assistant.",
            "user_query": "Tell me about quantum computing",
        }
        defaults.update(kwargs)
        sp = Scratchpad(**defaults)
        sp.messages.append(Message(role="user", content=sp.user_query))
        return sp

    def test_creation(self):
        sp = self._make_scratchpad()
        assert sp.turn_id.startswith("turn-")
        assert len(sp.findings) == 0
        assert not sp.is_complete()

    def test_to_llm_messages_basic(self):
        sp = self._make_scratchpad()
        msgs = sp.to_llm_messages()
        assert len(msgs) >= 2  # system + user
        assert msgs[0]["role"] == "system"
        assert "BUDGET STATUS" in msgs[0]["content"]

    def test_findings_injected_into_context(self):
        sp = self._make_scratchpad()
        sp.add_finding(
            Finding(key="temp_paris", value=22, type="weather", source_tool="weather_api")
        )
        msgs = sp.to_llm_messages()
        system_content = msgs[0]["content"]
        assert "KNOWN FACTS" in system_content
        assert "temp_paris" in system_content
        assert "22" in system_content

    def test_failed_attempts_injected(self):
        sp = self._make_scratchpad()
        sp.failed_attempts.append(
            FailedAttempt(tool_name="flaky_api", error_code="RATE_LIMITED", iteration=1)
        )
        msgs = sp.to_llm_messages()
        system_content = msgs[0]["content"]
        assert "PREVIOUSLY FAILED" in system_content
        assert "flaky_api" in system_content

    def test_budget_status_injected(self):
        sp = self._make_scratchpad()
        sp.budget.consume_tool()
        sp.budget.consume_tool()
        msgs = sp.to_llm_messages()
        system_content = msgs[0]["content"]
        assert "Tool calls remaining:" in system_content
        assert "8" in system_content  # 10 - 2 = 8 remaining

    def test_record_tool_result_decrements_budget(self):
        sp = self._make_scratchpad()
        call = ToolCall(name="web_search", arguments={"query": "test"})
        result = ToolResult(tool_name="web_search", ok=True, output={"data": "test"})
        sp.record_tool_result(call, result)
        assert sp.budget.tools_used == 1

    def test_record_tool_failure_tracked(self):
        sp = self._make_scratchpad()
        call = ToolCall(name="flaky_api", arguments={"endpoint": "test"})
        result = ToolResult(
            tool_name="flaky_api", ok=False, error_code="RATE_LIMITED", error_message="Try later"
        )
        sp.record_tool_result(call, result)
        assert len(sp.failed_attempts) == 1
        assert sp.failed_attempts[0].tool_name == "flaky_api"

    def test_add_finding(self):
        sp = self._make_scratchpad()
        sp.iteration = 3
        sp.add_finding(Finding(key="capital_france", value="Paris", type="fact"))
        assert "capital_france" in sp.findings
        assert sp.findings["capital_france"].source_iteration == 3

    def test_findings_summary(self):
        sp = self._make_scratchpad()
        sp.add_finding(Finding(key="temp", value=22, type="weather"))
        sp.add_finding(Finding(key="ev_sales", value="14.2M", type="fact"))
        summary = sp.findings_summary()
        assert "temp" in summary
        assert "ev_sales" in summary
        assert "WEATHER" in summary
        assert "FACT" in summary

    def test_needs_compaction(self):
        sp = self._make_scratchpad(compaction_token_ratio=0.0001)
        # Add messages with enough text to exceed the very low token ratio
        for i in range(5):
            sp.messages.append(Message(role="assistant", content=f"Response {i} " * 50))
            sp.messages.append(Message(role="user", content=f"Follow-up {i} " * 50))
        assert sp.needs_compaction()

    def test_no_compaction_needed(self):
        sp = self._make_scratchpad()
        sp.messages.append(Message(role="assistant", content="One response"))
        assert not sp.needs_compaction()

    @pytest.mark.asyncio
    async def test_compact_messages(self):
        sp = self._make_scratchpad(compaction_token_ratio=0.0001, keep_last_n=2)

        # Add enough messages to trigger compaction
        for i in range(8):
            sp.messages.append(Message(role="assistant", content=f"Response about topic {i}"))
            sp.messages.append(Message(role="user", content=f"Tell me about topic {i+1}"))

        initial_count = len(sp.messages)
        assert sp.needs_compaction()

        # Mock summarizer
        async def mock_summarizer(msgs):
            return f"Summarized {len(msgs)} messages about various topics."

        await sp.compact_messages(mock_summarizer)

        # Messages should be reduced
        assert len(sp.messages) < initial_count
        # Should have a compacted summary message
        compacted = [m for m in sp.messages if m.is_compacted_summary]
        assert len(compacted) == 1
        assert "Summarized" in compacted[0].content

    def test_is_complete_when_final_content(self):
        sp = self._make_scratchpad()
        sp.final_content = "The answer is 42."
        assert sp.is_complete()

    def test_is_complete_when_budget_exhausted(self):
        sp = self._make_scratchpad()
        sp.budget.tools_used = sp.budget.max_tools
        assert sp.is_complete()

    def test_spawn_sub_agent(self):
        sp = self._make_scratchpad()
        agent = sp.spawn_sub_agent(task="Research AI", tool_budget=3)
        assert agent.agent_id in sp.sub_agents
        assert agent.status == SubAgentStatus.RUNNING
        assert agent.budget_consumed.max_tools == 3
        # Parent budget should deduct
        assert sp.budget.tools_used == 3

    def test_complete_sub_agent(self):
        sp = self._make_scratchpad()
        agent = sp.spawn_sub_agent(task="Research AI", tool_budget=3)
        findings = [Finding(key="ai_market", value="$100B", type="fact")]
        sp.complete_sub_agent(agent.agent_id, findings, result="AI market is $100B")

        assert sp.sub_agents[agent.agent_id].status == SubAgentStatus.COMPLETE
        assert "ai_market" in sp.findings  # absorbed into parent

    def test_complete_sub_agent_returns_budget(self):
        sp = self._make_scratchpad()
        agent = sp.spawn_sub_agent(task="Research AI", tool_budget=5)
        # Sub-agent only used 2 of 5
        agent.budget_consumed.tools_used = 2
        sp.complete_sub_agent(agent.agent_id, [], result="done")
        # 3 unused should return to parent
        # Parent allocated 5, got 3 back -> net cost = 2
        assert sp.budget.tools_used < 5

    def test_snapshot_iteration(self):
        sp = self._make_scratchpad()
        sp.iteration = 1
        snap = sp.snapshot_iteration(
            thought="I should search for quantum computing",
            tools_called=["web_search"],
            tokens_in=100,
            tokens_out=50,
        )
        assert snap.iteration == 1
        assert snap.tools_called == ["web_search"]
        assert len(sp.iteration_snapshots) == 1
        assert sp.budget.tokens_in == 100

    def test_sub_agents_in_context(self):
        sp = self._make_scratchpad()
        agent = sp.spawn_sub_agent(task="Research climate data", tool_budget=3)
        sp.complete_sub_agent(
            agent.agent_id,
            [Finding(key="co2", value="424 ppm", type="fact")],
            result="CO2 is 424 ppm",
        )

        msgs = sp.to_llm_messages()
        system_content = msgs[0]["content"]
        assert "SUB-AGENTS" in system_content
        assert "co2" in system_content


class TestRecordToolResultModes:
    """Tests for the three-mode record_tool_result: findings-only, truncated, full."""

    def _make_scratchpad(self, **kwargs) -> Scratchpad:
        defaults = {
            "system_prompt": "You are a helpful assistant.",
            "user_query": "Analyze data",
        }
        defaults.update(kwargs)
        sp = Scratchpad(**defaults)
        sp.messages.append(Message(role="user", content=sp.user_query))
        return sp

    def test_findings_mode_stores_digest_not_raw(self):
        """When findings are provided, raw output must NOT appear in messages."""
        sp = self._make_scratchpad()
        call = ToolCall(name="search_database_large", arguments={"dataset": "customer_history"})
        # Simulate a large tool result (~3500 tokens)
        large_output = {
            "customers": [{"id": i, "name": f"User{i}", "revenue": i * 100} for i in range(200)]
        }
        result = ToolResult(tool_name="search_database_large", ok=True, output=large_output)

        findings = [
            Finding(key="total_customers", value=200, type="fact"),
            Finding(key="top_revenue_customer", value="User199", type="fact"),
            Finding(key="avg_revenue", value=9950, type="fact"),
        ]

        sp.record_tool_result(call, result, findings=findings)

        # Check that the raw output is NOT in any message
        all_content = " ".join(m.content for m in sp.messages)
        assert "User199" not in all_content or "top_revenue_customer=User199" in all_content
        # The word "User150" from raw data should NOT be in messages
        assert "User150" not in all_content

        # But finding keys SHOULD be in the digest
        assert "total_customers" in all_content
        assert "Extracted" in all_content or "findings" in all_content.lower()

    def test_findings_mode_context_stays_small(self):
        """Context tokens after findings-mode recording should be tiny."""
        sp = self._make_scratchpad()
        call = ToolCall(name="analytics_report", arguments={"report_type": "purchase"})
        # Big raw output
        raw = str({"data": "x" * 10_000})
        result = ToolResult(tool_name="analytics_report", ok=True, output=raw)

        findings = [
            Finding(key="total_revenue", value="$4.1M", type="revenue"),
            Finding(key="yoy_growth", value="23.4%", type="trend"),
        ]

        sp.record_tool_result(call, result, findings=findings)

        # The tool message should be much smaller than the raw output
        tool_msgs = [m for m in sp.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert len(tool_msgs[0].content) < 500  # digest, not 10K chars

    def test_truncation_mode_for_large_output_no_findings(self):
        """Large output without findings should be truncated."""
        sp = self._make_scratchpad()
        call = ToolCall(name="search_database_large", arguments={"dataset": "test"})
        large_output = "x" * 5000  # >500 token estimate
        result = ToolResult(tool_name="search_database_large", ok=True, output=large_output)

        sp.record_tool_result(call, result)  # no findings

        tool_msgs = [m for m in sp.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        # Should be truncated, not full 5000 chars
        assert len(tool_msgs[0].content) < 1000
        assert (
            "truncated" in tool_msgs[0].content.lower() or "large" in tool_msgs[0].content.lower()
        )

    def test_small_output_stored_in_full(self):
        """Small outputs (<500 token estimate) stored in full when no findings."""
        sp = self._make_scratchpad()
        call = ToolCall(name="weather_api", arguments={"city": "Paris"})
        small_output = {"city": "Paris", "temp_c": 22, "condition": "Sunny"}
        result = ToolResult(tool_name="weather_api", ok=True, output=small_output)

        sp.record_tool_result(call, result)  # no findings, small output

        tool_msgs = [m for m in sp.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        # Full output should be present
        assert "Paris" in tool_msgs[0].content
        assert "22" in tool_msgs[0].content

    def test_error_always_stored_fully(self):
        """Error results always stored in full regardless of size."""
        sp = self._make_scratchpad()
        call = ToolCall(name="flaky_api", arguments={"endpoint": "test"})
        result = ToolResult(
            tool_name="flaky_api",
            ok=False,
            error_code="RATE_LIMITED",
            error_message="API rate limit exceeded, try again later",
        )

        sp.record_tool_result(call, result)

        tool_msgs = [m for m in sp.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert "RATE_LIMITED" in tool_msgs[0].content
        assert len(sp.failed_attempts) == 1

    def test_large_payload_context_bounded_end_to_end(self):
        """Simulate 3 large tool calls and verify context stays bounded."""
        sp = self._make_scratchpad()
        import json

        # Simulate 3 large tool calls with findings
        datasets = [
            ("search_database_large", {"customers": [{"id": i} for i in range(200)]}),
            ("analytics_report", {"segments": [{"id": i, "data": "x" * 50} for i in range(50)]}),
            ("vector_search", {"results": [{"id": i, "score": 0.9} for i in range(100)]}),
        ]

        for tool_name, output in datasets:
            call = ToolCall(name=tool_name, arguments={"query": "test"})
            result = ToolResult(tool_name=tool_name, ok=True, output=output)
            findings = [
                Finding(key=f"{tool_name}_metric_1", value="value1", type="fact"),
                Finding(key=f"{tool_name}_metric_2", value="value2", type="fact"),
            ]
            sp.record_tool_result(call, result, findings=findings)
            sp.add_findings(findings)

        # Raw data would be ~10,000+ tokens
        raw_total = sum(len(json.dumps(d[1])) for d in datasets)
        assert raw_total > 5000, f"Test setup: raw should be >5000 chars, got {raw_total}"

        # Context via scratchpad should be bounded
        context_msgs = sp.to_llm_messages()
        context_total = sum(len(m.get("content", "")) for m in context_msgs)
        # Context should be well under the raw total (at least 50% smaller)
        assert (
            context_total < raw_total * 0.5
        ), f"Context ({context_total}) should be <50% of raw ({raw_total})"

    def test_budget_decremented_in_all_modes(self):
        """Budget should be decremented regardless of which storage mode is used."""
        sp = self._make_scratchpad()

        # Mode 1: findings
        call1 = ToolCall(name="tool_a", arguments={})
        result1 = ToolResult(tool_name="tool_a", ok=True, output="data")
        sp.record_tool_result(call1, result1, findings=[Finding(key="k", value="v")])

        # Mode 2: truncation
        call2 = ToolCall(name="tool_b", arguments={})
        result2 = ToolResult(tool_name="tool_b", ok=True, output="y" * 5000)
        sp.record_tool_result(call2, result2)

        # Mode 3: full
        call3 = ToolCall(name="tool_c", arguments={})
        result3 = ToolResult(tool_name="tool_c", ok=True, output="small")
        sp.record_tool_result(call3, result3)

        # Mode 4: error
        call4 = ToolCall(name="tool_d", arguments={})
        result4 = ToolResult(tool_name="tool_d", ok=False, error_code="ERR")
        sp.record_tool_result(call4, result4)

        assert sp.budget.tools_used == 4
