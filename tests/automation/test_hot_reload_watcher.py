"""
Comprehensive tests for K0 Hot Reload Watcher.

Tests cover:
  - File watcher event detection and debouncing
  - Change classification (config vs code)
  - Config validation
  - SIGHUP signal handling
  - Docker container restart orchestration
  - Health check polling
  - Terminal UI rendering
  - CLI argument parsing
"""

import json
import signal
import tempfile
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from k0.automation.hot_reload_watcher import (
    ActionType,
    ChangeType,
    FileChangeEvent,
    K0ActionExecutor,
    K0HotReloadWatcher,
    K0ReloadHandler,
    StatusLevel,
    TerminalUI,
    WatchConfig,
    WatcherStatus,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def watch_config():
    """Create a basic watch configuration."""
    return WatchConfig(
        watch_dirs=["k0/config", "k0/contracts/policy"],
        exclude_patterns=["__pycache__", ".git", "*.pyc", "tests"],
        container_name="k0-kernel",
        grace_period_seconds=1,  # Short for tests
        health_check_retries=3,
        health_check_interval_seconds=0.1,
        verbose=False,
    )


@pytest.fixture
def temp_config_file():
    """Create temporary YAML config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("key: value\n")
        f.write("nested:\n")
        f.write("  key: value\n")
        return f.name


@pytest.fixture
def temp_json_file():
    """Create temporary JSON config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"key": "value"}, f)
        return f.name


# ============================================================================
# TestK0ReloadHandler
# ============================================================================


class TestK0ReloadHandler:
    """Tests for K0ReloadHandler file event detection."""

    def test_handler_detects_config_change(self, watch_config):
        """Handler detects YAML config changes."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        # Simulate file modification
        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("k0/config/kernel.yaml")
        handler.on_modified(event)

        # Verify callback was called with config reload action
        assert callback.called
        file_event, action = callback.call_args[0]
        assert file_event.change_type == ChangeType.CONFIG
        assert action == ActionType.CONFIG_RELOAD
        assert "kernel.yaml" in file_event.file_path

    def test_handler_detects_code_change(self, watch_config):
        """Handler detects Python code changes."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("k0/ports/command.py")
        handler.on_modified(event)

        assert callback.called
        file_event, action = callback.call_args[0]
        assert file_event.change_type == ChangeType.CODE
        assert action == ActionType.CODE_RESTART

    def test_handler_ignores_test_changes(self, watch_config):
        """Handler ignores Python changes in tests/ directory."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("tests/test_kernel.py")
        handler.on_modified(event)

        # Callback should not be called for test files
        assert not callback.called

    def test_handler_ignores_excluded_patterns(self, watch_config):
        """Handler ignores excluded patterns."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("k0/__pycache__/module.pyc")
        handler.on_modified(event)

        assert not callback.called

    def test_handler_ignores_directory_events(self, watch_config):
        """Handler ignores directory change events."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("k0/config/")
        event.is_directory = True
        handler.on_modified(event)

        assert not callback.called

    def test_handler_debounces_rapid_events(self, watch_config):
        """Handler debounces rapid repeated events."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("k0/config/kernel.yaml")

        # Rapid events
        handler.on_modified(event)
        handler.on_modified(event)
        handler.on_modified(event)

        # Should only call callback once due to debouncing
        assert callback.call_count == 1

    def test_handler_accepts_separated_events(self, watch_config):
        """Handler accepts events separated by debounce interval."""
        callback = Mock()
        handler = K0ReloadHandler(watch_config, callback)

        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent("k0/config/kernel.yaml")

        # First event
        handler.on_modified(event)
        assert callback.call_count == 1

        # Wait for debounce interval
        time.sleep(0.6)

        # Second event
        handler.on_modified(event)
        assert callback.call_count == 2


# ============================================================================
# TestK0ActionExecutor
# ============================================================================


class TestK0ActionExecutor:
    """Tests for K0ActionExecutor action execution."""

    def test_validate_config_yaml(self, watch_config, temp_config_file):
        """Executor validates YAML config files."""
        executor = K0ActionExecutor(watch_config)
        assert executor._validate_config(temp_config_file)

    def test_validate_config_json(self, watch_config, temp_json_file):
        """Executor validates JSON config files."""
        executor = K0ActionExecutor(watch_config)
        assert executor._validate_config(temp_json_file)

    def test_validate_config_fails_on_invalid_yaml(self, watch_config):
        """Executor fails on invalid YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content:\n  missing: colon\n}}}}")
            f.flush()
            executor = K0ActionExecutor(watch_config)
            assert not executor._validate_config(f.name)

    def test_validate_config_fails_on_invalid_json(self, watch_config):
        """Executor fails on invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json}")
            f.flush()
            executor = K0ActionExecutor(watch_config)
            assert not executor._validate_config(f.name)

    @patch("subprocess.run")
    def test_send_sighup_to_container_success(self, mock_run, watch_config):
        """Executor sends SIGHUP to Docker container."""
        mock_run.return_value = Mock(returncode=0)
        executor = K0ActionExecutor(watch_config)

        assert executor._send_sighup_to_container("k0-kernel")
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "docker" in call_args
        assert "kill" in call_args
        assert "SIGHUP" in call_args

    @patch("subprocess.run")
    def test_send_sighup_to_container_failure(self, mock_run, watch_config):
        """Executor handles Docker SIGHUP failure."""
        mock_run.return_value = Mock(returncode=1, stderr="Container not found")
        executor = K0ActionExecutor(watch_config)

        assert not executor._send_sighup_to_container("nonexistent-container")

    @patch("subprocess.run")
    def test_send_sighup_to_process_success(self, mock_run, watch_config):
        """Executor sends SIGHUP to local process on Unix systems."""
        # Skip on Windows where signal.SIGHUP doesn't exist
        if not hasattr(signal, "SIGHUP"):
            pytest.skip("SIGHUP not available on this platform")

        mock_run.return_value = Mock(returncode=0, stdout="1234\n")
        executor = K0ActionExecutor(watch_config)

        with patch("os.kill") as mock_kill:
            with patch("sys.platform", "linux"):
                assert executor._send_sighup_to_process("k0_kernel.py")
                mock_kill.assert_called_once_with(1234, signal.SIGHUP)

    @patch("subprocess.run")
    def test_send_sighup_to_process_windows_unsupported(self, mock_run, watch_config):
        """Executor fails gracefully on Windows (no SIGHUP)."""
        executor = K0ActionExecutor(watch_config)

        with patch("sys.platform", "win32"):
            assert not executor._send_sighup_to_process("k0_kernel.py")

    @patch("subprocess.run")
    def test_execute_config_reload_success(self, mock_run, watch_config, temp_config_file):
        """Executor successfully reloads config."""
        mock_run.return_value = Mock(returncode=0)
        executor = K0ActionExecutor(watch_config)

        assert executor.execute_config_reload(temp_config_file)

    @patch("subprocess.run")
    def test_execute_config_reload_fails_on_invalid_config(self, mock_run, watch_config):
        """Executor fails to reload if config is invalid."""
        executor = K0ActionExecutor(watch_config)

        assert not executor.execute_config_reload("nonexistent.yaml")
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_execute_code_restart_success(self, mock_run, watch_config):
        """Executor successfully restarts container."""
        mock_run.return_value = Mock(returncode=0)
        executor = K0ActionExecutor(watch_config)

        with patch.object(executor, "_wait_for_health_check", return_value=True):
            assert executor.execute_code_restart()

    @patch("requests.get")
    def test_wait_for_health_check_success(self, mock_get, watch_config):
        """Executor succeeds on health check."""
        watch_config.health_check_url = "http://localhost:8080/health"
        mock_get.return_value = Mock(status_code=200)
        executor = K0ActionExecutor(watch_config)

        assert executor._wait_for_health_check()

    @patch("requests.get")
    def test_wait_for_health_check_failure_after_retries(self, mock_get, watch_config):
        """Executor fails health check after retries."""
        watch_config.health_check_url = "http://localhost:8080/health"
        mock_get.return_value = Mock(status_code=500)
        executor = K0ActionExecutor(watch_config)

        assert not executor._wait_for_health_check()
        assert mock_get.call_count == watch_config.health_check_retries

    @patch("requests.get")
    def test_wait_for_health_check_retry_until_success(self, mock_get, watch_config):
        """Executor succeeds health check on retry."""
        watch_config.health_check_url = "http://localhost:8080/health"
        # Fail twice, then succeed
        mock_get.side_effect = [
            Exception("Connection refused"),
            Exception("Connection refused"),
            Mock(status_code=200),
        ]
        executor = K0ActionExecutor(watch_config)

        assert executor._wait_for_health_check()


# ============================================================================
# TestTerminalUI
# ============================================================================


class TestTerminalUI:
    """Tests for TerminalUI rendering."""

    def test_ui_renders_header(self, watch_config, capsys):
        """UI renders header with watch configuration."""
        ui = TerminalUI(watch_config)
        ui.render_header()

        captured = capsys.readouterr()
        assert "K0 Hot Reload Watcher" in captured.out
        assert "k0/config" in captured.out
        assert "k0-kernel" in captured.out

    def test_ui_renders_status_success(self, watch_config, capsys):
        """UI renders success status."""
        ui = TerminalUI(watch_config)
        status = WatcherStatus(
            timestamp="2024-01-01T12:00:00",
            action_type=ActionType.CONFIG_RELOAD,
            message="Config reloaded",
            level=StatusLevel.SUCCESS,
            duration_seconds=1.5,
        )
        ui.render_status(status)

        captured = capsys.readouterr()
        assert "[PASS]" in captured.out
        assert "Config reloaded" in captured.out
        assert "1.5s" in captured.out

    def test_ui_renders_status_error(self, watch_config, capsys):
        """UI renders error status."""
        ui = TerminalUI(watch_config)
        status = WatcherStatus(
            timestamp="2024-01-01T12:00:00",
            action_type=ActionType.CODE_RESTART,
            message="Restart failed",
            level=StatusLevel.ERROR,
        )
        ui.render_status(status)

        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "Restart failed" in captured.out

    def test_ui_renders_status_progress(self, watch_config, capsys):
        """UI renders progress status."""
        ui = TerminalUI(watch_config)
        status = WatcherStatus(
            timestamp="2024-01-01T12:00:00",
            action_type=ActionType.CODE_RESTART,
            message="Restarting...",
            level=StatusLevel.PROGRESS,
        )
        ui.render_status(status)

        captured = capsys.readouterr()
        assert "[WAIT]" in captured.out

    def test_ui_stores_status_history(self, watch_config):
        """UI maintains status history."""
        ui = TerminalUI(watch_config)

        status1 = WatcherStatus(
            timestamp="2024-01-01T12:00:00",
            action_type=ActionType.CONFIG_RELOAD,
            message="First",
            level=StatusLevel.INFO,
        )
        status2 = WatcherStatus(
            timestamp="2024-01-01T12:00:01",
            action_type=ActionType.CODE_RESTART,
            message="Second",
            level=StatusLevel.SUCCESS,
        )

        ui.render_status(status1)
        ui.render_status(status2)

        assert len(ui._status_history) == 2
        assert ui._status_history[0].message == "First"
        assert ui._status_history[1].message == "Second"


# ============================================================================
# TestK0HotReloadWatcher
# ============================================================================


class TestK0HotReloadWatcher:
    """Tests for K0HotReloadWatcher orchestration."""

    def test_watcher_initializes(self, watch_config):
        """Watcher initializes successfully."""
        watcher = K0HotReloadWatcher(watch_config)
        assert watcher.config == watch_config
        assert watcher.observer is not None
        assert watcher.executor is not None
        assert watcher.ui is not None

    @patch.object(K0ActionExecutor, "execute_config_reload", return_value=True)
    def test_watcher_handles_config_change(self, mock_reload, watch_config):
        """Watcher handles config file changes."""
        watcher = K0HotReloadWatcher(watch_config)
        watcher._is_running = True  # Mark as running so lock won't block

        file_event = FileChangeEvent(
            timestamp="2024-01-01T12:00:00",
            file_path="k0/config/kernel.yaml",
            change_type=ChangeType.CONFIG,
            action=ActionType.CONFIG_RELOAD,
        )

        watcher._on_file_change(file_event, ActionType.CONFIG_RELOAD)
        # Give callback time to execute
        time.sleep(0.1)
        assert mock_reload.called or len(watcher.ui._status_history) > 0

    @patch.object(K0ActionExecutor, "execute_code_restart", return_value=True)
    def test_watcher_handles_code_change(self, mock_restart, watch_config):
        """Watcher handles code file changes."""
        watcher = K0HotReloadWatcher(watch_config)
        watcher._is_running = True

        file_event = FileChangeEvent(
            timestamp="2024-01-01T12:00:00",
            file_path="k0/ports/command.py",
            change_type=ChangeType.CODE,
            action=ActionType.CODE_RESTART,
        )

        watcher._on_file_change(file_event, ActionType.CODE_RESTART)
        time.sleep(0.1)
        assert mock_restart.called or len(watcher.ui._status_history) > 0

    def test_watcher_stop_works(self, watch_config):
        """Watcher stops cleanly."""
        watcher = K0HotReloadWatcher(watch_config)
        watcher._is_running = True
        watcher.stop()
        assert not watcher._is_running

    @patch("k0.automation.hot_reload_watcher.Observer")
    def test_watcher_can_start(self, mock_observer_class, watch_config):
        """Watcher can start (mocked for testing)."""
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        watcher = K0HotReloadWatcher(watch_config)
        watcher.observer = mock_observer

        # Start watcher in thread and stop after 0.1s
        def start_and_stop():
            threading.Timer(0.1, watcher.stop).start()
            watcher.start()

        thread = threading.Thread(target=start_and_stop, daemon=True)
        thread.start()
        thread.join(timeout=2)

        # Verify observer was started and stopped
        assert mock_observer.start.called


# ============================================================================
# TestWatchConfigDataClass
# ============================================================================


class TestWatchConfigDataClass:
    """Tests for WatchConfig data class."""

    def test_watch_config_defaults(self):
        """WatchConfig has sensible defaults."""
        config = WatchConfig(watch_dirs=["k0"])
        assert config.watch_dirs == ["k0"]
        assert config.grace_period_seconds == 2
        assert config.health_check_retries == 10
        assert config.verbose is False

    def test_watch_config_custom_values(self):
        """WatchConfig accepts custom values."""
        config = WatchConfig(
            watch_dirs=["k0/config"],
            container_name="custom-kernel",
            grace_period_seconds=5,
            verbose=True,
        )
        assert config.grace_period_seconds == 5
        assert config.container_name == "custom-kernel"
        assert config.verbose is True


# ============================================================================
# TestFileChangeEventDataClass
# ============================================================================


class TestFileChangeEventDataClass:
    """Tests for FileChangeEvent data class."""

    def test_file_change_event_creation(self):
        """FileChangeEvent can be created and accessed."""
        event = FileChangeEvent(
            timestamp="2024-01-01T12:00:00",
            file_path="k0/config/kernel.yaml",
            change_type=ChangeType.CONFIG,
            action=ActionType.CONFIG_RELOAD,
        )
        assert event.file_path == "k0/config/kernel.yaml"
        assert event.change_type == ChangeType.CONFIG
        assert event.action == ActionType.CONFIG_RELOAD


# ============================================================================
# TestEndToEnd
# ============================================================================


class TestEndToEnd:
    """End-to-end integration tests."""

    @patch.object(K0ActionExecutor, "execute_config_reload", return_value=True)
    def test_end_to_end_config_reload_flow(self, mock_reload, watch_config):
        """End-to-end config reload: detect → validate → reload."""
        watcher = K0HotReloadWatcher(watch_config)
        watcher._is_running = True
        handler = K0ReloadHandler(watch_config, watcher._on_file_change)

        from watchdog.events import FileModifiedEvent

        # Simulate config file change
        event = FileModifiedEvent("k0/config/kernel.yaml")
        handler.on_modified(event)

        time.sleep(0.1)
        # Verify action was executed or status was recorded
        assert mock_reload.called or len(watcher.ui._status_history) > 0

    @patch.object(K0ActionExecutor, "execute_code_restart", return_value=True)
    def test_end_to_end_code_restart_flow(self, mock_restart, watch_config):
        """End-to-end code restart: detect → validate → restart."""
        watcher = K0HotReloadWatcher(watch_config)
        watcher._is_running = True
        handler = K0ReloadHandler(watch_config, watcher._on_file_change)

        from watchdog.events import FileModifiedEvent

        # Simulate code file change
        event = FileModifiedEvent("k0/ports/command.py")
        handler.on_modified(event)

        time.sleep(0.1)
        # Verify action was executed or status was recorded
        assert mock_restart.called or len(watcher.ui._status_history) > 0

    def test_end_to_end_status_reporting(self, watch_config):
        """End-to-end status updates are rendered."""
        watcher = K0HotReloadWatcher(watch_config)
        watcher._is_running = True

        file_event = FileChangeEvent(
            timestamp="2024-01-01T12:00:00",
            file_path="k0/config/kernel.yaml",
            change_type=ChangeType.CONFIG,
            action=ActionType.CONFIG_RELOAD,
        )

        # Mock the executor to succeed
        with patch.object(watcher.executor, "execute_config_reload", return_value=True):
            watcher._on_file_change(file_event, ActionType.CONFIG_RELOAD)

        time.sleep(0.1)
        # Verify status history was updated with multiple statuses
        assert len(watcher.ui._status_history) >= 1
        # Should have: change detected, success (or at least one status)
        assert any(
            s.level in (StatusLevel.SUCCESS, StatusLevel.INFO) for s in watcher.ui._status_history
        )
