#!/usr/bin/env python3
"""
Hot Reload Watcher for K0 Kernel

Monitors filesystem changes and triggers graceful config reloads or orchestrated
restarts to minimize developer iteration time.

Features:
  - Config hot-reload (YAML changes trigger SIGHUP, no downtime)
  - Code restart (Python changes trigger orchestrated restart with health check)
  - Cross-platform support (Windows PowerShell, POSIX shells, Docker, local)
  - Terminal UI with real-time status updates
  - Configurable watch paths and exclusions

Usage:
  python -m k0.automation.hot_reload_watcher \
    --watch-dirs k0/config k0/contracts/policy \
    --container-name k0-kernel \
    --verbose

  # Local process mode:
  python -m k0.automation.hot_reload_watcher \
    --watch-dirs k0/ \
    --process-name k0_kernel.py \
    --health-check-url http://localhost:8080/health
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

# ============================================================================
# Configuration & Enums
# ============================================================================


class ChangeType(Enum):
    """Type of file system change detected."""

    CONFIG = "config"
    CODE = "code"


class ActionType(Enum):
    """Type of action to take."""

    CONFIG_RELOAD = "config_reload"
    CODE_RESTART = "code_restart"


class StatusLevel(Enum):
    """Terminal UI status levels."""

    INFO = "INFO"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    WARNING = "WARNING"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class WatchConfig:
    """Configuration for file watcher."""

    watch_dirs: List[str]
    exclude_patterns: List[str] = field(
        default_factory=lambda: ["__pycache__", ".git", "*.pyc", "tests"]
    )
    container_name: Optional[str] = None  # Docker container (if None, uses process_name)
    process_name: Optional[str] = None  # Local process name (if None, uses container_name)
    health_check_url: Optional[str] = None  # Health check URL for restart validation
    grace_period_seconds: int = 2  # Seconds to wait for graceful shutdown
    restart_timeout_seconds: int = 60  # Max time to wait for restart
    health_check_retries: int = 10  # Number of health check attempts
    health_check_interval_seconds: float = 0.5  # Delay between health checks
    verbose: bool = False


@dataclass
class FileChangeEvent:
    """File change event."""

    timestamp: str
    file_path: str
    change_type: ChangeType
    action: ActionType


@dataclass
class WatcherStatus:
    """Current watcher status."""

    timestamp: str
    action_type: ActionType
    message: str
    level: StatusLevel
    duration_seconds: Optional[float] = None


# ============================================================================
# File Change Detection
# ============================================================================


class K0ReloadHandler(FileSystemEventHandler):
    """
    Handles file system events and determines appropriate actions.
    """

    def __init__(
        self, config: WatchConfig, callback: Callable[[FileChangeEvent, ActionType], None]
    ):
        """
        Args:
            config: Watch configuration
            callback: Function to call when action is needed (event, action_type)
        """
        super().__init__()
        self.config = config
        self.callback = callback
        self.logger = logging.getLogger(__name__)
        self._last_events: Dict[str, float] = {}  # Debounce rapid events
        self._debounce_interval = 0.5  # seconds

    def on_modified(self, event: FileModifiedEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        # Debounce rapid repeated events from same file
        now = time.time()
        last_event_time = self._last_events.get(event.src_path, 0)
        if now - last_event_time < self._debounce_interval:
            return
        self._last_events[event.src_path] = now

        # Skip excluded patterns
        if self._should_exclude(event.src_path):
            return

        # Determine change type and action
        change_type, action = self._classify_change(event.src_path)
        if change_type is None or action is None:
            return

        self.logger.debug(f"Change detected: {event.src_path} ({change_type.value})")

        # Create event and invoke callback
        file_event = FileChangeEvent(
            timestamp=datetime.now().isoformat(),
            file_path=event.src_path,
            change_type=change_type,
            action=action,
        )
        self.callback(file_event, action)

    def _should_exclude(self, file_path: str) -> bool:
        """Check if file should be excluded from watching."""
        path_lower = file_path.lower()
        for pattern in self.config.exclude_patterns:
            if pattern in path_lower or path_lower.endswith(pattern):
                return True
        return False

    def _classify_change(self, file_path: str) -> tuple[Optional[ChangeType], Optional[ActionType]]:
        """Classify file change and determine action."""
        if file_path.endswith((".yaml", ".yml", ".json")):
            # Config changes
            if "config" in file_path or "contracts/policy" in file_path:
                return ChangeType.CONFIG, ActionType.CONFIG_RELOAD
        elif file_path.endswith(".py"):
            # Code changes (but not tests)
            if "tests" not in file_path:
                return ChangeType.CODE, ActionType.CODE_RESTART

        return None, None


# ============================================================================
# Action Execution
# ============================================================================


class K0ActionExecutor:
    """Executes actions (config reload, code restart) on detected changes."""

    def __init__(self, config: WatchConfig):
        """
        Args:
            config: Watch configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

    def execute_config_reload(self, file_path: str) -> bool:
        """
        Execute graceful config reload via SIGHUP.

        Args:
            file_path: Path to changed config file

        Returns:
            True if reload successful, False otherwise
        """
        self.logger.info(f"Executing config reload for {file_path}")

        # Validate config before reload
        if not self._validate_config(file_path):
            self.logger.error(f"Config validation failed: {file_path}")
            return False

        # Send SIGHUP to process
        if self.config.container_name:
            return self._send_sighup_to_container(self.config.container_name)
        elif self.config.process_name:
            return self._send_sighup_to_process(self.config.process_name)
        else:
            self.logger.error("No container_name or process_name configured")
            return False

    def execute_code_restart(self) -> bool:
        """
        Execute orchestrated code restart with health check.

        Returns:
            True if restart successful, False otherwise
        """
        self.logger.info("Executing orchestrated code restart")

        if self.config.container_name:
            return self._restart_container(self.config.container_name)
        elif self.config.process_name:
            return self._restart_process(self.config.process_name)
        else:
            self.logger.error("No container_name or process_name configured")
            return False

    def _validate_config(self, file_path: str) -> bool:
        """Validate YAML/JSON config file before reload."""
        try:
            if file_path.endswith((".yaml", ".yml")):
                import yaml

                with open(file_path) as f:
                    yaml.safe_load(f)
            elif file_path.endswith(".json"):
                with open(file_path) as f:
                    json.load(f)
            return True
        except Exception as e:
            self.logger.error(f"Config validation error: {e}")
            return False

    def _send_sighup_to_container(self, container_name: str) -> bool:
        """Send SIGHUP signal to Docker container process."""
        try:
            result = subprocess.run(
                ["docker", "kill", "--signal", "SIGHUP", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self.logger.info(f"SIGHUP sent to container {container_name}")
                return True
            else:
                self.logger.error(f"Failed to send SIGHUP: {result.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Error sending SIGHUP: {e}")
            return False

    def _send_sighup_to_process(self, process_name: str) -> bool:
        """Send SIGHUP signal to local process."""
        try:
            # SIGHUP is Unix-only; on Windows, return False
            if sys.platform == "win32":
                self.logger.warning(
                    "SIGHUP signal not available on Windows; requires Unix-like system"
                )
                return False

            # Find process by name
            result = subprocess.run(
                ["pgrep", "-f", process_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                self.logger.warning(f"Process {process_name} not found")
                return False

            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid:
                    os.kill(int(pid), signal.SIGHUP)
                    self.logger.info(f"SIGHUP sent to process {pid}")

            return True
        except Exception as e:
            self.logger.error(f"Error sending SIGHUP to process: {e}")
            return False

    def _restart_container(self, container_name: str) -> bool:
        """Restart Docker container with health check."""
        try:
            # Step 1: Drain requests (grace period)
            self.logger.info(
                f"Draining requests ({self.config.grace_period_seconds}s grace period)..."
            )
            time.sleep(self.config.grace_period_seconds)

            # Step 2: Restart container
            self.logger.info("Restarting container...")
            result = subprocess.run(
                ["docker", "restart", container_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                self.logger.error(f"Failed to restart container: {result.stderr}")
                return False

            # Step 3: Wait for health check
            if self.config.health_check_url:
                return self._wait_for_health_check()
            else:
                # Wait for container to be running
                time.sleep(2)
                return True

        except Exception as e:
            self.logger.error(f"Error restarting container: {e}")
            return False

    def _restart_process(self, process_name: str) -> bool:
        """Restart local process with health check."""
        try:
            # Step 1: Drain requests
            self.logger.info(
                f"Draining requests ({self.config.grace_period_seconds}s grace period)..."
            )
            time.sleep(self.config.grace_period_seconds)

            # Step 2: Kill process gracefully
            self.logger.info("Stopping process...")
            subprocess.run(
                ["pkill", "-f", process_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Wait for process to stop
            time.sleep(1)

            # Step 3: Restart process (assuming it's managed by supervisor or similar)
            # This is a simplified example; actual implementation depends on process manager
            self.logger.warning(
                "Process restart requires external process manager (supervisor, systemd, etc.)"
            )
            return False

        except Exception as e:
            self.logger.error(f"Error restarting process: {e}")
            return False

    def _wait_for_health_check(self) -> bool:
        """Poll health check endpoint until ready."""
        import requests

        for attempt in range(self.config.health_check_retries):
            try:
                response = requests.get(
                    self.config.health_check_url,
                    timeout=2,
                )
                if response.status_code == 200:
                    self.logger.info(f"Health check passed (attempt {attempt + 1})")
                    return True
            except Exception as e:
                self.logger.debug(f"Health check attempt {attempt + 1} failed: {e}")

            time.sleep(self.config.health_check_interval_seconds)

        self.logger.error("Health check failed after all retries")
        return False


# ============================================================================
# Terminal UI
# ============================================================================


class TerminalUI:
    """Renders real-time status updates to terminal."""

    def __init__(self, config: WatchConfig):
        """
        Args:
            config: Watch configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._status_history: List[WatcherStatus] = []

    def render_header(self) -> None:
        """Render header showing watch configuration."""
        watch_paths = ", ".join(self.config.watch_dirs)
        container_info = self.config.container_name or f"process:{self.config.process_name}"

        print("\n" + "=" * 80)
        print("K0 Hot Reload Watcher")
        print("=" * 80)
        print(f"Watching: {watch_paths}")
        print(f"Target: {container_info}")
        if self.config.health_check_url:
            print(f"Health Check: {self.config.health_check_url}")
        print("-" * 80)
        print("Press Ctrl+C to stop watching.\n")

    def render_status(self, status: WatcherStatus) -> None:
        """
        Render status update with timestamp and message.

        Args:
            status: Status to render
        """
        self._status_history.append(status)

        # Format status indicator
        if status.level == StatusLevel.SUCCESS:
            indicator = "[PASS]"
        elif status.level == StatusLevel.ERROR:
            indicator = "[FAIL]"
        elif status.level == StatusLevel.WARNING:
            indicator = "[WARN]"
        elif status.level == StatusLevel.PROGRESS:
            indicator = "[WAIT]"
        else:
            indicator = "[INFO]"

        # Format time
        timestamp = datetime.fromisoformat(status.timestamp).strftime("%H:%M:%S")

        # Format duration
        duration_str = ""
        if status.duration_seconds is not None:
            duration_str = f" ({status.duration_seconds:.1f}s)"

        # Print status line
        print(f"[{timestamp}] {indicator} {status.message}{duration_str}")

        # Log to file
        if self.config.verbose:
            self.logger.info(f"{status.level.value}: {status.message}")


# ============================================================================
# Watcher Orchestrator
# ============================================================================


class K0HotReloadWatcher:
    """
    Main orchestrator for hot reload watching.

    Coordinates file watching, change detection, action execution, and UI updates.
    """

    def __init__(self, config: WatchConfig):
        """
        Args:
            config: Watch configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._setup_logging()

        self.observer = Observer()
        self.executor = K0ActionExecutor(config)
        self.ui = TerminalUI(config)
        self._is_running = False
        self._lock = threading.Lock()

    def _setup_logging(self) -> None:
        """Configure logging."""
        log_level = logging.DEBUG if self.config.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("k0_hot_reload.log"),
                logging.StreamHandler() if self.config.verbose else logging.NullHandler(),
            ],
        )

    def start(self) -> None:
        """Start the file watcher."""
        try:
            self._is_running = True

            # Display header
            self.ui.render_header()

            # Register event handler and start observer
            handler = K0ReloadHandler(self.config, self._on_file_change)
            for watch_dir in self.config.watch_dirs:
                watch_path = Path(watch_dir)
                if not watch_path.exists():
                    self.logger.warning(f"Watch directory does not exist: {watch_dir}")
                    continue

                self.observer.schedule(handler, str(watch_path), recursive=True)
                self.logger.info(f"Watching: {watch_dir}")

            # Start observer
            self.observer.start()

            # Display ready status
            status = WatcherStatus(
                timestamp=datetime.now().isoformat(),
                action_type=ActionType.CONFIG_RELOAD,
                message="Watcher started and ready",
                level=StatusLevel.SUCCESS,
            )
            self.ui.render_status(status)

            # Keep running until interrupted
            while self._is_running:
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
            print("\nShutting down...")
        except Exception as e:
            self.logger.error(f"Error in watcher: {e}", exc_info=True)
            raise
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the file watcher."""
        with self._lock:
            self._is_running = False

        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)

        self.logger.info("Watcher stopped")
        print("\nWatcher stopped.")

    def _on_file_change(self, file_event: FileChangeEvent, action: ActionType) -> None:
        """
        Handle detected file change.

        Args:
            file_event: The file change event
            action: The action to take
        """
        with self._lock:
            if not self._is_running:
                return

        start_time = time.time()

        try:
            # Display change detected
            status = WatcherStatus(
                timestamp=datetime.now().isoformat(),
                action_type=action,
                message=f"{file_event.change_type.value.title()} change detected: {Path(file_event.file_path).name}",
                level=StatusLevel.INFO,
            )
            self.ui.render_status(status)

            # Display validation/preparation
            if action == ActionType.CONFIG_RELOAD:
                status = WatcherStatus(
                    timestamp=datetime.now().isoformat(),
                    action_type=action,
                    message="Validating config...",
                    level=StatusLevel.PROGRESS,
                )
                self.ui.render_status(status)

                # Execute reload
                success = self.executor.execute_config_reload(file_event.file_path)

                if success:
                    duration = time.time() - start_time
                    status = WatcherStatus(
                        timestamp=datetime.now().isoformat(),
                        action_type=action,
                        message="Config reloaded (no restart needed)",
                        level=StatusLevel.SUCCESS,
                        duration_seconds=duration,
                    )
                else:
                    status = WatcherStatus(
                        timestamp=datetime.now().isoformat(),
                        action_type=action,
                        message="Config reload failed",
                        level=StatusLevel.ERROR,
                    )

            elif action == ActionType.CODE_RESTART:
                status = WatcherStatus(
                    timestamp=datetime.now().isoformat(),
                    action_type=action,
                    message="Orchestrating restart...",
                    level=StatusLevel.PROGRESS,
                )
                self.ui.render_status(status)

                # Execute restart
                success = self.executor.execute_code_restart()

                if success:
                    duration = time.time() - start_time
                    status = WatcherStatus(
                        timestamp=datetime.now().isoformat(),
                        action_type=action,
                        message="Restart complete",
                        level=StatusLevel.SUCCESS,
                        duration_seconds=duration,
                    )
                else:
                    status = WatcherStatus(
                        timestamp=datetime.now().isoformat(),
                        action_type=action,
                        message="Restart failed",
                        level=StatusLevel.ERROR,
                    )

            self.ui.render_status(status)

        except Exception as e:
            self.logger.error(f"Error handling file change: {e}", exc_info=True)
            status = WatcherStatus(
                timestamp=datetime.now().isoformat(),
                action_type=action,
                message=f"Error: {str(e)}",
                level=StatusLevel.ERROR,
            )
            self.ui.render_status(status)


# ============================================================================
# CLI
# ============================================================================


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Hot reload watcher for K0 kernel development",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Watch Docker container
  python -m k0.automation.hot_reload_watcher \\
    --watch-dirs k0/config k0/contracts/policy \\
    --container-name k0-kernel

  # Watch local process with health check
  python -m k0.automation.hot_reload_watcher \\
    --watch-dirs k0/ \\
    --process-name k0_kernel.py \\
    --health-check-url http://localhost:8080/health \\
    --verbose
        """,
    )

    parser.add_argument(
        "--watch-dirs",
        nargs="+",
        default=["k0/config", "k0/contracts/policy", "k0"],
        help="Directories to watch (default: k0/config k0/contracts/policy k0)",
    )
    parser.add_argument(
        "--exclude-patterns",
        nargs="+",
        default=["__pycache__", ".git", "*.pyc", "tests"],
        help="Patterns to exclude from watching",
    )
    parser.add_argument(
        "--container-name",
        default="k0-kernel",
        help="Docker container name (default: k0-kernel)",
    )
    parser.add_argument(
        "--process-name",
        help="Local process name (overrides container mode)",
    )
    parser.add_argument(
        "--health-check-url",
        help="Health check URL for restart validation (optional)",
    )
    parser.add_argument(
        "--grace-period",
        type=int,
        default=2,
        help="Seconds to wait for graceful shutdown (default: 2)",
    )
    parser.add_argument(
        "--restart-timeout",
        type=int,
        default=60,
        help="Max time to wait for restart (default: 60)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Create config
    config = WatchConfig(
        watch_dirs=args.watch_dirs,
        exclude_patterns=args.exclude_patterns,
        container_name=args.container_name if not args.process_name else None,
        process_name=args.process_name,
        health_check_url=args.health_check_url,
        grace_period_seconds=args.grace_period,
        restart_timeout_seconds=args.restart_timeout,
        verbose=args.verbose,
    )

    # Start watcher
    watcher = K0HotReloadWatcher(config)
    try:
        watcher.start()
        return 0
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
