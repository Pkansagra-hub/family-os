"""HTTP handlers for the observability port (`/k0/obs.emit`)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from k0.ports.errors import ErrorEnvelope, KERNEL_COMPONENT_OBSERVE

router = APIRouter(prefix="/k0", tags=["observability"])


class ObservabilityPayload(BaseModel):
    """Envelope used to carry metrics/spans/log batches."""

    kind: str = Field(..., description="telemetry batch type")
    body: dict[str, Any]


@router.post(
    "/obs.emit",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_501_NOT_IMPLEMENTED: {
            "description": "Kernel implementation pending",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "NOT_IMPLEMENTED",
                            "component": "kernel.observe",
                            "reason": "ENDPOINT_DISABLED",
                            "trace_id": "c99fd6a9-4f4b-4bbc-8d53-05a40f6d27c2",
                        }
                    }
                }
            },
        }
    },
)
async def emit(_: ObservabilityPayload) -> JSONResponse:
    """Stub that will later forward telemetry to OTEL exporters."""

    trace_id = str(uuid.uuid4())
    envelope = ErrorEnvelope(
        code="NOT_IMPLEMENTED",
        component=KERNEL_COMPONENT_OBSERVE,
        trace_id=trace_id,
        reason="ENDPOINT_DISABLED",
        hint="obs.emit is not yet wired to exporters",
    )
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content=envelope.as_payload(),
    )
