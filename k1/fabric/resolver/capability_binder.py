"""CapabilityBinderService — RES-010 simplified (2026-06-17).

Returns full tools + constitutions for ALL connectors in the ranked set.
Back receives complete info for top 3 connectors — no re-resolve needed.
"""

from __future__ import annotations

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import ConstitutionArtifact
from k1.fabric.resolver.capability_type_resolver import RankedConnectorSet
from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    GlobalProjectionStore,
)


def _build_tool_dict(t: CapabilityRecord) -> dict:
    return {
        "capability_name": t.capability_name,
        "action_name": t.action_name,
        "invocation_mode": t.invocation_mode,
        "effect": t.effect,
        "description": t.description or "",
        "required_inputs": list(t.required_inputs),
        "optional_inputs": list(t.optional_inputs),
    }


def _build_constitution_dict(c: ConstitutionArtifact | None) -> dict | None:
    if c is None:
        return None
    return {
        "precondition_summary": c.precondition_summary or "",
        "how_to_sequence": list(c.how_to_sequence),
        "what_to_verify": list(c.what_to_verify),
        "companion_connectors": list(c.companion_connectors),
        "when_to_ask_human": list(c.when_to_ask_human),
        "conflict_rules": list(c.conflict_rules),
    }


class CapabilityBinderService:
    """Returns full tools + constitutions for all ranked connectors."""

    def __init__(self, global_store: GlobalProjectionStore) -> None:
        self.global_store = global_store

    def bind(
        self,
        connector_hits: RankedConnectorSet,
        *,
        actor_id: str = "",
        session_id: str = "",
        constitution_loader: ConstitutionLoader | None = None,
    ) -> list[dict]:
        """Return connector dicts — primary with full tools+constitution,
        alternatives as summaries only (id, label, score, description).

        Alternatives are lightweight to keep the packet small for the LLM.
        Back can re-resolve if it needs a different connector's full data.
        """
        results: list[dict] = []

        # ── Primary: full tools + constitution ──
        if connector_hits.primary is not None:
            hit = connector_hits.primary
            cid: str = hit.get("connector_id", "") or ""
            if cid:
                tools = self.global_store.get_capabilities_by_connector(cid)
                tool_dicts = [_build_tool_dict(t) for t in tools]
                constitution: ConstitutionArtifact | None = None
                if constitution_loader is not None:
                    constitution = constitution_loader.load(cid)
                results.append(
                    {
                        "connector_id": cid,
                        "label": hit.get("label", cid),
                        "description": hit.get("description", ""),
                        "score": hit.get("score", 0.0),
                        "tools": tool_dicts,
                        "constitution": _build_constitution_dict(constitution),
                    }
                )

        # ── Alternatives: summaries only (no tools, no constitution) ──
        for hit in connector_hits.alternatives:
            cid = hit.get("connector_id", "") or ""
            if not cid:
                continue
            results.append(
                {
                    "connector_id": cid,
                    "label": hit.get("label", cid),
                    "description": hit.get("description", ""),
                    "score": hit.get("score", 0.0),
                    "tools": [],
                    "constitution": None,
                }
            )

        return results
