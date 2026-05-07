"""MS-3d.1 contract tests for the 5 K0\u2192K1 SSE manifests.

These tests are the live demonstration of the Bridge MS-3d.1 exit
criteria for the first round of streaming (push) contracts:

1. All 5 SSE manifests parse against the meta-schema.
2. Each schema validates a representative payload (positive case).
3. Codegen emits the SSE-shaped artefacts: an ``<Topic>Subscriber``
   class on the K1 (consumer) handler file with an
   ``async def subscribe(handler, *, cursor=None)`` method, and an
   ``<Topic>Client.emit(payload)`` method on the K0 (producer) client
   file. Crucially, the kernel-level ``register_handlers(runtime, impl)``
   aggregate must NOT list SSE topics (different shape).
4. The 5 SSE topics are present in ``bus.yaml`` (registry alignment).
5. SSE manifests live under ``direction: k0_to_k1`` and ``transport: sse``
   (sanity: the codegen branch is keyed off ``transport``, not direction).

All tests use real components \u2014 real schema, real Pydantic, real
codegen artefacts, real manifest loader. No LLM verification, no
mocks.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from tooling.contracts.manifest_loader import load_manifests

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"
GENERATED_ROOT = Path(__file__).resolve().parents[3] / "bridge" / "_generated"
BUS_YAML = Path(__file__).resolve().parents[3] / "k1" / "config" / "bus.yaml"


SSE_TOPICS: tuple[str, ...] = (
    "curiosity.intent.v1",
    "k0.learning.advisory.v1",
    "k0.proactive.signal.v1",
    "p03.complete.v1",
    "p03.gap.detected.v1",
)


# Module-suffix per topic (codegen sluggifies dots to underscores).
_TOPIC_TO_MODULE = {
    "curiosity.intent.v1": "curiosity_intent_v1",
    "k0.learning.advisory.v1": "k0_learning_advisory_v1",
    "k0.proactive.signal.v1": "k0_proactive_signal_v1",
    "p03.complete.v1": "p03_complete_v1",
    "p03.gap.detected.v1": "p03_gap_detected_v1",
}


# Representative valid payloads (one per topic). These are the minimum
# schemas demand plus one optional field, to exercise both required and
# optional branches.
_VALID_PAYLOADS: dict[str, dict[str, Any]] = {
    "curiosity.intent.v1": {
        "envelope_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
        "gap_id": "gap-7-rachel-coffee",
        "question_text": "Who is Rachel?",
        "budget_remaining": 3,
        "trace_id": "trace-curio-1",
    },
    "k0.learning.advisory.v1": {
        "envelope_id": "01HZZZZZZZZZZZZZZZZZZZZZZA",
        "advisory_id": "adv-1",
        "pipeline_id": "p21.learning_loop",
        "signal_class": "drift",
        "details": {"metric": "recall_p99_ms", "delta_pct": 17.4},
    },
    "k0.proactive.signal.v1": {
        "envelope_id": "01HZZZZZZZZZZZZZZZZZZZZZZB",
        "trigger_type": "reminder",
        "priority": "HIGH",
        "context": {"due_in_min": 15},
    },
    "p03.complete.v1": {
        "envelope_id": "01HZZZZZZZZZZZZZZZZZZZZZZC",
        "cycle_id": "cycle-2026-05-13-T1",
        "completed_at_utc_ms": 1747100000000,
        "atoms_consolidated": 412,
        "patterns_discovered": 7,
        "gaps_emitted": 3,
    },
    "p03.gap.detected.v1": {
        "envelope_id": "01HZZZZZZZZZZZZZZZZZZZZZZD",
        "gap_id": "gap-7-rachel-coffee",
        "gap_type": "MISSING_CONTEXT",
        "detected_at_utc_ms": 1747100000000,
        "priority_score": 0.81,
    },
}


# ---------------------------------------------------------------------------
# 1. Manifest loader / meta-schema
# ---------------------------------------------------------------------------


def test_all_5_sse_manifests_load_without_error() -> None:
    """The full bundle must load \u2014 no meta-schema violations."""
    manifests = load_manifests(CONTRACTS_PATH)
    loaded_topics = {m.topic for m in manifests}
    for topic in SSE_TOPICS:
        assert topic in loaded_topics, f"missing manifest: {topic}"


@pytest.mark.parametrize("topic", SSE_TOPICS)
def test_sse_manifest_direction_and_transport(topic: str) -> None:
    """Every SSE manifest must declare ``direction: k0_to_k1`` and ``transport: sse``."""
    manifests = load_manifests(CONTRACTS_PATH)
    [m] = [m for m in manifests if m.topic == topic]
    assert m.raw["direction"] == "k0_to_k1", f"{topic}: wrong direction"
    assert m.raw["delivery"]["transport"] == "sse", f"{topic}: wrong transport"
    # Producer is K0, consumer is K1.
    assert m.producer_kernel == "k0", f"{topic}: producer_kernel must be k0"
    assert m.consumer_kernel == "k1", f"{topic}: consumer_kernel must be k1"


# ---------------------------------------------------------------------------
# 2. Schema payload validation (positive)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", SSE_TOPICS)
def test_sse_payload_validates_against_pydantic_model(topic: str) -> None:
    """Generated Pydantic models accept the representative payload."""
    module_name = _TOPIC_TO_MODULE[topic]
    # Both K0 and K1 sides have an independent generated model class \u2014
    # the consumer (K1) is the one that does on-wire decode, so test it.
    mod = importlib.import_module(f"bridge._generated.k1.models.{module_name}")
    # Convention: codegen uses the PascalCase'd module name as the class.
    cls = next(
        v
        for k, v in vars(mod).items()
        if k.lower().replace("_", "") == module_name.replace("_", "")
    )
    instance = cls.model_validate(_VALID_PAYLOADS[topic])
    # Round-trip: model_dump round-trips back through validation.
    cls.model_validate(instance.model_dump())


def test_sse_payload_missing_required_field_rejected() -> None:
    """Pydantic rejects a payload missing a required field."""
    from bridge._generated.k1.models.curiosity_intent_v1 import CuriosityIntentV1

    bad = {k: v for k, v in _VALID_PAYLOADS["curiosity.intent.v1"].items() if k != "gap_id"}
    with pytest.raises(ValidationError):
        CuriosityIntentV1.model_validate(bad)


# ---------------------------------------------------------------------------
# 3. Codegen artefact shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", SSE_TOPICS)
def test_codegen_emits_subscriber_on_k1_handler_file(topic: str) -> None:
    """K1 handler file exposes ``<Topic>Subscriber.subscribe`` (NOT register_handlers)."""
    module_name = _TOPIC_TO_MODULE[topic]
    mod = importlib.import_module(f"bridge._generated.k1.handlers.{module_name}")
    # Locate the subscriber class.
    subscribers = [
        v
        for k, v in vars(mod).items()
        if inspect.isclass(v) and k.endswith("Subscriber") and v.__module__ == mod.__name__
    ]
    assert len(subscribers) == 1, f"{topic}: expected exactly one Subscriber class"
    sub_cls = subscribers[0]
    assert sub_cls.__topic__ == topic
    assert sub_cls.__transport__ == "sse"
    assert hasattr(sub_cls, "subscribe"), f"{topic}: Subscriber missing .subscribe"
    # SSE files MUST NOT expose register_handlers (HTTP shape).
    assert not hasattr(
        mod, "register_handlers"
    ), f"{topic}: SSE handler must not expose register_handlers"
    assert hasattr(
        mod, "register_subscriber"
    ), f"{topic}: SSE handler must expose register_subscriber"


@pytest.mark.parametrize("topic", SSE_TOPICS)
def test_codegen_emits_emit_method_on_k0_client(topic: str) -> None:
    """K0 client file exposes ``<Topic>Client.emit(payload)`` (NOT publish/request)."""
    module_name = _TOPIC_TO_MODULE[topic]
    mod = importlib.import_module(f"bridge._generated.k0.clients.{module_name}")
    clients = [
        v
        for k, v in vars(mod).items()
        if inspect.isclass(v) and k.endswith("Client") and v.__module__ == mod.__name__
    ]
    assert len(clients) == 1, f"{topic}: expected exactly one Client class"
    cli_cls = clients[0]
    assert cli_cls.__topic__ == topic
    assert cli_cls.__transport__ == "sse"
    assert hasattr(cli_cls, "emit"), f"{topic}: Client missing .emit"
    # SSE clients MUST NOT publish/request (HTTP shapes).
    assert not hasattr(cli_cls, "publish"), f"{topic}: SSE client must not expose .publish"
    assert not hasattr(cli_cls, "request"), f"{topic}: SSE client must not expose .request"


def test_kernel_aggregate_handler_registry_excludes_sse_topics() -> None:
    """K1 ``register_handlers`` impl-binding aggregate must skip SSE topics.

    SSE has push-subscribe shape, not request/dispatch \u2014 listing it in
    the aggregate would falsely demand ``impl.<sse_method>`` callables
    on every kernel impl.
    """
    text = (GENERATED_ROOT / "k1" / "handler_registry.py").read_text(encoding="utf-8")
    for topic in SSE_TOPICS:
        method = _TOPIC_TO_MODULE[topic]
        assert (
            f'"{method}"' not in text
        ), f"k1/handler_registry.py must NOT list SSE method {method}"


def test_kernel_aggregate_client_stub_excludes_sse_topics() -> None:
    """K0 ``client_stub.py`` aggregate must skip SSE topics."""
    text = (GENERATED_ROOT / "k0" / "client_stub.py").read_text(encoding="utf-8")
    for topic in SSE_TOPICS:
        method = _TOPIC_TO_MODULE[topic]
        # The aggregate emits ``async def <method>(...)``; SSE method
        # names must not appear there.
        assert (
            f"async def {method}(" not in text
        ), f"k0/client_stub.py must NOT define stub for SSE method {method}"


# ---------------------------------------------------------------------------
# 4. bus.yaml timing alignment
# ---------------------------------------------------------------------------


def test_sse_topics_resolve_via_bus_yaml_timing_rules() -> None:
    """Each SSE topic resolves to a sensible timing mode via ``k1/config/bus.yaml``.

    ``bus.yaml`` uses longest-prefix match; SSE push topics are fire-and-forget
    and should land on RELAXED or BEST_EFFORT (never STRICT) per design D14.
    """
    if not BUS_YAML.exists():
        pytest.skip("k1/config/bus.yaml not present in this checkout")
    cfg = yaml.safe_load(BUS_YAML.read_text(encoding="utf-8")) or {}
    default_mode = cfg.get("default_mode", "RELAXED")
    rules: dict[str, str] = cfg.get("timing_rules", {}) or {}
    for topic in SSE_TOPICS:
        matches = [p for p in rules if topic.startswith(p)]
        mode = rules[max(matches, key=len)] if matches else default_mode
        assert mode in {
            "RELAXED",
            "BEST_EFFORT",
        }, f"SSE topic {topic} resolved to {mode} \u2014 must be RELAXED or BEST_EFFORT"
