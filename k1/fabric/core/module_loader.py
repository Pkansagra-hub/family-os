"""
k1.fabric.core.module_loader -- Module Loader (Subsystem 2).

Manages the full lifecycle of contract loading: initial scan, hot-reload
watching, programmatic registration, and file-to-capability tracking.

Issues Implemented:
  2.3.1 -- ModuleLoader class (constructor, start, stop, lifecycle)
  2.3.2 -- Hot-reload watcher (polling daemon thread, change detection)
  2.3.3 -- scan_directory() (recursive YAML discovery, parse, register)
  2.3.4 -- register_from_dict() (programmatic registration from dict)

Design Decisions:
  - FAB-12: All contracts validated against schema before registration
  - Polling-based watcher (no watchdog dependency), configurable interval
  - Atomic per-contract reload: only the changed file is re-parsed
  - On validation failure: log error, keep old contract, emit event
  - Constructor injection for registry, event_port, contracts_dir
  - Singleton per Fabric instance (enforced by caller)
  - Daemon thread for watch loop (auto-stops with main process)

Thread Safety:
  All mutable state guarded by RLock. The watcher thread only mutates
  _file_map and _mtime_cache under lock, then delegates to registry
  (which has its own RLock).

References:
  - fabric_discussion.md Section 7 (Hot-Reload Mechanism)
  - fabric.mmd Subsystem 2 (Module Loader block)
  - Epic 2.3 in fabric-implementation-plan.md

Exports:
  ModuleLoader -- Contract lifecycle manager
  ModuleLoaderError -- Base exception for loader operations
  ScanResult -- Frozen result of scan_directory()
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from k1.fabric.contracts import (
    ContractParseError,
    ContractUnion,
    parse_contract,
    parse_contract_body,
)
from k1.fabric.core.contract_validator import ContractValidationError, ContractValidator
from k1.fabric.core.registry import (
    CapabilityRegistry,
    DuplicateCapabilityError,
    EventPort,
    VersionConflictError,
    VersionRegressionError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event topic constants
# ---------------------------------------------------------------------------

EVENT_CONTRACT_VALIDATION_FAILED = "k1.fabric.contract.validation.failed.v1"
EVENT_CONTRACT_HOT_RELOADED = "k1.fabric.contract.hot_reloaded.v1"
EVENT_CONTRACT_REMOVED = "k1.fabric.contract.removed.v1"

# Subdirectories to scan under the contracts root
_CONTRACT_SUBDIRS = ("tools", "agents", "prompts", "workflows")

# File extensions recognized as contract files
_YAML_EXTENSIONS = frozenset((".yaml", ".yml"))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ModuleLoaderError(Exception):
    """Base exception for module loader operations."""


# ---------------------------------------------------------------------------
# 2.3.3 -- ScanResult (returned by scan_directory)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanResult:
    """
    Frozen result of a scan_directory() operation.

    Attributes:
        loaded: Number of contracts successfully loaded and registered.
        failed: Number of contracts that failed parsing or validation.
        errors: Details of each failure ({file: str, error: str}).
        contracts: List of canonical names that were registered.
    """

    loaded: int = 0
    failed: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    contracts: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 2.3.1 -- ModuleLoader class
# ---------------------------------------------------------------------------


class ModuleLoader:
    """
    Contract lifecycle manager for the Capability Fabric.

    Owns the full lifecycle: initial directory scan, hot-reload watching,
    programmatic registration, and file-to-capability tracking.

    Constructor Args:
        registry: The CapabilityRegistry to register/unregister contracts in.
        contracts_dir: Root directory containing tools/, agents/, prompts/,
            workflows/ subdirectories with YAML contract files.
        event_port: Optional event bus for emitting lifecycle events.
            Conforms to the EventPort protocol (emit(event_type, payload)).
        validator: Optional shared ContractValidator. If None, creates one.
        poll_interval_s: Hot-reload polling interval in seconds (default 2.0).

    Thread Safety:
        Internal state (_file_map, _mtime_cache) guarded by _lock (RLock).
        The watcher thread is a daemon -- it terminates when the main
        process exits or when stop_watching() is called.

    Lifecycle:
        1. Construct with registry + contracts_dir
        2. Call scan_directory() for initial load (or start() for scan + watch)
        3. Optionally call start_watching() for hot-reload
        4. Call stop_watching() or stop() to clean up

    References:
        - Epic 2.3 issues 2.3.1-2.3.4
        - fabric_discussion.md Section 7
    """

    __slots__ = (
        "_registry",
        "_contracts_dir",
        "_event_port",
        "_validator",
        "_poll_interval_s",
        "_lock",
        "_file_map",
        "_mtime_cache",
        "_watcher_thread",
        "_stop_event",
        "_running",
    )

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        contracts_dir: Union[str, Path],
        event_port: Optional[EventPort] = None,
        validator: Optional[ContractValidator] = None,
        poll_interval_s: float = 2.0,
    ) -> None:
        self._registry = registry
        self._contracts_dir = Path(contracts_dir)
        self._event_port = event_port
        self._validator = validator or ContractValidator()
        self._poll_interval_s = max(0.1, poll_interval_s)

        self._lock = threading.RLock()

        # file path -> canonical capability name
        self._file_map: Dict[Path, str] = {}

        # file path -> last known mtime (float, seconds since epoch)
        self._mtime_cache: Dict[Path, float] = {}

        # Watcher thread state
        self._watcher_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True if the watcher thread is alive."""
        return (
            self._running and self._watcher_thread is not None and self._watcher_thread.is_alive()
        )

    @property
    def contracts_dir(self) -> Path:
        """Root contracts directory."""
        return self._contracts_dir

    @property
    def file_count(self) -> int:
        """Number of tracked contract files."""
        with self._lock:
            return len(self._file_map)

    @property
    def tracked_files(self) -> Dict[str, str]:
        """
        Return a copy of file_map as {str(path): capability_name}.

        For diagnostics / health reporting.
        """
        with self._lock:
            return {str(p): n for p, n in self._file_map.items()}

    # ------------------------------------------------------------------
    # 2.3.1 -- Lifecycle: start() / stop()
    # ------------------------------------------------------------------

    def start(self, *, watch: bool = True) -> ScanResult:
        """
        Bootstrap the loader: scan directory and optionally start watcher.

        This is the primary entry point at Fabric startup.

        Args:
            watch: If True (default), start the hot-reload watcher
                after the initial scan.

        Returns:
            ScanResult from the initial directory scan.
        """
        result = self.scan_directory()

        if watch:
            self.start_watching()

        return result

    def stop(self) -> None:
        """
        Stop the watcher and clean up.

        Idempotent -- safe to call multiple times.
        """
        self.stop_watching()

    # ------------------------------------------------------------------
    # 2.3.2 -- Hot-reload watcher
    # ------------------------------------------------------------------

    def start_watching(self) -> None:
        """
        Start the polling-based hot-reload watcher in a daemon thread.

        The watcher polls for file changes at the configured interval.
        It detects:
          - New files (create)
          - Modified files (mtime change)
          - Deleted files (missing from disk)

        Idempotent -- calling when already watching is a no-op.
        """
        if self.is_running:
            logger.debug("Watcher already running, skipping start_watching()")
            return

        self._stop_event.clear()
        self._running = True

        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            name="fabric-module-watcher",
            daemon=True,
        )
        self._watcher_thread.start()
        logger.info(
            "Module watcher started (poll_interval=%.1fs, dir=%s)",
            self._poll_interval_s,
            self._contracts_dir,
        )

    def stop_watching(self) -> None:
        """
        Stop the watcher thread.

        Blocks until the thread exits (with timeout).
        Idempotent -- safe to call when not watching.
        """
        if not self._running:
            return

        self._stop_event.set()
        self._running = False

        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=self._poll_interval_s * 3)
            if self._watcher_thread.is_alive():
                logger.warning("Watcher thread did not terminate in time")

        self._watcher_thread = None
        logger.info("Module watcher stopped")

    def _watch_loop(self) -> None:
        """
        Main polling loop for the watcher thread.

        Runs until _stop_event is set. Each cycle:
          1. Discover current YAML files on disk
          2. Detect new files (not in _mtime_cache)
          3. Detect modified files (mtime changed)
          4. Detect deleted files (in _mtime_cache but not on disk)
          5. Process each change atomically
        """
        logger.debug("Watcher loop entered")

        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("Error in watcher poll cycle")

            # Sleep in small increments so stop_event is responsive
            self._stop_event.wait(timeout=self._poll_interval_s)

        logger.debug("Watcher loop exited")

    def _poll_once(self) -> None:
        """
        Single poll cycle: detect and process all file changes.

        Called by _watch_loop() each iteration.
        """
        current_files = self._discover_yaml_files()
        current_paths: Set[Path] = set(current_files)

        with self._lock:
            known_paths: Set[Path] = set(self._mtime_cache.keys())

        # Detect new and modified files
        for fpath in current_files:
            try:
                mtime = fpath.stat().st_mtime
            except OSError:
                continue  # Race: file deleted between discovery and stat

            with self._lock:
                old_mtime = self._mtime_cache.get(fpath)

            if old_mtime is None:
                # New file
                self._handle_file_created(fpath, mtime)
            elif mtime != old_mtime:
                # Modified file
                self._handle_file_modified(fpath, mtime)

        # Detect deleted files
        deleted = known_paths - current_paths
        for fpath in deleted:
            self._handle_file_deleted(fpath)

    def _handle_file_created(self, fpath: Path, mtime: float) -> None:
        """Handle a newly discovered contract file."""
        logger.debug("New contract file detected: %s", fpath)
        try:
            contract = parse_contract(
                fpath,
                validator=self._validator,
            )
        except (ContractParseError, ContractValidationError, FileNotFoundError) as exc:
            logger.warning("Failed to parse new file %s: %s", fpath, exc)
            self._emit_validation_failed(fpath, exc)
            # Still track mtime to avoid re-processing every cycle
            with self._lock:
                self._mtime_cache[fpath] = mtime
            return
        except Exception as exc:
            logger.exception("Unexpected error parsing new file %s", fpath)
            self._emit_validation_failed(fpath, exc)
            with self._lock:
                self._mtime_cache[fpath] = mtime
            return

        name = _get_contract_name(contract)

        try:
            self._registry.register(contract, skip_validation=True)
        except (DuplicateCapabilityError, VersionConflictError, VersionRegressionError):
            # Name conflict -- unregister old, then re-register
            self._registry.unregister(name)
            self._registry.register(contract, skip_validation=True)

        with self._lock:
            self._file_map[fpath] = name
            self._mtime_cache[fpath] = mtime

        self._emit(
            EVENT_CONTRACT_HOT_RELOADED,
            {"file": str(fpath), "name": name, "action": "created"},
        )

    def _handle_file_modified(self, fpath: Path, mtime: float) -> None:
        """Handle a modified contract file: re-parse, validate, swap."""
        logger.debug("Modified contract file detected: %s", fpath)

        # Parse the new version
        try:
            new_contract = parse_contract(
                fpath,
                validator=self._validator,
            )
        except (ContractParseError, ContractValidationError, FileNotFoundError) as exc:
            logger.warning(
                "Validation failed for modified file %s: %s -- keeping old contract",
                fpath,
                exc,
            )
            self._emit_validation_failed(fpath, exc)
            # Update mtime so we don't re-try every cycle
            with self._lock:
                self._mtime_cache[fpath] = mtime
            return
        except Exception as exc:
            logger.exception("Unexpected error parsing modified file %s", fpath)
            self._emit_validation_failed(fpath, exc)
            with self._lock:
                self._mtime_cache[fpath] = mtime
            return

        new_name = _get_contract_name(new_contract)

        with self._lock:
            old_name = self._file_map.get(fpath)

        # Unregister old contract (if tracked)
        if old_name is not None:
            self._registry.unregister(old_name)

        # Register new version
        try:
            self._registry.register(new_contract, skip_validation=True)
        except (DuplicateCapabilityError, VersionConflictError, VersionRegressionError):
            # Name collision with another file's contract
            self._registry.unregister(new_name)
            self._registry.register(new_contract, skip_validation=True)

        with self._lock:
            # If name changed, clean up old mapping
            if old_name is not None and old_name != new_name:
                # Remove stale name from file_map reverse lookups
                pass  # _file_map is forward-only (path -> name)
            self._file_map[fpath] = new_name
            self._mtime_cache[fpath] = mtime

        self._emit(
            EVENT_CONTRACT_HOT_RELOADED,
            {"file": str(fpath), "name": new_name, "action": "modified"},
        )

    def _handle_file_deleted(self, fpath: Path) -> None:
        """Handle a deleted contract file: unregister from registry."""
        logger.debug("Deleted contract file detected: %s", fpath)

        with self._lock:
            name = self._file_map.pop(fpath, None)
            self._mtime_cache.pop(fpath, None)

        if name is not None:
            self._registry.unregister(name)
            self._emit(
                EVENT_CONTRACT_REMOVED,
                {"file": str(fpath), "name": name, "action": "deleted"},
            )

    # ------------------------------------------------------------------
    # 2.3.3 -- scan_directory()
    # ------------------------------------------------------------------

    def scan_directory(
        self,
        path: Optional[Union[str, Path]] = None,
    ) -> ScanResult:
        """
        Scan a contracts directory for YAML files, parse, and register.

        Recursively discovers .yaml/.yml files in tools/, agents/,
        prompts/, workflows/ subdirectories. Each file is parsed via
        parse_contract(), validated, and registered in the registry.

        Args:
            path: Override directory to scan. If None, uses the
                contracts_dir from constructor.

        Returns:
            ScanResult with loaded/failed counts, error details,
            and list of registered capability names.
        """
        scan_dir = Path(path) if path is not None else self._contracts_dir
        yaml_files = self._discover_yaml_files(scan_dir)

        loaded_names: List[str] = []
        errors: List[Dict[str, str]] = []

        for fpath in yaml_files:
            try:
                contract = parse_contract(
                    fpath,
                    validator=self._validator,
                )
            except Exception as exc:
                errors.append({"file": str(fpath), "error": str(exc)})
                logger.warning("Failed to parse %s: %s", fpath, exc)
                # Track mtime even for failures so watcher can detect fixes
                try:
                    mtime = fpath.stat().st_mtime
                    with self._lock:
                        self._mtime_cache[fpath] = mtime
                except OSError:
                    pass
                continue

            name = _get_contract_name(contract)

            try:
                self._registry.register(contract, skip_validation=True)
            except (DuplicateCapabilityError, VersionConflictError, VersionRegressionError):
                errors.append(
                    {
                        "file": str(fpath),
                        "error": f"Duplicate capability name: {name}",
                    }
                )
                logger.warning("Duplicate name %s from %s, skipping", name, fpath)
                continue

            # Track file -> name mapping and mtime
            try:
                mtime = fpath.stat().st_mtime
            except OSError:
                mtime = 0.0

            with self._lock:
                self._file_map[fpath] = name
                self._mtime_cache[fpath] = mtime

            loaded_names.append(name)

        logger.info(
            "scan_directory complete: loaded=%d, failed=%d, dir=%s",
            len(loaded_names),
            len(errors),
            scan_dir,
        )

        return ScanResult(
            loaded=len(loaded_names),
            failed=len(errors),
            errors=errors,
            contracts=loaded_names,
        )

    # ------------------------------------------------------------------
    # 2.3.4 -- register_from_dict()
    # ------------------------------------------------------------------

    def register_from_dict(
        self,
        contract_dict: Dict[str, Any],
        *,
        contract_type: Optional[str] = None,
        skip_validation: bool = False,
    ) -> ContractUnion:
        """
        Parse and register a contract from a raw dictionary.

        Designed for MCP runtime tool discovery and programmatic
        registration (e.g., dynamic tool injection from external
        systems that supply contract definitions as dicts).

        If contract_type is provided, uses parse_contract_body()
        which expects an already-unwrapped body dict. If contract_type
        is None, uses parse_contract() which auto-detects from root key.

        Args:
            contract_dict: Raw contract dict. Either:
                - Full YAML-style dict with root key (tool_contract: {...})
                - Unwrapped body dict (when contract_type is specified)
            contract_type: Explicit type hint. One of:
                'tool_contract', 'agent_contract', 'prompt_contract',
                'workflow_contract'. If None, auto-detect from root key.
            skip_validation: If True, skip schema/semantic validation.

        Returns:
            The parsed and registered contract.

        Raises:
            ContractParseError: Cannot detect or parse contract.
            ContractValidationError: Schema or semantic rule violation.
            DuplicateCapabilityError: Name already registered.
        """
        validator = None if skip_validation else self._validator

        if contract_type is not None:
            contract = parse_contract_body(
                contract_dict,
                contract_type,
                validator=validator,
                skip_validation=skip_validation,
            )
        else:
            contract = parse_contract(
                contract_dict,
                validator=validator,
                skip_validation=skip_validation,
            )

        self._registry.register(contract, skip_validation=True)

        name = _get_contract_name(contract)
        logger.debug("Registered from dict: %s", name)

        return contract

    # ------------------------------------------------------------------
    # Private: File discovery
    # ------------------------------------------------------------------

    def _discover_yaml_files(
        self,
        root: Optional[Path] = None,
    ) -> List[Path]:
        """
        Recursively discover all YAML files in known subdirectories.

        Scans tools/, agents/, prompts/, workflows/ under the root.
        Returns a stable-sorted list for deterministic ordering.
        """
        scan_root = root or self._contracts_dir
        yaml_files: List[Path] = []

        for subdir in _CONTRACT_SUBDIRS:
            sub_path = scan_root / subdir
            if not sub_path.is_dir():
                continue
            for ext in _YAML_EXTENSIONS:
                yaml_files.extend(sub_path.glob(f"**/*{ext}"))

        # Sort for deterministic ordering
        yaml_files.sort()
        return yaml_files

    # ------------------------------------------------------------------
    # Private: Event emission
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit event if event_port is wired."""
        if self._event_port is None:
            return
        try:
            self._event_port.emit(event_type, payload)
        except Exception:
            logger.exception("Failed to emit event %s", event_type)

    def _emit_validation_failed(self, fpath: Path, exc: Exception) -> None:
        """Emit a contract validation failure event."""
        self._emit(
            EVENT_CONTRACT_VALIDATION_FAILED,
            {
                "file": str(fpath),
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _get_contract_name(contract: ContractUnion) -> str:
    """Extract the canonical name from any contract type."""
    return getattr(contract, "name", "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "ModuleLoader",
    "ModuleLoaderError",
    "ScanResult",
    "EVENT_CONTRACT_VALIDATION_FAILED",
    "EVENT_CONTRACT_HOT_RELOADED",
    "EVENT_CONTRACT_REMOVED",
]
