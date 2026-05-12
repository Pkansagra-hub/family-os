"""
k1.tools.family.routes -- FastAPI router factory for one family-tool service.

Each call to :func:`build_router` returns an ``APIRouter`` rooted at
``/k1/tools/<adapter_id>`` and exposing:

* ``GET  /manifest?role=<role>`` -- the role-filtered UI manifest.
* ``GET  /llm_specs``           -- the OpenAI-compatible tool spec list.
* ``GET  /<action>`` or
  ``POST /<action>``            -- one route per action.  GET for
                                   ``kind="read"``, POST for everything
                                   else.

Headers consumed (all caller-supplied; the kernel boot mounts
trust-zone-appropriate auth middleware in front of this router):

* ``X-Actor-Member-Id``  -- caller identity (``WriteContext.user_id``).
* ``X-Actor-Role``        -- caller role; defaults to ``"parent"``.
* ``X-Space-Id``          -- household scope; defaults to empty.
* ``X-Trace-Id``          -- correlation id; auto-generated when absent.
* ``X-Idem-Key``          -- idempotency key forwarded to the service.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.9.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request

from k1.tools.family.base import WriteContext
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.manifest import llm_tool_specs, ui_manifest

logger = logging.getLogger(__name__)


# Roles accepted on the wire.  Anything else is coerced to ``"parent"``
# so a misconfigured client fails to a sensible default; auth middleware
# is the authoritative gate for caller identity.
_ALLOWED_ROLES = {"parent", "child", "guardian", "elder", "system", "guest"}


def _resolve_role(raw: Optional[str]) -> str:
    if raw and raw in _ALLOWED_ROLES:
        return raw
    return "parent"


def _build_ctx(
    *,
    user_id: Optional[str],
    role: Optional[str],
    space_id: Optional[str],
    trace_id: Optional[str],
    idem_key: Optional[str],
) -> WriteContext:
    return WriteContext(
        user_id=user_id or "anonymous",
        space_id=space_id or "",
        role=_resolve_role(role),  # type: ignore[arg-type]
        trace_id=trace_id or uuid.uuid4().hex,
        face="ui",
        idempotency_key=idem_key,
    )


def build_router(service: BaseToolService) -> APIRouter:
    """Return a FastAPI :class:`APIRouter` exposing every action of ``service``."""

    defn = service.DEFINITION
    router = APIRouter(prefix=f"/k1/tools/{defn.adapter_id}", tags=[f"k1.tools.{defn.adapter_id}"])

    # -- manifest endpoints ------------------------------------------------

    @router.get("/manifest")
    async def get_manifest(
        role: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        resolved = _resolve_role(role) if role else None
        return ui_manifest(defn, resolved)  # type: ignore[arg-type]

    @router.get("/llm_specs")
    async def get_llm_specs() -> list[dict[str, Any]]:
        return llm_tool_specs(defn)

    # -- per-action endpoints ---------------------------------------------

    for action in defn.actions:
        _attach_action_route(router, service, action.name, action.kind)

    return router


def _attach_action_route(
    router: APIRouter,
    service: BaseToolService,
    action_name: str,
    action_kind: str,
) -> None:
    """Register one HTTP route for ``action_name`` on ``router``.

    Defined in module scope so the closure captures only the parameters
    we care about (avoiding late-binding pitfalls when iterating over
    multiple actions).
    """

    path = f"/{action_name}"

    if action_kind == "read":

        @router.get(path, name=f"{service.DEFINITION.adapter_id}.{action_name}")
        async def read_endpoint(
            request: Request,
            x_actor_member_id: Optional[str] = Header(default=None, alias="X-Actor-Member-Id"),
            x_actor_role: Optional[str] = Header(default=None, alias="X-Actor-Role"),
            x_space_id: Optional[str] = Header(default=None, alias="X-Space-Id"),
            x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
            x_idem_key: Optional[str] = Header(default=None, alias="X-Idem-Key"),
        ) -> dict[str, Any]:
            ctx = _build_ctx(
                user_id=x_actor_member_id,
                role=x_actor_role,
                space_id=x_space_id,
                trace_id=x_trace_id,
                idem_key=x_idem_key,
            )
            params: dict[str, Any] = {k: v for k, v in request.query_params.items()}
            return await service.dispatch(action_name, params, ctx)

    else:

        @router.post(path, name=f"{service.DEFINITION.adapter_id}.{action_name}")
        async def write_endpoint(
            params: dict[str, Any] = Body(default_factory=dict),
            x_actor_member_id: Optional[str] = Header(default=None, alias="X-Actor-Member-Id"),
            x_actor_role: Optional[str] = Header(default=None, alias="X-Actor-Role"),
            x_space_id: Optional[str] = Header(default=None, alias="X-Space-Id"),
            x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
            x_idem_key: Optional[str] = Header(default=None, alias="X-Idem-Key"),
        ) -> dict[str, Any]:
            ctx = _build_ctx(
                user_id=x_actor_member_id,
                role=x_actor_role,
                space_id=x_space_id,
                trace_id=x_trace_id,
                idem_key=x_idem_key,
            )
            result = await service.dispatch(action_name, params, ctx)
            if not result.get("success", True):
                # Surface foundation failure codes back through HTTP semantics
                # so middleware / clients can react.  We don't raise for
                # ``dispatch_failed`` because the body already encodes details.
                code = result.get("error_code", "dispatch_failed")
                status = _STATUS_FROM_CODE.get(code, 200)
                if status >= 400:
                    raise HTTPException(status_code=status, detail=result)
            return result


_STATUS_FROM_CODE: dict[str, int] = {
    "action_not_found": 404,
    "handler_missing": 500,
    "role_denied": 403,
    "role_below_min": 403,
    "band_denied": 403,
    "invalid_result": 500,
    "dispatch_failed": 500,
}
