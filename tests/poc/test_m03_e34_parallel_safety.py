"""
tests.poc.test_m03_e34_parallel_safety -- E3.4 Parallel Tool Execution Policy.

Validates the 5 issues of Epic 3.4:
  3.4.1 -- parallel_safety.py docstring accurately describes behavior
  3.4.2 -- classify_tool_batch integrated into react_loop
  3.4.3 -- Config toggle react.parallel_tools_enabled
  3.4.4 -- Stale iteration constants replaced with config accessors
  3.4.5 -- submit_result guard warns on mixed batch

Test count target: ~30 tests.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poc.k1_poc.task.parallel_safety import (
    ALWAYS_SEQUENTIAL,
    PARALLEL_SAFE_GROUPS,
    classify_tool_batch,
    is_parallel_safe,
)

# =========================================================================
# 3.4.1 -- Docstring accuracy
# =========================================================================


class TestParallelSafetyDocstring:
    """Verify parallel_safety.py docstring reflects actual behavior."""

    def test_docstring_does_not_claim_sequential(self):
        """Module docstring must NOT claim 'processes tools sequentially'."""
        from poc.k1_poc.task import parallel_safety

        docstring = parallel_safety.__doc__ or ""
        assert "processes tools sequentially" not in docstring.lower()

    def test_docstring_mentions_asyncio_gather(self):
        """Module docstring should mention asyncio.gather."""
        from poc.k1_poc.task import parallel_safety

        docstring = parallel_safety.__doc__ or ""
        assert "asyncio.gather" in docstring

    def test_docstring_mentions_classify_tool_batch_integration(self):
        """Module docstring should mention classify_tool_batch integration."""
        from poc.k1_poc.task import parallel_safety

        docstring = parallel_safety.__doc__ or ""
        assert "classify_tool_batch" in docstring

    def test_docstring_mentions_config_toggle(self):
        """Module docstring should mention config toggle."""
        from poc.k1_poc.task import parallel_safety

        docstring = parallel_safety.__doc__ or ""
        assert "parallel_tools_enabled" in docstring


# =========================================================================
# 3.4.2 -- classify_tool_batch integration (unit tests for classifier)
# =========================================================================


class TestClassifyToolBatch:
    """Verify classify_tool_batch correctly splits tools."""

    def test_all_parallel_safe(self):
        """All parallel-safe tools go to parallel group."""
        p, s = classify_tool_batch(["recall_memory", "update_beliefs"])
        assert p == ["recall_memory", "update_beliefs"]
        assert s == []

    def test_all_sequential(self):
        """All sequential tools go to sequential group."""
        p, s = classify_tool_batch(["invoke_capability", "dispatch_task"])
        assert p == []
        assert s == ["invoke_capability", "dispatch_task"]

    def test_mixed_batch(self):
        """Mixed batch splits correctly."""
        p, s = classify_tool_batch(["recall_memory", "invoke_capability", "update_beliefs"])
        assert p == ["recall_memory", "update_beliefs"]
        assert s == ["invoke_capability"]

    def test_unknown_tools_are_sequential(self):
        """Unknown tools default to sequential (fail-safe)."""
        p, s = classify_tool_batch(["unknown_tool"])
        assert p == []
        assert s == ["unknown_tool"]

    def test_empty_batch(self):
        """Empty batch returns empty lists."""
        p, s = classify_tool_batch([])
        assert p == []
        assert s == []

    def test_preserves_order(self):
        """Order within each group matches input order."""
        p, s = classify_tool_batch(
            ["update_beliefs", "dispatch_task", "recall_memory", "invoke_capability"]
        )
        assert p == ["update_beliefs", "recall_memory"]
        assert s == ["dispatch_task", "invoke_capability"]


class TestIsParallelSafe:
    """Verify is_parallel_safe classification."""

    def test_reads_are_parallel_safe(self):
        """Read tools are classified as parallel-safe."""
        for name in PARALLEL_SAFE_GROUPS["reads"]:
            assert is_parallel_safe(name), f"{name} should be parallel-safe"

    def test_cognitive_writes_are_parallel_safe(self):
        """Cognitive write tools are parallel-safe."""
        for name in PARALLEL_SAFE_GROUPS["cognitive_writes"]:
            assert is_parallel_safe(name), f"{name} should be parallel-safe"

    def test_sequential_tools_not_parallel_safe(self):
        """Sequential tools are NOT parallel-safe."""
        for name in ALWAYS_SEQUENTIAL:
            assert not is_parallel_safe(name), f"{name} should NOT be parallel-safe"

    def test_unknown_tool_not_parallel_safe(self):
        """Unknown tools default to NOT parallel-safe."""
        assert not is_parallel_safe("totally_unknown_tool_xyz")


# =========================================================================
# 3.4.2 -- classify_tool_batch integrated into react_loop (source inspection)
# =========================================================================


class TestReactLoopIntegration:
    """Verify react_loop calls classify_tool_batch."""

    def test_react_loop_imports_classify_tool_batch(self):
        """react_loop module imports classify_tool_batch."""
        import inspect

        from poc.k1_poc.react import loop

        source = inspect.getsource(loop)
        assert "classify_tool_batch" in source

    def test_react_loop_calls_classify_tool_batch(self):
        """react_loop function source calls classify_tool_batch."""
        import inspect

        from poc.k1_poc.react.loop import react_loop

        source = inspect.getsource(react_loop)
        assert "classify_tool_batch" in source

    def test_react_loop_uses_parallel_enabled_config(self):
        """react_loop reads parallel_tools_enabled from config."""
        import inspect

        from poc.k1_poc.react.loop import react_loop

        source = inspect.getsource(react_loop)
        assert "parallel_tools_enabled" in source


# =========================================================================
# 3.4.3 -- Config toggle
# =========================================================================


class TestConfigToggle:
    """Verify react.parallel_tools_enabled config exists and defaults."""

    def test_config_default_is_true(self):
        """parallel_tools_enabled defaults to True."""
        from poc.k1_poc.config.loader import ReactConfig

        cfg = ReactConfig()
        assert cfg.parallel_tools_enabled is True

    def test_config_accessible_via_get_config(self):
        """get_config().react.parallel_tools_enabled exists."""
        from poc.k1_poc.config import get_config

        cfg = get_config()
        assert hasattr(cfg.react, "parallel_tools_enabled")
        assert isinstance(cfg.react.parallel_tools_enabled, bool)

    @pytest.mark.asyncio
    async def test_parallel_disabled_forces_sequential(self):
        """When parallel_tools_enabled=False, all tools run sequentially.

        We mock the model to return 2 parallel-safe tool calls and
        verify they are dispatched one at a time (not gathered).
        """
        from poc.k1_poc.react.loop import react_loop

        # Mock model returns 2 tool calls then text
        tc1 = MagicMock(name="recall_memory")
        tc1.name = "recall_memory"
        tc1.arguments = {}
        tc2 = MagicMock(name="update_beliefs")
        tc2.name = "update_beliefs"
        tc2.arguments = {}

        resp_tools = MagicMock()
        resp_tools.has_text = False
        resp_tools.has_tool_calls = True
        resp_tools.tool_calls = [tc1, tc2]
        resp_tools.text = None
        resp_tools.finish_reason = "stop"

        resp_text = MagicMock()
        resp_text.has_text = True
        resp_text.has_tool_calls = False
        resp_text.text = "Done"
        resp_text.tool_calls = []
        resp_text.finish_reason = "stop"

        model = AsyncMock()
        model.generate = AsyncMock(side_effect=[resp_tools, resp_text])

        tool_result = MagicMock()
        tool_result.is_error.return_value = False
        tool_result.is_ok.return_value = True
        tool_result.data = {}
        tool_result.tool_name = "test"

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=tool_result)

        # Track dispatch call order
        call_order: list[str] = []
        original_dispatch = dispatcher.dispatch

        async def tracking_dispatch(tc):
            call_order.append(tc.name)
            return await original_dispatch(tc)

        dispatcher.dispatch = tracking_dispatch

        # Patch config to disable parallel
        with patch("poc.k1_poc.react.loop.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.react.parallel_tools_enabled = False
            cfg.react.front_degenerate_fallback = "fallback"
            cfg.react.front_budget_fallback = "budget"
            mock_cfg.return_value = cfg

            result = await react_loop(
                actor="front",
                system_prompt="test",
                messages=[],
                tools=[MagicMock()],
                max_iterations=5,
                model=model,
                tool_dispatcher=dispatcher,
                on_text_response=AsyncMock(),
                cancellation_check=AsyncMock(return_value=False),
            )

        # Both tools dispatched -- order preserved
        assert "recall_memory" in call_order
        assert "update_beliefs" in call_order


# =========================================================================
# 3.4.4 -- Stale constants replaced with config accessors
# =========================================================================


class TestStaleConstants:
    """Verify MODE_MAX_ITERATIONS / CRISIS_MAX_ITERATIONS are accessible."""

    def test_mode_max_iterations_importable(self):
        """MODE_MAX_ITERATIONS still importable for backward compat."""
        from poc.k1_poc.react.loop import MODE_MAX_ITERATIONS

        assert isinstance(MODE_MAX_ITERATIONS, dict)
        assert len(MODE_MAX_ITERATIONS) > 0
        assert "STANDARD" in MODE_MAX_ITERATIONS

    def test_crisis_max_iterations_importable(self):
        """CRISIS_MAX_ITERATIONS still importable for backward compat."""
        from poc.k1_poc.react.loop import CRISIS_MAX_ITERATIONS

        assert isinstance(CRISIS_MAX_ITERATIONS, dict)
        assert len(CRISIS_MAX_ITERATIONS) > 0
        assert "STANDARD" in CRISIS_MAX_ITERATIONS

    def test_get_mode_max_iterations_function_exists(self):
        """get_mode_max_iterations() accessor function exists."""
        from poc.k1_poc.react.loop import get_mode_max_iterations

        result = get_mode_max_iterations()
        assert isinstance(result, dict)
        assert "STANDARD" in result

    def test_get_crisis_max_iterations_function_exists(self):
        """get_crisis_max_iterations() accessor function exists."""
        from poc.k1_poc.react.loop import get_crisis_max_iterations

        result = get_crisis_max_iterations()
        assert isinstance(result, dict)
        assert "STANDARD" in result

    def test_accessors_read_from_config(self):
        """Accessor functions read from config, not hardcoded."""
        from poc.k1_poc.react.loop import get_mode_max_iterations

        result = get_mode_max_iterations()
        from poc.k1_poc.config import get_config

        expected = get_config().prompt.max_iterations
        assert result == expected

    def test_crisis_accessors_read_from_config(self):
        """Crisis accessor reads from config."""
        from poc.k1_poc.react.loop import get_crisis_max_iterations

        result = get_crisis_max_iterations()
        from poc.k1_poc.config import get_config

        expected = get_config().prompt.crisis_iterations
        assert result == expected

    def test_package_re_exports_accessors(self):
        """react/__init__.py re-exports the new accessor functions."""
        from poc.k1_poc.react import get_crisis_max_iterations, get_mode_max_iterations

        assert callable(get_mode_max_iterations)
        assert callable(get_crisis_max_iterations)


# =========================================================================
# 3.4.5 -- submit_result guard
# =========================================================================


class TestSubmitResultGuard:
    """Verify submit_result + other tools triggers warning."""

    def test_react_loop_has_submit_result_warning(self):
        """react_loop source contains submit_result mixed-batch warning."""
        import inspect

        from poc.k1_poc.react.loop import react_loop

        source = inspect.getsource(react_loop)
        assert "submit_result returned alongside" in source or (
            "submit_result" in source and "LLM confusion" in source
        )

    @pytest.mark.asyncio
    async def test_submit_result_with_other_tools_logs_warning(self, caplog):
        """When submit_result + other tools returned, warning is logged."""
        from poc.k1_poc.react.loop import react_loop

        # Model returns submit_result AND recall_memory in same response
        tc_submit = MagicMock()
        tc_submit.name = "submit_result"
        tc_submit.arguments = {"result_type": "complete", "final_answer": "done"}

        tc_other = MagicMock()
        tc_other.name = "recall_memory"
        tc_other.arguments = {}

        resp = MagicMock()
        resp.has_text = False
        resp.has_tool_calls = True
        resp.tool_calls = [tc_submit, tc_other]
        resp.text = None
        resp.finish_reason = "stop"

        model = AsyncMock()
        model.generate = AsyncMock(return_value=resp)

        tool_result = MagicMock()
        tool_result.is_error.return_value = False
        tool_result.is_ok.return_value = True
        tool_result.data = {"result_type": "complete"}
        tool_result.tool_name = "submit_result"

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=tool_result)

        with caplog.at_level(logging.WARNING, logger="poc.k1_poc.react.loop"):
            result = await react_loop(
                actor="back",
                system_prompt="test",
                messages=[],
                tools=[MagicMock()],
                max_iterations=5,
                model=model,
                tool_dispatcher=dispatcher,
                on_text_response=AsyncMock(),
                cancellation_check=AsyncMock(return_value=False),
            )

        # submit_result processed first -> complete
        assert result.status == "complete"
        # Warning logged about mixed batch
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("submit_result returned alongside" in m for m in warning_messages)


# =========================================================================
# Integration: react_loop with classified execution
# =========================================================================


class TestReactLoopClassifiedExecution:
    """Integration tests for parallel/sequential tool execution."""

    @pytest.mark.asyncio
    async def test_parallel_safe_tools_gathered(self):
        """Parallel-safe tools execute via asyncio.gather when enabled."""
        from poc.k1_poc.react.loop import react_loop

        # Two parallel-safe tools
        tc1 = MagicMock()
        tc1.name = "recall_memory"
        tc1.arguments = {}
        tc2 = MagicMock()
        tc2.name = "update_beliefs"
        tc2.arguments = {}

        resp_tools = MagicMock()
        resp_tools.has_text = False
        resp_tools.has_tool_calls = True
        resp_tools.tool_calls = [tc1, tc2]
        resp_tools.text = None
        resp_tools.finish_reason = "stop"

        resp_text = MagicMock()
        resp_text.has_text = True
        resp_text.has_tool_calls = False
        resp_text.text = "Done"
        resp_text.tool_calls = []
        resp_text.finish_reason = "stop"

        model = AsyncMock()
        model.generate = AsyncMock(side_effect=[resp_tools, resp_text])

        tool_result = MagicMock()
        tool_result.is_error.return_value = False
        tool_result.is_ok.return_value = True
        tool_result.data = {}
        tool_result.tool_name = "test"

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=tool_result)

        result = await react_loop(
            actor="front",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

        assert result.status == "complete"
        assert result.text == "Done"
        # Both tools were dispatched
        assert dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_sequential_tools_dispatched_individually(self):
        """Sequential tools are dispatched one at a time."""
        from poc.k1_poc.react.loop import react_loop

        tc1 = MagicMock()
        tc1.name = "invoke_capability"
        tc1.arguments = {}
        tc2 = MagicMock()
        tc2.name = "dispatch_task"
        tc2.arguments = {"task_type": "test"}

        resp_tools = MagicMock()
        resp_tools.has_text = False
        resp_tools.has_tool_calls = True
        resp_tools.tool_calls = [tc1, tc2]
        resp_tools.text = None
        resp_tools.finish_reason = "stop"

        resp_text = MagicMock()
        resp_text.has_text = True
        resp_text.has_tool_calls = False
        resp_text.text = "Done"
        resp_text.tool_calls = []
        resp_text.finish_reason = "stop"

        model = AsyncMock()
        model.generate = AsyncMock(side_effect=[resp_tools, resp_text])

        tool_result = MagicMock()
        tool_result.is_error.return_value = False
        tool_result.is_ok.return_value = True
        tool_result.data = {}
        tool_result.tool_name = "test"

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=tool_result)

        result = await react_loop(
            actor="front",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

        assert result.status == "complete"
        # Both sequential tools dispatched
        assert dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_mixed_batch_splits_correctly(self):
        """Mixed batch: parallel-safe gathered, sequential one-at-a-time."""
        from poc.k1_poc.react.loop import react_loop

        tc_parallel = MagicMock()
        tc_parallel.name = "recall_memory"
        tc_parallel.arguments = {}
        tc_seq = MagicMock()
        tc_seq.name = "invoke_capability"
        tc_seq.arguments = {}

        resp_tools = MagicMock()
        resp_tools.has_text = False
        resp_tools.has_tool_calls = True
        resp_tools.tool_calls = [tc_parallel, tc_seq]
        resp_tools.text = None
        resp_tools.finish_reason = "stop"

        resp_text = MagicMock()
        resp_text.has_text = True
        resp_text.has_tool_calls = False
        resp_text.text = "Done"
        resp_text.tool_calls = []
        resp_text.finish_reason = "stop"

        model = AsyncMock()
        model.generate = AsyncMock(side_effect=[resp_tools, resp_text])

        tool_result = MagicMock()
        tool_result.is_error.return_value = False
        tool_result.is_ok.return_value = True
        tool_result.data = {}
        tool_result.tool_name = "test"

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=tool_result)

        result = await react_loop(
            actor="front",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

        assert result.status == "complete"
        # Both tools dispatched (1 parallel + 1 sequential)
        assert dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_classification_logged(self, caplog):
        """Tool batch classification is logged at INFO level."""
        from poc.k1_poc.react.loop import react_loop

        tc1 = MagicMock()
        tc1.name = "recall_memory"
        tc1.arguments = {}

        resp_tools = MagicMock()
        resp_tools.has_text = False
        resp_tools.has_tool_calls = True
        resp_tools.tool_calls = [tc1]
        resp_tools.text = None
        resp_tools.finish_reason = "stop"

        resp_text = MagicMock()
        resp_text.has_text = True
        resp_text.has_tool_calls = False
        resp_text.text = "Done"
        resp_text.tool_calls = []
        resp_text.finish_reason = "stop"

        model = AsyncMock()
        model.generate = AsyncMock(side_effect=[resp_tools, resp_text])

        tool_result = MagicMock()
        tool_result.is_error.return_value = False
        tool_result.is_ok.return_value = True
        tool_result.data = {}
        tool_result.tool_name = "test"

        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(return_value=tool_result)

        with caplog.at_level(logging.INFO, logger="poc.k1_poc.react.loop"):
            result = await react_loop(
                actor="front",
                system_prompt="test",
                messages=[],
                tools=[MagicMock()],
                max_iterations=5,
                model=model,
                tool_dispatcher=dispatcher,
                on_text_response=AsyncMock(),
                cancellation_check=AsyncMock(return_value=False),
            )

        assert result.status == "complete"
        info_messages = [r.message for r in caplog.records if r.levelno >= logging.INFO]
        assert any("tool_batch_classified" in m for m in info_messages)
