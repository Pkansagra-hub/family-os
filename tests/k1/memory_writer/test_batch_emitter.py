"""Tests for BatchEmitter (E-MW-3.3).

10 tests in 3 classes covering:
  - Emit: calls submit_batch, returns count, empty batch, single envelope
  - Error handling: bridge error, timeout, logging
  - Integration: real envelope dicts, order preservation, offline adapter
"""

from __future__ import annotations

from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from k1.memory_writer.batch.batch_emitter import BatchEmitter

# ===========================================================================
# Helpers
# ===========================================================================


class FakeBridgePort:
    """Fake IBridgeCommandPort that captures submit_batch calls."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._calls: list[list[dict]] = []
        self._raises = raises

    async def submit(self, topic: str, schema_uri: str, body: Dict) -> None:
        pass  # pragma: no cover

    async def submit_batch(self, envelopes: List[Dict]) -> None:
        if self._raises:
            raise self._raises
        self._calls.append(list(envelopes))

    @property
    def calls(self) -> list[list[dict]]:
        return self._calls


def _envelope(text: str = "test", turn: int = 1) -> dict:
    return {
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "body": {
            "text": text,
            "conversation_turn": turn,
            "participants": ["person_mom"],
            "topics": ["dinner"],
        },
        "trace_id": "trace-abc",
    }


# ===========================================================================
# Tests
# ===========================================================================


class TestBatchEmitterEmit:
    """emit() — submit_batch delegation."""

    @pytest.mark.asyncio
    async def test_emit_calls_submit_batch(self) -> None:
        port = FakeBridgePort()
        emitter = BatchEmitter(port)
        batch = [_envelope("a"), _envelope("b"), _envelope("c")]
        await emitter.emit(batch)
        assert len(port.calls) == 1
        assert len(port.calls[0]) == 3

    @pytest.mark.asyncio
    async def test_emit_returns_count(self) -> None:
        port = FakeBridgePort()
        emitter = BatchEmitter(port)
        result = await emitter.emit([_envelope(), _envelope(), _envelope()])
        assert result == 3

    @pytest.mark.asyncio
    async def test_emit_empty_batch_returns_zero(self) -> None:
        port = FakeBridgePort()
        emitter = BatchEmitter(port)
        result = await emitter.emit([])
        assert result == 0
        assert len(port.calls) == 0

    @pytest.mark.asyncio
    async def test_emit_single_envelope(self) -> None:
        port = FakeBridgePort()
        emitter = BatchEmitter(port)
        env = _envelope()
        result = await emitter.emit([env])
        assert result == 1
        assert port.calls[0] == [env]


class TestBatchEmitterErrorHandling:
    """Error handling — bridge errors caught, not propagated."""

    @pytest.mark.asyncio
    async def test_bridge_error_returns_zero(self) -> None:
        port = FakeBridgePort(raises=RuntimeError("connection failed"))
        emitter = BatchEmitter(port)
        result = await emitter.emit([_envelope()])
        assert result == 0

    @pytest.mark.asyncio
    async def test_bridge_timeout_returns_zero(self) -> None:
        port = FakeBridgePort(raises=TimeoutError("timeout"))
        emitter = BatchEmitter(port)
        result = await emitter.emit([_envelope()])
        assert result == 0

    @pytest.mark.asyncio
    async def test_bridge_error_logged(self) -> None:
        port = FakeBridgePort(raises=RuntimeError("oops"))
        emitter = BatchEmitter(port)
        with patch("k1.memory_writer.batch.batch_emitter.log") as mock_log:
            await emitter.emit([_envelope(), _envelope()])
            mock_log.warning.assert_called_once()
            call_args = mock_log.warning.call_args
            assert "submit_batch failed" in call_args[0][0]


class TestBatchEmitterIntegration:
    """Integration — real envelope shapes."""

    @pytest.mark.asyncio
    async def test_emit_with_real_envelope_dicts(self) -> None:
        port = FakeBridgePort()
        emitter = BatchEmitter(port)
        env = {
            "topic": "memory.delta",
            "schema_uri": "schema://memory.delta",
            "body": {
                "text": "dinner with Mom",
                "participants": ["person_mom"],
                "topics": ["dinner"],
                "sentiment_score": 0.5,
            },
            "trace_id": "trace-123",
            "headers": {"cognitive_trace_id": "trace-123", "band": "GREEN"},
        }
        result = await emitter.emit([env])
        assert result == 1
        assert port.calls[0][0]["body"]["sentiment_score"] == 0.5

    @pytest.mark.asyncio
    async def test_emit_preserves_envelope_order(self) -> None:
        port = FakeBridgePort()
        emitter = BatchEmitter(port)
        batch = [_envelope("first", turn=1), _envelope("second", turn=2)]
        await emitter.emit(batch)
        texts = [e["body"]["text"] for e in port.calls[0]]
        assert texts == ["first", "second"]

    @pytest.mark.asyncio
    async def test_mw09_offline_adapter_capability(self) -> None:
        """Adapter with supports_offline=True is accepted."""
        port = FakeBridgePort()
        port.supports_offline = True  # type: ignore[attr-defined]
        emitter = BatchEmitter(port)
        result = await emitter.emit([_envelope()])
        assert result == 1
