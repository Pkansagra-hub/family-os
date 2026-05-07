"""Tests for HIL-local ports (E1.M1.7)."""

from __future__ import annotations

from k1.hil.ports import IEventPort, ILLMPort


def test_event_port_runtime_check_accepts_full_stub() -> None:
    class _Stub:
        async def publish(self, topic, payload):  # type: ignore[no-untyped-def]
            ...

        def subscribe(self, topic, handler):  # type: ignore[no-untyped-def]
            ...

        def unsubscribe(self, handle):  # type: ignore[no-untyped-def]
            ...

    assert isinstance(_Stub(), IEventPort)


def test_event_port_rejects_missing_subscribe() -> None:
    class _Bad:
        async def publish(self, topic, payload):  # type: ignore[no-untyped-def]
            ...

        def unsubscribe(self, handle):  # type: ignore[no-untyped-def]
            ...

    assert not isinstance(_Bad(), IEventPort)


def test_llm_port_runtime_check_accepts_stub() -> None:
    class _Stub:
        async def synthesize_question(self, *, context, max_tokens=300, trace_id=None):  # type: ignore[no-untyped-def]
            return "q?"

    assert isinstance(_Stub(), ILLMPort)


def test_llm_port_rejects_missing_method() -> None:
    class _Bad:
        async def something_else(self):  # type: ignore[no-untyped-def]
            ...

    assert not isinstance(_Bad(), ILLMPort)
