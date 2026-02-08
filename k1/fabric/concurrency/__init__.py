"""
k1.fabric.concurrency -- Concurrency model for the Capability Fabric.

Implements FAB-003 (Accepted): Hybrid async facade + WFQ-scheduled agent execution.
No FABRIC_MAILBOX. Uses asyncio.Semaphore for backpressure, deadline enforcement
via TimeoutGuard, and async dispatching via FabricDispatcher.

Exports:
  FabricDispatcher -- Async request dispatcher with bounded parallelism (4.4.1)
  FabricDispatcherConfig -- Configuration for FabricDispatcher
  DispatchResult -- Result envelope from dispatch operation
  DispatcherHealth -- Health snapshot of dispatcher state
  DispatcherError -- Base exception for dispatcher operations
  DispatcherOverloadedError -- Raised when dispatcher rejects due to backpressure
  DispatcherShutdownError -- Raised when dispatch is called after shutdown
  TimeoutGuard -- Deadline enforcement for capability requests (4.4.2)
  TimeoutGuardConfig -- Configuration for TimeoutGuard
  DeadlineExceededError -- Raised when request exceeds deadline
  BackpressureLevel -- Enum: NORMAL, WARNING, SHEDDING, SATURATED
  DEFAULT_MAX_CONCURRENT -- Default semaphore limit (10)
  DEFAULT_WARNING_THRESHOLD -- Default warning threshold (0.80)
  DEFAULT_SHEDDING_THRESHOLD -- Default shedding threshold (0.95)
  PRESSURE_WARNING_TOPIC -- Event topic for pressure warnings
  PRESSURE_SHEDDING_TOPIC -- Event topic for pressure shedding
"""

from k1.fabric.concurrency.dispatcher import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_SHEDDING_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    PRESSURE_SHEDDING_TOPIC,
    PRESSURE_WARNING_TOPIC,
    BackpressureLevel,
    DispatcherError,
    DispatcherHealth,
    DispatcherOverloadedError,
    DispatcherShutdownError,
    DispatchResult,
    FabricDispatcher,
    FabricDispatcherConfig,
)
from k1.fabric.concurrency.timeout import DeadlineExceededError, TimeoutGuard, TimeoutGuardConfig

__all__ = [
    # --- Dispatcher (4.4.1 / FAB-003) ---
    "FabricDispatcher",
    "FabricDispatcherConfig",
    "DispatchResult",
    "DispatcherHealth",
    "DispatcherError",
    "DispatcherOverloadedError",
    "DispatcherShutdownError",
    "BackpressureLevel",
    "DEFAULT_MAX_CONCURRENT",
    "DEFAULT_WARNING_THRESHOLD",
    "DEFAULT_SHEDDING_THRESHOLD",
    "PRESSURE_WARNING_TOPIC",
    "PRESSURE_SHEDDING_TOPIC",
    # --- TimeoutGuard (4.4.2 / FAB-003) ---
    "TimeoutGuard",
    "TimeoutGuardConfig",
    "DeadlineExceededError",
]
