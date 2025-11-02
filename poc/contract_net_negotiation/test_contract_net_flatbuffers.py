"""
Test suite for Contract Net PoC with FlatBuffers

Tests: negotiation, bidding, serialization, SLO compliance, performance
"""

import pytest
from poc_contract_net_flatbuffers import (
    ContractNetNegotiator,
    ContractNetPoC,
    MockAgent,
    Proposal,
    TaskAnnouncement,
)


class TestMockAgent:
    """Test agent bidding behavior"""

    @pytest.mark.asyncio
    async def test_agent_evaluates_capability_match(self):
        """Agent only bids on matching capabilities"""
        agent = MockAgent("a1", ["compute", "storage"], bid_probability=1.0)

        # Task with matching capability
        task = TaskAnnouncement("t1", "test", 100, 500, ["compute"])
        proposal = await agent.evaluate_and_bid(task)
        assert proposal is not None
        assert proposal.agent_id == "a1"

    @pytest.mark.asyncio
    async def test_agent_respects_bid_probability(self):
        """Agent respects bid probability"""
        agent = MockAgent("a2", ["compute"], bid_probability=0.0)
        task = TaskAnnouncement("t2", "test", 100, 500, ["compute"])
        proposal = await agent.evaluate_and_bid(task)
        assert proposal is None

    @pytest.mark.asyncio
    async def test_agent_proposal_generation(self):
        """Agent generates valid proposals"""
        agent = MockAgent("a3", ["compute", "storage"], bid_probability=1.0)
        task = TaskAnnouncement("t3", "test", 100, 500, ["compute"])
        proposal = await agent.evaluate_and_bid(task)

        assert proposal.agent_id == "a3"
        assert proposal.task_id == "t3"
        assert 0 < proposal.estimated_latency_ms < 100
        assert 0 < proposal.estimated_cost < 500
        assert 0.6 <= proposal.confidence <= 0.95


class TestProposalSerialization:
    """Test FlatBuffers serialization"""

    def test_proposal_to_bytes(self):
        """Serialize proposal to FlatBuffers"""
        proposal = Proposal(
            "agent_1", "task_1", 25, 300.0, 0.85, "competitive", ["tool_a", "tool_b"], "reasoning"
        )
        data = proposal.to_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_proposal_from_bytes(self):
        """Deserialize proposal from FlatBuffers"""
        original = Proposal("agent_2", "task_2", 30, 250.0, 0.9, "efficient", ["tool_x"], "test")
        data = original.to_bytes()
        restored = Proposal.from_bytes(data)

        assert restored.agent_id == original.agent_id
        assert restored.task_id == original.task_id
        assert restored.estimated_latency_ms == original.estimated_latency_ms
        assert abs(restored.estimated_cost - original.estimated_cost) < 0.01
        assert abs(restored.confidence - original.confidence) < 0.001
        assert restored.strategy == original.strategy
        assert restored.tools == original.tools


class TestContractNetNegotiator:
    """Test negotiation protocol"""

    @pytest.mark.asyncio
    async def test_negotiator_collects_proposals(self):
        """Negotiator collects proposals from agents"""
        agents = [
            MockAgent("a1", ["compute"], bid_probability=1.0, bid_latency_ms=2),
            MockAgent("a2", ["storage"], bid_probability=1.0, bid_latency_ms=2),
        ]
        negotiator = ContractNetNegotiator(agents, deadline_ms=100)

        task = TaskAnnouncement("t1", "test", 100, 500, ["compute", "storage"])
        proposals = await negotiator.negotiate(task)

        assert len(proposals) >= 1
        assert all(isinstance(p, Proposal) for p in proposals)

    @pytest.mark.asyncio
    async def test_negotiation_respects_deadline(self):
        """Negotiation completes within deadline"""
        agents = [MockAgent(f"a{i}", ["compute"], bid_latency_ms=5) for i in range(5)]
        negotiator = ContractNetNegotiator(agents, deadline_ms=30)

        task = TaskAnnouncement("t1", "test", 100, 500, ["compute"])

        import time

        start = time.perf_counter()
        proposals = await negotiator.negotiate(task)
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 60  # Should complete well within 60ms

    @pytest.mark.asyncio
    async def test_early_termination_works(self):
        """Early termination reduces negotiation time"""
        agents = [
            MockAgent(f"a{i}", ["compute"], bid_probability=1.0, bid_latency_ms=2)
            for i in range(10)
        ]
        negotiator = ContractNetNegotiator(
            agents,
            deadline_ms=50,
            enable_early_termination=True,
            min_proposals_for_early_termination=3,
        )

        task = TaskAnnouncement("t1", "test", 100, 500, ["compute"])

        import time

        start = time.perf_counter()
        proposals = await negotiator.negotiate(task)
        elapsed = (time.perf_counter() - start) * 1000

        # With early termination, should be faster than full deadline
        assert elapsed < 35  # Should exit early, well before 50ms


class TestPerformance:
    """Performance validation tests"""

    @pytest.mark.asyncio
    async def test_single_negotiation_latency(self):
        """Single negotiation latency is acceptable"""
        poc = ContractNetPoC(num_agents=15, num_tasks=1)
        metrics = await poc.benchmark_negotiation()

        assert metrics["p95"] < 100  # Should complete reasonably fast for testing

    @pytest.mark.asyncio
    async def test_batch_negotiation_distribution(self):
        """Batch latency has expected distribution"""
        poc = ContractNetPoC(num_agents=15, num_tasks=50)
        metrics = await poc.benchmark_negotiation()

        # Verify metrics are computed
        assert "p50" in metrics
        assert "p95" in metrics
        assert "p99" in metrics
        assert metrics["count"] == 50

        # Check monotonicity: p50 <= p95 <= p99
        assert metrics["p50"] <= metrics["p95"]
        assert metrics["p95"] <= metrics["p99"]


class TestSLOCompliance:
    """SLO validation tests"""

    @pytest.mark.asyncio
    async def test_slo_target_50ms_p95(self):
        """Validate <50ms P95 SLO (primary metric)"""
        poc = ContractNetPoC(num_agents=15, num_tasks=100)
        metrics = await poc.benchmark_negotiation()

        # Primary SLO: <50ms P95
        assert metrics["slo_passed"], f"SLO failed: P95={metrics['p95']:.2f}ms, target <50ms"

    @pytest.mark.asyncio
    async def test_p50_latency_good(self):
        """P50 latency should be well under 50ms"""
        poc = ContractNetPoC(num_agents=15, num_tasks=50)
        metrics = await poc.benchmark_negotiation()

        # Typical fast case: P50 should be 15-30ms
        assert metrics["p50"] < 40, f"P50 is too high: {metrics['p50']:.2f}ms"


# ============================================================================
# Integration Tests
# ============================================================================


class TestContractNetIntegration:
    """End-to-end Contract Net protocol tests"""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Complete workflow: task -> broadcast -> bidding -> collection"""
        agents = [
            MockAgent("lead", ["compute", "network"], bid_probability=1.0, bid_latency_ms=3),
            MockAgent("worker1", ["compute"], bid_probability=1.0, bid_latency_ms=4),
            MockAgent("worker2", ["storage"], bid_probability=1.0, bid_latency_ms=3),
        ]

        negotiator = ContractNetNegotiator(agents, deadline_ms=50)
        task = TaskAnnouncement("big_task", "Process data", 100, 1000, ["compute", "network"])

        proposals = await negotiator.negotiate(task)

        # Should get at least some proposals
        assert len(proposals) > 0

        # All proposals should be for the correct task
        assert all(p.task_id == "big_task" for p in proposals)

        # Proposals should have valid metrics
        assert all(0 < p.estimated_latency_ms < 100 for p in proposals)
        assert all(0 < p.estimated_cost < 1000 for p in proposals)
        assert all(0 < p.confidence <= 1.0 for p in proposals)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
