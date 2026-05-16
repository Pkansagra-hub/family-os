from __future__ import annotations

from k1.concierge.tools.schemas_back import SUBMIT_RESULT_SCHEMA


def test_submit_result_schema_accepts_structured_artifacts_and_semantics() -> None:
    properties = SUBMIT_RESULT_SCHEMA.parameters["properties"]

    assert properties["artifacts_created"]["items"]["type"] == "object"
    assert properties["semantic_context"]["type"] == "object"
    assert properties["presentation_guidance"]["type"] == "string"
