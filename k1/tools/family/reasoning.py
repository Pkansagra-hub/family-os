"""
k1.tools.family.reasoning -- Build Fabric CapabilityContract descriptors
for family-tool adapters.

Two entrypoints are provided so callers can choose the appropriate
surface:

1. :func:`build_fabric_contracts_from_registry` (in-process) -- iterates
   a live :class:`ToolRegistry` and calls
   :func:`k1.fabric.manifest_translator.build_contract` directly.  Used
   at boot time (no HTTP round-trip, no external dependency).

2. :func:`build_fabric_contracts_from_http` (HTTP) -- fetches
   ``/llm_specs`` from one or more adapter base URLs, translates the
   JSON response into the same contract shape, and returns the list.
   Used when adapters run as separate processes or are hosted remotely.

Both return a list of :class:`CapabilityContract` objects suitable for
direct insertion into a :class:`CapabilityRegistry`.

The ``description`` field on each contract is assembled by
:func:`_build_description`: it weaves the action ``summary`` with the
first ``use_when`` LLM hint (when present) so the Concierge LLM gets
richer natural-language context when choosing a tool.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import httpx

from k1.fabric.manifest_translator import (
    NATIVE_PROVIDER_ENDPOINT,
    NATIVE_PROVIDER_ID,
    NATIVE_PROVIDER_TYPE,
    build_contract,
)
from k1.fabric.types import CapabilityContract, InputSpec

if TYPE_CHECKING:  # pragma: no cover
    from k1.tools.family.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Description helper
# ---------------------------------------------------------------------------


def _build_description(summary: str, use_when: list[str]) -> str:
    """Weave ``summary`` with the first ``use_when`` hint.

    When a ``use_when`` hint is present it is appended after the summary
    with `` -- `` as separator, mirroring the behaviour in
    :func:`k1.tools.family.manifest.llm_tool_specs`.

    Parameters
    ----------
    summary:
        Short one-line description from :class:`ActionSpec`.
    use_when:
        List of natural-language sentences describing when to invoke the
        action (from :class:`LLMHints`).
    """
    if use_when and use_when[0].strip():
        return f"{summary} -- {use_when[0]}"
    return summary


# ---------------------------------------------------------------------------
# In-process path (recommended for K1 boot)
# ---------------------------------------------------------------------------


def build_fabric_contracts_from_registry(
    registry: "ToolRegistry",
) -> list[CapabilityContract]:
    """Return :class:`CapabilityContract` objects for every registered adapter.

    Iterates the live :class:`ToolRegistry`, calls
    :func:`~k1.fabric.manifest_translator.build_contract` for each
    :class:`ActionSpec`, and returns the resulting list.

    Parameters
    ----------
    registry:
        A fully constructed :class:`ToolRegistry` whose services have
        already been registered via :meth:`~ToolRegistry.register_class`
        or :meth:`~ToolRegistry.register_all`.

    Returns
    -------
    list[CapabilityContract]
        One entry per action across all registered adapters.  The list
        order follows ``registry.adapter_ids()`` (alphabetical) then
        action declaration order within each adapter.
    """
    contracts: list[CapabilityContract] = []
    for adapter_id in registry.adapter_ids():
        svc = registry.get_service(adapter_id)
        if svc is None:
            continue
        defn = svc.DEFINITION
        for action in defn.actions:
            contracts.append(build_contract(defn, action))
    return contracts


# ---------------------------------------------------------------------------
# HTTP path (remote / out-of-process adapters)
# ---------------------------------------------------------------------------


def _llm_spec_to_contract(spec: dict[str, Any]) -> CapabilityContract:
    """Convert a single entry from ``/llm_specs`` into a :class:`CapabilityContract`.

    The ``/llm_specs`` JSON shape (from
    :func:`k1.tools.family.manifest.llm_tool_specs`) is:

    .. code-block:: json

        {
            "name":             "<adapter_id>.<action_name>",
            "capability_name":  "tool.read.<adapter_id>.<action_name>",
            "kind":             "read",
            "description":      "...",
            "parameters":       { "type": "object", "properties": {...} },
            "output_schema":    {...},
            "examples":         [...]
        }

    We map this to a minimal :class:`CapabilityContract` using the
    ``LOCAL`` provider constants so that the Fabric registry treats
    these as in-process native tools regardless of how the spec was
    fetched.
    """
    from datetime import datetime, timezone

    cap_name: str = spec.get("capability_name") or spec["name"]
    description: str = spec.get("description", "")

    # Build InputSpec list from JSON-schema properties.
    parameters: dict[str, Any] = spec.get("parameters") or {}
    properties: dict[str, Any] = parameters.get("properties") or {}
    required_names: list[str] = parameters.get("required") or []

    required_inputs: list[InputSpec] = []
    optional_inputs: list[InputSpec] = []
    for field_name, field_schema in properties.items():
        inp = InputSpec(
            name=field_name,
            type=field_schema.get("type", "string"),
            description=field_schema.get("description", ""),
        )
        if field_name in required_names:
            required_inputs.append(inp)
        else:
            optional_inputs.append(inp)

    # Infer safety band from capability name prefix.
    # Writes/executes are GREEN by default; only payment/purchase flows warrant AMBER+.
    safety_band_min = "GREEN"

    now_iso = datetime.now(timezone.utc).isoformat()

    return CapabilityContract(
        name=cap_name,
        version="1.0.0",
        domain=["family"],
        description=description,
        capabilities=[spec.get("kind", "read"), f"spec:{spec['name']}"],
        limitations=list(spec.get("avoid_when") or []),
        required_inputs=required_inputs,
        optional_inputs=optional_inputs,
        required_context=[],
        optional_context=["control"],
        output=spec.get("output_schema") or {},
        provider_type=NATIVE_PROVIDER_TYPE,
        provider_id=NATIVE_PROVIDER_ID,
        provider_endpoint=NATIVE_PROVIDER_ENDPOINT,
        safety_band_min=safety_band_min,
        cost_per_call=0.0,
        avg_latency_ms=10,
        max_latency_ms=1000,
        registered_at=now_iso,
        last_updated=now_iso,
        ephemeral=False,
        created_by=NATIVE_PROVIDER_ID,
        created_at_iso=now_iso,
        session_scoped=False,
        risk_class="benign" if safety_band_min == "GREEN" else "safety_sensitive",
    )


async def build_fabric_contracts_from_http(
    adapter_base_urls: list[str],
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[CapabilityContract]:
    """Fetch ``/llm_specs`` from each adapter URL and return contracts.

    Parameters
    ----------
    adapter_base_urls:
        List of adapter root URLs (without trailing slash).
        Example: ``["http://localhost:8001/family/calendar",
                    "http://localhost:8002/family/tasks"]``.
    http_client:
        Optional pre-configured :class:`httpx.AsyncClient`.  A default
        client is created (and closed) when omitted.

    Returns
    -------
    list[CapabilityContract]
        Contracts from all adapters, in URL list order.  Failures on
        individual adapters raise :class:`httpx.HTTPError` (caller's
        responsibility to handle).
    """
    own_client = http_client is None
    client = http_client or httpx.AsyncClient()

    try:
        contracts: list[CapabilityContract] = []
        for base_url in adapter_base_urls:
            url = f"{base_url.rstrip('/')}/llm_specs"
            response = await client.get(url)
            response.raise_for_status()
            specs: list[dict[str, Any]] = response.json()
            for spec in specs:
                contracts.append(_llm_spec_to_contract(spec))
        return contracts
    finally:
        if own_client:
            await client.aclose()
