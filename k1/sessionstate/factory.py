"""
SessionStateFactory - Build SessionState with Appropriate Adapters
===================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.5 SessionStateFactory and Standalone Mode
ISSUES: 3.5.1, 3.5.2, 3.5.3

ARCHITECTURE DIAGRAMS:
- k1/sessionstate/sessionstate.mmd (external view)
- k1/sessionstate/sessionstate_internal.mmd (internal structure)

ADRs:
- ADR-0017 series: SessionState 6-Section Design
- ADR-0020: Multi-Tier Storage Architecture

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Factory for building SessionStateManager with appropriate adapters.
    Supports three modes:
    1. STANDALONE: For development, testing, offline operation
    2. TESTING: For fast unit tests (in-memory storage)
    3. WIRED: For production with real adapters (Bridge, DeltaBus, Fabric)

EDGE-FIRST DESIGN:
    Standalone mode uses LOCAL COLD (K1 SQLite) which works fully offline.
    K0 sync is optional enhancement, never a requirement.

==============================================================================
CLASS: SessionStateFactory
==============================================================================
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from .adapters.direct_writer import DirectWriterAdapter
from .adapters.local_events import LocalEventAdapter
from .adapters.memory_storage import InMemoryStorageAdapter
from .adapters.sqlite_storage import SQLiteStorageAdapter
from .adapters.standalone_lifecycle import StandaloneLifecycle
from .local_cold import LocalColdArchive
from .manager import SessionStateManager
from .ports.events import IEventPort
from .ports.k0_sync import IK0SyncPort
from .ports.lifecycle import ILifecyclePort, LifecycleConfig
from .ports.storage import IStoragePort
from .ports.writer import IWriterPort

logger = logging.getLogger(__name__)

# Default paths (config: sessionstate.storage.default_db_path)
DEFAULT_DB_PATH = Path.home() / ".familyos" / "k1" / "sessionstate.db"


# =============================================================================
# EXCEPTIONS
# =============================================================================


class PortProtocolError(Exception):
    """Raised when a port doesn't implement required protocol."""

    def __init__(self, port_name: str, expected: type, got: type):
        self.port_name = port_name
        self.expected = expected
        self.got = got
        super().__init__(
            f"Port '{port_name}' must implement {expected.__name__}, " f"got {got.__name__}"
        )


# =============================================================================
# FACTORY CLASS
# =============================================================================


class SessionStateFactory:
    """
    Factory for creating SessionStateManager instances.

    Supports three creation modes:
    1. create_standalone(): For development, testing, offline operation
    2. create_for_testing(): For fast unit tests (in-memory)
    3. create_with_ports(): For production with injected adapters

    Usage:
        # Standalone mode (development/offline)
        manager = SessionStateFactory.create_standalone(session_id="test-123")

        # Testing mode (fast in-memory)
        manager = SessionStateFactory.create_for_testing()

        # Production mode (with real adapters)
        manager = SessionStateFactory.create_with_ports(
            session_id="prod-456",
            storage=bridge_storage_adapter,
            events=deltabus_adapter,
            writer=concierge_adapter,
            lifecycle=fabric_lifecycle,
        )
    """

    @staticmethod
    def create_standalone(
        session_id: Optional[str] = None,
        db_path: Optional[Path] = None,
        checkpoint_interval_s: float | None = None,
    ) -> SessionStateManager:
        """
        Create SessionStateManager for standalone operation.

        Uses SQLite for LOCAL COLD persistence. Works fully offline.
        Periodic checkpoints enabled by default.

        Args:
            session_id: Unique session identifier (auto-generated if None)
            db_path: Optional path for SQLite database.
                     Default: ~/.familyos/k1/sessionstate.db
            checkpoint_interval_s: Checkpoint interval in seconds (0 = disabled)

        Returns:
            SessionStateManager: Fully configured for standalone operation

        Adapters Wired:
            - IStoragePort -> SQLiteStorageAdapter (LOCAL COLD)
            - IEventPort -> LocalEventAdapter (in-process callbacks)
            - IWriterPort -> DirectWriterAdapter (direct mutation)
            - ILifecyclePort -> StandaloneLifecycle (self-managed)

        Example:
            manager = SessionStateFactory.create_standalone("dev-session-1")
            manager.start()

            # Use the manager
            result = manager.mutate("beliefs_active", "append", {...})

            manager.stop()
        """
        # Generate session ID if not provided
        if session_id is None:
            session_id = f"session-{uuid.uuid4().hex[:12]}"

        # Resolve database path
        if db_path is None:
            resolved_path = DEFAULT_DB_PATH.expanduser()
        else:
            resolved_path = db_path

        # Ensure parent directory exists
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Creating standalone SessionStateManager (session=%s, db=%s)",
            session_id[:16] if session_id else "none",
            str(resolved_path),
        )

        # Create adapters
        storage_adapter = SQLiteStorageAdapter(db_path=resolved_path)
        event_adapter = LocalEventAdapter(capture_mode=False)
        local_cold_archive = LocalColdArchive(db_path=resolved_path)

        # Create writer/lifecycle adapters unbound (no manager reference yet).
        # This breaks the circular dependency: manager needs ports, ports need manager.
        writer_adapter = DirectWriterAdapter(
            writer_id="direct",
        )

        lifecycle_adapter = StandaloneLifecycle(
            checkpoint_interval_s=(
                checkpoint_interval_s if checkpoint_interval_s is not None else 30.0
            ),
        )

        # Single-phase construction: manager gets ALL ports at once, never None.
        manager = SessionStateManager(
            session_id=session_id,
            storage_port=storage_adapter,
            event_port=event_adapter,
            writer_port=writer_adapter,
            lifecycle_port=lifecycle_adapter,
            local_cold_archive=local_cold_archive,
        )

        # Bind manager back-references on adapters that need it.
        writer_adapter.bind_manager(manager, manager.mutation_guard)
        lifecycle_adapter.bind_manager(manager)

        logger.debug(
            "Standalone manager created (session=%s, storage=%s, events=%s, writer=%s, lifecycle=%s)",
            session_id[:8] if session_id else "none",
            storage_adapter.storage_type,
            "local",
            writer_adapter.writer_id,
            "standalone",
        )

        return manager

    @staticmethod
    def create_for_testing(
        session_id: Optional[str] = None,
    ) -> SessionStateManager:
        """
        Create SessionStateManager optimized for testing.

        Uses InMemoryStorageAdapter instead of SQLite for faster tests.
        LocalEventAdapter is configured with capture mode for assertions.
        Periodic checkpoints disabled for deterministic testing.

        Args:
            session_id: Test session identifier (default: auto-generated)

        Returns:
            SessionStateManager: Configured for fast testing

        Adapters Wired:
            - IStoragePort -> InMemoryStorageAdapter (no disk I/O)
            - IEventPort -> LocalEventAdapter (with capture mode)
            - IWriterPort -> DirectWriterAdapter
            - ILifecyclePort -> StandaloneLifecycle (no periodic checkpoint)

        Example:
            manager = SessionStateFactory.create_for_testing()
            manager.start()

            # Make mutations
            manager.mutate("scoreboard", "set", {"topic": "weather"})

            # Assert events were emitted
            events = manager._event_port.get_captured_events()
            assert len(events) >= 1
        """
        # Generate session ID if not provided
        if session_id is None:
            session_id = f"test-{uuid.uuid4().hex[:8]}"

        logger.debug(
            "Creating test SessionStateManager (session=%s)",
            session_id,
        )

        # Create in-memory adapters for speed
        storage_adapter = InMemoryStorageAdapter()
        event_adapter = LocalEventAdapter(capture_mode=True)

        # Create writer/lifecycle adapters unbound (no manager reference yet).
        writer_adapter = DirectWriterAdapter(
            writer_id="test",
        )

        # Disable periodic checkpoints for deterministic testing
        lifecycle_config = LifecycleConfig.testing()
        lifecycle_adapter = StandaloneLifecycle(
            config=lifecycle_config,
        )

        # Single-phase construction: manager gets ALL ports at once, never None.
        manager = SessionStateManager(
            session_id=session_id,
            storage_port=storage_adapter,
            event_port=event_adapter,
            writer_port=writer_adapter,
            lifecycle_port=lifecycle_adapter,
            local_cold_archive=None,  # Use default in-memory
        )

        # Bind manager back-references on adapters that need it.
        writer_adapter.bind_manager(manager, manager.mutation_guard)
        lifecycle_adapter.bind_manager(manager)

        return manager

    @staticmethod
    def create_with_ports(
        session_id: str,
        storage: IStoragePort,
        events: IEventPort,
        writer: IWriterPort,
        lifecycle: ILifecyclePort,
        k0_sync: Optional[IK0SyncPort] = None,
        db_path: Optional[Path] = None,
    ) -> SessionStateManager:
        """
        Create SessionStateManager with injected ports.

        For production wiring with real adapters (Bridge, DeltaBus, Fabric).
        Validates that all ports implement required protocols.

        Args:
            session_id: Unique session identifier
            storage: Storage port implementation (e.g., BridgeStorageAdapter)
            events: Event port implementation (e.g., DeltaBusAdapter)
            writer: Writer port implementation (e.g., ConciergeAdapter)
            lifecycle: Lifecycle port implementation (e.g., FabricLifecycle)
            k0_sync: Optional K0 sync port for cross-device sync
            db_path: Optional path for the local cold archive SQLite database.
                When None, ``LocalColdArchive`` uses its default path
                (``~/.familyos/k1/sessionstate.db``).  Pass
                ``KernelConfig.sessionstate_db_path`` here to ensure
                checkpoints land in the configured location (SS-02).

        Returns:
            SessionStateManager: Configured with provided ports

        Raises:
            PortProtocolError: If any port doesn't implement required protocol

        Example:
            # Production wiring (future, after Bridge/DeltaBus exist)
            manager = SessionStateFactory.create_with_ports(
                session_id="user-123-session-456",
                storage=BridgeStorageAdapter(bridge_client),
                events=DeltaBusAdapter(deltabus),
                writer=ConciergeAdapter(concierge),
                lifecycle=FabricLifecycle(fabric),
                k0_sync=BridgeSyncAdapter(bridge_client),  # Optional
            )
        """
        # Validate ports
        SessionStateFactory._validate_port(storage, IStoragePort, "storage")
        SessionStateFactory._validate_port(events, IEventPort, "events")
        SessionStateFactory._validate_port(writer, IWriterPort, "writer")
        SessionStateFactory._validate_port(lifecycle, ILifecyclePort, "lifecycle")

        if k0_sync is not None:
            SessionStateFactory._validate_port(k0_sync, IK0SyncPort, "k0_sync")

        logger.info(
            "Creating wired SessionStateManager (session=%s, storage=%s, db_path=%s)",
            session_id[:16] if session_id else "none",
            storage.storage_type if hasattr(storage, "storage_type") else "unknown",
            db_path,
        )

        # SS-02: Build LocalColdArchive with the configured path so
        # checkpoints go to the right location, not the default home-dir path.
        local_cold_archive = LocalColdArchive(db_path=db_path) if db_path is not None else None

        # Create manager with injected ports
        manager = SessionStateManager(
            session_id=session_id,
            storage_port=storage,
            event_port=events,
            writer_port=writer,
            lifecycle_port=lifecycle,
            k0_sync_port=k0_sync,
            local_cold_archive=local_cold_archive,
        )

        return manager

    @staticmethod
    def _validate_port(port: Any, protocol: type, port_name: str) -> None:
        """
        Validate that a port implements the required protocol.

        Uses isinstance() check for ABC/Protocol compliance.

        Args:
            port: Port instance to validate
            protocol: Expected ABC/Protocol type
            port_name: Name for error messages

        Raises:
            PortProtocolError: If port doesn't implement protocol
        """
        if not isinstance(port, protocol):
            raise PortProtocolError(
                port_name=port_name,
                expected=protocol,
                got=type(port),
            )


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================


def create_standalone(
    session_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    checkpoint_interval_s: float | None = None,
) -> SessionStateManager:
    """
    Convenience function for creating standalone SessionStateManager.

    See SessionStateFactory.create_standalone() for details.
    """
    return SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=checkpoint_interval_s,
    )


def create_for_testing(
    session_id: Optional[str] = None,
) -> SessionStateManager:
    """
    Convenience function for creating test SessionStateManager.

    See SessionStateFactory.create_for_testing() for details.
    """
    return SessionStateFactory.create_for_testing(session_id=session_id)
