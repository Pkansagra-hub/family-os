"""Component tests for Layer 5 hot reload (ADR-0080).

Validates file watching, config validation, atomic updates, and rollback
for the hot reload system defined in:
- ADR-0080 – Config Hot-Reload (change detection, validation, rollback)
- ADR-0024 – Performance Budgets (<100ms reload)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, cast

from ward import fixture, test  # type: ignore[attr-defined]

from k1.l5_infrastructure.resilience.hot_reload import (
    ConfigChange,
    ConfigValidationError,
    HotReloadManager,
    HotReloadState,
)


@fixture
async def temp_config_dir() -> AsyncGenerator[Path, None]:
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        yield config_dir


@fixture
async def basic_manager(
    temp_config_dir_dep: Any = temp_config_dir,
) -> AsyncGenerator[HotReloadManager, None]:
    """Create a basic hot reload manager."""
    config_dir = cast(Path, temp_config_dir_dep)
    manager = HotReloadManager(config_dir=config_dir)
    yield manager


@test("hot reload manager initializes correctly")
async def _(manager_dep: Any = basic_manager) -> None:
    """Test that the manager initializes with correct state."""
    manager = cast(HotReloadManager, manager_dep)
    assert manager.state == HotReloadState.STOPPED
    assert manager.config_dir.exists()
    assert len(manager.get_all_configs()) == 0


@test("hot reload manager starts and stops")
async def _(manager_dep: Any = basic_manager) -> None:
    """Test starting and stopping the manager."""
    manager = cast(HotReloadManager, manager_dep)
    await manager.start()
    assert manager.state == HotReloadState.RUNNING

    await manager.stop()
    assert manager.state == HotReloadState.STOPPED


@test("config file loading works")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test loading YAML config files."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    # Create a test config file
    config_file = temp_config_dir / "test.yml"
    config_content = """
    key1: value1
    key2:
      nested: true
    """

    config_file.write_text(config_content)

    # Start manager to load configs
    await manager.start()

    # Check config was loaded
    config = manager.get_config("test")
    expected: Dict[str, Any] = {"key1": "value1", "key2": {"nested": True}}

    assert config == expected
    await manager.stop()


@test("invalid YAML raises error")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test that invalid YAML raises ConfigValidationError."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    config_file = temp_config_dir / "invalid.yml"
    config_file.write_text("invalid: yaml: content: [")

    # Try to reload invalid config
    try:
        success = await manager.reload_config("invalid.yml")
        assert not success, "Should have failed to reload invalid config"
    except ConfigValidationError as e:
        assert "YAML parse error" in str(e)


@test("config validation works")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test config validation."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    # Create valid config
    valid_config_file = temp_config_dir / "retry_policy.yml"
    valid_config_file.write_text("max_retries: 5\nbase_delay_ms: 100\n")

    # Should succeed
    success = await manager.reload_config("retry_policy.yml")
    assert success

    # Create invalid config
    invalid_config_file = temp_config_dir / "invalid_retry.yml"
    invalid_config_file.write_text("max_retries: -1\nbase_delay_ms: 100\n")

    # Should fail
    success = await manager.reload_config("invalid_retry.yml")
    assert not success


@test("manual config reload works")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test manual config reload."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    # Create initial config
    config_file = temp_config_dir / "test.yml"
    config_file.write_text("value: 1\n")

    # Start manager
    await manager.start()

    # Reload config
    success = await manager.reload_config("test.yml")
    assert success

    # Check config was loaded
    config = manager.get_config("test")
    assert config == {"value": 1}

    await manager.stop()


@test("config change detection works")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test that config changes are detected."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    # Create initial config
    config_file = temp_config_dir / "test.yml"
    config_file.write_text("value: 1\n")

    # Start manager
    await manager.start()

    # Track change events
    changes: list[ConfigChange] = []

    def on_change(change: ConfigChange) -> None:
        changes.append(change)

    manager.add_change_callback(on_change)

    # Modify config
    config_file.write_text("value: 2\n")

    # Wait for detection (with some buffer)
    await asyncio.sleep(0.2)

    # Check that change was detected
    assert len(changes) > 0
    change = changes[0]
    assert change.config_file == "test.yml"
    assert change.old_config == {"value": 1}
    assert change.new_config == {"value": 2}
    assert change.validation_passed

    await manager.stop()


@test("invalid config change is rejected")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test that invalid config changes are rejected."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    # Create initial valid config
    config_file = temp_config_dir / "retry_policy.yml"
    config_file.write_text("max_retries: 5\nbase_delay_ms: 100\n")

    # Start manager
    await manager.start()

    # Track change events
    changes: list[ConfigChange] = []

    def on_change(change: ConfigChange) -> None:
        changes.append(change)

    manager.add_change_callback(on_change)

    # Modify to invalid config
    config_file.write_text("max_retries: -1\nbase_delay_ms: 100\n")

    # Wait for detection
    await asyncio.sleep(0.2)

    # Check that change was detected but validation failed
    assert len(changes) > 0
    change = changes[0]
    assert change.config_file == "retry_policy.yml"
    assert not change.validation_passed
    assert change.error_message is not None
    assert "max_retries must be non-negative" in change.error_message

    await manager.stop()


@test("reload callbacks are called")
async def _(
    temp_config_dir_dep: Any = temp_config_dir, manager_dep: Any = basic_manager
) -> None:
    """Test that reload callbacks are invoked."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    manager = cast(HotReloadManager, manager_dep)

    # Create config
    config_file = temp_config_dir / "test.yml"
    config_file.write_text("value: 1\n")

    # Start manager
    await manager.start()

    # Track reload events
    reloads: list[tuple[str, Dict[str, Any]]] = []

    def on_reload(name: str, config: Dict[str, Any]) -> None:
        reloads.append((name, config))

    manager.add_reload_callback(on_reload)

    # Trigger reload
    success = await manager.reload_config("test.yml")
    assert success

    # Check callback was called
    assert len(reloads) == 1
    name, config = reloads[0]
    assert name == "test"
    assert config == {"value": 1}

    await manager.stop()
