"""
Pipeline Loader - Auto-Discovery System

This module implements auto-discovery and validation for K0 pipelines.
Scans k0/pipelines/ for p*.py files, validates contracts, and boots pipelines.

Related:
- M2 R2.2: Pipeline Loader implementation
- M1 R1.3: PipelineProtocol definition (k0/pipelines/protocol.py)
- M2 R2.1: Syscalls capability-gated storage (k0/kernel/syscalls.py)

Architecture Pattern:
- Fail-fast contract validation
- Explicit lifecycle management (on_startup/on_shutdown)
- Topic-based subscription via BusDispatcher v2
- Capability-gated storage access via Syscalls

Example Usage:
    >>> from k0.pipelines.loader import discover_and_boot_pipelines
    >>> pipelines = await discover_and_boot_pipelines(
    ...     bus_dispatcher=bus_dispatcher,
    ...     uow_factory=lambda: UnitOfWork(...),
    ...     config={"P02": {"batch_size": 100}},
    ...     logger=logger
    ... )
    >>> # Returns: {"P02": <P02EpisodicWritePipeline instance>, ...}
"""

from __future__ import annotations

import importlib
import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.bus.core import BusDispatcher
    from k0.runtime.schemas import PipelineSpec

logger = logging.getLogger(__name__)


@dataclass
class PipelineLoadResult:
    """
    Result from pipeline loading (Issue 3.2.2).

    Contains loaded specs, runner instances, and any errors encountered.

    Attributes:
        loaded_count: Number of pipelines successfully loaded
        specs: List of loaded PipelineSpec objects
        runners: Dictionary mapping pipeline_id to runner instance
        errors: List of error messages from failed loads
    """

    loaded_count: int = 0
    specs: list["PipelineSpec"] = field(default_factory=list)
    runners: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ContractValidationError(Exception):
    """
    Raised when pipeline contract is invalid.

    Indicates missing required attributes, methods, or contract violations.
    """

    pass


async def discover_and_boot_pipelines(
    bus_dispatcher: "BusDispatcher",
    uow_factory: Any,
    config: dict[str, Any],
    logger: logging.Logger,
    syscalls_factory: Any = None,
    pipeline_context_class: Any = None,
) -> dict[str, Any]:
    """
    Discover, validate, and boot all pipelines.

    Scans k0/pipelines/ for p*.py files, validates contracts against
    PipelineProtocol, creates Syscalls adapters, calls on_startup(),
    and subscribes to declared topics.
           ...     required_caps = ("st_hipp_events.write",)
    Args:
        bus_dispatcher: BusDispatcher v2 with subscribe() API
        uow_factory: Factory function returning UnitOfWork for transactions
        config: Pipeline-specific configuration (keyed by pipeline_id)
        logger: Structured logger for boot sequence logging
        syscalls_factory: Optional factory for creating Syscalls instances
                         (defaults to real Syscalls if None - for testing)
        pipeline_context_class: Optional PipelineContext class
                               (defaults to real PipelineContext if None - for testing)

    Returns:
        Dictionary mapping pipeline_id to pipeline instance
        Example: {"P02": <P02EpisodicWritePipeline>, "P03": <P03Consolidation>}

    Raises:
        ContractValidationError: Pipeline contract validation failed
        ImportError: Pipeline module failed to import
        Exception: Pipeline on_startup() failed

    Example:
        >>> pipelines = await discover_and_boot_pipelines(
        ...     bus_dispatcher=bus_dispatcher,
        ...     uow_factory=lambda: UnitOfWork(pool),
        ...     config={"P02": {"batch_size": 100}},
        ...     logger=logger
        ... )
        >>> len(pipelines)
        1
        >>> "P02" in pipelines
        True

    Note:
        - Imports PipelineProtocol, PipelineContext from k0.pipelines.protocol
          (defined in M1 R1.3, already implemented)
        - Imports Syscalls from k0.kernel.syscalls (M2 R2.1, already implemented)
        - Processes pipelines in sorted order by filename
        - Stops boot sequence on first validation error (fail-fast)
        - Dependency injection for syscalls_factory and pipeline_context_class
          enables testing without triggering FastAPI import cascade
    """
    # Dependency injection: Use provided factories or default to real imports
    if syscalls_factory is None:
        from k0.kernel.syscalls import Syscalls  # M2 R2.1

        def _create_syscalls(pid: str, caps: set[str], uow: Any) -> Any:
            return Syscalls(pid, caps, uow)

        syscalls_factory_fn = _create_syscalls
    else:
        syscalls_factory_fn = syscalls_factory

    if pipeline_context_class is None:
        from k0.pipelines.protocol import PipelineContext

        pipeline_context_cls = PipelineContext
    else:
        pipeline_context_cls = pipeline_context_class

    pipelines: dict[str, Any] = {}
    pipeline_dir = Path(__file__).parent

    logger.info(
        f"Starting pipeline discovery in {pipeline_dir}",
        extra={"pipeline_dir": str(pipeline_dir)},
    )

    # Scan for p*.py files (sorted for deterministic boot order)
    # Filter to only include files starting with 'p' followed by digits (p01, p02, etc.)
    all_p_files = pipeline_dir.glob("p*.py")
    pipeline_modules = sorted(
        [p for p in all_p_files if p.stem[0] == "p" and len(p.stem) > 1 and p.stem[1].isdigit()]
    )
    logger.debug(
        f"Found {len(pipeline_modules)} pipeline modules",
        extra={"count": len(pipeline_modules), "modules": [p.name for p in pipeline_modules]},
    )

    for module_path in pipeline_modules:
        # Extract pipeline_id from filename (p02_episodic_write.py -> P02_EPISODIC_WRITE)
        pipeline_id = module_path.stem.upper()

        logger.info(
            f"Loading pipeline: {pipeline_id}",
            extra={"pipeline_id": pipeline_id, "module_path": str(module_path)},
        )

        try:
            # Import module
            module = importlib.import_module(f"k0.pipelines.{module_path.stem}")
            logger.debug(
                f"Imported module: k0.pipelines.{module_path.stem}",
                extra={"pipeline_id": pipeline_id},
            )

            # Find pipeline class (must implement PipelineProtocol)
            pipeline_class = _find_pipeline_class(module)
            logger.debug(
                f"Found pipeline class: {pipeline_class.__name__}",
                extra={"pipeline_id": pipeline_id, "class_name": pipeline_class.__name__},
            )

            # Validate contract
            _validate_contract(pipeline_class, pipeline_id)
            logger.info(
                f"Contract validation passed for {pipeline_id}",
                extra={
                    "pipeline_id": pipeline_id,
                    "contract_version": pipeline_class.contract_version,
                    "declared_topics": list(pipeline_class.declared_topics),
                    "required_caps": list(pipeline_class.required_caps),
                },
            )

            # Check kernel version compatibility (if min_kernel_semver in manifest)
            # (Future: Add manifest support in M5)

            # Create syscalls adapter with granted capabilities
            granted_caps = set(pipeline_class.required_caps)
            syscalls = syscalls_factory_fn(pipeline_id, granted_caps, uow_factory)
            logger.debug(
                f"Created Syscalls adapter for {pipeline_id}",
                extra={"pipeline_id": pipeline_id, "granted_caps": list(granted_caps)},
            )

            # Create pipeline context
            ctx = pipeline_context_cls(
                syscalls=syscalls,
                config=config.get(pipeline_id, {}),
                logger=logger.getChild(pipeline_id),  # Child logger with pipeline_id prefix
            )

            # Instantiate pipeline
            pipeline = pipeline_class()
            logger.debug(
                f"Instantiated pipeline: {pipeline_id}",
                extra={"pipeline_id": pipeline_id},
            )

            # Call on_startup lifecycle
            await pipeline.on_startup(ctx)
            logger.info(
                f"Called on_startup() for {pipeline_id}",
                extra={"pipeline_id": pipeline_id},
            )

            # Subscribe to declared topics
            for topic in pipeline_class.declared_topics:
                bus_dispatcher.subscribe(topic, pipeline.handle)
                logger.info(
                    f"Subscribed {pipeline_id} to {topic}",
                    extra={"pipeline_id": pipeline_id, "topic": topic},
                )

            # Store pipeline instance
            pipelines[pipeline_id] = pipeline
            logger.info(
                f"Booted pipeline: {pipeline_id}",
                extra={
                    "pipeline_id": pipeline_id,
                    "topics": list(pipeline_class.declared_topics),
                    "concurrency": pipeline_class.concurrency,
                    "max_queue": pipeline_class.max_queue,
                },
            )

        except ContractValidationError as e:
            logger.error(
                f"Contract validation failed for {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id, "error": str(e)},
                exc_info=True,
            )
            raise
        except ImportError as e:
            logger.error(
                f"Failed to import {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id, "error": str(e)},
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                f"Failed to boot {pipeline_id}: {e}",
                extra={"pipeline_id": pipeline_id, "error": str(e)},
                exc_info=True,
            )
            raise

    logger.info(
        f"Booted {len(pipelines)} pipelines: {list(pipelines.keys())}",
        extra={"count": len(pipelines), "pipeline_ids": list(pipelines.keys())},
    )
    return pipelines


def _find_pipeline_class(module: Any) -> type:
    """
    Find class implementing PipelineProtocol in module.

    Searches for a class with 'pipeline_id' attribute, which is a required
    property of PipelineProtocol.

    Args:
        module: Imported Python module containing pipeline class

    Returns:
        Class implementing PipelineProtocol

    Raises:
        ContractValidationError: No class with pipeline_id found

    Example:
        >>> import k0.pipelines.p02_episodic_write as p02
        >>> pipeline_class = _find_pipeline_class(p02)
        >>> pipeline_class.pipeline_id
        'P02'
    """
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Check if class (not imported) and has pipeline_id attribute
        if isinstance(obj, type) and hasattr(obj, "pipeline_id"):
            try:
                logger.debug(
                    f"Found pipeline class: {obj.__name__}",
                    extra={
                        "class_name": obj.__name__,
                        "module": getattr(module, "__name__", "unknown"),
                    },
                )
            except Exception:
                # Guard against mock objects in tests
                pass
            return obj

    raise ContractValidationError(
        f"No class with pipeline_id found in module {getattr(module, '__name__', 'unknown')}"
    )


def _validate_contract(pipeline_class: type, expected_id: str) -> None:
    """
    Validate pipeline contract against PipelineProtocol.

    Checks for:
    - All 6 required class properties (pipeline_id, contract_version, declared_topics,
      concurrency, max_queue, required_caps)
    - All 3 required lifecycle methods (on_startup, on_shutdown, handle)
    - pipeline_id matches expected filename-based ID
    - declared_topics is non-empty

    Args:
        pipeline_class: Class to validate against PipelineProtocol
        expected_id: Expected pipeline_id (derived from filename)

    Raises:
        ContractValidationError: Contract validation failed

    Example:
        >>> class ValidPipeline:
        ...     pipeline_id = "P02"
        ...     contract_version = 1
        ...     declared_topics = ("event.created",)
        ...     concurrency = 1
        ...     max_queue = 512
        ...     required_caps = ("st_hipp_events.write",)
        ...     async def on_startup(self, ctx): pass
        ...     async def on_shutdown(self): pass
        ...     async def handle(self, msg): pass
        >>> _validate_contract(ValidPipeline, "P02")  # No exception
    """
    # Check required class properties (6 required)
    required_attrs = [
        "pipeline_id",
        "contract_version",
        "declared_topics",
        "concurrency",
        "max_queue",
        "required_caps",
    ]

    for attr in required_attrs:
        if not hasattr(pipeline_class, attr):
            raise ContractValidationError(
                f"Missing required attribute: {attr} in {pipeline_class.__name__}"
            )

    # Check pipeline_id matches filename
    if pipeline_class.pipeline_id != expected_id:
        raise ContractValidationError(
            f"pipeline_id mismatch: {pipeline_class.pipeline_id} != {expected_id} "
            f"(filename-based ID) in {pipeline_class.__name__}"
        )

    # Check declared_topics is non-empty
    if not pipeline_class.declared_topics:
        raise ContractValidationError(
            f"declared_topics cannot be empty in {pipeline_class.__name__}"
        )

    # Check required methods (3 required)
    required_methods = ["on_startup", "on_shutdown", "handle"]
    for method in required_methods:
        if not hasattr(pipeline_class, method):
            raise ContractValidationError(
                f"Missing required method: {method} in {pipeline_class.__name__}"
            )

    logger.debug(
        f"Contract validation passed for {pipeline_class.__name__}",
        extra={
            "class_name": pipeline_class.__name__,
            "pipeline_id": pipeline_class.pipeline_id,
            "attributes_checked": len(required_attrs),
            "methods_checked": len(required_methods),
        },
    )


async def load_yaml_pipeline_specs(
    contracts_dir: Path | None = None,
) -> PipelineLoadResult:
    """
    Load pipeline specifications from YAML files (Issue 3.2.2).

    Scans the contracts directory for p*.yaml files and loads them
    as PipelineSpec objects. This is a lightweight loader that only
    parses specs without creating runners.

    Args:
        contracts_dir: Directory containing pipeline YAML specs.
                       Defaults to k0/contracts/pipelines/

    Returns:
        PipelineLoadResult with loaded specs and any errors

    Example:
        result = await load_yaml_pipeline_specs()
        for spec in result.specs:
            if spec.triggers:
                scheduler.register_pipeline(spec)
    """
    from k0.runtime.schemas import PipelineSpec

    result = PipelineLoadResult()

    if contracts_dir is None:
        contracts_dir = Path(__file__).parent.parent / "contracts" / "pipelines"

    if not contracts_dir.exists():
        result.errors.append(f"Contracts directory not found: {contracts_dir}")
        logger.warning(
            f"Pipeline contracts directory not found: {contracts_dir}",
            extra={"contracts_dir": str(contracts_dir)},
        )
        return result

    # Find all p*.yaml and p*.yml files
    spec_files = sorted(list(contracts_dir.glob("p*.yaml")) + list(contracts_dir.glob("p*.yml")))

    logger.info(
        f"Found {len(spec_files)} pipeline specification files",
        extra={
            "contracts_dir": str(contracts_dir),
            "spec_count": len(spec_files),
            "spec_files": [f.name for f in spec_files],
        },
    )

    for spec_path in spec_files:
        try:
            spec = PipelineSpec.load(spec_path)
            result.specs.append(spec)
            result.loaded_count += 1

            logger.debug(
                f"Loaded pipeline spec: {spec.pipeline_id}",
                extra={
                    "pipeline_id": spec.pipeline_id,
                    "version": spec.version,
                    "triggers": len(spec.triggers) if spec.triggers else 0,
                    "spec_path": str(spec_path),
                },
            )

        except Exception as e:
            error_msg = f"Failed to load {spec_path.name}: {e}"
            result.errors.append(error_msg)
            logger.error(
                error_msg,
                extra={"spec_path": str(spec_path), "error": str(e)},
                exc_info=True,
            )

    logger.info(
        f"Loaded {result.loaded_count} pipeline specs ({len(result.errors)} errors)",
        extra={
            "loaded_count": result.loaded_count,
            "error_count": len(result.errors),
            "pipeline_ids": [s.pipeline_id for s in result.specs],
        },
    )

    return result
