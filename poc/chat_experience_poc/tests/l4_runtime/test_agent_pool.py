"""
Integration tests for Agent Pool

Tests pooling constraints, LRU eviction, health checks, and metrics.
"""

import asyncio

import pytest
from l4_runtime.lifecycle import AgentPool


@pytest.fixture
async def agent_pool():
    """Create fresh agent pool for each test"""
    pool = AgentPool()
    pool.clear_pool()  # Clear any existing agents
    pool._metrics = type(pool._metrics)()  # Reset metrics
    # Stop any running health checks
    if pool._health_check_task and not pool._health_check_task.done():
        await pool.stop_health_checks()
    yield pool
    # Cleanup
    if pool._health_check_task and not pool._health_check_task.done():
        await pool.stop_health_checks()
    pool.clear_pool()


class TestPoolBasics:
    """Test basic pool operations"""

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test: AgentPool is a singleton"""
        pool1 = AgentPool()
        pool2 = AgentPool()
        assert pool1 is pool2

    @pytest.mark.asyncio
    async def test_add_to_pool(self, agent_pool):
        """Test: Add agent to pool"""
        result = agent_pool.add_to_pool("agent_001", "planner")
        assert result is True
        assert agent_pool.pool_size("planner") == 1

    @pytest.mark.asyncio
    async def test_get_from_pool(self, agent_pool):
        """Test: Get agent from pool"""
        agent_pool.add_to_pool("agent_001", "planner")

        agent_id = agent_pool.get_from_pool("planner")
        assert agent_id == "agent_001"

    @pytest.mark.asyncio
    async def test_get_from_empty_pool(self, agent_pool):
        """Test: Get from empty pool returns None"""
        agent_id = agent_pool.get_from_pool("planner")
        assert agent_id is None

    @pytest.mark.asyncio
    async def test_remove_from_pool(self, agent_pool):
        """Test: Remove agent from pool"""
        agent_pool.add_to_pool("agent_001", "planner")

        result = agent_pool.remove_from_pool("agent_001")
        assert result is True
        assert agent_pool.pool_size("planner") == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, agent_pool):
        """Test: Remove nonexistent agent returns False"""
        result = agent_pool.remove_from_pool("agent_999")
        assert result is False

    @pytest.mark.asyncio
    async def test_pool_size_by_type(self, agent_pool):
        """Test: Pool size by agent type"""
        agent_pool.add_to_pool("agent_001", "planner")
        agent_pool.add_to_pool("agent_002", "planner")
        agent_pool.add_to_pool("agent_003", "coder")

        assert agent_pool.pool_size("planner") == 2
        assert agent_pool.pool_size("coder") == 1
        assert agent_pool.pool_size() == 3  # Total

    @pytest.mark.asyncio
    async def test_clear_pool_by_type(self, agent_pool):
        """Test: Clear pool by type"""
        agent_pool.add_to_pool("agent_001", "planner")
        agent_pool.add_to_pool("agent_002", "coder")

        count = agent_pool.clear_pool("planner")
        assert count == 1
        assert agent_pool.pool_size("planner") == 0
        assert agent_pool.pool_size("coder") == 1


class TestSessionConstraints:
    """Test max 3 agents per session constraint"""

    def test_add_within_session_limit(self, agent_pool):
        """Test: Add 3 agents to same session (within limit)"""
        session_id = "session_001"

        assert agent_pool.add_to_pool("agent_001", "planner", session_id) is True
        assert agent_pool.add_to_pool("agent_002", "planner", session_id) is True
        assert agent_pool.add_to_pool("agent_003", "planner", session_id) is True

        assert agent_pool.pool_size("planner") == 3

    def test_exceed_session_limit(self, agent_pool):
        """Test: Adding 4th agent to session fails"""
        session_id = "session_001"

        agent_pool.add_to_pool("agent_001", "planner", session_id)
        agent_pool.add_to_pool("agent_002", "planner", session_id)
        agent_pool.add_to_pool("agent_003", "planner", session_id)

        # 4th agent should fail
        result = agent_pool.add_to_pool("agent_004", "planner", session_id)
        assert result is False
        assert agent_pool.pool_size("planner") == 3

    def test_different_sessions_independent(self, agent_pool):
        """Test: Different sessions have independent limits"""
        agent_pool.add_to_pool("agent_001", "planner", "session_001")
        agent_pool.add_to_pool("agent_002", "planner", "session_001")
        agent_pool.add_to_pool("agent_003", "planner", "session_001")

        # Different session should succeed
        result = agent_pool.add_to_pool("agent_004", "planner", "session_002")
        assert result is True
        assert agent_pool.pool_size("planner") == 4


class TestTypeConstraints:
    """Test max 5 agents per type constraint"""

    def test_add_within_type_limit(self, agent_pool):
        """Test: Add 5 agents of same type (within limit)"""
        for i in range(5):
            result = agent_pool.add_to_pool(f"agent_{i:03d}", "planner")
            assert result is True

        assert agent_pool.pool_size("planner") == 5

    def test_exceed_type_limit_evicts_lru(self, agent_pool):
        """Test: Adding 6th agent evicts LRU"""
        # Add 5 agents
        for i in range(5):
            agent_pool.add_to_pool(f"agent_{i:03d}", "planner")

        # Add 6th agent (should evict agent_000)
        result = agent_pool.add_to_pool("agent_005", "planner")
        assert result is True
        assert agent_pool.pool_size("planner") == 5

        # Verify agent_000 was evicted
        agents = agent_pool.get_pooled_agents("planner")
        agent_ids = [a.agent_id for a in agents]
        assert "agent_000" not in agent_ids
        assert "agent_005" in agent_ids


class TestLRUEviction:
    """Test LRU eviction logic"""

    def test_lru_eviction_order(self, agent_pool):
        """Test: LRU evicts least recently accessed agent"""
        # Add 3 agents
        agent_pool.add_to_pool("agent_001", "planner")
        agent_pool.add_to_pool("agent_002", "planner")
        agent_pool.add_to_pool("agent_003", "planner")

        # Access agent_001 (moves to end)
        agent_pool.get_from_pool("planner")  # Gets agent_001

        # Add 2 more agents (fill to 5)
        agent_pool.add_to_pool("agent_004", "planner")
        agent_pool.add_to_pool("agent_005", "planner")

        # Add 6th agent (should evict agent_002, the LRU)
        agent_pool.add_to_pool("agent_006", "planner")

        agents = agent_pool.get_pooled_agents("planner")
        agent_ids = [a.agent_id for a in agents]

        assert "agent_001" in agent_ids  # Was accessed, not LRU
        assert "agent_002" not in agent_ids  # Was LRU, evicted
        assert "agent_006" in agent_ids  # Newly added


class TestGetFromPool:
    """Test get_from_pool logic"""

    def test_prefer_same_session(self, agent_pool):
        """Test: Prefer agent from same session"""
        # Add agents from different sessions
        agent_pool.add_to_pool("agent_001", "planner", "session_001")
        agent_pool.add_to_pool("agent_002", "planner", "session_002")

        # Get for session_002 should return agent_002
        agent_id = agent_pool.get_from_pool("planner", "session_002")
        assert agent_id == "agent_002"

    def test_fallback_any_agent(self, agent_pool):
        """Test: Return any agent if no session match"""
        agent_pool.add_to_pool("agent_001", "planner", "session_001")

        # Request for different session should still return agent_001
        agent_id = agent_pool.get_from_pool("planner", "session_999")
        assert agent_id == "agent_001"

    def test_get_updates_lru(self, agent_pool):
        """Test: get_from_pool updates LRU order"""
        agent_pool.add_to_pool("agent_001", "planner")
        agent_pool.add_to_pool("agent_002", "planner")

        # Access agent_001
        agent_pool.get_from_pool("planner")

        # Fill pool to capacity
        for i in range(3, 6):
            agent_pool.add_to_pool(f"agent_{i:03d}", "planner")

        # Add 6th agent (should evict agent_002, not agent_001)
        agent_pool.add_to_pool("agent_006", "planner")

        agents = agent_pool.get_pooled_agents("planner")
        agent_ids = [a.agent_id for a in agents]

        assert "agent_001" in agent_ids  # Was accessed
        assert "agent_002" not in agent_ids  # Was LRU


class TestMetrics:
    """Test pool metrics"""

    def test_metrics_hit_rate(self, agent_pool):
        """Test: Hit rate calculation"""
        agent_pool.add_to_pool("agent_001", "planner")

        # 2 hits
        agent_pool.get_from_pool("planner")
        agent_pool.get_from_pool("planner")

        # 1 miss
        agent_pool.get_from_pool("coder")

        metrics = agent_pool.get_metrics()
        assert metrics.total_gets == 3
        assert metrics.total_hits == 2
        assert metrics.total_misses == 1
        assert metrics.hit_rate() == 2 / 3

    def test_metrics_reuse_latency(self, agent_pool):
        """Test: Reuse latency tracking"""
        agent_pool.add_to_pool("agent_001", "planner")

        agent_pool.get_from_pool("planner")

        metrics = agent_pool.get_metrics()
        assert len(metrics.reuse_latencies) == 1
        # Latency should be very low (likely 0.0 in fast tests)
        assert metrics.avg_reuse_latency() >= 0
        assert metrics.avg_reuse_latency() < 10  # Should be <10ms

    def test_metrics_evictions(self, agent_pool):
        """Test: Eviction count tracking"""
        # Fill pool to capacity
        for i in range(5):
            agent_pool.add_to_pool(f"agent_{i:03d}", "planner")

        # Add 6th agent (triggers eviction)
        agent_pool.add_to_pool("agent_005", "planner")

        metrics = agent_pool.get_metrics()
        assert metrics.total_evictions == 1


class TestHealthChecks:
    """Test health check functionality"""

    @pytest.mark.asyncio
    async def test_start_stop_health_checks(self, agent_pool):
        """Test: Start and stop health check loop"""
        await agent_pool.start_health_checks()

        # Wait a bit
        await asyncio.sleep(0.1)

        await agent_pool.stop_health_checks()

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, agent_pool):
        """Test: TTL expiration logic (manual trigger)"""
        # Override TTL for test
        agent_pool._ttl_seconds = 0.1  # 100ms

        # Add agent
        agent_pool.add_to_pool("agent_001", "planner")
        assert agent_pool.pool_size() == 1

        # Wait for TTL to expire
        await asyncio.sleep(0.15)

        # Manually trigger health check
        await agent_pool._run_health_checks()

        # Agent should be removed
        assert agent_pool.pool_size() == 0

        # Check metrics
        metrics = agent_pool.get_metrics()
        assert metrics.total_ttl_expirations == 1

        # Restore defaults
        agent_pool._ttl_seconds = 600


class TestPooledAgentMetadata:
    """Test PooledAgent metadata"""

    def test_pooled_agent_age(self, agent_pool):
        """Test: PooledAgent age calculation"""
        agent_pool.add_to_pool("agent_001", "planner")

        agents = agent_pool.get_pooled_agents("planner")
        assert len(agents) == 1

        agent = agents[0]
        assert agent.age_seconds() >= 0
        assert agent.age_seconds() < 1  # Should be very recent

    def test_pooled_agent_idle_time(self, agent_pool):
        """Test: PooledAgent idle time calculation"""
        agent_pool.add_to_pool("agent_001", "planner")

        agents = agent_pool.get_pooled_agents("planner")
        agent = agents[0]

        # Initially idle time ~0
        assert agent.idle_seconds() < 1

        # After some time
        import time

        time.sleep(0.05)

        assert agent.idle_seconds() >= 0.05


class TestRepr:
    """Test string representation"""

    def test_repr(self, agent_pool):
        """Test: AgentPool repr shows stats"""
        agent_pool.add_to_pool("agent_001", "planner")
        agent_pool.get_from_pool("planner")

        repr_str = repr(agent_pool)
        assert "AgentPool" in repr_str
        assert "total_agents" in repr_str
        assert "hit_rate" in repr_str
        assert "hit_rate" in repr_str
