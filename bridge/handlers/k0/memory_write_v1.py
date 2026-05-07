"""Hand-written K0 consumer impl for the ``memory.write.v1`` contract.

The generated module
:mod:`bridge._generated.k0.handlers.memory_write_v1` defines a
``register_handlers(runtime, impl=...)`` entry-point. This module
provides the concrete ``impl`` callable that takes the validated
Pydantic model and forwards into :mod:`k0.pipelines.p02_write_ingest`.

Keeping the impl outside the generated tree means regeneration never
overwrites business logic. Per the MS-2.5 contract design, the wiring
is the only line that knows about both K0 internals and the bridge
contract — it sits at the boundary by design.
"""

from __future__ import annotations

import logging
from typing import Any

from bridge._generated.k0.handlers.memory_write_v1 import register_handlers as _register_generated
from bridge._generated.k0.models.memory_write_v1 import MemoryWriteV1
from bridge.runtime import BridgeRuntime
from k0.pipelines.p02_write_ingest import ingest as _p02_ingest

_log = logging.getLogger("bridge.k0.handlers.memory_write_v1")


async def handle_memory_write_v1(payload: MemoryWriteV1) -> dict[str, Any]:
    """Forward a validated atom into K0 P02 and return its ack envelope."""
    _log.info(
        "k0.memory_write_v1.received",
        extra={
            "topic": "memory.write.v1",
            "operation": getattr(payload, "operation", None),
            "schema_version": getattr(payload, "schema_version", None),
        },
    )
    return _p02_ingest(payload)


def install(runtime: BridgeRuntime) -> None:
    """Register the K0-side handler on ``runtime``."""
    _register_generated(runtime, impl=handle_memory_write_v1)
