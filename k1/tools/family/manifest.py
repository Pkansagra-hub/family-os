"""
k1.tools.family.manifest -- UI / LLM / OpenAPI manifest generators.

Three pure helpers consume a :class:`ToolDefinition` and emit the
manifest shape each downstream consumer expects:

* :func:`ui_manifest` -- role-filtered structure consumed by the web /
  mobile UI to render action buttons, list filters, and views.

* :func:`llm_tool_specs` -- OpenAI / Anthropic compatible "tools" array
  consumed by the planner / concierge LLM call.  Each entry carries
  both a legacy ``"<adapter>.<action>"`` name AND the canonical Fabric
  ``capability_name`` so callers can pick the routing surface they need.

* :func:`openapi_paths` -- ``paths`` fragment merged into the
  per-adapter REST router's OpenAPI document.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.8.
"""

from __future__ import annotations

from typing import Any, Optional

from k1.tools.family.base import Role, role_satisfies
from k1.tools.family.definition import ActionSpec, FieldSpec, ToolDefinition

# ---------------------------------------------------------------------------
# Field-spec -> JSON schema
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "datetime": "string",  # JSON-schema doesn't have a native datetime; use ISO-8601 string.
    "object": "object",
    "array": "array",
}


def _field_to_json_schema(field: FieldSpec) -> dict[str, Any]:
    """Convert a :class:`FieldSpec` to a minimal JSON-schema node."""

    node: dict[str, Any] = {"type": _TYPE_MAP.get(field.type, "string")}
    if field.type == "datetime":
        node["format"] = "date-time"
    if field.description:
        node["description"] = field.description
    if field.example is not None:
        node["example"] = field.example
    return node


def _params_schema(fields: list[FieldSpec]) -> dict[str, Any]:
    """Build a JSON-schema ``object`` from a list of FieldSpecs."""

    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields:
        properties[f.name] = _field_to_json_schema(f)
        if f.required:
            required.append(f.name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# Action filtering by role
# ---------------------------------------------------------------------------


def _action_visible_to_role(action: ActionSpec, role: Role) -> bool:
    """Return True iff ``role`` can both call and is at-or-above ``min_role``."""

    if role not in action.allowed_roles:
        return False
    if action.min_role is not None and not role_satisfies(role, action.min_role):
        return False
    return True


# ---------------------------------------------------------------------------
# UI manifest
# ---------------------------------------------------------------------------


def ui_manifest(defn: ToolDefinition, role: Optional[Role] = None) -> dict[str, Any]:
    """Return the role-filtered UI manifest dict for ``defn``.

    When ``role`` is ``None`` every action is included regardless of
    ``allowed_roles`` / ``min_role`` -- callers should usually pass a
    role so the rendered manifest matches the caller's privileges.
    """

    actions_out: list[dict[str, Any]] = []
    for action in defn.actions:
        if role is not None and not _action_visible_to_role(action, role):
            continue
        actions_out.append(
            {
                "name": action.name,
                "kind": action.kind,
                "summary": action.summary,
                "label": action.label or action.name.replace("_", " ").title(),
                "primary": action.primary,
                "context": list(action.context),
                "params": _params_schema(action.params),
                "min_band": action.min_band,
            }
        )

    return {
        "adapter_id": defn.adapter_id,
        "version": defn.version,
        "category": defn.category,
        "title": defn.title or defn.adapter_id.replace("_", " ").title(),
        "icon": defn.icon,
        "summary": defn.summary,
        "description": defn.description or defn.summary,
        "entity_type": defn.entity_type,
        "views": list(defn.views),
        "filters": [_field_to_json_schema(f) | {"name": f.name} for f in defn.filters],
        "can_reference": list(defn.can_reference),
        "feature_flags": list(defn.feature_flags),
        "actions": actions_out,
    }


# ---------------------------------------------------------------------------
# LLM tool specs
# ---------------------------------------------------------------------------


def llm_tool_specs(defn: ToolDefinition) -> list[dict[str, Any]]:
    """Return the OpenAI-compatible ``tools`` array for ``defn``.

    Every entry carries:

    * ``name`` -- ``<adapter_id>.<action_name>``.  Legacy planner code
      that does exact-name matching keeps working.
    * ``capability_name`` -- ``tool.<read|execute>.<adapter_id>.<action_name>``.
      The canonical Fabric capability name.
    * ``description`` -- the action's ``summary`` (extended with the
      first ``use_when`` hint when present).
    * ``parameters`` -- JSON-schema for the action ``params``.
    * ``output_schema`` -- explicit when the adapter author provided one
      on the spec, otherwise derived from ``result`` fields.
    * ``examples`` -- ``llm.examples`` for in-context priming.
    """

    specs: list[dict[str, Any]] = []
    for action in defn.actions:
        cap_prefix = "tool.read" if action.kind == "read" else "tool.execute"
        capability_name = f"{cap_prefix}.{defn.adapter_id}.{action.name}"

        description = action.summary
        if action.llm.use_when:
            description = f"{action.summary} -- {action.llm.use_when[0]}"

        output_schema = action.output_schema or _params_schema(action.result)

        specs.append(
            {
                "name": f"{defn.adapter_id}.{action.name}",
                "capability_name": capability_name,
                "kind": action.kind,
                "description": description,
                "parameters": _params_schema(action.params),
                "output_schema": output_schema,
                "examples": list(action.llm.examples),
            }
        )
    return specs


# ---------------------------------------------------------------------------
# OpenAPI paths fragment
# ---------------------------------------------------------------------------


def openapi_paths(defn: ToolDefinition) -> dict[str, Any]:
    """Return an OpenAPI ``paths`` fragment for the adapter's REST router."""

    base = f"/k1/tools/{defn.adapter_id}"
    paths: dict[str, Any] = {
        f"{base}/manifest": {
            "get": {
                "summary": f"{defn.adapter_id} UI manifest",
                "responses": {"200": {"description": "Role-filtered UI manifest."}},
            }
        },
        f"{base}/llm_specs": {
            "get": {
                "summary": f"{defn.adapter_id} LLM tool specs",
                "responses": {"200": {"description": "OpenAI-compatible tool array."}},
            }
        },
    }

    for action in defn.actions:
        method = "get" if action.kind == "read" else "post"
        paths[f"{base}/{action.name}"] = {
            method: {
                "summary": action.summary,
                "description": action.label or action.summary,
                "requestBody": (
                    {
                        "required": True,
                        "content": {"application/json": {"schema": _params_schema(action.params)}},
                    }
                    if method == "post"
                    else None
                ),
                "responses": {"200": {"description": "Action result."}},
            }
        }
        # Trim nulls from the path entry for GET routes.
        if method == "get":
            paths[f"{base}/{action.name}"][method].pop("requestBody", None)

    return paths
