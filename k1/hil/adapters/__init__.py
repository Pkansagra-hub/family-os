"""Production adapters for the HIL service (E7.M1.1).

These adapters wire the unified `HumanInTheLoopService` into kernel-level
infrastructure (the K1 IBus). They satisfy the HIL-local `IEventPort` and
`ILLMPort` Protocols structurally — neither this package nor the consumers
import the Protocols at runtime.
"""

from __future__ import annotations

from k1.hil.adapters.event_bus import KernelHILEventAdapter

__all__ = ["KernelHILEventAdapter"]
