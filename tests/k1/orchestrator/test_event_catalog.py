"""
Epic 7.4.4 -- Orchestrator event catalog compliance tests.

Validates runtime compliance against:
  - k1/orchestrator/events.py (authoritative constants)
  - k1/contracts/modules/orchestrator/wiring.contract.yaml (catalog contract)
  - k1/contracts/schemas/orchestrator/events/** (schema contracts)

Design notes:
  - Contract YAML is parsed at runtime (anti-hardcode policy).
  - Schema validation checks topic const and ORCH-09 trace_id requirement.
  - Routing checks cover direct service subscriptions plus declared handlers.
"""

from __future__ import annotations

import ast
import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import jsonschema
import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVENTS_FILE = _REPO_ROOT / "k1" / "orchestrator" / "events.py"
_WIRING_CONTRACT_PATH = (
    _REPO_ROOT / "k1" / "contracts" / "modules" / "orchestrator" / "wiring.contract.yaml"
)

with _WIRING_CONTRACT_PATH.open("r", encoding="utf-8") as _f:
    _CONTRACT: dict[str, Any] = yaml.safe_load(_f)

_EVENTS = importlib.import_module("k1.orchestrator.events")

ALL_EMITTED: set[str] = set(_EVENTS.ALL_EMITTED)
ALL_CONSUMED: set[str] = set(_EVENTS.ALL_CONSUMED)

CONTRACT_EMITS: dict[str, str] = {
    item["topic"]: item["schema"] for item in _CONTRACT.get("events", {}).get("emits", [])
}
CONTRACT_SUBSCRIBES: dict[str, dict[str, str]] = {
    item["topic"]: {"schema": item["schema"], "handler": item["handler"]}
    for item in _CONTRACT.get("events", {}).get("subscribes", [])
}


def _load_schema(rel_path: str) -> dict[str, Any]:
    schema_path = _REPO_ROOT / rel_path
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _resolve_handler(handler_path: str) -> Any:
    """Resolve a handler path of form 'module.path:Class.method' or ':function'."""
    module_path, symbol_path = handler_path.split(":", maxsplit=1)
    module = importlib.import_module(module_path)

    target: Any = module
    for part in symbol_path.split("."):
        target = getattr(target, part)
    return target


def _event_constants() -> dict[str, str]:
    """All UPPER_CASE string constants from events.py excluding aggregate sets."""
    out: dict[str, str] = {}
    for name, value in vars(_EVENTS).items():
        if not name.isupper():
            continue
        if name in {"ALL_EMITTED", "ALL_CONSUMED"}:
            continue
        if isinstance(value, str):
            out[name] = value
    return out


def _symbol_usage_index() -> dict[str, int]:
    """Index symbol usage count across k1/orchestrator Python files."""
    counts: dict[str, int] = {}
    for py_file in (_REPO_ROOT / "k1" / "orchestrator").rglob("*.py"):
        if py_file == _EVENTS_FILE:
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for symbol in _event_constants():
            counts[symbol] = counts.get(symbol, 0) + text.count(symbol)
    return counts


def _subscribe_patterns_in_code() -> set[str]:
    """Collect literal subscribe() patterns from orchestrator code."""
    patterns: set[str] = set()

    for py_file in (_REPO_ROOT / "k1" / "orchestrator").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "subscribe":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                patterns.add(first.value)
    return patterns


class TestEventCatalogConstants:
    @pytest.mark.parametrize("topic", sorted(ALL_EMITTED))
    def test_each_emitted_topic_constant_is_importable_string(self, topic: str) -> None:
        assert isinstance(topic, str)
        assert topic.startswith("k1.")
        assert topic.endswith(".v1")

    @pytest.mark.parametrize("topic", sorted(ALL_CONSUMED))
    def test_each_consumed_topic_constant_is_importable_string(self, topic: str) -> None:
        assert isinstance(topic, str)
        assert topic.startswith("k1.")
        assert topic.endswith(".v1")

    def test_emitted_catalog_size(self) -> None:
        # V1 catalog after phantom-field removals.
        # M16.E2.I2: +1 for ORCH_DAG_NODE_FAILED.
        assert len(ALL_EMITTED) == 20

    def test_consumed_catalog_size(self) -> None:
        assert len(ALL_CONSUMED) == 10


class TestEventContractAlignment:
    def test_emitted_topics_match_wiring_contract(self) -> None:
        assert set(CONTRACT_EMITS) == ALL_EMITTED

    def test_consumed_topics_match_wiring_contract(self) -> None:
        assert set(CONTRACT_SUBSCRIBES) == ALL_CONSUMED

    @pytest.mark.parametrize("topic,schema_rel", sorted(CONTRACT_EMITS.items()))
    def test_emitted_schema_file_exists_and_matches_topic_const(
        self,
        topic: str,
        schema_rel: str,
    ) -> None:
        schema_path = _REPO_ROOT / schema_rel
        assert schema_path.is_file(), f"Missing emitted schema file: {schema_rel}"

        schema = _load_schema(schema_rel)
        topic_const = schema.get("properties", {}).get("topic", {}).get("const")
        assert topic_const == topic

        required = set(schema.get("required", []))
        assert "trace_id" in required, f"ORCH-09 missing in schema required fields: {schema_rel}"

    @pytest.mark.parametrize("topic,item", sorted(CONTRACT_SUBSCRIBES.items()))
    def test_consumed_schema_file_exists_handler_resolves_and_topic_const_matches(
        self,
        topic: str,
        item: dict[str, str],
    ) -> None:
        schema_rel = item["schema"]
        handler = item["handler"]

        schema_path = _REPO_ROOT / schema_rel
        assert schema_path.is_file(), f"Missing consumed schema file: {schema_rel}"

        schema = _load_schema(schema_rel)
        topic_const = schema.get("properties", {}).get("topic", {}).get("const")
        assert topic_const == topic

        resolved = _resolve_handler(handler)
        assert callable(resolved), f"Declared handler is not callable: {handler}"


class TestEventCoverageAndOrphans:
    def test_each_emitted_topic_has_at_least_one_emitter_reference(self) -> None:
        usages = _symbol_usage_index()
        symbol_to_topic = _event_constants()

        missing_symbols = [
            symbol
            for symbol, topic in symbol_to_topic.items()
            if topic in ALL_EMITTED and usages.get(symbol, 0) == 0
        ]
        assert not missing_symbols, (
            "Emitted catalog topics without code-path references: " f"{missing_symbols}"
        )

    def test_each_consumed_topic_has_at_least_one_routing_declaration(self) -> None:
        # A routing declaration may come from:
        #  1) wiring.contract handler map (explicit contract wiring), and/or
        #  2) concrete subscribe() literals in code.
        patterns = _subscribe_patterns_in_code()

        missing: list[str] = []
        for topic in sorted(ALL_CONSUMED):
            declared_in_contract = topic in CONTRACT_SUBSCRIBES
            declared_in_code = topic in patterns
            if not declared_in_contract and not declared_in_code:
                missing.append(topic)

        assert not missing, f"Consumed topics without routing declaration: {missing}"

    def test_no_orphan_catalog_topics_in_wiring_contract(self) -> None:
        emitted_orphans = set(CONTRACT_EMITS) - ALL_EMITTED
        consumed_orphans = set(CONTRACT_SUBSCRIBES) - ALL_CONSUMED
        assert not emitted_orphans
        assert not consumed_orphans


class TestRoutingViaTestEventAdapter:
    @pytest.mark.asyncio
    async def test_core_consumed_events_route_to_service_handlers(
        self,
        orchestrator_for_testing: Any,
    ) -> None:
        service = orchestrator_for_testing
        await service.init()

        event = service._event_port
        mailbox = service._mailbox
        from k1.orchestrator.types import PlanStep

        # PLAN_READY -> mailbox enqueue side effect
        before_depth = mailbox.depth()
        event.fire(
            _EVENTS.PLAN_READY,
            {
                "plan_id": str(uuid4()),
                "request_id": str(uuid4()),
                "intent": "intent",
                "steps": [
                    PlanStep(
                        id="step-1",
                        capability="tool.calendar.search",
                        params={"query": "x"},
                        deps=[],
                        prompt_template=None,
                        tools_granted=None,
                        output_schema=None,
                        condition=None,
                        is_optional=False,
                        has_side_effects=False,
                        compensation=None,
                        timeout_ms=None,
                        required_context=None,
                    )
                ],
                "dependencies": {},
                "trace_id": str(uuid4()),
            },
        )
        assert mailbox.depth() == before_depth + 1

        # PLAN_FAILED -> pending cleanup
        request_id_failed = str(uuid4())
        service._pending_plans[request_id_failed] = object()  # type: ignore[assignment]
        event.fire(_EVENTS.PLAN_FAILED, {"request_id": request_id_failed})
        assert request_id_failed not in service._pending_plans

        # PLAN_CANCELLED -> pending cleanup
        request_id_cancelled = str(uuid4())
        service._pending_plans[request_id_cancelled] = object()  # type: ignore[assignment]
        event.fire(_EVENTS.PLAN_CANCELLED, {"request_id": request_id_cancelled})
        assert request_id_cancelled not in service._pending_plans


class TestTracePropagationAndSchemaRuntime:
    @pytest.mark.asyncio
    async def test_runtime_emitted_events_include_trace_id_and_validate_schema_envelope(
        self,
        orchestrator_for_testing: Any,
        sample_task_envelope: Any,
    ) -> None:
        service = orchestrator_for_testing
        await service.process(sample_task_envelope)

        delta = service._delta_port
        assert delta.emitted, "Expected at least one emitted event in MEDIUM flow"

        emitted_schema_by_topic = {t: p for t, p in CONTRACT_EMITS.items()}

        for topic, payload, trace_id in delta.emitted:
            assert trace_id, f"Empty trace_id on emitted topic: {topic}"

            # ORCH-09: emitted payload should carry trace_id (legacy field name).
            assert (
                "trace_id" in payload or "cognitive_trace_id" in payload
            ), f"Missing trace field in payload for topic: {topic}"

            schema_rel = emitted_schema_by_topic.get(topic)
            if not schema_rel:
                # Not part of orchestrator emitted catalog (ignore e.g. aux events).
                continue

            schema = _load_schema(schema_rel)
            payload_for_schema = {
                k: v for k, v in payload.items() if k not in {"trace_id", "cognitive_trace_id"}
            }
            event_doc = {
                "event_id": str(uuid4()),
                "topic": topic,
                "timestamp": datetime.now(UTC).isoformat(),
                "trace_id": trace_id,
                "source": "orchestrator",
                "version": "v1",
                "payload": payload_for_schema,
            }
            jsonschema.validate(instance=event_doc, schema=schema)
