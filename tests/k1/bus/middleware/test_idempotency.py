"""
Tests for Phase 6 P6.12 -- IdempotencyMiddleware.
"""

from __future__ import annotations

import time

import pytest

from k1.bus.envelope import Envelope
from k1.bus.middleware.idempotency import IdempotencyMiddleware


def _env(topic: str, request_id: str, envelope_id: int = 1) -> Envelope:
    return Envelope(topic=topic, request_id=request_id, envelope_id=envelope_id, payload=b"{}")


class TestBasicDedup:
    def test_first_envelope_passes(self) -> None:
        mw = IdempotencyMiddleware()
        env = _env("k1.cmd.do.v1", "req-1")
        assert mw.process(env) is env
        assert mw.pass_count == 1
        assert mw.drop_count == 0

    def test_duplicate_request_id_is_dropped(self) -> None:
        mw = IdempotencyMiddleware()
        env1 = _env("k1.cmd.do.v1", "req-1", envelope_id=1)
        env2 = _env("k1.cmd.do.v1", "req-1", envelope_id=2)
        assert mw.process(env1) is env1
        assert mw.process(env2) is None
        assert mw.drop_count == 1
        assert mw.pass_count == 1

    def test_different_request_ids_both_pass(self) -> None:
        mw = IdempotencyMiddleware()
        assert mw.process(_env("k1.cmd.do.v1", "req-1", 1)) is not None
        assert mw.process(_env("k1.cmd.do.v1", "req-2", 2)) is not None
        assert mw.drop_count == 0
        assert mw.pass_count == 2

    def test_same_request_id_different_topics_both_pass(self) -> None:
        mw = IdempotencyMiddleware()
        assert mw.process(_env("k1.cmd.a.v1", "req-1", 1)) is not None
        assert mw.process(_env("k1.cmd.b.v1", "req-1", 2)) is not None
        assert mw.drop_count == 0

    def test_envelopes_without_request_id_bypass_dedup(self) -> None:
        mw = IdempotencyMiddleware()
        env1 = _env("k1.cmd.do.v1", "", 1)
        env2 = _env("k1.cmd.do.v1", "", 2)
        assert mw.process(env1) is env1
        assert mw.process(env2) is env2
        assert mw.no_key_count == 2
        assert mw.drop_count == 0


class TestTTL:
    def test_entry_expires_after_ttl(self) -> None:
        mw = IdempotencyMiddleware(ttl_s=0.05)  # 50ms
        env1 = _env("k1.cmd.do.v1", "req-1", 1)
        assert mw.process(env1) is env1
        time.sleep(0.08)
        env2 = _env("k1.cmd.do.v1", "req-1", 2)
        assert mw.process(env2) is env2  # passes again after TTL
        assert mw.drop_count == 0


class TestBoundedSize:
    def test_max_entries_caps_cache(self) -> None:
        mw = IdempotencyMiddleware(max_entries=3)
        for i in range(10):
            env = _env("k1.cmd.do.v1", f"req-{i}", i + 1)
            assert mw.process(env) is env
        assert mw.cache_size <= 3

    def test_invalid_args_raise(self) -> None:
        with pytest.raises(ValueError):
            IdempotencyMiddleware(max_entries=0)
        with pytest.raises(ValueError):
            IdempotencyMiddleware(ttl_s=0)


class TestThreadSafety:
    def test_concurrent_publish_one_pass_one_drop(self) -> None:
        import threading

        mw = IdempotencyMiddleware()
        results: list[object] = []
        results_lock = threading.Lock()

        def go(envelope: Envelope) -> None:
            r = mw.process(envelope)
            with results_lock:
                results.append(r)

        envs = [_env("k1.cmd.do.v1", "req-1", i + 1) for i in range(20)]
        threads = [threading.Thread(target=go, args=(e,)) for e in envs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        passes = sum(1 for r in results if r is not None)
        drops = sum(1 for r in results if r is None)
        assert passes == 1
        assert drops == 19
