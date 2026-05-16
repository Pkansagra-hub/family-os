"""
ui.web.routes.family_tools -- Discovery + context API for family-tool adapters.

Provides two REST endpoints consumed by the front-end ``Family Apps`` panel:

* ``GET /api/family-tools``
      Returns the list of all registered adapters (title, icon, action
      summaries) plus the *caller context* the browser must forward as
      request headers when invoking tool routes.

* ``GET /api/family-tools/{adapter_id}``
      Returns the role-filtered :func:`k1.tools.family.manifest.ui_manifest`
      for a single adapter.  The ``role`` query param overrides the default
      (first family-member's role).

Both routes are lazily-evaluated: the coordinator is fetched via a
zero-arg callable injected at mount time so the router can be registered
at module-level while the coordinator is initialised later on the first
WebSocket connection.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.8.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Query

from k1.tools.family.manifest import ui_manifest

# ---------------------------------------------------------------------------
# Relation → family-tool role mapping
# ---------------------------------------------------------------------------

_RELATION_TO_ROLE: dict[str, str] = {
    "parent": "parent",
    "child": "child",
    "guardian": "guardian",
    "grandparent": "elder",
    "elder": "elder",
    "system": "system",
}

_DEFAULT_ICONS: dict[str, str] = {
    "calendar": "📅",
    "tasks": "✅",
    "reminders": "⏰",
    "chores": "🧹",
    "shopping": "🛒",
    "family_settings": "⚙️",
}


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_family_tools_api(get_coordinator: Callable[[], Any]) -> APIRouter:
    """Return a FastAPI router exposing the adapter discovery + context API.

    Parameters
    ----------
    get_coordinator:
        Zero-arg callable that returns the current ``UiCoordinator`` instance
        (or ``None`` before the first WebSocket connection initialises it).
        Typically ``lambda: _coordinator`` from ``ui.web.app``.
    """
    router = APIRouter(prefix="/api/family-tools", tags=["family_tools_api"])

    @router.get("")
    async def list_adapters() -> dict[str, Any]:
        """Return all registered adapters plus the caller context.

        The ``context`` block tells the browser what identity headers to
        attach when calling ``/k1/tools/{adapter_id}/{action}``:

        .. code-block:: json

            {
              "adapters": [
                { "adapter_id": "calendar", "title": "Calendar",
                  "icon": "📅", "summary": "...", "actions": [...] },
                ...
              ],
              "context": {
                "space_id": "smith_family",
                "member_id": "alex",
                "role": "parent"
              }
            }
        """
        coord = get_coordinator()
        context = _extract_context(coord)
        adapters = _list_adapters(coord, context.get("role", "parent"))
        return {"adapters": adapters, "context": context}

    @router.get("/{adapter_id}")
    async def get_adapter_manifest(
        adapter_id: str,
        role: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        """Return the role-filtered UI manifest for ``adapter_id``.

        When ``role`` is omitted the first family member's role is used.
        """
        coord = get_coordinator()
        bundle = _get_bundle(coord)
        if bundle is None:
            return {"error": "family tools not initialized", "actions": []}
        svc = bundle.tool_registry.get_service(adapter_id)
        if svc is None:
            return {"error": f"adapter '{adapter_id}' not found", "actions": []}
        effective_role = role or _extract_context(coord).get("role", "parent")
        return ui_manifest(svc.DEFINITION, effective_role)  # type: ignore[arg-type]

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_bundle(coord: Any) -> Any:
    """Drill coordinator → runtime → service → FamilyToolsBundle."""
    runtime = getattr(coord, "_runtime", None)
    service = getattr(runtime, "_service", None) if runtime is not None else None
    return getattr(service, "family_tools", None) if service is not None else None


def _extract_context(coord: Any) -> dict[str, Any]:
    """Best-effort extraction of space_id and current-member identity.

    Returns a safe fallback when the coordinator has not yet initialised or
    the kernel config is not available.
    """
    space_id = "smith_family"
    member_id = "alex"
    role = "parent"

    if coord is None:
        return {"space_id": space_id, "member_id": member_id, "role": role}

    # Space id from kernel config ------------------------------------------
    runtime = getattr(coord, "_runtime", None)
    service = getattr(runtime, "_service", None) if runtime is not None else None
    if service is not None:
        config = getattr(service, "_config", None)
        if config is not None:
            sid = getattr(config, "selfmodel_space_id", None)
            if sid:
                space_id = sid

    # Primary member from family profile -----------------------------------
    profile: dict[str, Any] = getattr(coord, "family_profile", None) or {}
    members: list[dict[str, Any]] = profile.get("members", [])
    if members:
        first = members[0]
        # M13 profile dicts expose `actor_id`; legacy dicts use `name`.
        member_id = first.get("actor_id") or first.get("name", "alex").lower().replace(" ", "_")
        relation = first.get("relation", "parent")
        role = _RELATION_TO_ROLE.get(relation, "parent")

    return {"space_id": space_id, "member_id": member_id, "role": role}


def _list_adapters(coord: Any, role: str) -> list[dict[str, Any]]:
    """Build the adapter descriptor list for the discovery response."""
    bundle = _get_bundle(coord)
    if bundle is None:
        return []

    result: list[dict[str, Any]] = []
    for adapter_id in bundle.tool_registry.adapter_ids():
        svc = bundle.tool_registry.get_service(adapter_id)
        if svc is None:
            continue
        defn = svc.DEFINITION
        manifest = ui_manifest(defn, role)  # type: ignore[arg-type]
        result.append(
            {
                "adapter_id": adapter_id,
                "title": manifest.get("title") or adapter_id.replace("_", " ").title(),
                "icon": _DEFAULT_ICONS.get(adapter_id) or getattr(defn, "icon", None) or "📦",
                "summary": manifest.get("summary", ""),
                "category": manifest.get("category", ""),
                "actions": [
                    {
                        "name": a["name"],
                        "kind": a["kind"],
                        "label": a.get("label") or a["name"].replace("_", " ").title(),
                    }
                    for a in manifest.get("actions", [])
                ],
            }
        )
    return result
