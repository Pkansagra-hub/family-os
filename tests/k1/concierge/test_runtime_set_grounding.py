"""M1.5-E4: ConciergeRuntime grounding attachment contract."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k1.concierge.session import ConciergeRuntime


def _runtime() -> ConciergeRuntime:
    return ConciergeRuntime(
        bus=MagicMock(),
        router=MagicMock(),
        front_mailbox=MagicMock(),
        back_mailbox=MagicMock(),
        fsm=MagicMock(),
        model=MagicMock(),
        session_state=MagicMock(),
        front_dispatcher=MagicMock(),
        back_dispatcher=MagicMock(),
        front_subscriptions=[],
    )


def test_runtime_set_grounding_before_start() -> None:
    runtime = _runtime()
    handle = object()

    runtime.set_grounding(handle)

    assert runtime.grounding is handle


def test_runtime_rejects_set_grounding_after_start() -> None:
    runtime = _runtime()
    runtime._started = True

    with pytest.raises(RuntimeError, match="set_grounding"):
        runtime.set_grounding(object())
