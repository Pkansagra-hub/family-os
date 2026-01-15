"""
Runner Factory — Generic Pipeline Runner Dispatch

This module provides a factory for creating pipeline runners based on
the runner_type declared in the pipeline specification.

The kernel uses this factory to remain pipeline-agnostic. It doesn't
know or care about P03SequentialRunner vs PipelineRunner - it just
calls `create_runner(spec, registry)` and gets back something with
a `handle()` method.

Runner Types:
- "dag": Uses PipelineRunner for DAG-based execution (default)
- "sequential": Loads a SequentialRunner from the pipeline's module
- "custom": Loads a custom runner class from the specified path

Example:
    >>> from k0.runtime.runner_factory import create_runner
    >>> runner = create_runner(spec, module_registry)
    >>> await runner.handle(message)

Related:
- k0/runtime/schemas.py: PipelineSpec with runner_type field
- k0/runtime/pipeline_runner.py: Default DAG-based runner
- k0/pipelines/p03/sequential_runner.py: Example sequential runner
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from k0.runtime.module_registry import ModuleRegistry
    from k0.runtime.schemas import PipelineSpec

logger = logging.getLogger(__name__)


class RunnerProtocol(Protocol):
    """Protocol that all pipeline runners must implement."""

    async def handle(self, message: Any) -> None:
        """Handle an incoming message/trigger event."""
        ...

    async def on_startup(self, ctx: Any) -> None:
        """Initialize the runner with pipeline context."""
        ...

    async def on_shutdown(self) -> None:
        """Cleanup on shutdown."""
        ...

    @property
    def declared_topics(self) -> tuple[str, ...]:
        """Topics this runner subscribes to."""
        ...


class RunnerLoadError(Exception):
    """Raised when runner cannot be loaded or instantiated."""

    pass


def create_runner(
    spec: "PipelineSpec",
    registry: "ModuleRegistry",
) -> RunnerProtocol:
    """
    Create a pipeline runner based on the spec's runner_type.

    This factory keeps the kernel generic - it doesn't contain any
    pipeline-specific logic. All dispatch is based on metadata in
    the pipeline specification.

    Args:
        spec: Pipeline specification with runner_type field
        registry: Module registry for DAG-based runners

    Returns:
        Runner instance implementing RunnerProtocol

    Raises:
        RunnerLoadError: If runner cannot be loaded or instantiated

    Example:
        >>> spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")
        >>> runner = create_runner(spec, registry)
        >>> # runner is a PipelineRunner (default dag type)

        >>> spec = PipelineSpec.load("k0/contracts/pipelines/p03_consolidation.v1.yaml")
        >>> # spec.runner_type = "sequential"
        >>> runner = create_runner(spec, registry)
        >>> # runner is P03SequentialRunner
    """
    runner_type = spec.runner_type

    logger.info(
        f"Creating runner for {spec.pipeline_id}",
        extra={
            "pipeline_id": spec.pipeline_id,
            "runner_type": runner_type,
            "runner_class": spec.runner_class,
        },
    )

    if runner_type == "dag":
        return _create_dag_runner(spec, registry)
    elif runner_type == "sequential":
        return _create_sequential_runner(spec, registry)
    elif runner_type == "custom":
        return _create_custom_runner(spec, registry)
    else:
        raise RunnerLoadError(
            f"Unknown runner_type '{runner_type}' for pipeline {spec.pipeline_id}"
        )


def _create_dag_runner(
    spec: "PipelineSpec",
    registry: "ModuleRegistry",
) -> RunnerProtocol:
    """Create a DAG-based PipelineRunner (default)."""
    from k0.runtime.pipeline_runner import PipelineRunner

    runner = PipelineRunner(spec, registry)
    logger.debug(
        f"Created DAG runner for {spec.pipeline_id}",
        extra={"pipeline_id": spec.pipeline_id},
    )
    return runner


def _create_sequential_runner(
    spec: "PipelineSpec",
    registry: "ModuleRegistry",
) -> RunnerProtocol:
    """
    Create a sequential runner by loading from the pipeline's module.

    For a pipeline like P03_CONSOLIDATION, this:
    1. Derives the module path: k0.pipelines.p03
    2. Looks for a sequential_runner submodule
    3. Loads the SequentialRunner class
    4. Wraps it in an adapter that conforms to RunnerProtocol
    """
    # Derive pipeline module path from pipeline_id
    # P03_CONSOLIDATION -> p03 -> k0.pipelines.p03
    pipeline_prefix = spec.pipeline_id.split("_")[0].lower()  # "P03" -> "p03"
    module_path = f"k0.pipelines.{pipeline_prefix}.sequential_runner"

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise RunnerLoadError(
            f"Cannot import sequential runner module '{module_path}' "
            f"for pipeline {spec.pipeline_id}: {e}"
        ) from e

    # Look for SequentialRunner class (or pipeline-specific variant)
    # Convention: P03SequentialRunner or SequentialRunner
    class_name = f"{pipeline_prefix.upper()}SequentialRunner"
    runner_class = getattr(module, class_name, None)
    if runner_class is None:
        runner_class = getattr(module, "SequentialRunner", None)
    if runner_class is None:
        raise RunnerLoadError(
            f"Cannot find '{class_name}' or 'SequentialRunner' class "
            f"in module '{module_path}' for pipeline {spec.pipeline_id}"
        )

    # Create adapter that wraps the sequential runner
    from k0.runtime.sequential_adapter import SequentialRunnerAdapter

    runner = SequentialRunnerAdapter(spec, runner_class, registry)
    logger.debug(
        f"Created sequential runner for {spec.pipeline_id}",
        extra={
            "pipeline_id": spec.pipeline_id,
            "runner_class": f"{module_path}:{class_name}",
        },
    )
    return runner


def _create_custom_runner(
    spec: "PipelineSpec",
    registry: "ModuleRegistry",
) -> RunnerProtocol:
    """
    Create a custom runner from the specified runner_class path.

    runner_class format: "module.path:ClassName"
    Example: "k0.pipelines.p03.my_runner:MyCustomRunner"
    """
    if not spec.runner_class:
        raise RunnerLoadError(
            f"runner_type='custom' requires runner_class for pipeline {spec.pipeline_id}"
        )

    # Parse module:class format
    if ":" not in spec.runner_class:
        raise RunnerLoadError(
            f"runner_class must be in 'module.path:ClassName' format, "
            f"got '{spec.runner_class}' for pipeline {spec.pipeline_id}"
        )

    module_path, class_name = spec.runner_class.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise RunnerLoadError(
            f"Cannot import custom runner module '{module_path}' "
            f"for pipeline {spec.pipeline_id}: {e}"
        ) from e

    runner_class = getattr(module, class_name, None)
    if runner_class is None:
        raise RunnerLoadError(
            f"Cannot find class '{class_name}' in module '{module_path}' "
            f"for pipeline {spec.pipeline_id}"
        )

    # Instantiate with spec and registry (custom runners must accept these)
    try:
        runner = runner_class(spec, registry)
    except TypeError as e:
        # Try without registry (some runners don't need it)
        try:
            runner = runner_class(spec)
        except TypeError:
            raise RunnerLoadError(
                f"Cannot instantiate custom runner '{spec.runner_class}' "
                f"for pipeline {spec.pipeline_id}: {e}"
            ) from e

    logger.debug(
        f"Created custom runner for {spec.pipeline_id}",
        extra={
            "pipeline_id": spec.pipeline_id,
            "runner_class": spec.runner_class,
        },
    )
    return runner
