"""MS-3e Epic 3e.1 contract tests for the obs/feedback channel.

These tests are the live demonstration of the Bridge MS-3e.1 exit
criteria for the K1 -> K0 obs/feedback contracts:

1. Both obs manifests (feedback.envelope.v1 + observability.payload.v1)
   parse against the meta-schema and declare ``transport: obs``.
2. Each schema validates a representative payload (positive case)
   against the codegen-emitted Pydantic model.
3. Codegen emits the obs-shaped artefacts: an ``<Topic>Client.publish``
   on the K1 producer side carrying ``__obs_kind__``, and a no-op K0
   consumer-side stub (no register_handlers — dispatch lives inside
   /k0/obs.emit by ``kind``).
4. The kernel-level aggregate handler_registry / client_stub MUST NOT
   list these obs topics (different shape).

All tests use real components — real schema, real Pydantic, real
codegen artefacts, real manifest loader. No mocks.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tooling.contracts.manifest_loader import load_manifests

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"
GENERATED_ROOT = Path(__file__).resolve().parents[3] / "bridge" / "_generated"


OBS_TOPICS: tuple[str, ...] = (
    "feedback.envelope.v1",
    "observability.payload.v1",
)


_TOPIC_TO_MODULE = {
    "feedback.envelope.v1": "feedback_envelope_v1",
    "observability.payload.v1": "observability_payload_v1",
}


_TOPIC_TO_OBS_KIND = {
    "feedback.envelope.v1": "feedback",
    "observability.payload.v1": "metrics",
}


_VALID_PAYLOADS: dict[str, dict[str, Any]] = {
    "feedback.envelope.v1": {
        "feedback_id": "f7c2c4f6-1f1f-4e1f-9e9e-aaaaaaaaaaaa",
        "pipeline_id": "P02",
        "signal_class": "CORRECTION",
        "signal_subtype": "user_explicit_correction",
        "tenant_id": "t-1",
        "space_id": "s-1",
        "source": "USER",
        "source_component": "concierge.correction_detector",
        "session_id": "sess-1",
        "trace_id": "trace-1",
        "correlation": {
            "session_id": "sess-1",
            "message_id": "msg-1",
            "event_ids": ["evt-1", "evt-2"],
            "target_entity_type": "event",
            "target_entity_id": "evt-1",
        },
        "provenance": {
            "source_message_id": "msg-1",
            "recall_context_hash": "deadbeef",
        },
        "priority": 0.9,
        "payload": {
            "event_id": "evt-1",
            "feedback_type": "correction",
            "original_content": "had coffee with Rachel",
            "corrected_content": "had tea with Rachel",
            "confidence": 0.85,
        },
    },
    "observability.payload.v1": {
        "kind": "metrics",
        "snapshot": "# HELP foo bar\nfoo_total 42\n",
        "envelope_id": "obs-001",
        "tenant_id": "t-1",
    },
}


# ---------------------------------------------------------------------------
# 1. Manifest loader / meta-schema
# ---------------------------------------------------------------------------


def test_both_obs_manifests_load_without_error() -> None:
    """The full bundle must load — no meta-schema violations."""
    manifests = load_manifests(CONTRACTS_PATH)
    loaded_topics = {m.topic for m in manifests}
    for topic in OBS_TOPICS:
        assert topic in loaded_topics, f"missing manifest: {topic}"


@pytest.mark.parametrize("topic", OBS_TOPICS)
def test_obs_manifest_direction_and_transport(topic: str) -> None:
    """Every obs manifest must declare direction=k1_to_k0, transport=obs, obs_kind."""
    manifests = load_manifests(CONTRACTS_PATH)
    [m] = [m for m in manifests if m.topic == topic]
    assert m.raw["direction"] == "k1_to_k0", f"{topic}: wrong direction"
    assert m.raw["delivery"]["transport"] == "obs", f"{topic}: wrong transport"
    assert m.raw["delivery"].get("obs_kind") in {
        "feedback",
        "metrics",
        "logs",
    }, f"{topic}: obs_kind missing or invalid"
    assert m.producer_kernel == "k1", f"{topic}: producer_kernel must be k1"
    assert m.consumer_kernel == "k0", f"{topic}: consumer_kernel must be k0"


@pytest.mark.parametrize("topic", OBS_TOPICS)
def test_obs_manifest_queueable_with_24h_max_age(topic: str) -> None:
    """Obs is queueable: online_required=false, max_queue_age=PT24H."""
    manifests = load_manifests(CONTRACTS_PATH)
    [m] = [m for m in manifests if m.topic == topic]
    assert (
        m.raw["delivery"]["online_required"] is False
    ), f"{topic}: obs must be queueable (online_required=false)"
    assert (
        m.raw["delivery"].get("max_queue_age") == "PT24H"
    ), f"{topic}: obs must have max_queue_age=PT24H per D-resolved item 3"


# ---------------------------------------------------------------------------
# 2. Schema payload validation against generated Pydantic model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", OBS_TOPICS)
def test_obs_payload_validates_against_pydantic_model(topic: str) -> None:
    module_name = _TOPIC_TO_MODULE[topic]
    mod = importlib.import_module(f"bridge._generated.k1.models.{module_name}")
    cls = next(
        v
        for k, v in vars(mod).items()
        if inspect.isclass(v) and k.lower().replace("_", "") == module_name.replace("_", "")
    )
    instance = cls.model_validate(_VALID_PAYLOADS[topic])
    cls.model_validate(instance.model_dump(mode="json", exclude_none=True))


def test_feedback_envelope_pipeline_id_pattern_enforced() -> None:
    """pipeline_id must match ^P\\d{2,3}$ (P02, P08, P120 etc.)."""
    from bridge._generated.k1.models.feedback_envelope_v1 import FeedbackEnvelopeV1

    bad = dict(_VALID_PAYLOADS["feedback.envelope.v1"])
    bad["pipeline_id"] = "p02"  # lowercase fails pattern
    with pytest.raises(ValidationError):
        FeedbackEnvelopeV1.model_validate(bad)
    bad["pipeline_id"] = "PIPELINE2"
    with pytest.raises(ValidationError):
        FeedbackEnvelopeV1.model_validate(bad)


def test_feedback_envelope_signal_class_enum_enforced() -> None:
    from bridge._generated.k1.models.feedback_envelope_v1 import FeedbackEnvelopeV1

    bad = dict(_VALID_PAYLOADS["feedback.envelope.v1"])
    bad["signal_class"] = "BANANA"
    with pytest.raises(ValidationError):
        FeedbackEnvelopeV1.model_validate(bad)


def test_feedback_envelope_extra_fields_rejected() -> None:
    """extra=forbid: unknown top-level fields are rejected."""
    from bridge._generated.k1.models.feedback_envelope_v1 import FeedbackEnvelopeV1

    bad = dict(_VALID_PAYLOADS["feedback.envelope.v1"])
    bad["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        FeedbackEnvelopeV1.model_validate(bad)


def test_observability_payload_logs_kind_requires_entries() -> None:
    """Schema allOf: kind=logs requires entries[]."""
    # Pydantic codegen does not natively translate allOf if/then/else into
    # constraints, so test the wire-side via the raw JSON Schema validator
    # to back the contract guarantee.
    import json

    import jsonschema

    from bridge._generated.k1.models.observability_payload_v1 import (
        ObservabilityPayloadV1,
    )

    schema_path = CONTRACTS_PATH / "schemas" / "observability.payload.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # logs without entries -> rejected
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"kind": "logs"}, schema)
    # metrics without snapshot -> rejected
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"kind": "metrics"}, schema)
    # logs with entries -> ok
    jsonschema.validate(
        {
            "kind": "logs",
            "entries": [{"level": "INFO", "message": "boot"}],
        },
        schema,
    )
    # Pydantic still accepts both shapes (no allOf enforcement); model is
    # the wire shim, not the wire validator.
    ObservabilityPayloadV1.model_validate({"kind": "metrics", "snapshot": "x"})


# ---------------------------------------------------------------------------
# 3. Codegen artefact shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", OBS_TOPICS)
def test_codegen_emits_publish_method_on_k1_obs_client(topic: str) -> None:
    """K1 client file exposes ``<Topic>Client.publish(payload)`` with __obs_kind__."""
    module_name = _TOPIC_TO_MODULE[topic]
    mod = importlib.import_module(f"bridge._generated.k1.clients.{module_name}")
    clients = [
        v
        for k, v in vars(mod).items()
        if inspect.isclass(v) and k.endswith("Client") and v.__module__ == mod.__name__
    ]
    assert len(clients) == 1, f"{topic}: expected exactly one Client class"
    cli_cls = clients[0]
    assert cli_cls.__topic__ == topic
    assert cli_cls.__transport__ == "obs"
    assert cli_cls.__obs_kind__ == _TOPIC_TO_OBS_KIND[topic]
    assert hasattr(cli_cls, "publish"), f"{topic}: Client missing .publish"
    # Obs clients MUST NOT use SSE/HTTP-RR shapes.
    assert not hasattr(cli_cls, "emit"), f"{topic}: obs client must not expose .emit"
    assert not hasattr(cli_cls, "request"), f"{topic}: obs client must not expose .request"


@pytest.mark.parametrize("topic", OBS_TOPICS)
def test_codegen_emits_noop_handler_stub_on_k0_side(topic: str) -> None:
    """K0 handler file exposes only __topic__ and __model__ (no register_handlers)."""
    module_name = _TOPIC_TO_MODULE[topic]
    mod = importlib.import_module(f"bridge._generated.k0.handlers.{module_name}")
    assert getattr(mod, "__topic__", None) == topic
    assert (
        getattr(mod, "__model__", None) is not None
    ), f"{topic}: handler stub must export the Pydantic model class"
    # Obs handlers MUST NOT register handlers — dispatch is inside K0
    # ports.observe, keyed by inner ``kind`` field.
    assert not hasattr(
        mod, "register_handlers"
    ), f"{topic}: obs handler must not expose register_handlers"
    assert not hasattr(
        mod, "register_subscriber"
    ), f"{topic}: obs handler must not expose register_subscriber"


def test_kernel_aggregate_handler_registry_excludes_obs_topics() -> None:
    """K0 ``register_handlers`` impl-binding aggregate must skip obs topics."""
    text = (GENERATED_ROOT / "k0" / "handler_registry.py").read_text(encoding="utf-8")
    for topic in OBS_TOPICS:
        method = _TOPIC_TO_MODULE[topic]
        assert (
            f'"{method}"' not in text
        ), f"k0/handler_registry.py must NOT list obs method {method}"


def test_kernel_aggregate_client_stub_excludes_obs_topics() -> None:
    """K1 ``client_stub.py`` aggregate must skip obs topics."""
    text = (GENERATED_ROOT / "k1" / "client_stub.py").read_text(encoding="utf-8")
    for topic in OBS_TOPICS:
        method = _TOPIC_TO_MODULE[topic]
        assert (
            f"async def {method}(" not in text
        ), f"k1/client_stub.py must NOT define stub for obs method {method}"
