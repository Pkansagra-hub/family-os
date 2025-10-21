from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Dict, Iterator, List

from ward import test  # type: ignore[attr-defined]

from k0.policy import evaluate_envelope
from k0.policy.pep_syscall import LOGGER, Obligation, PolicyDecision


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(
        self, record: logging.LogRecord
    ) -> None:  # pragma: no cover - logging hook
        self.records.append(record)


@contextmanager
def capture_pep_logs() -> Iterator[List[logging.LogRecord]]:
    handler = _ListHandler()
    previous_level = LOGGER.level
    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(handler)
    try:
        yield handler.records
    finally:
        LOGGER.removeHandler(handler)
        LOGGER.setLevel(previous_level)


def _obligation_index(decision: PolicyDecision) -> Dict[str, Obligation]:
    return {obligation.name: obligation for obligation in decision.obligations}


@test("PEP allows amber band submissions with matching role and caps")
def _() -> None:
    envelope: Dict[str, object] = {
        "band": "AMBER",
        "tenant_id": "tenant-main",
        "space_id": "space-main",
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.1",
        "ts": "2025-08-01T00:00:00Z",
        "payload_bytes": 4096,
        "policy": {
            "abac": {
                "roles": ["coordinator"],
                "device_posture": "out_of_date",
            },
            "caps": {
                "fanout": {"requested": 6},
                "throughput_pps": {"requested": 120},
            },
        },
    }

    with capture_pep_logs() as records:
        decision = evaluate_envelope(envelope)

    assert decision.admit is True
    obligations: Dict[str, Obligation] = _obligation_index(decision)
    assert "kernel.audit.log" in obligations
    assert obligations["kernel.audit.log"].details.get("level") == "amber"
    assert "kernel.device.patch" in obligations
    assert obligations["kernel.device.patch"].details.get("deadline") == "PT24H"

    assert any(record.levelno == logging.INFO for record in records)


@test("PEP blocks red band submissions and emits security obligation")
def _() -> None:
    envelope: Dict[str, object] = {
        "band": "RED",
        "tenant_id": "tenant-main",
        "space_id": "space-main",
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.1",
        "ts": "2025-08-01T00:00:00Z",
        "payload_bytes": 256,
        "policy": {
            "abac": {
                "roles": ["security"],
                "device_posture": "active",
            },
            "caps": {
                "fanout": {"requested": 2},
                "throughput_pps": {"requested": 50},
            },
        },
    }

    decision = evaluate_envelope(envelope)

    assert decision.admit is False
    assert decision.deny_reason == "BAND_BLOCKED"
    obligations = _obligation_index(decision)
    assert "kernel.security.notify" in obligations
    assert obligations["kernel.security.notify"].details.get("severity") == "critical"


@test("PEP denies submissions that exceed fanout caps and annotates obligation")
def _() -> None:
    envelope: Dict[str, object] = {
        "band": "GREEN",
        "tenant_id": "tenant-main",
        "space_id": "space-main",
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.1",
        "ts": "2025-08-01T00:00:00Z",
        "payload_bytes": 512,
        "policy": {
            "abac": {
                "roles": ["coordinator"],
                "device_posture": "active",
            },
            "caps": {
                "fanout": {"requested": 32},
                "throughput_pps": {"requested": 100},
            },
        },
    }

    with capture_pep_logs() as records:
        decision = evaluate_envelope(envelope)

    assert decision.admit is False
    assert decision.deny_reason == "CAP_FANOUT_EXCEEDED"

    obligations = _obligation_index(decision)
    assert "kernel.qos.tighten" in obligations
    tighten_details = obligations["kernel.qos.tighten"].details
    assert tighten_details.get("cap") == "fanout"
    assert tighten_details.get("limit") == "16"
    assert tighten_details.get("requested") == "32"

    assert any(record.levelno == logging.WARNING for record in records)
