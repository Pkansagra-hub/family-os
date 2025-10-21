"""HTTP handlers for driver handshake coordination."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, cast
from urllib.parse import urlparse

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from k0.outbox import DriverHandshakeError, DriverWorkerPool
from k0.ports.errors import KERNEL_COMPONENT_DRIVER, ErrorEnvelope

router = APIRouter(prefix="/k0", tags=["drivers"])


def _format_timestamp(moment: datetime) -> str:
    normalized = moment.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _resolve_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "cognitive_trace_id", None)
    if trace_id:
        return str(trace_id)
    generated = uuid.uuid4().hex
    request.state.cognitive_trace_id = generated
    return generated


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    reason: str,
    hint: str | None = None,
) -> JSONResponse:
    trace_id = _resolve_trace_id(request)
    envelope = ErrorEnvelope(
        code=code,
        component=KERNEL_COMPONENT_DRIVER,
        trace_id=trace_id,
        reason=reason,
        hint=hint,
    )
    return JSONResponse(status_code=status_code, content=envelope.as_payload())


class DriverHandshakeRequest(BaseModel):
    """Schema-aligned representation of the driver handshake payload."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1)
    transport: Literal["http", "grpc"]
    endpoint: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    metadata: Mapping[str, Any] | None = None

    @field_validator("alias")
    @classmethod
    def _normalize_alias(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("alias must not be empty")
        return normalized

    @field_validator("endpoint")
    @classmethod
    def _normalize_endpoint(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("endpoint must not be empty")
        return normalized

    @field_validator("capabilities")
    @classmethod
    def _normalize_capabilities(cls, values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = value.strip()
            if not candidate:
                raise ValueError("capabilities entries must not be empty")
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    @model_validator(mode="after")
    def _validate_transport(self) -> "DriverHandshakeRequest":
        if self.transport == "http":
            parsed = urlparse(self.endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("HTTP transport requires a valid http(s) URL")
        else:
            if "://" not in self.endpoint and ":" not in self.endpoint:
                raise ValueError("gRPC transport requires a scheme or host:port value")
        return self


class DriverHandshakeResponse(BaseModel):
    """Successful handshake response payload."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    alias: str
    driver_module: str
    transport: Literal["http", "grpc"]
    endpoint: str
    lease_seconds: int = Field(ge=1)
    issued_at: str
    expires_at: str
    capabilities: list[str] = Field(default_factory=list)
    metadata: Mapping[str, Any] | None = None


@router.post(
    "/driver.handshake",
    response_model=DriverHandshakeResponse,
)
async def driver_handshake(
    payload: DriverHandshakeRequest,
    request: Request,
) -> DriverHandshakeResponse | JSONResponse:
    pool = getattr(request.app.state, "driver_worker_pool", None)
    if not isinstance(pool, DriverWorkerPool):
        return _error_response(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="DRIVER_POOL_UNAVAILABLE",
            reason="Driver worker pool is not initialised",
        )

    try:
        session = pool.register_handshake(
            alias=payload.alias,
            transport=payload.transport,
            endpoint=payload.endpoint,
            capabilities=payload.capabilities,
            metadata=payload.metadata,
        )
    except DriverHandshakeError as exc:
        return _error_response(
            request,
            status_code=int(exc.status_code),
            code=exc.code,
            reason=exc.reason,
            hint=exc.hint,
        )

    response = DriverHandshakeResponse(
        session_id=session.session_id,
        alias=session.alias,
        driver_module=session.driver_module,
        transport=cast(Literal["http", "grpc"], session.transport),
        endpoint=session.endpoint,
        lease_seconds=pool.lease_seconds,
        issued_at=_format_timestamp(session.issued_at),
        expires_at=_format_timestamp(session.expires_at),
        capabilities=list(session.capabilities),
        metadata=dict(session.metadata) if session.metadata else None,
    )
    return response


__all__ = ["router", "DriverHandshakeRequest", "DriverHandshakeResponse"]
__all__ = ["router", "DriverHandshakeRequest", "DriverHandshakeResponse"]
__all__ = ["router", "DriverHandshakeRequest", "DriverHandshakeResponse"]
__all__ = ["router", "DriverHandshakeRequest", "DriverHandshakeResponse"]
__all__ = ["router", "DriverHandshakeRequest", "DriverHandshakeResponse"]
__all__ = ["router", "DriverHandshakeRequest", "DriverHandshakeResponse"]
