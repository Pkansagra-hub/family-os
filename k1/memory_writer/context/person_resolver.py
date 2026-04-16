"""
PersonResolver -- Resolve natural names to stable person_ids.

Follows PlaceResolver pattern: no async, no I/O, pure lookup against
ExtractionContext.active_persons and persona_context aliases.

Resolution priority:
  1. Exact match (case-insensitive) in active_persons → confidence 1.0
  2. Alias match from persona_context["aliases"] → confidence 0.9
  3. Partial/substring match in active_persons → confidence 0.8
  4. Fallback: generate provisional person_{sanitized} → confidence 0.5
"""

from __future__ import annotations

import re
from typing import List, Set

from k1.memory_writer.types import ExtractionContext, PersonResolution

_PERSON_ID_SANITIZE = re.compile(r"[^a-z0-9_]")


class PersonResolver:
    """Resolve natural names to stable person_ids.

    Follows PlaceResolver pattern: constructor builds lookup map,
    resolve() returns cached result.

    No port dependencies -- reads from ExtractionContext (already built).
    """

    def resolve(self, name: str, context: ExtractionContext) -> PersonResolution:
        """Resolve a single natural name to a PersonResolution."""
        if not name or not name.strip():
            return PersonResolution(
                natural_name=name,
                person_id="person_unknown",
                confidence=0.0,
                is_provisional=True,
            )

        key = name.strip().lower()

        # Step 1: Exact match in active_persons
        for display_name, info in context.active_persons.items():
            if display_name.lower() == key:
                pid = info.get("person_id", "") if isinstance(info, dict) else ""
                if pid:
                    return PersonResolution(
                        natural_name=name,
                        person_id=pid,
                        confidence=1.0,
                        is_provisional=False,
                    )

        # Step 2: Alias match from persona_context
        aliases = context.persona_context.get("aliases", {})
        if isinstance(aliases, dict):
            for primary_name, alias_list in aliases.items():
                if isinstance(alias_list, list) and key in [a.lower() for a in alias_list]:
                    # Find person_id for primary_name
                    for dn, info in context.active_persons.items():
                        if dn.lower() == primary_name.lower():
                            pid = info.get("person_id", "") if isinstance(info, dict) else ""
                            if pid:
                                return PersonResolution(
                                    natural_name=name,
                                    person_id=pid,
                                    confidence=0.9,
                                    is_provisional=False,
                                )

        # Step 3: Partial/substring match in active_persons
        for display_name, info in context.active_persons.items():
            if key in display_name.lower() or display_name.lower() in key:
                pid = info.get("person_id", "") if isinstance(info, dict) else ""
                if pid:
                    return PersonResolution(
                        natural_name=name,
                        person_id=pid,
                        confidence=0.8,
                        is_provisional=False,
                    )

        # Step 4: Fallback -- generate provisional person_id
        sanitized = _PERSON_ID_SANITIZE.sub("_", key).strip("_")
        if not sanitized:
            sanitized = "unknown"
        return PersonResolution(
            natural_name=name,
            person_id=f"person_{sanitized}",
            confidence=0.5,
            is_provisional=True,
        )

    def resolve_all(self, names: List[str], context: ExtractionContext) -> List[PersonResolution]:
        """Resolve all names. Dedup by person_id, preserving order."""
        seen: Set[str] = set()
        results: List[PersonResolution] = []
        for name in names:
            r = self.resolve(name, context)
            if r.person_id not in seen:
                seen.add(r.person_id)
                results.append(r)
        return results
