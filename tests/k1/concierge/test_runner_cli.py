"""
tests.k1.concierge.test_runner_cli
E-0.5.24 I-0.5.24.3: Runner CLI test.

Validates:
    1. _parse_args() argument parsing: --test-mode, --unordered, --session-mode,
       --tool-tier, --log-level defaults and explicit values.
    2. KernelConfig construction from parsed args.
    3. Signal handler registration (SIGINT/SIGTERM).
    4. _run() invokes start_kernel then stop_kernel.
"""

from __future__ import annotations

import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.concierge.kernel.runner import _parse_args

# =========================================================================
# 1. Argument parsing: defaults
# =========================================================================


class TestParseArgsDefaults:
    """_parse_args() returns correct defaults when no args provided."""

    def test_default_test_mode(self) -> None:
        with patch("sys.argv", ["runner"]):
            args = _parse_args()
        assert args.test_mode is False

    def test_default_unordered(self) -> None:
        with patch("sys.argv", ["runner"]):
            args = _parse_args()
        assert args.unordered is False

    def test_default_session_mode(self) -> None:
        with patch("sys.argv", ["runner"]):
            args = _parse_args()
        assert args.session_mode == "standalone"

    def test_default_tool_tier(self) -> None:
        with patch("sys.argv", ["runner"]):
            args = _parse_args()
        assert args.tool_tier == "LOW"

    def test_default_log_level(self) -> None:
        with patch("sys.argv", ["runner"]):
            args = _parse_args()
        assert args.log_level == "INFO"


# =========================================================================
# 2. Argument parsing: explicit values
# =========================================================================


class TestParseArgsExplicit:
    """_parse_args() correctly parses explicit CLI arguments."""

    def test_test_mode_flag(self) -> None:
        with patch("sys.argv", ["runner", "--test-mode"]):
            args = _parse_args()
        assert args.test_mode is True

    def test_unordered_flag(self) -> None:
        with patch("sys.argv", ["runner", "--unordered"]):
            args = _parse_args()
        assert args.unordered is True

    def test_session_mode_testing(self) -> None:
        with patch("sys.argv", ["runner", "--session-mode", "testing"]):
            args = _parse_args()
        assert args.session_mode == "testing"

    def test_tool_tier_high(self) -> None:
        with patch("sys.argv", ["runner", "--tool-tier", "HIGH"]):
            args = _parse_args()
        assert args.tool_tier == "HIGH"

    def test_tool_tier_crisis_rejected(self) -> None:
        """CRISIS is no longer a valid tier (P4.5)."""
        with patch("sys.argv", ["runner", "--tool-tier", "CRISIS"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_log_level_debug(self) -> None:
        with patch("sys.argv", ["runner", "--log-level", "DEBUG"]):
            args = _parse_args()
        assert args.log_level == "DEBUG"

    def test_all_flags_combined(self) -> None:
        with patch(
            "sys.argv",
            [
                "runner",
                "--test-mode",
                "--unordered",
                "--session-mode",
                "testing",
                "--tool-tier",
                "MEDIUM",
                "--log-level",
                "WARNING",
            ],
        ):
            args = _parse_args()
        assert args.test_mode is True
        assert args.unordered is True
        assert args.session_mode == "testing"
        assert args.tool_tier == "MEDIUM"
        assert args.log_level == "WARNING"


# =========================================================================
# 3. Invalid arguments rejected
# =========================================================================


class TestParseArgsInvalid:
    """Invalid CLI arguments are rejected by argparse."""

    def test_invalid_session_mode(self) -> None:
        with patch("sys.argv", ["runner", "--session-mode", "invalid"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_invalid_tool_tier(self) -> None:
        with patch("sys.argv", ["runner", "--tool-tier", "NONE"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_invalid_log_level(self) -> None:
        with patch("sys.argv", ["runner", "--log-level", "TRACE"]):
            with pytest.raises(SystemExit):
                _parse_args()


# =========================================================================
# 4. Config construction from args
# =========================================================================


class TestConfigFromArgs:
    """KernelConfig is correctly built from parsed args in _run()."""

    def test_config_from_defaults(self) -> None:
        with patch("sys.argv", ["runner"]):
            args = _parse_args()
        cfg = KernelConfig(
            ordered_bus=not args.unordered,
            test_mode=args.test_mode,
            session_mode=args.session_mode,
            tool_tier=args.tool_tier,
        )
        assert cfg.ordered_bus is True
        assert cfg.test_mode is False
        assert cfg.session_mode == "standalone"
        assert cfg.tool_tier == "LOW"

    def test_config_from_explicit_args(self) -> None:
        with patch(
            "sys.argv",
            [
                "runner",
                "--test-mode",
                "--unordered",
                "--session-mode",
                "testing",
                "--tool-tier",
                "HIGH",
            ],
        ):
            args = _parse_args()
        cfg = KernelConfig(
            ordered_bus=not args.unordered,
            test_mode=args.test_mode,
            session_mode=args.session_mode,
            tool_tier=args.tool_tier,
        )
        assert cfg.ordered_bus is False
        assert cfg.test_mode is True
        assert cfg.session_mode == "testing"
        assert cfg.tool_tier == "HIGH"


# =========================================================================
# 5. _run() lifecycle: start_kernel → wait → stop_kernel
# =========================================================================


class TestRunLifecycle:
    """_run() calls start_kernel, waits for stop_event, then stop_kernel."""

    async def test_run_calls_start_and_stop(self) -> None:
        mock_runtime = MagicMock()
        mock_runtime.started = True

        mock_start = AsyncMock(return_value=mock_runtime)
        mock_stop = AsyncMock()

        with (
            patch("sys.argv", ["runner", "--test-mode"]),
            patch("k1.kernel.runner.start_kernel", mock_start),
            patch("k1.kernel.runner.stop_kernel", mock_stop),
            patch("asyncio.Event") as mock_event_cls,
        ):
            # Make stop_event.wait() return immediately
            mock_event = MagicMock()
            mock_event.wait = AsyncMock()
            mock_event_cls.return_value = mock_event

            from k1.concierge.kernel.runner import _run

            await _run()

            mock_start.assert_called_once()
            mock_stop.assert_called_once_with(mock_runtime)

    async def test_run_passes_test_mode_config(self) -> None:
        mock_runtime = MagicMock()
        mock_start = AsyncMock(return_value=mock_runtime)
        mock_stop = AsyncMock()

        with (
            patch("sys.argv", ["runner", "--test-mode", "--tool-tier", "HIGH"]),
            patch("k1.kernel.runner.start_kernel", mock_start),
            patch("k1.kernel.runner.stop_kernel", mock_stop),
            patch("asyncio.Event") as mock_event_cls,
        ):
            mock_event = MagicMock()
            mock_event.wait = AsyncMock()
            mock_event_cls.return_value = mock_event

            from k1.concierge.kernel.runner import _run

            await _run()

            call_args = mock_start.call_args
            cfg = call_args[0][0] if call_args[0] else call_args[1].get("config") or call_args[0][0]
            assert isinstance(cfg, KernelConfig)
            assert cfg.test_mode is True
            assert cfg.tool_tier == "HIGH"


# =========================================================================
# 6. Signal handling: SIGINT / SIGTERM registered
# =========================================================================


class TestSignalHandling:
    """_run() registers signal handlers for graceful shutdown."""

    async def test_signal_handlers_registered(self) -> None:
        mock_runtime = MagicMock()
        mock_start = AsyncMock(return_value=mock_runtime)
        mock_stop = AsyncMock()

        registered_signals: list[int] = []

        def capture_signal(sig: int, handler: object) -> None:
            registered_signals.append(sig)

        with (
            patch("sys.argv", ["runner", "--test-mode"]),
            patch("k1.kernel.runner.start_kernel", mock_start),
            patch("k1.kernel.runner.stop_kernel", mock_stop),
            patch("signal.signal", side_effect=capture_signal),
            patch("asyncio.Event") as mock_event_cls,
        ):
            mock_event = MagicMock()
            mock_event.wait = AsyncMock()
            mock_event_cls.return_value = mock_event

            from k1.concierge.kernel.runner import _run

            await _run()

            assert signal.SIGINT in registered_signals
            assert signal.SIGTERM in registered_signals
