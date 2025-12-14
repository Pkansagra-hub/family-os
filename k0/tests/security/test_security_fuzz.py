"""Property-based and observability-focused Ward tests for Issue 8.2.3."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from ward import raises, test  # type: ignore[attr-defined]

from k0.gate.minimal_gate import (
    DEVICE_NOT_PROVISIONED,
    IDEM_KEY_INVALID,
    IDEM_KEY_MISMATCH,
    NO_VALID_KEYS,
    PAYLOAD_HASH_MISMATCH,
    PAYLOAD_HASH_MISSING,
    SCHEMA_BLOCKED,
    SCHEMA_NOT_ACTIVE,
    SIGNATURE_INVALID,
    SIGNATURE_MISSING,
    SPACE_MISMATCH,
)
from k0.idem import LedgerEntry
from k0.policy import evaluate_envelope
from k0.qos import Scheduler, SchedulerCapacityError, SchedulerProfile
from k0.tests.security.fixtures import (
    LedgerSuiteContext,
    SecuritySuiteContext,
    ledger_suite_context,
    security_suite_context,
)

SNAPSHOT_DIR_ENV = "WARD_SECURITY_SNAPSHOT_DIR"


def _snapshot_enabled() -> Path | None:
    directory = os.environ.get(SNAPSHOT_DIR_ENV)
    if not directory:
        return None
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _apply_mutation(
    mutation: str,
    replacement: str,
    *,
    envelope: dict[str, object],
    body: bytes,
) -> tuple[dict[str, object], bytes | None]:
    mutated = deepcopy(envelope)
    mutated_body: bytes | None = body

    if mutation == "tenant_id":
        mutated["tenant_id"] = f"tenant-{replacement}" or "tenant-attacker"
    elif mutation == "space_id":
        mutated["space_id"] = f"space-{replacement}" or "space-adversary"
    elif mutation == "schema_uri":
        mutated["schema_uri"] = f"schema://{replacement or 'rogue'}"
    elif mutation == "signature":
        mutated["sig"] = "A" * len(str(mutated.get("sig", "")) or "dummy")
    elif mutation == "payload_hash":
        mutated["payload_sha256"] = "0" * 64
    elif mutation == "missing_signature":
        mutated.pop("sig", None)
    elif mutation == "idem_key_spoof":
        mutated["idem_key"] = "deadbeef" * 8
    elif mutation == "body_tamper":
        mutated_body = f'{{"data": "tampered-{replacement or "payload"}"}}'.encode(
            "utf-8"
        )
    else:
        raise ValueError(f"Unsupported mutation: {mutation}")

    return mutated, mutated_body


@test(
    "hypothesis: tampered envelopes are rejected by the minimal gate",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)

    @settings(max_examples=25, deadline=200)
    @given(
        mutation=st.sampled_from(
            [
                "tenant_id",
                "space_id",
                "schema_uri",
                "signature",
                "payload_hash",
                "missing_signature",
                "idem_key_spoof",
                "body_tamper",
            ]
        ),
        replacement=st.text(
            min_size=3,
            max_size=10,
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        ),
    )
    def runner(mutation: str, replacement: str) -> None:
        payloads = ctx.payload_library()
        base = payloads["valid_active"]
        envelope = deepcopy(base.envelope)
        body = base.body or b""

        mutated_envelope, mutated_body = _apply_mutation(
            mutation,
            replacement,
            envelope=envelope,
            body=body,
        )

        gate = ctx.gate()
        outcome = gate.validate(mutated_envelope, mutated_body, connection=None)

        assert outcome.accepted is False
        assert outcome.reason is not None
        allowed_exact = {
            SIGNATURE_INVALID,
            SPACE_MISMATCH,
            IDEM_KEY_MISMATCH,
            IDEM_KEY_INVALID,
            SIGNATURE_MISSING,
            PAYLOAD_HASH_MISMATCH,
            PAYLOAD_HASH_MISSING,
        }
        allowed_prefixes = (
            f"{SCHEMA_NOT_ACTIVE}:",
            f"{SCHEMA_BLOCKED}:",
        )
        assert outcome.reason in allowed_exact or outcome.reason.startswith(
            allowed_prefixes
        )

    runner()


@test(
    "metrics: signature outcomes emit counters and observability events",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)
    ctx.observability.clear()
    gate = ctx.gate()

    payloads = ctx.payload_library()
    valid = payloads["valid_active"]
    success = gate.validate(valid.envelope, valid.body, connection=None)

    assert success.accepted is True
    assert (
        ctx.metric_value(
            "k0_signature_verified",
            key_state="ACTIVE",
            key_version="v1-active",
        )
        == 1.0
    )

    success_events = ctx.observability.snapshot()
    assert any(
        event.get("event") == "signature_verification"
        and event.get("outcome") == "success"
        and event.get("key_version") == "v1-active"
        for event in success_events
    )

    ctx.observability.clear()

    tampered = payloads["tampered_signature"]
    failure = gate.validate(tampered.envelope, tampered.body, connection=None)

    assert failure.accepted is False
    assert failure.reason == SIGNATURE_INVALID
    assert (
        ctx.metric_value(
            "k0_signature_verification_failed",
            device_id=ctx.device.device_id,
            reason=SIGNATURE_INVALID,
        )
        == 1.0
    )

    failure_events = ctx.observability.snapshot()
    assert any(
        event.get("event") == "signature_verification"
        and event.get("outcome") == "failure"
        and event.get("reason") == SIGNATURE_INVALID
        for event in failure_events
    )


@test(
    "metrics: provisioning denials emit counters and buffered events",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)
    ctx.observability.clear()

    gate = ctx.gate()
    payloads = ctx.payload_library()
    base = payloads["valid_active"]

    missing_envelope = deepcopy(base.envelope)
    missing_envelope["device_id"] = "device-missing"

    outcome = gate.validate(missing_envelope, base.body, connection=None)

    assert outcome.accepted is False
    assert outcome.reason == DEVICE_NOT_PROVISIONED

    assert (
        ctx.metric_value(
            "k0_provisioning_denial",
            device_id="device-missing",
            reason=DEVICE_NOT_PROVISIONED,
        )
        == 1.0
    )

    events = ctx.observability.snapshot()
    assert any(
        event.get("event") == "provisioning_check"
        and event.get("outcome") == "failure"
        and event.get("reason") == DEVICE_NOT_PROVISIONED
        and event.get("device_id") == "device-missing"
        for event in events
    )


@test(
    "metrics: schema hierarchy denials emit counters and buffered events",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)
    ctx.observability.clear()

    gate = ctx.gate()
    payloads = ctx.payload_library()
    base = payloads["valid_active"]

    blocked_envelope = deepcopy(base.envelope)
    blocked_envelope["schema_uri"] = "schema://memory.blocked"

    outcome = gate.validate(blocked_envelope, base.body, connection=None)

    assert outcome.accepted is False
    assert outcome.reason == f"{SCHEMA_BLOCKED}:schema://memory.blocked@1.0"

    assert (
        ctx.metric_value(
            "k0_schema_denial",
            reason=SCHEMA_BLOCKED,
            schema_uri="schema://memory.blocked",
            schema_version="1.0",
        )
        == 1.0
    )

    events = ctx.observability.snapshot()
    assert any(
        event.get("event") == "schema_validation"
        and event.get("outcome") == "failure"
        and event.get("reason") == SCHEMA_BLOCKED
        and event.get("schema_uri") == "schema://memory.blocked"
        and event.get("schema_version") == "1.0"
        and event.get("operator_id") == "security@family-ai"
        for event in events
    )


@test(
    "ledger: commit writes emit telemetry counters and events",
    tags=["security-fuzz"],
)
def _(context: Any = ledger_suite_context) -> None:
    ctx = cast(LedgerSuiteContext, context)
    ctx.observability.clear()

    entry = LedgerEntry(
        idem_key="idem-test-commit",
        receipt_id="receipt-ledger-commit",
        first_seen_ts="2025-10-01T00:00:00Z",
        state="COMMITTED",
        expiry_ts=None,
    )

    ctx.ledger.upsert(entry)

    assert (
        ctx.metric_value(
            "k0_idem_commit_recorded",
            state="COMMITTED",
        )
        == 1.0
    )

    events = ctx.observability.snapshot()
    assert any(
        event.get("event") == "idem_ledger_upsert"
        and event.get("idem_key") == entry.idem_key
        and event.get("state") == "COMMITTED"
        and event.get("receipt_id") == entry.receipt_id
        for event in events
    )


@test(
    "ledger: duplicate detection emits lookup telemetry and observability events",
    tags=["security-fuzz"],
)
def _(context: Any = ledger_suite_context) -> None:
    ctx = cast(LedgerSuiteContext, context)

    entry = LedgerEntry(
        idem_key="idem-test-duplicate",
        receipt_id="receipt-ledger-duplicate",
        first_seen_ts="2025-10-01T01:00:00Z",
        state="COMMITTED",
        expiry_ts=None,
    )

    ctx.ledger.upsert(entry)
    ctx.observability.clear()

    lookup = ctx.ledger.lookup(entry.idem_key)

    assert lookup is not None
    assert lookup.receipt_id == entry.receipt_id
    assert (
        ctx.metric_value(
            "k0_idem_lookup",
            outcome="hit",
            state="COMMITTED",
        )
        == 1.0
    )
    assert (
        ctx.metric_value(
            "k0_idem_duplicate_detected",
            state="COMMITTED",
        )
        == 1.0
    )

    events = ctx.observability.snapshot()
    assert any(
        event.get("event") == "idem_ledger_lookup"
        and event.get("outcome") == "hit"
        and event.get("idem_key") == entry.idem_key
        and event.get("receipt_id") == entry.receipt_id
        for event in events
    )


@test(
    "telemetry snapshots capture gate and ledger enforcement signals",
    tags=["security-fuzz", "snapshot"],
)
def _(
    security_context: Any = security_suite_context,
    ledger_context: Any = ledger_suite_context,
) -> None:
    gate_ctx = cast(SecuritySuiteContext, security_context)
    ledger_ctx = cast(LedgerSuiteContext, ledger_context)

    payloads = gate_ctx.payload_library()
    gate = gate_ctx.gate()
    valid = payloads["valid_active"]
    success = gate.validate(valid.envelope, valid.body, connection=None)
    assert success.accepted is True

    tampered = payloads["tampered_signature"]
    failure = gate.validate(tampered.envelope, tampered.body, connection=None)
    assert failure.accepted is False
    assert failure.reason == SIGNATURE_INVALID

    missing_device = deepcopy(valid.envelope)
    missing_device["device_id"] = "device-snapshot-missing"
    gate.validate(missing_device, valid.body, connection=None)

    blocked_envelope = deepcopy(valid.envelope)
    blocked_envelope["schema_uri"] = "schema://memory.blocked"
    gate.validate(blocked_envelope, valid.body, connection=None)

    ledger_entry = LedgerEntry(
        idem_key="idem-snapshot",
        receipt_id="receipt-snapshot",
        first_seen_ts="2025-10-01T02:00:00Z",
        state="COMMITTED",
        expiry_ts=None,
    )

    ledger_ctx.ledger.upsert(ledger_entry)
    ledger_ctx.ledger.lookup(ledger_entry.idem_key)

    assert (
        gate_ctx.metric_value(
            "k0_signature_verified",
            key_state="ACTIVE",
            key_version="v1-active",
        )
        == 1.0
    )
    assert (
        gate_ctx.metric_value(
            "k0_signature_verification_failed",
            device_id=gate_ctx.device.device_id,
            reason=SIGNATURE_INVALID,
        )
        == 1.0
    )
    assert (
        gate_ctx.metric_value(
            "k0_provisioning_denial",
            device_id="device-snapshot-missing",
            reason=DEVICE_NOT_PROVISIONED,
        )
        == 1.0
    )
    assert (
        gate_ctx.metric_value(
            "k0_schema_denial",
            reason=SCHEMA_BLOCKED,
            schema_uri="schema://memory.blocked",
            schema_version="1.0",
        )
        == 1.0
    )
    assert (
        ledger_ctx.metric_value(
            "k0_idem_lookup",
            outcome="hit",
            state="COMMITTED",
        )
        == 1.0
    )
    assert (
        ledger_ctx.metric_value(
            "k0_idem_duplicate_detected",
            state="COMMITTED",
        )
        == 1.0
    )

    if snapshot_dir := _snapshot_enabled():
        gate_ctx.snapshot_metrics(snapshot_dir / "security-gate.prom")
        ledger_ctx.snapshot_metrics(snapshot_dir / "security-ledger.prom")


@test(
    "hypothesis: key lifecycle permutations enforce verification rules",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)

    @settings(max_examples=30, deadline=200)
    @given(
        state=st.sampled_from(["active", "rotating", "revoked", "pending", "attacker"])
    )
    def runner(state: str) -> None:
        envelope = ctx.sign(signer=state)
        if state == "attacker":
            envelope["device_id"] = ctx.device.device_id

        gate = ctx.gate()
        outcome = gate.validate(envelope, None, connection=None)

        if state in {"active", "rotating"}:
            assert outcome.accepted is True
            assert outcome.key_state in {"ACTIVE", "ROTATING"}
        else:
            assert outcome.accepted is False
            assert outcome.reason in {SIGNATURE_INVALID, NO_VALID_KEYS}

    runner()


@test(
    "hypothesis: cross-space replays are blocked before WAL admission",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)

    @settings(max_examples=20, deadline=200)
    @given(
        space=st.text(
            min_size=5,
            max_size=12,
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        )
    )
    def runner(space: str) -> None:
        assume(space != ctx.device.space_id)

        payloads = ctx.payload_library()
        replay = deepcopy(payloads["valid_active"].envelope)
        replay["space_id"] = space

        gate = ctx.gate()
        outcome = gate.validate(replay, payloads["valid_active"].body, connection=None)

        assert outcome.accepted is False
        assert outcome.reason in {SPACE_MISMATCH, SIGNATURE_INVALID}

    runner()


@test(
    "hypothesis: privilege escalation attempts are denied by policy enforcement",
    tags=["security-fuzz"],
)
def _(context: Any = security_suite_context) -> None:
    ctx = cast(SecuritySuiteContext, context)
    base = deepcopy(ctx.base_envelope)
    base["payload_bytes"] = 1024
    base["ts"] = "2025-09-15T12:00:00+00:00"

    scenarios = st.sampled_from(
        [
            {
                "roles": ["guest"],
                "topic": "memory.delta",
                "band": "GREEN",
                "expected": "ROLE_FORBIDDEN",
            },
            {
                "roles": ["guest"],
                "topic": "ui.timeline",
                "band": "AMBER",
                "expected": "ROLE_FORBIDDEN",
            },
            {
                "roles": ["coordinator"],
                "topic": "policy.override",
                "band": "RED",
                "expected": "BAND_BLOCKED",
            },
            {
                "roles": ["coordinator"],
                "topic": "infra.sanitized.metrics",
                "band": "AMBER",
                "expected": "ROLE_FORBIDDEN",
            },
            {
                "roles": ["coordinator"],
                "topic": "memory.delta",
                "band": "GREEN",
                "expected": "DEVICE_POSTURE_DENIED",
                "posture": "revoked",
            },
        ]
    )

    @settings(max_examples=20, deadline=200)
    @given(scenario=scenarios)
    def runner(scenario: dict[str, object]) -> None:
        envelope = deepcopy(base)
        envelope["topic"] = scenario["topic"]  # type: ignore[index]
        envelope["band"] = scenario["band"]  # type: ignore[index]
        posture = scenario.get("posture")  # type: ignore[assignment]
        policy_ctx: dict[str, Any] = {
            "abac": {"roles": scenario["roles"]},  # type: ignore[index]
            "caps": {
                "fanout": {"requested": 1},
                "throughput_pps": {"requested": 16},
            },
        }
        if posture is not None:
            policy_ctx["abac"]["device_posture"] = posture
        envelope["policy"] = policy_ctx

        decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == scenario["expected"]  # type: ignore[index]

    runner()


@test(
    "hypothesis: qos scheduler throttles bursts and recovers after release",
    tags=["security-fuzz"],
)
def _() -> None:
    profile = SchedulerProfile(
        name="security-fuzz",
        description="Hypothesis-driven QoS validation",
        port_limits={"command": 8, "sse": 4},
        default_port_limit=4,
    )

    @settings(max_examples=40, deadline=200)
    @given(
        costs=st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=6),
        ports=st.lists(st.sampled_from(["command", "sse"]), min_size=1, max_size=6),
    )
    def runner(costs: list[int], ports: list[str]) -> None:
        scheduler = Scheduler(profile)
        active_counts: dict[str, int] = {}
        tokens: list[Any] = []

        for cost, port in zip(costs, ports):
            limit = profile.port_limits.get(port, profile.default_port_limit)
            current = active_counts.get(port, 0)
            if current + cost <= limit:
                token = scheduler.acquire(band="GREEN", port=port, cost=cost)
                tokens.append(token)
                active_counts[port] = current + cost
                assert scheduler.active_tokens(port) == active_counts[port]
            else:
                with raises(SchedulerCapacityError):
                    scheduler.acquire(band="GREEN", port=port, cost=cost)
                break

        while tokens:
            token = tokens.pop()
            port = token.port
            cost = token.cost
            token.release()
            previous = active_counts.get(port, 0)
            new_value = max(previous - cost, 0)
            active_counts[port] = new_value
            assert scheduler.active_tokens(port) == new_value

        for port, remaining in active_counts.items():
            assert remaining == 0
            assert scheduler.active_tokens(port) == 0

    runner()

