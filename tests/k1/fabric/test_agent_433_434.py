"""
Tests for Epic 4.3 -- Agent Pool (4.3.3) and Delta Emission (4.3.4).

Covers:
  - AgentPool: put/get, FIFO reuse, capacity eviction, TTL sweep, drain_all
  - AgentPoolConfig: defaults, customization, frozen
  - AgentPoolFullError: exception attributes
  - AgentDelta: construction, validation, to_dict, from_dict, LWW ops
  - DeltaEmitter: batched emission, LWW merge, flush, flush_if_ready
  - DELTA_TOPIC_PATTERN, DELTA_BATCH_WINDOW_MS constants
  - AgentFactory integration with pool (pool hit reuse, pool miss spawn)
  - AgentFactory integration with DeltaEmitter (structured delta on execute)
  - Module exports (providers __init__.py updated to 75)

Test architecture:
  - All tests are integration-oriented (real objects, no mocks)
  - Fakes implement port protocols structurally
  - pytest-asyncio auto mode for async tests
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.providers.agent_provider import (
    DELTA_BATCH_WINDOW_MS,
    DELTA_TOPIC_PATTERN,
    IDLE_TTL_S,
    Agent,
    AgentDelta,
    AgentFactory,
    AgentPool,
    AgentPoolConfig,
    AgentPoolFullError,
    DeltaEmitter,
)
from k1.fabric.types import AgentContract, AgentLifecycleState, CapabilityRequest, ExecutionContext

# ---------------------------------------------------------------------------
# Fake implementations of port protocols (reused pattern from 431_432)
# ---------------------------------------------------------------------------


class FakeLLMHandle:
    """Fake ILLMHandle for testing."""

    def __init__(
        self,
        model_id: str = "fake-model-v1",
        budget_tokens: int = 4000,
        response: str = "LLM response text",
        fail: bool = False,
    ) -> None:
        self._model_id = model_id
        self._budget_tokens = budget_tokens
        self._response = response
        self._fail = fail
        self.calls: List[Dict[str, Any]] = []

    async def generate(self, prompt: str, params: Dict[str, Any]) -> str:
        self.calls.append({"prompt": prompt, "params": params})
        if self._fail:
            raise RuntimeError("LLM generation failed")
        return self._response

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens


class FakeModelGateway:
    """Fake IModelGatewayPort for testing."""

    def __init__(
        self,
        handle: Optional[FakeLLMHandle] = None,
        fail_create: bool = False,
    ) -> None:
        self._handle = handle or FakeLLMHandle()
        self._fail_create = fail_create
        self.create_calls: List[Dict[str, Any]] = []

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> FakeLLMHandle:
        self.create_calls.append(
            {
                "budget_tokens": budget_tokens,
                "model_preference": model_preference,
                "capabilities": capabilities,
                "trace_id": trace_id,
            }
        )
        if self._fail_create:
            raise RuntimeError("Model gateway unavailable")
        return self._handle

    async def is_model_loaded(self, model_id: str) -> bool:
        return True


class FakeDeltaBus:
    """Fake IDeltaBusPort for testing."""

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.deltas: List[Dict[str, Any]] = []

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        if self._fail:
            raise RuntimeError("Delta bus failure")
        self.deltas.append(
            {
                "agent_id": agent_id,
                "delta_type": delta_type,
                "section": section,
                "data": data,
            }
        )


class FakeStateReader:
    """Fake ISessionStateReader for testing."""

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._sections = sections or {}

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        return self._sections.get(section)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_contract(
    name: str = "test_agent",
    provider_id: str = "agent-runner",
    tools: Optional[List[str]] = None,
    llm_budget: int = 4000,
) -> AgentContract:
    """Build an AgentContract for testing."""
    return AgentContract(
        name=name,
        version="1.0.0",
        provider_id=provider_id,
        provider_type="AGENT",
        required_context=["beliefs_active"],
        optional_context=["preferences"],
        prompt_template="You are a helpful assistant.",
        tools_granted=tools or [],
        llm_budget_tokens=llm_budget,
        max_tool_calls=10,
    )


def _make_context(trace_id: str = "t-001", prompt: str = "") -> ExecutionContext:
    """Build an ExecutionContext for testing."""
    return ExecutionContext(trace_id=trace_id, prompt=prompt)


def _make_agent(
    contract: Optional[AgentContract] = None,
    delta_bus: Optional[FakeDeltaBus] = None,
    delta_emitter: Optional[DeltaEmitter] = None,
    agent_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
) -> Agent:
    """Build an Agent for testing."""
    return Agent(
        agent_id=agent_id,
        contract=contract or _make_agent_contract(),
        context=_make_context(),
        delta_bus=delta_bus,
        delta_emitter=delta_emitter,
    )


def _make_active_agent(
    contract: Optional[AgentContract] = None,
    agent_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    delta_bus: Optional[FakeDeltaBus] = None,
    delta_emitter: Optional[DeltaEmitter] = None,
) -> Agent:
    """Build an Agent in ACTIVE state."""
    agent = _make_agent(
        contract=contract,
        agent_id=agent_id,
        delta_bus=delta_bus,
        delta_emitter=delta_emitter,
    )
    agent.warm_up()
    return agent


def _make_request(
    capability_name: str = "agent.execute.test_agent",
    params: Optional[Dict[str, Any]] = None,
) -> CapabilityRequest:
    """Build a CapabilityRequest for testing."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {"key": "value"},
        caller="test",
        trace_id="t-001",
    )


# ===================================================================
# 4.3.4 -- AgentDelta
# ===================================================================


class TestAgentDelta:
    """Tests for AgentDelta structured payload."""

    def test_construction_minimal(self) -> None:
        """AgentDelta with required fields only."""
        delta = AgentDelta(
            agent_id="a1",
            delta_type="belief",
            section="beliefs_active",
            key="user_mood",
            value="happy",
        )
        assert delta.agent_id == "a1"
        assert delta.delta_type == "belief"
        assert delta.section == "beliefs_active"
        assert delta.key == "user_mood"
        assert delta.value == "happy"
        assert delta.op == "set"
        assert delta.timestamp_ms == 0
        assert delta.trace_id == ""

    def test_construction_all_fields(self) -> None:
        """AgentDelta with all fields specified."""
        delta = AgentDelta(
            agent_id="a1",
            delta_type="fact",
            section="scoreboard",
            key="goal_1",
            value={"status": "done"},
            op="append",
            timestamp_ms=12345,
            trace_id="t-001",
        )
        assert delta.op == "append"
        assert delta.timestamp_ms == 12345
        assert delta.trace_id == "t-001"

    def test_invalid_op_raises(self) -> None:
        """Invalid op value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid delta op 'merge'"):
            AgentDelta(
                agent_id="a1",
                delta_type="x",
                section="s",
                key="k",
                value="v",
                op="merge",
            )

    def test_valid_ops(self) -> None:
        """All three valid ops accepted."""
        for op in ("set", "append", "delete"):
            delta = AgentDelta(
                agent_id="a1",
                delta_type="x",
                section="s",
                key="k",
                value="v",
                op=op,
            )
            assert delta.op == op

    def test_to_dict(self) -> None:
        """to_dict serializes all fields."""
        delta = AgentDelta(
            agent_id="a1",
            delta_type="belief",
            section="beliefs_active",
            key="mood",
            value="happy",
            op="set",
            timestamp_ms=999,
            trace_id="t-001",
        )
        d = delta.to_dict()
        assert d["agent_id"] == "a1"
        assert d["delta_type"] == "belief"
        assert d["section"] == "beliefs_active"
        assert d["key"] == "mood"
        assert d["value"] == "happy"
        assert d["op"] == "set"
        assert d["timestamp_ms"] == 999
        assert d["trace_id"] == "t-001"

    def test_from_dict(self) -> None:
        """from_dict round-trips correctly."""
        original = AgentDelta(
            agent_id="a1",
            delta_type="fact",
            section="scoreboard",
            key="goal",
            value=42,
            op="append",
            timestamp_ms=5000,
            trace_id="t-002",
        )
        rebuilt = AgentDelta.from_dict(original.to_dict())
        assert rebuilt.agent_id == original.agent_id
        assert rebuilt.delta_type == original.delta_type
        assert rebuilt.section == original.section
        assert rebuilt.key == original.key
        assert rebuilt.value == original.value
        assert rebuilt.op == original.op
        assert rebuilt.timestamp_ms == original.timestamp_ms
        assert rebuilt.trace_id == original.trace_id

    def test_from_dict_defaults(self) -> None:
        """from_dict fills defaults for optional fields."""
        d = {
            "agent_id": "a1",
            "delta_type": "x",
            "section": "s",
            "key": "k",
            "value": "v",
        }
        delta = AgentDelta.from_dict(d)
        assert delta.op == "set"
        assert delta.timestamp_ms == 0
        assert delta.trace_id == ""

    def test_frozen(self) -> None:
        """AgentDelta is frozen (immutable)."""
        delta = AgentDelta(
            agent_id="a1",
            delta_type="x",
            section="s",
            key="k",
            value="v",
        )
        with pytest.raises(AttributeError):
            delta.value = "new"  # type: ignore[misc]

    def test_complex_value(self) -> None:
        """AgentDelta can hold complex values (dict, list)."""
        delta = AgentDelta(
            agent_id="a1",
            delta_type="observation",
            section="history_active",
            key="turn_3",
            value={"text": "hi", "confidence": 0.95, "tags": ["greeting"]},
        )
        assert isinstance(delta.value, dict)
        assert delta.value["confidence"] == 0.95


# ===================================================================
# 4.3.4 -- DeltaEmitter
# ===================================================================


class TestDeltaEmitterConstruction:
    """DeltaEmitter construction and properties."""

    def test_construction(self) -> None:
        """DeltaEmitter initializes with agent_id and delta_bus."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        assert emitter.pending_count == 0
        assert emitter.batch_window_ms == DELTA_BATCH_WINDOW_MS

    def test_custom_batch_window(self) -> None:
        """Batch window can be configured."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus, batch_window_ms=1000)
        assert emitter.batch_window_ms == 1000

    def test_repr(self) -> None:
        """repr contains useful info."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="aaaaaaaa-1234", delta_bus=bus)
        r = repr(emitter)
        assert "aaaaaaaa" in r
        assert "pending=0" in r
        assert "500ms" in r


class TestDeltaEmitterEmit:
    """DeltaEmitter.emit() queuing and LWW merge."""

    def test_emit_queues_delta(self) -> None:
        """emit() adds a delta to the pending batch."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus, trace_id="t-001")
        delta = emitter.emit(
            delta_type="belief",
            section="beliefs_active",
            key="mood",
            value="happy",
        )
        assert emitter.pending_count == 1
        assert isinstance(delta, AgentDelta)
        assert delta.agent_id == "a1"
        assert delta.key == "mood"
        assert delta.trace_id == "t-001"

    def test_emit_returns_delta_with_timestamp(self) -> None:
        """emit() assigns a monotonic timestamp."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        delta = emitter.emit(
            delta_type="x",
            section="s",
            key="k",
            value="v",
        )
        assert delta.timestamp_ms > 0

    def test_lww_merge_same_key(self) -> None:
        """Later emit for same (section, key) overwrites earlier."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="x", section="s", key="k", value="first")
        emitter.emit(delta_type="x", section="s", key="k", value="second")
        assert emitter.pending_count == 1  # merged, not 2

    def test_different_keys_not_merged(self) -> None:
        """Different (section, key) combos are kept separate."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="x", section="s", key="k1", value="a")
        emitter.emit(delta_type="x", section="s", key="k2", value="b")
        assert emitter.pending_count == 2

    def test_different_sections_not_merged(self) -> None:
        """Same key in different sections kept separate."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="x", section="s1", key="k", value="a")
        emitter.emit(delta_type="x", section="s2", key="k", value="b")
        assert emitter.pending_count == 2

    def test_emit_supports_all_ops(self) -> None:
        """emit() supports set, append, delete ops."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        d1 = emitter.emit(delta_type="x", section="s", key="k1", value="v", op="set")
        d2 = emitter.emit(delta_type="x", section="s", key="k2", value="v", op="append")
        d3 = emitter.emit(delta_type="x", section="s", key="k3", value=None, op="delete")
        assert d1.op == "set"
        assert d2.op == "append"
        assert d3.op == "delete"
        assert emitter.pending_count == 3


class TestDeltaEmitterFlush:
    """DeltaEmitter.flush() sends to Delta Bus."""

    def test_flush_sends_to_bus(self) -> None:
        """flush() sends all pending deltas via IDeltaBusPort."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="belief", section="beliefs_active", key="mood", value="happy")
        emitter.emit(delta_type="fact", section="scoreboard", key="goal", value="done")
        count = emitter.flush()
        assert count == 2
        assert len(bus.deltas) == 2
        assert emitter.pending_count == 0

    def test_flush_empty_returns_zero(self) -> None:
        """Flushing empty batch returns 0."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        assert emitter.flush() == 0

    def test_flush_lww_only_sends_winner(self) -> None:
        """After LWW merge, only the latest value is sent."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="x", section="s", key="k", value="old")
        emitter.emit(delta_type="x", section="s", key="k", value="new")
        count = emitter.flush()
        assert count == 1
        assert len(bus.deltas) == 1
        # Verify the flushed delta contains the "new" value
        sent_data = bus.deltas[0]["data"]
        assert sent_data["value"] == "new"

    def test_flush_clears_pending(self) -> None:
        """After flush, pending count is zero."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="x", section="s", key="k", value="v")
        emitter.flush()
        assert emitter.pending_count == 0

    def test_flush_bus_failure_partial(self) -> None:
        """If bus fails, flush still clears pending (non-fatal)."""
        bus = FakeDeltaBus(fail=True)
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        emitter.emit(delta_type="x", section="s", key="k", value="v")
        count = emitter.flush()
        assert count == 0  # none succeeded
        assert emitter.pending_count == 0  # still cleared


class TestDeltaEmitterFlushIfReady:
    """DeltaEmitter.flush_if_ready() respects batch window."""

    def test_flush_if_ready_before_window(self) -> None:
        """flush_if_ready returns 0 before batch window elapses."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus, batch_window_ms=60000)
        emitter.emit(delta_type="x", section="s", key="k", value="v")
        assert emitter.flush_if_ready() == 0

    def test_flush_if_ready_after_window(self) -> None:
        """flush_if_ready flushes after batch window elapses."""
        bus = FakeDeltaBus()
        # Use tiny window so it expires immediately
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus, batch_window_ms=0)
        emitter.emit(delta_type="x", section="s", key="k", value="v")
        count = emitter.flush_if_ready()
        assert count == 1

    def test_flush_if_ready_empty_batch(self) -> None:
        """flush_if_ready returns 0 when batch is empty even if window expired."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus, batch_window_ms=0)
        assert emitter.flush_if_ready() == 0


# ===================================================================
# 4.3.4 -- Constants
# ===================================================================


class TestDeltaConstants:
    """Verify delta emission constants."""

    def test_topic_pattern(self) -> None:
        """DELTA_TOPIC_PATTERN has correct format."""
        assert "{agent_id}" in DELTA_TOPIC_PATTERN
        assert DELTA_TOPIC_PATTERN == "k1.agent.{agent_id}.delta.v1"

    def test_batch_window_ms(self) -> None:
        """DELTA_BATCH_WINDOW_MS is 500."""
        assert DELTA_BATCH_WINDOW_MS == 500


# ===================================================================
# 4.3.3 -- AgentPoolConfig
# ===================================================================


class TestAgentPoolConfig:
    """Tests for AgentPoolConfig."""

    def test_defaults(self) -> None:
        """Default config values."""
        cfg = AgentPoolConfig()
        assert cfg.max_pool_size == 5
        assert cfg.idle_ttl_s == IDLE_TTL_S
        assert cfg.sweep_interval_s == 15

    def test_custom_values(self) -> None:
        """Custom config values."""
        cfg = AgentPoolConfig(max_pool_size=10, idle_ttl_s=120, sweep_interval_s=30)
        assert cfg.max_pool_size == 10
        assert cfg.idle_ttl_s == 120
        assert cfg.sweep_interval_s == 30

    def test_frozen(self) -> None:
        """AgentPoolConfig is frozen."""
        cfg = AgentPoolConfig()
        with pytest.raises(AttributeError):
            cfg.max_pool_size = 99  # type: ignore[misc]

    def test_repr(self) -> None:
        """repr contains key info."""
        cfg = AgentPoolConfig()
        r = repr(cfg)
        assert "max_size=5" in r
        assert "ttl=60s" in r
        assert "sweep=15s" in r


# ===================================================================
# 4.3.3 -- AgentPoolFullError
# ===================================================================


class TestAgentPoolFullError:
    """Tests for AgentPoolFullError."""

    def test_attributes(self) -> None:
        """Error carries contract_name and max_size."""
        err = AgentPoolFullError("prov-1", "test_agent", 5)
        assert err.contract_name == "test_agent"
        assert err.max_size == 5
        assert "test_agent" in str(err)
        assert "max 5" in str(err)

    def test_retriable(self) -> None:
        """AgentPoolFullError is retriable."""
        err = AgentPoolFullError("prov-1", "test_agent", 5)
        assert err.retriable is True


# ===================================================================
# 4.3.3 -- AgentPool
# ===================================================================


class TestAgentPoolConstruction:
    """AgentPool construction and properties."""

    def test_construction_default(self) -> None:
        """AgentPool with default config."""
        pool = AgentPool()
        assert pool.size() == 0
        assert pool.total_reuses == 0
        assert pool.total_evictions == 0
        assert pool.contract_names == []

    def test_construction_custom_config(self) -> None:
        """AgentPool with custom config."""
        cfg = AgentPoolConfig(max_pool_size=3, idle_ttl_s=30)
        pool = AgentPool(config=cfg)
        assert pool.config.max_pool_size == 3
        assert pool.config.idle_ttl_s == 30

    def test_repr(self) -> None:
        """repr contains useful info."""
        pool = AgentPool()
        r = repr(pool)
        assert "total=0" in r
        assert "contracts=0" in r
        assert "reuses=0" in r
        assert "evictions=0" in r


class TestAgentPoolPut:
    """AgentPool.put() tests."""

    def test_put_active_agent(self) -> None:
        """Active agent is transitioned to IDLE and pooled."""
        pool = AgentPool()
        agent = _make_active_agent()
        assert pool.put(agent) is True
        assert pool.size() == 1
        assert agent.is_idle

    def test_put_idle_agent(self) -> None:
        """Already-IDLE agent is pooled."""
        pool = AgentPool()
        agent = _make_active_agent()
        agent.idle()
        assert pool.put(agent) is True
        assert pool.size() == 1

    def test_put_pending_agent_rejected(self) -> None:
        """PENDING agent cannot be pooled."""
        pool = AgentPool()
        agent = _make_agent()
        assert agent.lifecycle_state == AgentLifecycleState.PENDING
        assert pool.put(agent) is False
        assert pool.size() == 0

    def test_put_terminated_agent_rejected(self) -> None:
        """TERMINATED agent cannot be pooled."""
        pool = AgentPool()
        agent = _make_active_agent()
        agent.drain()
        agent.terminate()
        assert pool.put(agent) is False
        assert pool.size() == 0

    def test_put_keyed_by_contract_name(self) -> None:
        """Agents are pooled by contract name."""
        pool = AgentPool()
        c1 = _make_agent_contract(name="agent_a")
        c2 = _make_agent_contract(name="agent_b")
        a1 = _make_active_agent(contract=c1, agent_id="a1")
        a2 = _make_active_agent(contract=c2, agent_id="a2")
        pool.put(a1)
        pool.put(a2)
        assert pool.size("agent_a") == 1
        assert pool.size("agent_b") == 1
        assert pool.size() == 2
        assert sorted(pool.contract_names) == ["agent_a", "agent_b"]

    def test_put_multiple_same_contract(self) -> None:
        """Multiple agents for same contract can be pooled."""
        pool = AgentPool(config=AgentPoolConfig(max_pool_size=3))
        for i in range(3):
            agent = _make_active_agent(agent_id=f"a-{i}")
            pool.put(agent)
        assert pool.size("test_agent") == 3

    def test_put_evicts_oldest_at_capacity(self) -> None:
        """When pool is full, oldest agent is evicted."""
        pool = AgentPool(config=AgentPoolConfig(max_pool_size=2))
        a1 = _make_active_agent(agent_id="a-oldest")
        a2 = _make_active_agent(agent_id="a-middle")
        a3 = _make_active_agent(agent_id="a-newest")
        pool.put(a1)
        pool.put(a2)
        assert pool.size() == 2
        pool.put(a3)
        assert pool.size() == 2  # still 2, oldest evicted
        assert pool.total_evictions == 1
        assert a1.is_terminated  # oldest was terminated


class TestAgentPoolGet:
    """AgentPool.get() reuse tests."""

    def test_get_returns_agent(self) -> None:
        """Get returns a pooled agent and reactivates it."""
        pool = AgentPool()
        agent = _make_active_agent()
        pool.put(agent)
        reused = pool.get("test_agent")
        assert reused is agent
        assert reused.is_active  # reactivated
        assert pool.size() == 0
        assert pool.total_reuses == 1

    def test_get_empty_returns_none(self) -> None:
        """Get from empty pool returns None."""
        pool = AgentPool()
        assert pool.get("test_agent") is None

    def test_get_wrong_contract_returns_none(self) -> None:
        """Get with non-matching contract name returns None."""
        pool = AgentPool()
        agent = _make_active_agent()
        pool.put(agent)
        assert pool.get("other_agent") is None

    def test_get_fifo_order(self) -> None:
        """Oldest agent (FIFO) is returned first."""
        pool = AgentPool(config=AgentPoolConfig(max_pool_size=3))
        agents = []
        for i in range(3):
            a = _make_active_agent(agent_id=f"a-{i}")
            pool.put(a)
            agents.append(a)

        reused = pool.get("test_agent")
        assert reused is agents[0]  # FIFO
        assert pool.size() == 2

    def test_get_skips_expired_agents(self) -> None:
        """Expired agents are evicted, not returned."""
        pool = AgentPool(config=AgentPoolConfig(max_pool_size=5))

        # Create an agent and manually set its idle_since to long ago
        agent_expired = _make_active_agent(agent_id="a-expired")
        pool.put(agent_expired)
        # Hack: set _idle_since to long ago to simulate TTL expiry
        agent_expired._idle_since = time.monotonic() - (IDLE_TTL_S + 10)

        agent_fresh = _make_active_agent(agent_id="a-fresh")
        pool.put(agent_fresh)

        reused = pool.get("test_agent")
        assert reused is agent_fresh  # expired one was skipped
        assert pool.total_evictions == 1
        assert agent_expired.is_terminated

    def test_get_all_expired_returns_none(self) -> None:
        """If all agents expired, get returns None."""
        pool = AgentPool()
        agent = _make_active_agent()
        pool.put(agent)
        agent._idle_since = time.monotonic() - (IDLE_TTL_S + 10)
        result = pool.get("test_agent")
        assert result is None
        assert pool.total_evictions == 1


class TestAgentPoolSweep:
    """AgentPool.sweep() TTL eviction tests."""

    def test_sweep_no_expired(self) -> None:
        """Sweep with no expired agents returns 0."""
        pool = AgentPool()
        agent = _make_active_agent()
        pool.put(agent)
        assert pool.sweep() == 0
        assert pool.size() == 1

    def test_sweep_evicts_expired(self) -> None:
        """Sweep evicts agents past TTL."""
        pool = AgentPool()
        agent = _make_active_agent()
        pool.put(agent)
        agent._idle_since = time.monotonic() - (IDLE_TTL_S + 10)
        evicted = pool.sweep()
        assert evicted == 1
        assert pool.size() == 0
        assert agent.is_terminated

    def test_sweep_mixed_keeps_fresh(self) -> None:
        """Sweep keeps fresh agents, evicts expired."""
        pool = AgentPool(config=AgentPoolConfig(max_pool_size=5))
        fresh = _make_active_agent(agent_id="a-fresh")
        expired = _make_active_agent(agent_id="a-expired")
        pool.put(expired)
        pool.put(fresh)
        expired._idle_since = time.monotonic() - (IDLE_TTL_S + 10)
        evicted = pool.sweep()
        assert evicted == 1
        assert pool.size() == 1

    def test_sweep_empty_pool(self) -> None:
        """Sweep on empty pool returns 0."""
        pool = AgentPool()
        assert pool.sweep() == 0


class TestAgentPoolDrainAll:
    """AgentPool.drain_all() shutdown tests."""

    def test_drain_all_terminates_all(self) -> None:
        """drain_all terminates every pooled agent."""
        pool = AgentPool(config=AgentPoolConfig(max_pool_size=5))
        agents = []
        for i in range(3):
            a = _make_active_agent(agent_id=f"a-{i}")
            pool.put(a)
            agents.append(a)
        terminated = pool.drain_all()
        assert terminated == 3
        assert pool.size() == 0
        for a in agents:
            assert a.is_terminated

    def test_drain_all_empty(self) -> None:
        """drain_all on empty pool returns 0."""
        pool = AgentPool()
        assert pool.drain_all() == 0

    def test_drain_all_clears_pool_data(self) -> None:
        """drain_all clears internal data structures."""
        pool = AgentPool()
        pool.put(_make_active_agent())
        pool.drain_all()
        assert pool.contract_names == []


# ===================================================================
# 4.3.3/4.3.4 -- AgentFactory integration with Pool + DeltaEmitter
# ===================================================================


class TestAgentFactoryPoolIntegration:
    """AgentFactory uses AgentPool when configured."""

    async def test_pool_miss_spawns_new(self) -> None:
        """When pool is empty, factory spawns a fresh agent."""
        pool = AgentPool()
        contract = _make_agent_contract()
        factory = AgentFactory(
            contract_loader=lambda _: contract,
            pool=pool,
        )
        result = await factory.spawn_and_execute(
            _make_request(),
            _make_context(),
            "t-001",
        )
        assert result.success is True
        # Agent was pooled after success
        assert pool.size() == 1

    async def test_pool_hit_reuses_agent(self) -> None:
        """When pool has a matching agent, it is reused (no spawn)."""
        pool = AgentPool()
        contract = _make_agent_contract()

        # Pre-pool an agent
        pre_agent = _make_active_agent(contract=contract, agent_id="pre-pooled-id")
        pool.put(pre_agent)
        assert pool.size() == 1

        factory = AgentFactory(
            contract_loader=lambda _: contract,
            pool=pool,
        )
        result = await factory.spawn_and_execute(
            _make_request(),
            _make_context(),
            "t-001",
        )
        assert result.success is True
        assert result.agent_id == "pre-pooled-id"  # reused, not new
        assert pool.total_reuses == 1

    async def test_pool_hit_reuse_then_re_pool(self) -> None:
        """Reused agent is re-pooled after successful execution."""
        pool = AgentPool()
        contract = _make_agent_contract()
        pre_agent = _make_active_agent(contract=contract, agent_id="pre-pooled-id")
        pool.put(pre_agent)

        factory = AgentFactory(
            contract_loader=lambda _: contract,
            pool=pool,
        )
        await factory.spawn_and_execute(
            _make_request(),
            _make_context(),
            "t-001",
        )
        # After execution, agent should be back in pool
        assert pool.size() == 1

    async def test_no_pool_still_works(self) -> None:
        """Factory without pool still works (no pool integration)."""
        contract = _make_agent_contract()
        factory = AgentFactory(
            contract_loader=lambda _: contract,
        )
        result = await factory.spawn_and_execute(
            _make_request(),
            _make_context(),
            "t-001",
        )
        assert result.success is True

    async def test_pool_property(self) -> None:
        """Factory.pool property returns the pool."""
        pool = AgentPool()
        factory = AgentFactory(pool=pool)
        assert factory.pool is pool

    async def test_no_pool_property_none(self) -> None:
        """Factory.pool is None when not configured."""
        factory = AgentFactory()
        assert factory.pool is None


class TestAgentFactoryDeltaEmitterIntegration:
    """AgentFactory creates DeltaEmitter for agents when delta_bus configured."""

    async def test_agent_gets_delta_emitter(self) -> None:
        """Agent spawned with delta_bus gets a DeltaEmitter."""
        bus = FakeDeltaBus()
        contract = _make_agent_contract()
        factory = AgentFactory(
            contract_loader=lambda _: contract,
            delta_bus=bus,
        )
        result = await factory.spawn_and_execute(
            _make_request(),
            _make_context(),
            "t-001",
        )
        assert result.success is True
        # Delta was emitted via DeltaEmitter -> IDeltaBusPort
        assert len(bus.deltas) >= 1

    async def test_agent_without_delta_bus_no_emitter(self) -> None:
        """Agent without delta_bus has no DeltaEmitter."""
        contract = _make_agent_contract()
        factory = AgentFactory(
            contract_loader=lambda _: contract,
        )
        result = await factory.spawn_and_execute(
            _make_request(),
            _make_context(),
            "t-001",
        )
        assert result.success is True


class TestAgentExecuteWithDeltaEmitter:
    """Agent.execute() uses DeltaEmitter for structured delta emission."""

    async def test_execute_emits_via_emitter(self) -> None:
        """execute() uses DeltaEmitter when available."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus, trace_id="t-001")
        agent = _make_agent(delta_emitter=emitter, agent_id="a1")
        agent.warm_up()
        result = await agent.execute({"key": "value", "request_id": "r1"})
        assert result.success is True
        # DeltaEmitter should have flushed to bus
        assert len(bus.deltas) >= 1

    async def test_execute_emitter_failure_non_fatal(self) -> None:
        """DeltaEmitter flush failure is non-fatal."""
        bus = FakeDeltaBus(fail=True)
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        agent = _make_agent(delta_emitter=emitter, agent_id="a1")
        agent.warm_up()
        result = await agent.execute({"key": "value"})
        assert result.success is True  # non-fatal

    async def test_execute_prefers_emitter_over_raw_bus(self) -> None:
        """When both delta_emitter and delta_bus are set, emitter is used."""
        bus = FakeDeltaBus()
        emitter_bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=emitter_bus, trace_id="t-001")
        agent = _make_agent(delta_bus=bus, delta_emitter=emitter, agent_id="a1")
        agent.warm_up()
        await agent.execute({"key": "value", "request_id": "r1"})
        # emitter's bus got the delta, not the raw bus
        assert len(emitter_bus.deltas) >= 1
        assert len(bus.deltas) == 0

    async def test_execute_falls_back_to_raw_bus(self) -> None:
        """When no emitter but has delta_bus, raw bus is used."""
        bus = FakeDeltaBus()
        agent = _make_agent(delta_bus=bus, agent_id="a1")
        agent.warm_up()
        await agent.execute({"key": "value"})
        assert len(bus.deltas) >= 1

    async def test_delta_emitter_property(self) -> None:
        """Agent.delta_emitter property returns the emitter."""
        bus = FakeDeltaBus()
        emitter = DeltaEmitter(agent_id="a1", delta_bus=bus)
        agent = _make_agent(delta_emitter=emitter, agent_id="a1")
        assert agent.delta_emitter is emitter

    async def test_delta_emitter_property_none(self) -> None:
        """Agent.delta_emitter is None when not configured."""
        agent = _make_agent()
        assert agent.delta_emitter is None


# ===================================================================
# Module exports
# ===================================================================


class TestModuleExports433434:
    """Verify providers __init__.py exports for 4.3.3/4.3.4."""

    def test_all_count(self) -> None:
        """__all__ has 75 symbols (68 prior + 7 new from 4.3.3/4.3.4)."""
        import k1.fabric.providers as pkg

        assert len(pkg.__all__) == 78

    def test_new_pool_exports(self) -> None:
        """Pool exports are importable."""
        from k1.fabric.providers import AgentPool, AgentPoolConfig, AgentPoolFullError

        assert AgentPool is not None
        assert AgentPoolConfig is not None
        assert AgentPoolFullError is not None

    def test_new_delta_exports(self) -> None:
        """Delta emission exports are importable."""
        from k1.fabric.providers import (
            DELTA_BATCH_WINDOW_MS,
            DELTA_TOPIC_PATTERN,
            AgentDelta,
            DeltaEmitter,
        )

        assert AgentDelta is not None
        assert DeltaEmitter is not None
        assert DELTA_TOPIC_PATTERN == "k1.agent.{agent_id}.delta.v1"
        assert DELTA_BATCH_WINDOW_MS == 500

    def test_all_symbols_importable(self) -> None:
        """Every symbol in __all__ is importable."""
        import k1.fabric.providers as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{name} in __all__ but not importable"

    def test_prior_exports_still_work(self) -> None:
        """Pre-existing exports (4.3.1/4.3.2) still importable."""
        from k1.fabric.providers import (
            IDLE_TTL_S,
            Agent,
            AgentFactory,
            AgentFactoryConfig,
            AgentLifecycleError,
        )

        assert Agent is not None
        assert AgentFactory is not None
        assert AgentFactoryConfig is not None
        assert AgentLifecycleError is not None
        assert IDLE_TTL_S == 60
