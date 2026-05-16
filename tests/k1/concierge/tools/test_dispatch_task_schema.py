from __future__ import annotations

from k1.concierge.tools.schemas_front import DISPATCH_TASK_SCHEMA


def test_dispatch_reference_context_accepts_structured_artifact_context() -> None:
    reference_context = DISPATCH_TASK_SCHEMA.parameters["properties"]["reference_context"]
    any_of = reference_context["additionalProperties"]["anyOf"]

    assert {"type": "object"} in any_of
    assert {"type": "array"} in any_of
    assert "general_context_to_add" in reference_context["description"]
    assert "authority/provenance" in reference_context["description"]
