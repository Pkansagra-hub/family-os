"""
Config Manager - Hot Reload Integration

Purpose: Configuration management with hot reload support
Location: k1/l5_infrastructure/config/config_manager.py
Performance: <100ms reload latency P95

Primary ADRs:
- ADR-0080: Config Hot-Reload (file watching, atomic reload, rollback)
- ADR-0024b: Performance Budgets (<100ms reload P95)

Related ADRs:
- ADR-0009b: Per-Service Circuit Configuration
- ADR-0006: Component Configuration

Features:
- File system monitoring (watchdog)
- Atomic config reload
- Automatic rollback on validation failure
- Change callbacks for components
- Performance tracking

Last Updated: January 2025
ADR Reference: docs/architecture/decisions/0080-continuous-config-hot-reload.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    FileSystemEventHandler = object  # type: ignore
    FileSystemEvent = object  # type: ignore
    Observer = None  # type: ignore
    WATCHDOG_AVAILABLE = False

from k1.l5_infrastructure.config.loader import ConfigLoader

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigManagerState",
    "ConfigChangeEvent",
    "ConfigManager",
    "ConfigManagerError",
]


class ConfigManagerState(str, Enum):
    """States for config manager"""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class ConfigChangeEvent:
    """Configuration change event"""

    config_name: str
    timestamp_ms: float
    success: bool
    old_config: Optional[Dict[str, Any]] = None
    new_config: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    latency_ms: float = 0.0


class ConfigManagerError(Exception):
    """Configuration manager error"""

    pass


class _ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for config file changes"""

    def __init__(self, manager: ConfigManager) -> None:
        super().__init__()
        self.manager = manager
        self._pending_changes: asyncio.Queue[Path] = asyncio.Queue()

    def on_modified(self, event: FileSystemEvent) -> None:  # type: ignore
        """Handle file modification events"""
        if event.is_directory:  # type: ignore
            return

        file_path = Path(event.src_path)  # type: ignore
        if file_path.suffix not in (".yaml", ".yml"):
            return

        # Queue the change for async processing
        try:
            asyncio.create_task(self._queue_change(file_path))
        except RuntimeError:
            # No event loop running, queue directly
            try:
                self._pending_changes.put_nowait(file_path)
            except Exception as e:
                logger.warning(
                    "[ConfigFileHandler] Failed to queue change",
                    extra={"file_path": str(file_path), "error": str(e)},
                )

    async def _queue_change(self, file_path: Path) -> None:
        """Queue change for processing"""
        try:
            await self._pending_changes.put(file_path)
        except Exception as e:
            logger.warning(
                "[ConfigFileHandler] Failed to queue change",
                extra={"file_path": str(file_path), "error": str(e)},
            )


class ConfigManager:
    """Configuration manager with hot reload support

    Integrates ConfigLoader with file system watching for zero-downtime
    configuration updates per ADR-0080.

    Features:
    - File system monitoring (watchdog)
    - Atomic config reload via ConfigLoader
    - Automatic rollback on validation failure
    - Change callbacks for components
    - Performance tracking (<100ms P95 target)

    Example:
        >>> manager = ConfigManager(config_dir="k1/config")
        >>> await manager.start()
        >>>
        >>> # Register callback for config changes
        >>> def on_config_change(event: ConfigChangeEvent):
        ...     print(f"Config {event.config_name} changed")
        >>>
        >>> manager.add_change_callback(on_config_change)
        >>>
        >>> # Get current config
        >>> kernel_config = manager.get_config("kernel")
        >>>
        >>> # Stop manager
        >>> await manager.stop()
    """

    def __init__(
        self,
        config_dir: Optional[str | Path] = None,
        loader: Optional[ConfigLoader] = None,
        watch_enabled: bool = True,
    ) -> None:
        """Initialize ConfigManager

        Args:
            config_dir: Directory containing config files (defaults to k1/config)
            loader: ConfigLoader instance (creates new if not provided)
            watch_enabled: Enable file watching (requires watchdog)
        """
        self.config_dir = (
            Path(config_dir)
            if config_dir
            else Path(__file__).parent.parent.parent / "config"
        )
        self.loader = (
            loader if loader else ConfigLoader(config_dir=str(self.config_dir))
        )
        self.watch_enabled = watch_enabled and WATCHDOG_AVAILABLE

        # State
        self.state = ConfigManagerState.STOPPED
        self._configs: Dict[str, Dict[str, Any]] = {}

        # File watching components
        self._observer: Optional[Observer] = None
        self._handler: Optional[_ConfigFileHandler] = None
        self._queue_processor_task: Optional[asyncio.Task[None]] = None

        # Callbacks
        self._change_callbacks: List[Callable[[ConfigChangeEvent], None]] = []

        # Performance tracking
        self._reload_count = 0
        self._reload_failures = 0
        self._total_reload_latency_ms = 0.0

        logger.info(
            "[ConfigManager] Initialized",
            extra={
                "config_dir": str(self.config_dir),
                "watch_enabled": self.watch_enabled,
                "watchdog_available": WATCHDOG_AVAILABLE,
            },
        )

    async def start(self) -> None:
        """Start config manager and file watching

        Raises:
            ConfigManagerError: If startup fails
        """
        if self.state == ConfigManagerState.RUNNING:
            logger.warning("[ConfigManager] Already running")
            return

        try:
            self.state = ConfigManagerState.STARTING

            # Load initial configs
            await self._load_initial_configs()

            # Start file watching if enabled
            if self.watch_enabled:
                await self._start_file_watching()

            self.state = ConfigManagerState.RUNNING
            logger.info("[ConfigManager] Started successfully")

        except Exception as e:
            self.state = ConfigManagerState.STOPPED
            logger.error("[ConfigManager] Startup failed", extra={"error": str(e)})
            raise ConfigManagerError(f"Failed to start ConfigManager: {e}") from e

    async def stop(self) -> None:
        """Stop config manager and file watching"""
        if self.state == ConfigManagerState.STOPPED:
            return

        logger.info("[ConfigManager] Stopping")

        # Stop file watching
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None

        # Cancel queue processor
        if self._queue_processor_task and not self._queue_processor_task.done():
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
            self._queue_processor_task = None

        self.state = ConfigManagerState.STOPPED
        logger.info("[ConfigManager] Stopped")

    def get_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """Get current configuration

        Args:
            config_name: Config name (kernel, logging, circuit_breaker, etc.)

        Returns:
            Configuration dictionary or None if not loaded
        """
        return self._configs.get(config_name)

    def add_change_callback(
        self, callback: Callable[[ConfigChangeEvent], None]
    ) -> None:
        """Register callback for configuration changes

        Args:
            callback: Function called when config changes
        """
        self._change_callbacks.append(callback)
        logger.debug(
            "[ConfigManager] Callback registered",
            extra={"num_callbacks": len(self._change_callbacks)},
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get reload statistics

        Returns:
            Statistics dictionary with reload counts and latencies
        """
        avg_latency = (
            self._total_reload_latency_ms / self._reload_count
            if self._reload_count > 0
            else 0.0
        )

        return {
            "state": self.state.value,
            "total_reloads": self._reload_count,
            "successful_reloads": self._reload_count - self._reload_failures,
            "failed_reloads": self._reload_failures,
            "avg_reload_latency_ms": avg_latency,
            "configs_loaded": list(self._configs.keys()),
            "watch_enabled": self.watch_enabled,
        }

    async def _load_initial_configs(self) -> None:
        """Load all configs from config directory"""
        logger.info("[ConfigManager] Loading initial configs")

        if not self.config_dir.exists():
            logger.warning(
                "[ConfigManager] Config directory not found",
                extra={"config_dir": str(self.config_dir)},
            )
            return

        # Load all .yaml and .yml files
        for config_file in self.config_dir.glob("*.y*ml"):
            config_name = config_file.stem
            result = self.loader.load_config(config_name)

            if result.success and result.config_data:
                self._configs[config_name] = result.config_data
                logger.debug(
                    "[ConfigManager] Config loaded", extra={"config_name": config_name}
                )
            else:
                logger.warning(
                    "[ConfigManager] Config load failed",
                    extra={
                        "config_name": config_name,
                        "errors": [str(e) for e in result.errors],
                    },
                )

    async def _start_file_watching(self) -> None:
        """Start file system watching"""
        if not WATCHDOG_AVAILABLE:
            logger.warning(
                "[ConfigManager] Watchdog not available, file watching disabled"
            )
            return

        logger.info("[ConfigManager] Starting file watching")

        # Create file handler
        self._handler = _ConfigFileHandler(self)

        # Create observer
        self._observer = Observer()  # type: ignore
        self._observer.schedule(self._handler, str(self.config_dir), recursive=False)  # type: ignore
        self._observer.start()  # type: ignore

        # Start queue processor
        self._queue_processor_task = asyncio.create_task(self._process_change_queue())

        logger.info("[ConfigManager] File watching started")

    async def _process_change_queue(self) -> None:
        """Process file change events from queue"""
        if not self._handler:
            return

        logger.info("[ConfigManager] Change queue processor started")

        try:
            while True:
                # Wait for file change
                file_path = await self._handler._pending_changes.get()

                # Small delay to handle rapid successive writes
                await asyncio.sleep(0.05)

                # Drain any duplicate changes for same file
                while not self._handler._pending_changes.empty():
                    try:
                        pending = self._handler._pending_changes.get_nowait()
                        if pending != file_path:
                            await self._handler._pending_changes.put(pending)
                            break
                    except asyncio.QueueEmpty:
                        break

                # Process the change
                await self._handle_config_change(file_path)

        except asyncio.CancelledError:
            logger.info("[ConfigManager] Change queue processor cancelled")
        except Exception as e:
            logger.error(
                "[ConfigManager] Change queue processor error", extra={"error": str(e)}
            )

    async def _handle_config_change(self, file_path: Path) -> None:
        """Handle config file change with atomic reload and rollback

        Args:
            file_path: Path to changed config file
        """
        config_name = file_path.stem
        start_time = time.perf_counter()

        logger.info(
            "[ConfigManager] Config change detected",
            extra={"config_name": config_name, "file_path": str(file_path)},
        )

        # Get old config for rollback
        old_config = self._configs.get(config_name)

        # Attempt reload
        result = self.loader.reload_config(config_name)

        latency_ms = (time.perf_counter() - start_time) * 1000
        self._reload_count += 1
        self._total_reload_latency_ms += latency_ms

        # Create change event
        event = ConfigChangeEvent(
            config_name=config_name,
            timestamp_ms=time.time() * 1000,
            success=result.success,
            old_config=old_config,
            new_config=result.config_data if result.success else None,
            error_message=None if result.success else str(result.errors),
            latency_ms=latency_ms,
        )

        if result.success and result.config_data:
            # Update cached config
            self._configs[config_name] = result.config_data

            logger.info(
                "[ConfigManager] Config reloaded successfully",
                extra={"config_name": config_name, "latency_ms": f"{latency_ms:.2f}"},
            )
        else:
            # Rollback: keep old config
            self._reload_failures += 1

            logger.warning(
                "[ConfigManager] Config reload failed, rolled back",
                extra={
                    "config_name": config_name,
                    "errors": [str(e) for e in result.errors],
                    "latency_ms": f"{latency_ms:.2f}",
                },
            )

        # Notify callbacks
        await self._notify_callbacks(event)

    async def _notify_callbacks(self, event: ConfigChangeEvent) -> None:
        """Notify all registered callbacks about config change

        Args:
            event: Configuration change event
        """
        for callback in self._change_callbacks:
            try:
                # Check if callback is async
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(
                    "[ConfigManager] Callback error",
                    extra={"config_name": event.config_name, "error": str(e)},
                )
