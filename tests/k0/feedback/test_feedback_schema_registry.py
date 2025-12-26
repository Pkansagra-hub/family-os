"""Tests for FeedbackSchemaRegistry.

Epic 0.2: Feedback Schema Registry
Stories: FEEDBACK-003, FEEDBACK-004
Related ADR: K020
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from k0.feedback.payloads import P02FeedbackPayload
from k0.feedback.schema_registry import FeedbackSchemaRegistry


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    FeedbackSchemaRegistry.reset()


def test_validate_permissive_for_unregistered_pipeline_by_default() -> None:
    ok, err = FeedbackSchemaRegistry.validate("P02", {"anything": 1})
    assert ok is True
    assert err is None


def test_validate_strict_for_unregistered_pipeline_when_configured() -> None:
    ok, err = FeedbackSchemaRegistry.validate(
        "P02",
        {"anything": 1},
        permissive_unregistered=False,
    )
    assert ok is False
    assert err is not None


def test_register_pydantic_schema_and_validate_success() -> None:
    FeedbackSchemaRegistry.register_pydantic("P02", P02FeedbackPayload)

    ok, err = FeedbackSchemaRegistry.validate(
        "P02",
        {"extraction_quality": "good"},
        permissive_unregistered=False,
    )
    assert ok is True
    assert err is None


def test_register_pydantic_schema_and_validate_failure() -> None:
    FeedbackSchemaRegistry.register_pydantic("P02", P02FeedbackPayload)

    ok, err = FeedbackSchemaRegistry.validate(
        "P02",
        {"extraction_quality": "excellent"},
        permissive_unregistered=False,
    )
    assert ok is False
    assert err is not None


def test_register_json_schema_and_validate() -> None:
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }

    FeedbackSchemaRegistry.register_json_schema("P08", schema)

    ok, err = FeedbackSchemaRegistry.validate("P08", {"name": "ok"}, permissive_unregistered=False)
    assert ok is True
    assert err is None

    ok, err = FeedbackSchemaRegistry.validate("P08", {"nope": 1}, permissive_unregistered=False)
    assert ok is False
    assert err is not None


def test_load_schemas_from_directory(tmp_path: Path) -> None:
    # Create schema file
    (tmp_path / "p02.json").write_text(
        '{"$schema":"http://json-schema.org/draft-07/schema#","type":"object"}',
        encoding="utf-8",
    )

    FeedbackSchemaRegistry.load_schemas_from_directory(tmp_path)

    assert FeedbackSchemaRegistry.list_registered() == ["P02"]


def test_pipeline_id_normalization_and_validation() -> None:
    class Demo(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: int = Field(ge=0)

    FeedbackSchemaRegistry.register_pydantic("p08", Demo)
    ok, err = FeedbackSchemaRegistry.validate("P08", {"value": 0}, permissive_unregistered=False)
    assert ok is True
    assert err is None

    with pytest.raises(ValueError):
        FeedbackSchemaRegistry.register_pydantic("not-a-pipeline", Demo)
