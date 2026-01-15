"""Tests for k0.kernel.main - ASGI entrypoint and runtime harness."""

from __future__ import annotations

import signal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import uvicorn

from k0.kernel.config import KernelSettings
from k0.kernel.main import DEFAULT_SIGNALS, build_uvicorn_config, install_signal_handlers, run


class TestDefaultSignals:
    """Tests for DEFAULT_SIGNALS constant."""

    def test_default_signals_contains_sigterm(self) -> None:
        """SIGTERM should be in default signals for container orchestration."""
        assert signal.SIGTERM in DEFAULT_SIGNALS

    def test_default_signals_contains_sigint(self) -> None:
        """SIGINT should be in default signals for Ctrl+C handling."""
        assert signal.SIGINT in DEFAULT_SIGNALS

    def test_default_signals_is_tuple(self) -> None:
        """DEFAULT_SIGNALS should be immutable tuple."""
        assert isinstance(DEFAULT_SIGNALS, tuple)


class TestBuildUvicornConfig:
    """Tests for build_uvicorn_config function."""

    @pytest.fixture
    def mock_settings(self) -> KernelSettings:
        """Create mock kernel settings for testing."""
        return KernelSettings.default()

    def test_build_config_returns_uvicorn_config(self, mock_settings: KernelSettings) -> None:
        """build_uvicorn_config should return uvicorn.Config instance."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert isinstance(config, uvicorn.Config)

    def test_build_config_uses_provided_host(self, mock_settings: KernelSettings) -> None:
        """Config should use the provided host parameter."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="0.0.0.0",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert config.host == "0.0.0.0"

    def test_build_config_uses_provided_port(self, mock_settings: KernelSettings) -> None:
        """Config should use the provided port parameter."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=9000,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert config.port == 9000

    def test_build_config_uses_provided_log_level(self, mock_settings: KernelSettings) -> None:
        """Config should use the provided log_level parameter."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="debug",
            timeout_graceful_shutdown=30.0,
        )
        assert config.log_level == "debug"

    def test_build_config_sets_factory_mode(self, mock_settings: KernelSettings) -> None:
        """Config should use factory mode for app creation."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert config.factory is True

    def test_build_config_enables_lifespan(self, mock_settings: KernelSettings) -> None:
        """Config should enable lifespan for startup/shutdown hooks."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert config.lifespan == "on"

    def test_build_config_disables_server_header(self, mock_settings: KernelSettings) -> None:
        """Config should disable server header for security."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert config.server_header is False

    def test_build_config_disables_date_header(self, mock_settings: KernelSettings) -> None:
        """Config should disable date header for security."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=30.0,
        )
        assert config.date_header is False

    def test_build_config_rounds_graceful_timeout(self, mock_settings: KernelSettings) -> None:
        """Graceful timeout should be rounded to integer."""
        config = build_uvicorn_config(
            settings=mock_settings,
            host="127.0.0.1",
            port=8080,
            log_level="info",
            timeout_graceful_shutdown=15.7,
        )
        assert config.timeout_graceful_shutdown == 16


class TestInstallSignalHandlers:
    """Tests for install_signal_handlers context manager."""

    def test_signal_handlers_installed_on_enter(self) -> None:
        """Signal handlers should be installed when entering context."""
        mock_server = MagicMock(spec=uvicorn.Server)

        original_handlers: dict[int, Any] = {}
        for sig in (signal.SIGTERM, signal.SIGINT):
            original_handlers[sig] = signal.getsignal(sig)

        with install_signal_handlers(mock_server, (signal.SIGTERM, signal.SIGINT)):
            for sig in (signal.SIGTERM, signal.SIGINT):
                current_handler = signal.getsignal(sig)
                assert current_handler != original_handlers[sig]

        # Verify handlers restored after exit
        for sig in (signal.SIGTERM, signal.SIGINT):
            current_handler = signal.getsignal(sig)
            assert current_handler == original_handlers[sig]

    def test_signal_handlers_restored_on_exit(self) -> None:
        """Signal handlers should be restored when exiting context."""
        mock_server = MagicMock(spec=uvicorn.Server)

        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        with install_signal_handlers(mock_server, (signal.SIGTERM, signal.SIGINT)):
            pass  # Just enter and exit

        assert signal.getsignal(signal.SIGTERM) == original_sigterm
        assert signal.getsignal(signal.SIGINT) == original_sigint

    def test_signal_handlers_restored_on_exception(self) -> None:
        """Signal handlers should be restored even if exception occurs."""
        mock_server = MagicMock(spec=uvicorn.Server)

        original_sigterm = signal.getsignal(signal.SIGTERM)

        with pytest.raises(RuntimeError):
            with install_signal_handlers(mock_server, (signal.SIGTERM,)):
                raise RuntimeError("Test exception")

        assert signal.getsignal(signal.SIGTERM) == original_sigterm

    def test_empty_signals_list_works(self) -> None:
        """Context manager should work with empty signals list."""
        mock_server = MagicMock(spec=uvicorn.Server)

        with install_signal_handlers(mock_server, ()):
            pass  # Should not raise


class TestRunFunction:
    """Tests for the run() function."""

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_creates_server_with_config(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should create uvicorn Server with built config."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        settings = KernelSettings.default()
        run(settings=settings)

        mock_server_class.assert_called_once_with(mock_config)
        mock_server.run.assert_called_once()

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_configures_structured_logging(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should configure structured logging."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        settings = KernelSettings.default()
        run(settings=settings)

        mock_configure_logging.assert_called_once()

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_uses_default_settings_when_none(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should use default settings when none provided."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        run()  # No settings provided

        # Verify build_uvicorn_config was called (means settings were created)
        mock_build_config.assert_called_once()

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_overrides_host(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should allow overriding host."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        run(host="0.0.0.0")

        call_kwargs = mock_build_config.call_args[1]
        assert call_kwargs["host"] == "0.0.0.0"

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_overrides_port(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should allow overriding port."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        run(port=9000)

        call_kwargs = mock_build_config.call_args[1]
        assert call_kwargs["port"] == 9000

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_overrides_log_level(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should allow overriding log_level."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        run(log_level="DEBUG")

        call_kwargs = mock_build_config.call_args[1]
        assert call_kwargs["log_level"] == "debug"

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_handles_keyboard_interrupt(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should handle KeyboardInterrupt gracefully."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server.run.side_effect = KeyboardInterrupt()
        mock_server_class.return_value = mock_server

        # Should not raise
        run()

    @patch("k0.kernel.main.uvicorn.Server")
    @patch("k0.kernel.main.configure_structured_logging")
    @patch("k0.kernel.main.build_uvicorn_config")
    def test_run_reraises_other_exceptions(
        self,
        mock_build_config: MagicMock,
        mock_configure_logging: MagicMock,
        mock_server_class: MagicMock,
    ) -> None:
        """run() should reraise non-KeyboardInterrupt exceptions."""
        mock_config = MagicMock()
        mock_build_config.return_value = mock_config
        mock_server = MagicMock()
        mock_server.run.side_effect = RuntimeError("Server error")
        mock_server_class.return_value = mock_server

        with pytest.raises(RuntimeError, match="Server error"):
            run()
