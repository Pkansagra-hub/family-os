"""
Tests for Config Manager (Hot Reload Integration)

Purpose: Test config manager with file watching and hot reload
Location: tests/k1/l5_infrastructure/config/test_config_manager.py

Test Coverage:
- ConfigManager initialization
- Config loading on startup
- File system watching
- Atomic config reload
- Rollback on validation failure
- Change callbacks
- Performance budgets (<100ms reload P95)

ADR References:
- ADR-0080: Config Hot-Reload
- ADR-0024b: Performance Budgets
"""

import asyncio
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List

from ward import fixture, test

from k1.l5_infrastructure.config.config_manager import (
    ConfigChangeEvent,
    ConfigManager,
    ConfigManagerState,
)
from k1.l5_infrastructure.config.loader import ConfigLoader

# ============================================================================
# Fixtures
# ============================================================================


@fixture
def temp_config_dir():
    """Create temporary config directory with sample configs"""
    with TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create sample kernel.yaml
        kernel_config = temp_path / "kernel.yaml"
        kernel_config.write_text(
            """
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: 300000
  max_agents_per_session: 3
runtime:
  worker_threads: 4
  max_memory_mb: 512
"""
        )

        # Create sample logging.yaml
        logging_config = temp_path / "logging.yaml"
        logging_config.write_text(
            """
version: "1.0.0"
logging:
  level: "INFO"
  format: "json"
  output:
    console: true
  trace_context:
    enabled: true
    baggage_keys:
      - "cognitive_trace_id"
      - "session_id"
"""
        )

        yield temp_path


@fixture
def config_manager(temp_config_dir=temp_config_dir):
    """Create ConfigManager instance with temp directory"""
    manager = ConfigManager(
        config_dir=str(temp_config_dir),
        watch_enabled=False,  # Disable watching for most tests
    )
    yield manager


@fixture
def config_manager_with_watch(temp_config_dir=temp_config_dir):
    """Create ConfigManager with file watching enabled"""
    manager = ConfigManager(config_dir=str(temp_config_dir), watch_enabled=True)
    yield manager


# ============================================================================
# Group 1: Initialization & State (3 tests)
# ============================================================================


@test("ConfigManager initializes successfully")
def _(manager=config_manager):
    """Verify ConfigManager initializes with correct state"""
    assert manager.state == ConfigManagerState.STOPPED
    assert manager.config_dir.exists()
    assert isinstance(manager.loader, ConfigLoader)
    assert len(manager._configs) == 0


@test("ConfigManager starts and loads configs")
async def _(manager=config_manager):
    """Verify ConfigManager starts and loads all configs"""
    await manager.start()

    assert manager.state == ConfigManagerState.RUNNING
    assert "kernel" in manager._configs
    assert "logging" in manager._configs

    kernel_config = manager.get_config("kernel")
    assert kernel_config is not None
    assert kernel_config["version"] == "1.0.0"

    await manager.stop()
    assert manager.state == ConfigManagerState.STOPPED


@test("ConfigManager handles missing config directory")
async def _():
    """Verify ConfigManager handles missing directory gracefully"""
    manager = ConfigManager(config_dir="/nonexistent/path", watch_enabled=False)

    # Should start without error (just warns about missing dir)
    await manager.start()
    assert manager.state == ConfigManagerState.RUNNING
    assert len(manager._configs) == 0

    await manager.stop()


# ============================================================================
# Group 2: Config Access (3 tests)
# ============================================================================


@test("ConfigManager get_config returns loaded config")
async def _(manager=config_manager):
    """Verify get_config returns configuration data"""
    await manager.start()

    kernel_config = manager.get_config("kernel")
    assert kernel_config is not None
    assert kernel_config["kernel"]["name"] == "k1_intelligence"
    assert kernel_config["runtime"]["worker_threads"] == 4

    await manager.stop()


@test("ConfigManager get_config returns None for unknown config")
async def _(manager=config_manager):
    """Verify get_config returns None for unloaded config"""
    await manager.start()

    unknown_config = manager.get_config("nonexistent")
    assert unknown_config is None

    await manager.stop()


@test("ConfigManager get_stats returns metrics")
async def _(manager=config_manager):
    """Verify get_stats returns reload statistics"""
    await manager.start()

    stats = manager.get_stats()
    assert stats["state"] == "running"
    assert stats["total_reloads"] == 0
    assert "kernel" in stats["configs_loaded"]
    assert "logging" in stats["configs_loaded"]

    await manager.stop()


# ============================================================================
# Group 3: Change Callbacks (3 tests)
# ============================================================================


@test("ConfigManager registers change callbacks")
def _(manager=config_manager):
    """Verify add_change_callback registers callbacks"""
    callback_called = []

    def on_change(event: ConfigChangeEvent):
        callback_called.append(event)

    manager.add_change_callback(on_change)
    assert len(manager._change_callbacks) == 1


@test("ConfigManager notifies callbacks on config change")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify callbacks are invoked on config change"""
    await manager.start()

    events: List[ConfigChangeEvent] = []

    def on_change(event: ConfigChangeEvent):
        events.append(event)

    manager.add_change_callback(on_change)

    # Simulate config change
    kernel_file = temp_config_dir / "kernel.yaml"
    kernel_file.write_text(
        """
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: 600000
  max_agents_per_session: 5
runtime:
  worker_threads: 8
  max_memory_mb: 1024
"""
    )

    # Manually trigger reload
    await manager._handle_config_change(kernel_file)

    # Wait for callback
    await asyncio.sleep(0.1)

    assert len(events) == 1
    event = events[0]
    assert event.config_name == "kernel"
    assert event.success is True
    assert event.new_config is not None
    assert event.new_config["runtime"]["worker_threads"] == 8

    await manager.stop()


@test("ConfigManager handles async callbacks")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify async callbacks are awaited correctly"""
    await manager.start()

    events: List[ConfigChangeEvent] = []

    async def async_callback(event: ConfigChangeEvent):
        await asyncio.sleep(0.01)  # Simulate async work
        events.append(event)

    manager.add_change_callback(async_callback)

    # Trigger change
    logging_file = temp_config_dir / "logging.yaml"
    logging_file.write_text(
        """
version: "1.0.0"
logging:
  level: "DEBUG"
  format: "text"
  output:
    console: true
    file: true
"""
    )

    await manager._handle_config_change(logging_file)
    await asyncio.sleep(0.1)

    assert len(events) == 1
    assert events[0].config_name == "logging"

    await manager.stop()


# ============================================================================
# Group 4: Atomic Reload & Rollback (4 tests)
# ============================================================================


@test("ConfigManager reloads valid config successfully")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify valid config reloads successfully"""
    await manager.start()

    old_config = manager.get_config("kernel")
    assert old_config["kernel"]["session_timeout_ms"] == 300000

    # Update config
    kernel_file = temp_config_dir / "kernel.yaml"
    kernel_file.write_text(
        """
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: 600000
  max_agents_per_session: 3
runtime:
  worker_threads: 4
  max_memory_mb: 512
"""
    )

    await manager._handle_config_change(kernel_file)

    new_config = manager.get_config("kernel")
    assert new_config["kernel"]["session_timeout_ms"] == 600000

    stats = manager.get_stats()
    assert stats["successful_reloads"] == 1
    assert stats["failed_reloads"] == 0

    await manager.stop()


@test("ConfigManager rolls back invalid config")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify invalid config triggers rollback"""
    await manager.start()

    old_config = manager.get_config("kernel")
    old_timeout = old_config["kernel"]["session_timeout_ms"]

    # Write invalid config (max_agents_per_session > 10)
    kernel_file = temp_config_dir / "kernel.yaml"
    kernel_file.write_text(
        """
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: 300000
  max_agents_per_session: 25
runtime:
  worker_threads: 4
  max_memory_mb: 512
"""
    )

    await manager._handle_config_change(kernel_file)

    # Config should remain unchanged (rolled back)
    current_config = manager.get_config("kernel")
    assert current_config["kernel"]["session_timeout_ms"] == old_timeout
    assert current_config["kernel"]["max_agents_per_session"] == 3

    stats = manager.get_stats()
    assert stats["failed_reloads"] == 1

    await manager.stop()


@test("ConfigManager preserves old config on YAML parse error")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify YAML parse errors don't clear config"""
    await manager.start()

    old_config = manager.get_config("logging")
    assert old_config is not None, "logging config should be loaded"
    assert old_config["logging"]["level"] == "INFO"

    # Write malformed YAML
    logging_file = temp_config_dir / "logging.yaml"
    logging_file.write_text(
        """
version: "1.0.0"
logging:
  level: "DEBUG
  format: "json"  # Unclosed quote above
"""
    )

    await manager._handle_config_change(logging_file)

    # Old config should be preserved
    current_config = manager.get_config("logging")
    assert current_config is not None
    assert current_config == old_config
    assert current_config["logging"]["level"] == "INFO"

    await manager.stop()


@test("ConfigManager tracks rollback in change event")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify rollback is reported in change event"""
    await manager.start()

    events: List[ConfigChangeEvent] = []
    manager.add_change_callback(lambda e: events.append(e))

    # Write invalid config
    kernel_file = temp_config_dir / "kernel.yaml"
    kernel_file.write_text(
        """
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: 300000
  max_agents_per_session: 100
runtime:
  worker_threads: 4
  max_memory_mb: 512
"""
    )

    await manager._handle_config_change(kernel_file)
    await asyncio.sleep(0.05)

    assert len(events) == 1
    event = events[0]
    assert event.success is False
    assert event.error_message is not None
    assert event.new_config is None  # Rollback means no new config

    await manager.stop()


# ============================================================================
# Group 5: Performance (2 tests)
# ============================================================================


@test("ConfigManager reload completes within 100ms budget")
async def _(manager=config_manager, temp_config_dir=temp_config_dir):
    """Verify reload latency meets <100ms P95 budget"""
    await manager.start()

    latencies: List[float] = []

    def track_latency(event: ConfigChangeEvent):
        latencies.append(event.latency_ms)

    manager.add_change_callback(track_latency)

    # Perform 10 reloads
    for i in range(10):
        kernel_file = temp_config_dir / "kernel.yaml"
        kernel_file.write_text(
            f"""
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: {300000 + i * 1000}
  max_agents_per_session: 3
runtime:
  worker_threads: 4
  max_memory_mb: 512
"""
        )
        await manager._handle_config_change(kernel_file)
        await asyncio.sleep(0.02)  # Small delay between reloads

    # Calculate P95 latency
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    assert p95_latency < 100, f"P95 latency {p95_latency:.2f}ms exceeds 100ms budget"

    await manager.stop()


@test("ConfigManager startup loads all configs efficiently")
async def _(manager=config_manager):
    """Verify startup config loading is efficient"""
    start_time = time.perf_counter()

    await manager.start()

    startup_latency_ms = (time.perf_counter() - start_time) * 1000

    # Should load 2 configs (kernel, logging) in <200ms
    assert (
        startup_latency_ms < 200
    ), f"Startup latency {startup_latency_ms:.2f}ms too high"
    assert len(manager._configs) == 2

    await manager.stop()


# ============================================================================
# Group 6: File Watching Integration (2 tests - requires watchdog)
# ============================================================================


@test("ConfigManager file watching detects changes")
async def _(manager=config_manager_with_watch, temp_config_dir=temp_config_dir):
    """Verify file watching detects config file changes"""
    try:
        from watchdog.observers import Observer

        watchdog_available = True
    except ImportError:
        watchdog_available = False

    if not watchdog_available:
        # Skip test if watchdog not installed
        return

    await manager.start()

    events: List[ConfigChangeEvent] = []
    manager.add_change_callback(lambda e: events.append(e))

    # Wait for observer to start
    await asyncio.sleep(0.2)

    # Modify config file
    kernel_file = temp_config_dir / "kernel.yaml"
    kernel_file.write_text(
        """
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: 900000
  max_agents_per_session: 3
runtime:
  worker_threads: 16
  max_memory_mb: 2048
"""
    )

    # Wait for file event to be detected and processed
    await asyncio.sleep(0.5)

    # Should have detected change
    assert len(events) > 0
    assert events[0].config_name == "kernel"
    assert events[0].success is True

    await manager.stop()


@test("ConfigManager deduplicates rapid file changes")
async def _(manager=config_manager_with_watch, temp_config_dir=temp_config_dir):
    """Verify rapid file changes are deduplicated"""
    try:
        from watchdog.observers import Observer

        watchdog_available = True
    except ImportError:
        watchdog_available = False

    if not watchdog_available:
        return

    await manager.start()

    events: List[ConfigChangeEvent] = []
    manager.add_change_callback(lambda e: events.append(e))

    await asyncio.sleep(0.2)

    # Write to file multiple times rapidly
    kernel_file = temp_config_dir / "kernel.yaml"
    for i in range(5):
        kernel_file.write_text(
            f"""
version: "1.0.0"
kernel:
  name: "k1_intelligence"
  session_timeout_ms: {300000 + i * 1000}
  max_agents_per_session: 3
runtime:
  worker_threads: 4
  max_memory_mb: 512
"""
        )
        await asyncio.sleep(0.01)  # Very rapid writes

    # Wait for processing
    await asyncio.sleep(0.5)

    # Should have fewer events than writes (deduplication)
    assert len(events) < 5, f"Expected deduplication but got {len(events)} events"

    await manager.stop()
