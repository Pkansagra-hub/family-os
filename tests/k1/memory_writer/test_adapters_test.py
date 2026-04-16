"""Tests for Test Adapters (E-MW-5.2).

Covers all 5 fake port implementations:
  - FakeSessionReadPort: configurable sections, fail_on
  - FakeModelHubPort: canned responses, call capture, fail modes
  - FakeBridgeCommandPort: submission capture, batch capture, fail
  - FakeEventSubscriptionPort: subscribe/publish/unsubscribe dispatch
  - FakeHealthPort: configurable health state

20 tests organized in 5 test classes.
"""

from __future__ import annotations

import pytest

from k1.memory_writer.adapters.test_adapters import (
    FakeBridgeCommandPort,
    FakeEventSubscriptionPort,
    FakeHealthPort,
    FakeModelHubPort,
    FakeSessionReadPort,
)
from k1.memory_writer.types import ChatResponse, HealthStatus, Subscription

# ---------------------------------------------------------------------------
# FakeSessionReadPort
# ---------------------------------------------------------------------------


class TestFakeSessionReadPort:
    """Tests for FakeSessionReadPort."""

    @pytest.mark.asyncio
    async def test_snapshot_returns_configured_sections(self) -> None:
        """3 sections -> all returned."""
        port = FakeSessionReadPort(
            sections={
                "beliefs_active": {"data": 1},
                "persona": {"data": 2},
                "history": {"data": 3},
            }
        )
        result = await port.snapshot(["beliefs_active", "persona", "history"])
        assert len(result) == 3
        assert result["beliefs_active"] == {"data": 1}
        assert result["persona"] == {"data": 2}
        assert result["history"] == {"data": 3}

    @pytest.mark.asyncio
    async def test_read_section_missing_returns_none(self) -> None:
        """unknown section -> None."""
        port = FakeSessionReadPort(sections={"known": {"x": 1}})
        result = await port.read_section("unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_fail_on_raises(self) -> None:
        """fail_on={"plan"} -> read_section("plan") raises."""
        port = FakeSessionReadPort(
            sections={"plan": {"x": 1}},
            fail_on={"plan"},
        )
        with pytest.raises(RuntimeError, match="configured failure for plan"):
            await port.read_section("plan")

    @pytest.mark.asyncio
    async def test_empty_snapshot(self) -> None:
        """no sections configured -> empty dict."""
        port = FakeSessionReadPort()
        result = await port.snapshot(["any", "thing"])
        assert result == {}


# ---------------------------------------------------------------------------
# FakeModelHubPort
# ---------------------------------------------------------------------------


class TestFakeModelHubPort:
    """Tests for FakeModelHubPort."""

    @pytest.mark.asyncio
    async def test_chat_returns_canned_response(self) -> None:
        """response_content='[{"fact": "test"}]' -> ChatResponse.content matches."""
        port = FakeModelHubPort(response_content='[{"fact": "test"}]')
        resp = await port.chat([{"role": "user", "content": "hi"}], 2000, "cheapest")
        assert isinstance(resp, ChatResponse)
        assert resp.content == '[{"fact": "test"}]'

    @pytest.mark.asyncio
    async def test_chat_captures_calls(self) -> None:
        """2 calls -> .calls has 2 entries with messages/budget/hint."""
        port = FakeModelHubPort()
        await port.chat([{"role": "user", "content": "a"}], 1000, "fast")
        await port.chat([{"role": "user", "content": "b"}], 2000, "cheap")
        assert len(port.calls) == 2
        assert port.calls[0]["budget_tokens"] == 1000
        assert port.calls[1]["model_hint"] == "cheap"

    @pytest.mark.asyncio
    async def test_fail_raises(self) -> None:
        """fail=True -> chat raises RuntimeError."""
        port = FakeModelHubPort(fail=True)
        with pytest.raises(RuntimeError, match="configured LLM failure"):
            await port.chat([], 2000, "cheapest")

    @pytest.mark.asyncio
    async def test_fail_count_temporary(self) -> None:
        """fail_count=2 -> first 2 calls fail, 3rd succeeds."""
        port = FakeModelHubPort(fail_count=2)
        with pytest.raises(RuntimeError):
            await port.chat([], 2000, "x")
        with pytest.raises(RuntimeError):
            await port.chat([], 2000, "x")
        resp = await port.chat([], 2000, "x")
        assert isinstance(resp, ChatResponse)


# ---------------------------------------------------------------------------
# FakeBridgeCommandPort
# ---------------------------------------------------------------------------


class TestFakeBridgeCommandPort:
    """Tests for FakeBridgeCommandPort."""

    @pytest.mark.asyncio
    async def test_submit_captures(self) -> None:
        """submit(topic, schema, body) -> .submitted has 1 entry."""
        port = FakeBridgeCommandPort()
        await port.submit("memory.write", "schema://mem", {"key": "val"})
        assert len(port.submitted) == 1
        assert port.submitted[0]["topic"] == "memory.write"
        assert port.submitted[0]["body"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_submit_batch_captures(self) -> None:
        """submit_batch([3 envs]) -> .batches has 1, .submitted has 3."""
        port = FakeBridgeCommandPort()
        envs = [{"topic": f"t{i}"} for i in range(3)]
        await port.submit_batch(envs)
        assert len(port.batches) == 1
        assert len(port.submitted) == 3

    @pytest.mark.asyncio
    async def test_fail_raises(self) -> None:
        """fail=True -> submit raises RuntimeError."""
        port = FakeBridgeCommandPort(fail=True)
        with pytest.raises(RuntimeError, match="configured failure"):
            await port.submit("t", "s", {})

    @pytest.mark.asyncio
    async def test_empty_batch_ok(self) -> None:
        """submit_batch([]) -> no error."""
        port = FakeBridgeCommandPort()
        await port.submit_batch([])
        assert len(port.batches) == 1
        assert port.batches[0] == []


# ---------------------------------------------------------------------------
# FakeEventSubscriptionPort
# ---------------------------------------------------------------------------


class TestFakeEventSubscriptionPort:
    """Tests for FakeEventSubscriptionPort."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription(self) -> None:
        """subscribe -> Subscription with id and topic."""

        async def handler(payload: dict) -> None:
            pass

        port = FakeEventSubscriptionPort()
        sub = await port.subscribe("turn.complete.v1", handler)
        assert isinstance(sub, Subscription)
        assert sub.topic == "turn.complete.v1"
        assert sub.subscription_id  # non-empty

    @pytest.mark.asyncio
    async def test_publish_dispatches_to_handler(self) -> None:
        """subscribe + publish -> handler called with payload."""
        received: list = []

        async def handler(payload: dict) -> None:
            received.append(payload)

        port = FakeEventSubscriptionPort()
        await port.subscribe("my.topic", handler)
        await port.publish("my.topic", {"data": 42})

        assert len(received) == 1
        assert received[0] == {"data": 42}

    @pytest.mark.asyncio
    async def test_publish_captures(self) -> None:
        """publish -> .published has (topic, payload)."""
        port = FakeEventSubscriptionPort()
        await port.publish("topic.x", {"val": 1})
        assert len(port.published) == 1
        assert port.published[0] == ("topic.x", {"val": 1})

    @pytest.mark.asyncio
    async def test_unsubscribe_removes(self) -> None:
        """unsubscribe -> subscription removed from internal tracking."""

        async def handler(payload: dict) -> None:
            pass

        port = FakeEventSubscriptionPort()
        sub = await port.subscribe("t", handler)
        assert sub.subscription_id in port._subscriptions
        await port.unsubscribe(sub.subscription_id)
        assert sub.subscription_id not in port._subscriptions

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_topic(self) -> None:
        """2 handlers on same topic -> both called."""
        received_a: list = []
        received_b: list = []

        async def handler_a(payload: dict) -> None:
            received_a.append(payload)

        async def handler_b(payload: dict) -> None:
            received_b.append(payload)

        port = FakeEventSubscriptionPort()
        await port.subscribe("shared", handler_a)
        await port.subscribe("shared", handler_b)
        await port.publish("shared", {"x": 1})

        assert len(received_a) == 1
        assert len(received_b) == 1


# ---------------------------------------------------------------------------
# FakeHealthPort
# ---------------------------------------------------------------------------


class TestFakeHealthPort:
    """Tests for FakeHealthPort."""

    @pytest.mark.asyncio
    async def test_is_ready_default_true(self) -> None:
        """default construction -> is_ready returns True."""
        port = FakeHealthPort()
        assert await port.is_ready() is True

    @pytest.mark.asyncio
    async def test_health_check_default_healthy(self) -> None:
        """default -> is_healthy=True."""
        port = FakeHealthPort()
        status = await port.health_check()
        assert isinstance(status, HealthStatus)
        assert status.is_healthy is True

    @pytest.mark.asyncio
    async def test_configurable_circuit_open(self) -> None:
        """circuit_open=True -> llm_circuit_open=True."""
        port = FakeHealthPort(circuit_open=True)
        status = await port.health_check()
        assert status.llm_circuit_open is True
