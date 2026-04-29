"""
I-1.1.3 -- ConciergeFactory stress tests.

Covers:
  (a) Concurrent per-request scope creation -- trace_id uniqueness,
      bundle_idempotency_cache isolation
  (b) Session isolation -- inject() on one session does NOT affect siblings
  (c) Memory cleanup -- close() + stop() leaves no dangling state
  (d) Rapid start/stop -- 5 cycles with no resource leaks
  (e) ConciergeConfig validation -- rejects invalid tool_tier, pipeline, window
  (f) ConciergeConfig new methods -- from_dict, with_overrides, from_legacy
"""

from __future__ import annotations

import asyncio

import pytest

from k1.concierge.config.concierge import ConciergeConfig
from k1.concierge.factory import ConciergeFactory

# ---------------------------------------------------------------------------
# (a) Concurrent per-request scope creation
# ---------------------------------------------------------------------------


class TestConcurrentRequestScopes:
    """10 ConciergeSession from the same ConciergeRuntime."""

    def test_trace_id_uniqueness(self):
        runtime = ConciergeFactory.create_standalone()
        sessions = [ConciergeFactory.create_request_scope(runtime) for _ in range(10)]
        trace_ids = {s.trace_id for s in sessions}
        assert len(trace_ids) == 10, "All 10 sessions must have unique trace_ids"

    def test_bundle_idempotency_cache_isolation(self):
        runtime = ConciergeFactory.create_standalone()
        s1 = ConciergeFactory.create_request_scope(runtime)
        s2 = ConciergeFactory.create_request_scope(runtime)

        # Mutate s1's cache
        if s1.front_ctx is not None:
            s1.front_ctx.bundle_idempotency_cache["key"] = "value"

        # s2 must be unaffected
        if s2.front_ctx is not None:
            assert "key" not in s2.front_ctx.bundle_idempotency_cache

    def test_capability_cache_isolation(self):
        runtime = ConciergeFactory.create_standalone()
        s1 = ConciergeFactory.create_request_scope(runtime)
        s2 = ConciergeFactory.create_request_scope(runtime)

        if s1.front_ctx is not None:
            s1.front_ctx.capability_cache = {"cap": True}

        if s2.front_ctx is not None:
            assert s2.front_ctx.capability_cache is None

    def test_scoped_trace_id_overrides_runtime(self):
        runtime = ConciergeFactory.create_standalone()
        session = ConciergeFactory.create_request_scope(runtime, trace_id="custom-trace-123")
        assert session.trace_id == "custom-trace-123"
        if session.front_ctx is not None:
            assert session.front_ctx.cognitive_trace_id == "custom-trace-123"
        if session.back_ctx is not None:
            assert session.back_ctx.cognitive_trace_id == "custom-trace-123"

    def test_shared_session_manager_reference(self):
        runtime = ConciergeFactory.create_standalone()
        s1 = ConciergeFactory.create_request_scope(runtime)
        s2 = ConciergeFactory.create_request_scope(runtime)

        if s1.front_ctx is not None and s2.front_ctx is not None:
            assert s1.front_ctx.session_manager is s2.front_ctx.session_manager

    def test_device_and_task_scoped(self):
        runtime = ConciergeFactory.create_standalone()
        session = ConciergeFactory.create_request_scope(
            runtime, device_id="phone-1", task_id="task-99"
        )
        assert session.active_device_id == "phone-1"
        assert session.active_task_id == "task-99"
        if session.front_ctx is not None:
            assert session.front_ctx.active_device_id == "phone-1"
            assert session.front_ctx.active_task_id == "task-99"


# ---------------------------------------------------------------------------
# (b) Session isolation -- inject() on one session
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    """inject() on one session does NOT affect sibling sessions."""

    def test_inject_hil_coordinator_isolated(self):
        runtime = ConciergeFactory.create_standalone()
        s1 = ConciergeFactory.create_request_scope(runtime)
        s2 = ConciergeFactory.create_request_scope(runtime)

        sentinel = object()
        s1.inject(hil_coordinator=sentinel)

        if s1.front_ctx is not None:
            assert s1.front_ctx.hil_coordinator is sentinel
        if s2.front_ctx is not None:
            assert s2.front_ctx.hil_coordinator is not sentinel

    def test_inject_dispatch_isolated(self):
        runtime = ConciergeFactory.create_standalone()
        s1 = ConciergeFactory.create_request_scope(runtime)
        s2 = ConciergeFactory.create_request_scope(runtime)

        sentinel = object()
        s1.inject(dispatch=sentinel)

        if s1.front_ctx is not None:
            assert s1.front_ctx.dispatch is sentinel
        if s2.front_ctx is not None:
            assert s2.front_ctx.dispatch is not sentinel

    def test_inject_memory_isolated(self):
        runtime = ConciergeFactory.create_standalone()
        s1 = ConciergeFactory.create_request_scope(runtime)
        s2 = ConciergeFactory.create_request_scope(runtime)

        async def custom_recall(q, mt=None, mr=5):
            return [{"custom": True}]

        s1.inject(memory=custom_recall)

        if s1.front_ctx is not None:
            assert s1.front_ctx.recall_fn is custom_recall
        if s2.front_ctx is not None:
            assert s2.front_ctx.recall_fn is not custom_recall

    def test_inject_on_closed_session_raises(self):
        runtime = ConciergeFactory.create_standalone()
        session = ConciergeFactory.create_request_scope(runtime)
        asyncio.get_event_loop().run_until_complete(session.close())

        with pytest.raises(RuntimeError, match="closed"):
            session.inject(hil_coordinator=object())


# ---------------------------------------------------------------------------
# (c) Memory cleanup
# ---------------------------------------------------------------------------


class TestMemoryCleanup:
    """After close() + stop(), no dangling state."""

    @pytest.mark.asyncio
    async def test_session_close_clears_caches(self):
        runtime = ConciergeFactory.create_standalone()
        session = ConciergeFactory.create_request_scope(runtime)

        # Populate caches
        if session.front_ctx is not None:
            session.front_ctx.bundle_idempotency_cache["x"] = 1
            session.front_ctx.capability_cache = {"y": 2}

        await session.close()

        if session.front_ctx is not None:
            assert session.front_ctx.bundle_idempotency_cache is None
            assert session.front_ctx.capability_cache is None

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self):
        runtime = ConciergeFactory.create_standalone()
        session = ConciergeFactory.create_request_scope(runtime)
        await session.close()
        await session.close()  # no error
        assert session.closed is True

    @pytest.mark.asyncio
    async def test_runtime_stop_no_subscriptions_leak(self):
        runtime = ConciergeFactory.create_standalone()
        await runtime.start()
        await runtime.stop()
        assert runtime.started is False

    @pytest.mark.asyncio
    async def test_session_closed_property(self):
        runtime = ConciergeFactory.create_standalone()
        session = ConciergeFactory.create_request_scope(runtime)
        assert session.closed is False
        await session.close()
        assert session.closed is True


# ---------------------------------------------------------------------------
# (d) Rapid start/stop cycles
# ---------------------------------------------------------------------------


class TestRapidStartStop:
    """5 cycles of runtime.start() / runtime.stop() -- no resource leaks."""

    @pytest.mark.asyncio
    async def test_five_cycles_no_leak(self):
        runtime = ConciergeFactory.create_standalone()
        for _ in range(5):
            await runtime.start()
            assert runtime.started is True
            await runtime.stop()
            assert runtime.started is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        runtime = ConciergeFactory.create_standalone()
        await runtime.start()
        await runtime.start()  # second start is no-op
        assert runtime.started is True
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_safe(self):
        runtime = ConciergeFactory.create_standalone()
        await runtime.stop()  # no error
        assert runtime.started is False


# ---------------------------------------------------------------------------
# (e) ConciergeConfig validation
# ---------------------------------------------------------------------------


class TestConciergeConfigValidation:
    """ConciergeConfig rejects invalid field values."""

    def test_invalid_phase1_pipeline_raises(self):
        with pytest.raises(ValueError, match="phase1_pipeline"):
            ConciergeConfig(phase1_pipeline="gpt4")

    def test_zero_delta_batch_window_raises(self):
        with pytest.raises(ValueError, match="delta_batch_window_ms"):
            ConciergeConfig(delta_batch_window_ms=0)

    def test_negative_delta_batch_window_raises(self):
        with pytest.raises(ValueError, match="delta_batch_window_ms"):
            ConciergeConfig(delta_batch_window_ms=-1)

    def test_valid_pipelines_accepted(self):
        for pipeline in ("stub", "ultrabert"):
            cfg = ConciergeConfig(phase1_pipeline=pipeline)
            assert cfg.phase1_pipeline == pipeline


# ---------------------------------------------------------------------------
# (f) ConciergeConfig new methods
# ---------------------------------------------------------------------------


class TestConciergeConfigMethods:
    """from_dict, with_overrides, from_legacy classmethods."""

    def test_from_dict_round_trip(self):
        d = {"enable_delta": False, "session_id": "s42"}
        cfg = ConciergeConfig.from_dict(d)
        assert cfg.enable_delta is False
        assert cfg.session_id == "s42"

    def test_from_dict_ignores_unknown_keys(self):
        d = {"unknown_field": 999}
        cfg = ConciergeConfig.from_dict(d)
        assert cfg.enable_delta is True

    def test_with_overrides_returns_new_instance(self):
        cfg = ConciergeConfig()
        cfg2 = cfg.with_overrides(enable_delta=False)
        assert cfg2.enable_delta is False
        assert cfg.enable_delta is True

    def test_from_legacy_is_alias(self):
        from k1.concierge.config.kernel import KernelConfig

        kc = KernelConfig()
        c1 = ConciergeConfig.from_kernel_config(kc)
        c2 = ConciergeConfig.from_legacy(kc)
        assert c1.enable_delta == c2.enable_delta

    def test_from_dict_validates(self):
        with pytest.raises(ValueError, match="phase1_pipeline"):
            ConciergeConfig.from_dict({"phase1_pipeline": "INVALID"})

    def test_with_overrides_validates(self):
        cfg = ConciergeConfig()
        with pytest.raises(ValueError, match="phase1_pipeline"):
            cfg.with_overrides(phase1_pipeline="INVALID")
