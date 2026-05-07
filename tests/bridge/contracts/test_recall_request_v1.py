"""MS-3c.1 contract tests for ``recall.request.v1`` / ``recall.response.v1``.

These tests are the live demonstration of the Bridge MS-3c.1 exit
criteria for the first paired (request/response) contract:

1. Request body validation accepts a fully-formed selector bundle.
2. Response body validation accepts a fully-formed hit list.
3. The ``paired_with`` cross-manifest invariant fails on dangling
   references (verified by transient corruption of the registry).
4. Codegen emits a typed ``request(payload) -> RecallResponseV1`` method
   on the producer client and skips client/handler/port files for the
   response-only manifest (model-only emission).
5. Round-trip: K1 client → in-process HTTP transport → bridge dispatcher
   → K0 handler → typed ``RecallResponseV1`` returned to caller.

All tests use real components — real schema, real Pydantic, real
codegen artifacts, real httpx ASGI transport, real FastAPI dispatcher.
"""

from __future__ import annotations

import inspect  # noqa: F401  -- kept for future signature-shape tests
import shutil
from pathlib import Path
from typing import Any, get_type_hints

import pytest
import yaml
from pydantic import ValidationError

from bridge._generated.k0.handlers.recall_request_v1 import (
    register_handlers as register_k0_recall_handlers,
)
from bridge._generated.k0.models.recall_request_v1 import RecallRequestV1 as K0RecallRequestV1
from bridge._generated.k1.clients.recall_request_v1 import RecallRequestV1Client
from bridge._generated.k1.models.recall_request_v1 import RecallRequestV1
from bridge._generated.k1.models.recall_response_v1 import RecallResponseV1
from bridge.core.transport.in_process_http import InProcessHttpTransport
from bridge.runtime import BridgeRuntime, Role
from bridge.testing.dispatcher_app import build_app
from tooling.contracts.manifest_loader import ManifestValidationError, load_manifests

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"
GENERATED_ROOT = Path(__file__).resolve().parents[3] / "bridge" / "_generated"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _valid_request_payload() -> dict[str, Any]:
    return {
        "selectors": [
            {
                "type": "semantic",
                "topic": "coffee",
                "limit": 5,
                "query": "starbucks rachel",
            },
            {
                "type": "episodic",
                "limit": 3,
            },
        ],
        "space_id": "space-test",
        "tenant_id": "tenant-test",
        "max_latency_ms": 200,
        "fail_fast": False,
        "max_results": 8,
        "vector_query": "rachel coffee",
        "trace_id": "trace-ms3c-1",
    }


def _valid_response_payload() -> dict[str, Any]:
    return {
        "hits": [
            {
                "atom_id": "atom-aaa",
                "content": {"text": "Had coffee with Rachel."},
                "score": 0.91,
                "source": "pgvector",
                "selector_type": "semantic",
            },
            {
                "atom_id": "atom-bbb",
                "content": {"text": "Discussed her new role."},
                "score": 0.74,
                "source": "wal",
                "selector_type": "episodic",
            },
        ],
        "total": 2,
        "latency_ms": 42,
        "truncated": False,
        "trace_id": "trace-ms3c-1",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_recall_request_payload_validation_accepts_valid() -> None:
    """A fully-formed selector bundle passes Pydantic validation."""
    payload = _valid_request_payload()
    model = RecallRequestV1.model_validate(payload)
    dumped = model.model_dump(mode="json", exclude_none=True)
    assert dumped["space_id"] == "space-test"
    assert len(dumped["selectors"]) == 2
    assert dumped["selectors"][0]["type"] == "semantic"


def test_recall_request_payload_validation_rejects_empty_selectors() -> None:
    """``selectors`` must contain at least one entry."""
    payload = _valid_request_payload()
    payload["selectors"] = []
    with pytest.raises(ValidationError):
        RecallRequestV1.model_validate(payload)


def test_recall_request_payload_validation_rejects_unknown_selector_type() -> None:
    """Selector ``type`` must be one of the documented enum values."""
    payload = _valid_request_payload()
    payload["selectors"][0]["type"] = "telepathy"
    with pytest.raises(ValidationError):
        RecallRequestV1.model_validate(payload)


def test_recall_response_payload_validation_accepts_valid() -> None:
    """A fully-formed response with hits passes Pydantic validation."""
    payload = _valid_response_payload()
    model = RecallResponseV1.model_validate(payload)
    dumped = model.model_dump(mode="json", exclude_none=True)
    assert dumped["total"] == 2
    assert dumped["hits"][0]["atom_id"] == "atom-aaa"
    assert dumped["truncated"] is False


def test_recall_response_payload_validation_rejects_score_out_of_range() -> None:
    """Hit ``score`` must lie in the closed unit interval."""
    payload = _valid_response_payload()
    payload["hits"][0]["score"] = 1.5
    with pytest.raises(ValidationError):
        RecallResponseV1.model_validate(payload)


def test_paired_with_meta_schema_rule_fails_on_dangling_partner(
    tmp_path: Path,
) -> None:
    """The cross-manifest invariant rejects unknown ``paired_with`` topics.

    We mirror the contracts tree into ``tmp_path``, point one manifest's
    ``paired_with`` at a non-existent topic, and verify
    :func:`load_manifests` raises :class:`ManifestValidationError`.
    """
    # Mirror the contracts root.
    mirror = tmp_path / "contracts"
    shutil.copytree(CONTRACTS_PATH, mirror)
    # Corrupt the request manifest's paired_with target.
    request_yaml = mirror / "manifests" / "recall.request.v1.yaml"
    raw = yaml.safe_load(request_yaml.read_text(encoding="utf-8"))
    raw["paired_with"] = "ghost.partner.v1"
    request_yaml.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ManifestValidationError) as exc:
        load_manifests(mirror)
    assert "ghost.partner.v1" in str(exc.value)
    assert "paired_with" in str(exc.value)


def test_codegen_emits_typed_request_method() -> None:
    """The producer client exposes ``request(payload) -> RecallResponseV1``."""
    hints = get_type_hints(RecallRequestV1Client.request)
    # ``payload`` parameter is typed as the (k1) request model.
    assert hints["payload"] is RecallRequestV1
    # Return type is the paired response model — never ``Any``/``object``/dict.
    assert hints["return"] is RecallResponseV1


def test_codegen_skips_client_handler_port_for_response_only_manifest() -> None:
    """``recall.response.v1`` is emitted as a model-only artifact.

    No client, no handler, no port files exist — the response rides on
    the request's HTTP response body and is never independently
    published or dispatched.
    """
    for kernel in ("k0", "k1"):
        models_file = GENERATED_ROOT / kernel / "models" / "recall_response_v1.py"
        assert models_file.exists(), f"response model missing under {kernel}"
    # Forbidden artefacts.
    forbidden = [
        GENERATED_ROOT / "k0" / "clients" / "recall_response_v1.py",
        GENERATED_ROOT / "k1" / "clients" / "recall_response_v1.py",
        GENERATED_ROOT / "k0" / "handlers" / "recall_response_v1.py",
        GENERATED_ROOT / "k1" / "handlers" / "recall_response_v1.py",
        GENERATED_ROOT / "k0" / "ports" / "recall_response_v1.py",
        GENERATED_ROOT / "k1" / "ports" / "recall_response_v1.py",
    ]
    for path in forbidden:
        assert not path.exists(), (
            f"unexpected artefact for response-only manifest: "
            f"{path.relative_to(GENERATED_ROOT.parent.parent).as_posix()}"
        )


@pytest.mark.asyncio
async def test_recall_request_response_round_trip_in_process() -> None:
    """End-to-end: K1 client → ASGI transport → dispatcher → K0 handler.

    The handler receives a :class:`RecallRequestV1`, returns a
    :class:`RecallResponseV1`-shaped dict; the generated client
    deserialises the wire dict into a typed
    :class:`RecallResponseV1` instance for the caller.
    """
    seen: dict[str, Any] = {}

    async def fake_recall(payload: K0RecallRequestV1) -> dict[str, Any]:
        seen["payload"] = payload
        # Echo the trace id and synthesise a deterministic response shape.
        return {
            "hits": [
                {
                    "atom_id": "atom-rt-1",
                    "content": {"text": "round-trip hit"},
                    "score": 0.5,
                    "source": "test",
                    "selector_type": payload.selectors[0].type,
                },
            ],
            "total": 1,
            "latency_ms": 7,
            "truncated": False,
            "trace_id": payload.trace_id or "",
        }

    rt_k0 = BridgeRuntime(role=Role.K0, contracts_path=CONTRACTS_PATH)
    register_k0_recall_handlers(rt_k0, impl=fake_recall)
    app = build_app(runtime=rt_k0)
    transport = InProcessHttpTransport(app=app)
    try:
        rt_k1 = BridgeRuntime(
            role=Role.K1,
            contracts_path=CONTRACTS_PATH,
            transport=transport,
        )
        client = RecallRequestV1Client(runtime=rt_k1)
        request_model = RecallRequestV1.model_validate(_valid_request_payload())
        response = await client.request(request_model)
    finally:
        await transport.close()

    # The caller sees a typed model — not a dict.
    assert isinstance(response, RecallResponseV1)
    assert response.total == 1
    assert response.truncated is False
    assert len(response.hits) == 1
    assert response.hits[0].atom_id == "atom-rt-1"
    assert response.trace_id == "trace-ms3c-1"
    # The handler received a real Pydantic model (validated upstream) of the
    # K0-side variant — each kernel owns its own generated copy of the body.
    assert isinstance(seen["payload"], K0RecallRequestV1)
    assert seen["payload"].space_id == "space-test"
