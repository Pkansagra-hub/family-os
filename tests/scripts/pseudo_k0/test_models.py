"""tests/scripts/pseudo_k0/test_models.py — Pydantic model wire-shape tests.

Run: python -m pytest tests/scripts/pseudo_k0/test_models.py -q --no-cov
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.pseudo_k0.models import (
    K0Envelope,
    ObsPayload,
    RecallRequestBody,
    RecallResponseBody,
    RecallSelectorBody,
)


class TestK0Envelope:
    def test_minimal_envelope(self):
        e = K0Envelope(topic="memory.write.v1", body={"content": "hi"})
        assert e.topic == "memory.write.v1"
        assert e.body == {"content": "hi"}

    def test_full_envelope_roundtrip(self):
        raw = {
            "cognitive_trace_id": "trace-1",
            "tenant_id": "t",
            "space_id": "family:smith",
            "actor": "alex",
            "device_id": "alex_phone",
            "topic": "recall.request.v1",
            "band": "GREEN",
            "ts": "2026-05-11T12:00:00Z",
            "policy_version": "1.0",
            "schema_uri": "bridge://contracts/schemas/recall.request.v1.json",
            "schema_version": "2.2",
            "body": {"selectors": [], "space_id": "family:smith"},
            "payload_sha256": "a" * 64,
            "envelope_sha256": "b" * 64,
            "policy": {"abac": {"roles": ["guest"]}},
            "sig_alg": "ed25519",
            "sig_kid": "k1",
            "sig": {"signature": "deadbeef"},
        }
        e = K0Envelope.model_validate(raw)
        assert e.topic == "recall.request.v1"
        assert e.space_id == "family:smith"
        assert e.sig == {"signature": "deadbeef"}

    def test_extra_fields_are_ignored(self):
        e = K0Envelope.model_validate({"topic": "x.y.z", "body": {}, "unknown_future_field": 123})
        # extra="ignore" — should not raise
        assert e.topic == "x.y.z"

    def test_missing_topic_raises(self):
        with pytest.raises(ValidationError):
            K0Envelope.model_validate({"body": {}})


class TestRecallRequestBody:
    def test_minimal(self):
        b = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic")],
            space_id="family:smith",
        )
        assert len(b.selectors) == 1
        assert b.max_results == 10
        assert b.fail_fast is False

    def test_selector_limit_bounds(self):
        with pytest.raises(ValidationError):
            RecallSelectorBody(type="episodic", limit=0)
        with pytest.raises(ValidationError):
            RecallSelectorBody(type="episodic", limit=999)

    def test_too_many_selectors_rejected(self):
        with pytest.raises(ValidationError):
            RecallRequestBody(
                selectors=[RecallSelectorBody(type="episodic")] * 17,
                space_id="x",
            )

    def test_at_least_one_selector_required(self):
        with pytest.raises(ValidationError):
            RecallRequestBody(selectors=[], space_id="x")


class TestRecallResponseBody:
    def test_empty_default(self):
        r = RecallResponseBody()
        assert r.hits == []
        assert r.total == 0
        assert r.truncated is False


class TestObsPayload:
    def test_minimal(self):
        p = ObsPayload(kind="feedback", body={"score": 0.9})
        assert p.kind == "feedback"
        assert p.body == {"score": 0.9}

    def test_missing_kind_raises(self):
        with pytest.raises(ValidationError):
            ObsPayload.model_validate({"body": {}})
