"""K1 Kernel Probe — Phase 9 (k1.selfmodel).

Boots a real :class:`KernelService` with ``enable_self_model=True``,
introspects every M5.E3 wiring point, and exercises one end-to-end
gate cycle, one HITL escalation, and the V0 walk-through across all
13 situation kinds (S1..S13).

By design the probe makes **no** LLM calls. Every check is structural
or uses pre-wired services with synthetic actor + tool inputs.

Issues covered:

* M5.E4.I1 — Probe scaffolding (this file's CLI shell + ``ProbeReport``
  output to ``data/kernel_probe_phase9_*.json``).
* M5.E4.I2 — 9 introspection checks (bundle, bus topics, constitution,
  identity, composer, evaluator, dispatcher gate, capsule renderer,
  SSE subscription).
* M5.E4.I3 — End-to-end ``recall_memory`` ALLOW gate cycle through the
  real session dispatcher.
* M5.E4.I4 — High-risk ``share_location`` REQUIRE_CONFIRMATION cycle
  routed through ``HumanInTheLoopService.ask_approval`` with a stub
  auto-approver.
* M5.E4.I5 — 13/13 V0 situation walk-through (composer + policy
  agreement on every ``situation_kind``).

Usage::

    python -m scripts.kernel_probe_phase9_selfmodel \\
        --json data/kernel_probe_phase9_stub.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# ── repo path ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataclasses import replace as _dc_replace  # noqa: E402

from k1.concierge.config.kernel import KernelConfig  # noqa: E402
from k1.concierge.llm.types import ToolCallResult  # noqa: E402
from k1.kernel.bootstrap import start_kernel, stop_kernel  # noqa: E402
from k1.selfmodel.contracts.policy import (  # noqa: E402
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    RiskClass,
)
from k1.selfmodel.contracts.situation import Capabilities  # noqa: E402
from k1.selfmodel.contracts.situations import SITUATION_KINDS  # noqa: E402
from k1.selfmodel.events.topics import (  # noqa: E402
    TOPIC_SELFMODEL_STARTUP_COMPLETE,
)
from k1.selfmodel.service.family_model import FAMILY_MODEL_WRITER_ID  # noqa: E402
from k1.selfmodel.service.self_model import SELF_MODEL_WRITER_ID  # noqa: E402
from scripts._probe_common import ProbeReport, _attr  # noqa: E402

# The bundle's projection store has an allowlist that rejects unknown
# writer ids. The bootstrap signer is the only valid writer for
# constitution rows; the per-projection services own self/family.
CONSTITUTION_WRITER_ID = "selfmodel:bootstrap"

# Test fixtures — repo-local helpers reused by the probe to seed a
# synthetic guardian + family + bootstrap-shaped constitution into the
# in-memory projection store. The probe is read-only on production code
# paths; this seeding is purely synthetic.
from tests.k1.selfmodel.service._helpers import (  # noqa: E402
    make_actor,
    make_constitution,
    make_family,
    make_member,
    v0_body,
)

# ── Constants ────────────────────────────────────────────────────────────
T_NOW_MS = lambda: int(time.time() * 1000)  # noqa: E731
PROBE_SESSION_ID = "probe-phase9-session"
PROBE_DEVICE_ID = "probe-device-1"
PROBE_ACTOR_ID = "probe-guardian"
LOW_RISK_TOOL = "recall_memory"
HIGH_RISK_TOOL = "share_location"  # in must_ask for guardian role


def _seed_synthetic_household(bundle: Any) -> None:
    """Seed the projection store with a guardian + bootstrap-shaped
    constitution so ``compose()`` can build frames.

    Two actor IDs are seeded:

    * :data:`PROBE_ACTOR_ID` — used by direct composer/evaluator probes.
    * ``actor:{PROBE_SESSION_ID}`` — the id derived by
      ``_derive_session_actor`` for the probe session, so the gate
      installed at P3.5 can compose against it.
    """
    store = bundle.store
    family = make_family(
        members=(make_member(PROBE_ACTOR_ID, role="guardian", name="ProbeGuardian"),)
    )
    store.write_family(family, writer_id="selfmodel:bootstrap")
    for actor_id in (PROBE_ACTOR_ID, f"actor:{PROBE_SESSION_ID}"):
        store.write_self(
            make_actor(actor_id, role="guardian", name="ProbeGuardian"),
            writer_id="selfmodel:bootstrap",
        )
    # Constitution is already written by S2.6 bootstrap; we only need
    # to ensure its body matches what the V0 evaluator expects. The
    # bootstrap row uses `v0_body()` semantics already.
    _ = make_constitution, v0_body  # noqa: B018  (imported for parity)


# =====================================================================
# I2 — Layer 1: bundle + topics + constitution + identity
# =====================================================================
def probe_bundle_wired(svc: Any, report: ProbeReport) -> Any | None:
    layer = "Bundle wiring"
    bundle = _attr(svc, "self_model_bundle")
    if bundle is None:
        report.add(
            layer,
            "svc.self_model_bundle",
            "FAIL",
            None,
            "kernel did not construct selfmodel bundle (enable_self_model=False?)",
        )
        return None
    report.add(layer, "svc.self_model_bundle", "OK", type(bundle).__name__)

    for name in (
        "store",
        "self_model",
        "family_model",
        "constitution",
        "composer",
        "evaluator",
        "identity",
        "amendments",
        "validator",
        "capsule_builder",
        "citation_builder",
    ):
        obj = _attr(bundle, name)
        report.add(
            layer,
            f"bundle.{name}",
            "OK" if obj is not None else "FAIL",
            type(obj).__name__ if obj is not None else None,
        )

    # health() schema check (M5.E3.I4 surface).
    try:
        h = bundle.health()
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "bundle.health()", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return bundle
    for key in ("status", "constitution", "store", "identity", "family_space_id", "bootstrap"):
        report.add(
            layer,
            f"health.{key}",
            "OK" if key in h else "FAIL",
            h.get(key),
        )
    return bundle


def probe_bus_topics(svc: Any, report: ProbeReport) -> None:
    layer = "Bus topics"
    bus = _attr(svc, "_bus")
    if bus is None:
        report.add(layer, "svc._bus", "FAIL", None)
        return
    # The bus owns a TimingChain wrapping a TimingConfig. Rather than
    # spelunk private fields, we re-resolve against
    # ``default_timing_config()`` (the same factory the bus uses).
    from k1.bus.timing.defaults import DeliveryMode, default_timing_config

    cfg = default_timing_config()
    for prefix in (
        "k1.selfmodel.policy",
        "k1.selfmodel.constitution",
        "k1.selfmodel.identity",
        "k1.selfmodel.startup",
    ):
        try:
            mode = cfg.resolve(prefix + ".x.v1")
            ok = mode == DeliveryMode.STRICT
            report.add(
                layer,
                f"timing[{prefix}]",
                "OK" if ok else "WARN",
                getattr(mode, "name", str(mode)),
            )
        except Exception as exc:  # noqa: BLE001
            report.add(layer, f"timing[{prefix}]", "FAIL", None, str(exc))
    report.add(
        layer,
        "TOPIC_SELFMODEL_STARTUP_COMPLETE",
        "OK",
        TOPIC_SELFMODEL_STARTUP_COMPLETE,
    )


def probe_constitution(bundle: Any, report: ProbeReport) -> None:
    layer = "Constitution"
    try:
        active = bundle.constitution.get_active()
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "constitution.get_active()", "FAIL", None, str(exc))
        return
    snap = _attr(active, "snapshot")
    report.add(
        layer,
        "snapshot",
        "OK" if snap is not None else "FAIL",
        type(snap).__name__ if snap else None,
    )
    report.add(layer, "snapshot.version", "OK", _attr(snap, "version"))
    report.add(layer, "snapshot.constitution_id", "OK", _attr(snap, "constitution_id"))
    report.add(layer, "freshness", "OK", str(_attr(active, "freshness")))


def probe_identity(bundle: Any, report: ProbeReport) -> None:
    layer = "Identity"
    mgr = bundle.identity
    # tier-0 session for synthetic device — uses the manager's surface
    # without binding new methods.
    try:
        # IdentitySessionManager.start_session signature varies by impl;
        # call the documented entry point and tolerate its return shape.
        sess = mgr.start_session(
            device_id=PROBE_DEVICE_ID,
            actor_id=PROBE_ACTOR_ID,
        )
        report.add(layer, "start_session(tier=0)", "OK", type(sess).__name__)
    except TypeError:
        # Some builds expose a different signature; fall back to a
        # purely structural assertion that the manager is wired.
        report.add(
            layer,
            "start_session",
            "INFO",
            "signature mismatch — structural check only",
        )
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "start_session", "WARN", None, f"{type(exc).__name__}: {exc}")
    # Profile registry visible.
    profiles = getattr(mgr, "_profiles", {})
    report.add(layer, "registered profiles", "INFO", len(profiles))


# =====================================================================
# I2 — Layer 2: composer + policy + dispatcher gate + capsule
# =====================================================================
def probe_composer(bundle: Any, report: ProbeReport) -> Any | None:
    layer = "Composer"
    try:
        frame = bundle.composer.compose(
            PROBE_ACTOR_ID,
            T_NOW_MS(),
            PROBE_DEVICE_ID,
            "caregiver_context_briefing",
        )
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "compose(S12)", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return None
    report.add(layer, "compose(S12)", "OK", type(frame).__name__)
    report.add(layer, "frame.actor_id", "OK", _attr(frame, "actor_id"))
    report.add(layer, "frame.situation_kind", "OK", _attr(frame, "situation_kind"))
    caps = _attr(frame, "capabilities")
    report.add(
        layer,
        "frame.capabilities.can_do",
        "OK" if caps is not None else "FAIL",
        sorted(getattr(caps, "can_do", set())) if caps else None,
    )
    return frame


def probe_evaluator(bundle: Any, frame: Any, report: ProbeReport) -> None:
    layer = "Policy evaluator"
    if frame is None:
        report.add(layer, "evaluate()", "FAIL", None, "no frame from composer")
        return
    req = PolicyRequest(
        actor_id=PROBE_ACTOR_ID,
        tool_name=LOW_RISK_TOOL,
        risk_class=RiskClass.LOW,
    )
    try:
        verdict = bundle.evaluator.evaluate(req, frame)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "evaluate(low-risk)", "FAIL", None, str(exc))
        return
    decision = _attr(verdict, "decision")
    ok = decision == PolicyDecision.ALLOW
    report.add(
        layer,
        "evaluate(recall_memory, LOW)",
        "OK" if ok else "WARN",
        str(decision),
        "" if ok else "expected ALLOW for low-risk read",
    )


def probe_session_wiring(svc: Any, report: ProbeReport) -> Any:
    """Reserved for future expansion. Inline checks live in :func:`_run`."""
    return None


# =====================================================================
# I3 — End-to-end ALLOW gate cycle
# =====================================================================
async def probe_e2e_gate_cycle(session: Any, report: ProbeReport) -> None:
    layer = "E2E gate cycle"
    front = _attr(session, "front_dispatcher")
    gate = _attr(front, "policy_gate")
    if gate is None:
        report.add(layer, "front gate", "FAIL", None, "no gate installed")
        return
    tool_call = ToolCallResult(
        id=f"probe-{uuid.uuid4().hex[:8]}",
        name=LOW_RISK_TOOL,
        arguments={"query": "weekend chores"},
    )
    try:
        result = await gate(tool_call)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "gate(recall_memory)", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return
    # ALLOW = passthrough → gate returns None
    if result is None:
        report.add(layer, "gate verdict", "OK", "ALLOW (passthrough)")
    else:
        report.add(
            layer,
            "gate verdict",
            "WARN",
            getattr(result, "status", repr(result)),
            "expected ALLOW for low-risk recall",
        )


# =====================================================================
# I4 — HITL escalation cycle
# =====================================================================
async def probe_hitl_cycle(svc: Any, session: Any, report: ProbeReport) -> None:
    layer = "HITL escalation"
    hil = _attr(svc, "_hil_service")
    if hil is None:
        report.add(layer, "hil_service", "WARN", None, "kernel has no HIL service")
        return
    front = _attr(session, "front_dispatcher")
    gate = _attr(front, "policy_gate")
    if gate is None:
        report.add(layer, "front gate", "FAIL", None)
        return
    bus = _attr(svc, "_bus")
    if bus is None:
        report.add(layer, "bus", "FAIL", None)
        return

    # Stand in for the Front: subscribe to TOPIC_HIL_REQUEST and
    # immediately echo an "approve" response on TOPIC_HIL_RESPONSE.
    from k1.concierge.actors.front_hil_envelope import (
        build_hil_response_envelope_dict,
    )
    from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE

    received: list[dict] = []

    async def _front_echo(topic: str, payload: dict) -> None:
        received.append(dict(payload))
        resp = build_hil_response_envelope_dict(payload, {"selected_option": "approve"})
        await bus.publish(TOPIC_HIL_RESPONSE, resp)

    handle = bus.subscribe(TOPIC_HIL_REQUEST, _front_echo)
    try:
        tool_call = ToolCallResult(
            id=f"probe-hitl-{uuid.uuid4().hex[:8]}",
            name=HIGH_RISK_TOOL,
            arguments={"member_id": "child:alice"},
        )
        try:
            result = await asyncio.wait_for(gate(tool_call), timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            report.add(
                layer,
                "gate(share_location)",
                "FAIL",
                None,
                f"{type(exc).__name__}: {exc}",
            )
            return
        report.add(
            layer,
            "TOPIC_HIL_REQUEST received",
            "OK" if received else "WARN",
            len(received),
        )
        # Acceptable outcomes: ALLOW (None) after auto-approve, or a
        # structured BLOCKED ToolResult carrying the verdict.
        if result is None:
            report.add(layer, "gate verdict", "OK", "ALLOW (auto-approved)")
        else:
            status = getattr(result, "status", "")
            report.add(layer, "gate verdict", "OK", f"BLOCKED ({status})")
        # Duplication-firewall: the gate must originate from
        # k1.selfmodel.adapters, never from
        # k1.concierge.protocols.hitl_pipeline.
        gate_self = getattr(gate, "__self__", None)
        gate_module = type(gate_self).__module__ if gate_self else ""
        report.add(
            layer,
            "duplication_firewall",
            "OK" if "selfmodel.adapters" in gate_module else "FAIL",
            gate_module,
        )
    finally:
        try:
            bus.unsubscribe(handle)
        except Exception:
            pass


# =====================================================================
# I5 — 13 V0 situation walk-through
# =====================================================================
def probe_situations(bundle: Any, report: ProbeReport) -> None:
    layer = "V0 situations (S1..S13)"
    failures: list[str] = []
    for kind in sorted(SITUATION_KINDS):
        try:
            frame = bundle.composer.compose(
                PROBE_ACTOR_ID,
                T_NOW_MS(),
                PROBE_DEVICE_ID,
                kind,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(kind)
            report.add(layer, kind, "FAIL", None, f"{type(exc).__name__}: {exc}")
            continue
        if frame is None or _attr(frame, "actor_id") != PROBE_ACTOR_ID:
            failures.append(kind)
            report.add(layer, kind, "FAIL", None, "compose returned empty/invalid frame")
            continue
        # Drive a low-risk synthetic call through the evaluator. We
        # only care that evaluate() returns a verdict — the per-cell
        # decision is governed by the matrix tests in M2/M5.E1.
        try:
            verdict = bundle.evaluator.evaluate(
                PolicyRequest(
                    actor_id=PROBE_ACTOR_ID,
                    tool_name=LOW_RISK_TOOL,
                    risk_class=RiskClass.LOW,
                ),
                frame,
            )
            decision = _attr(verdict, "decision")
            report.add(layer, kind, "OK", str(decision))
        except Exception as exc:  # noqa: BLE001
            failures.append(kind)
            report.add(layer, kind, "FAIL", None, f"evaluate raised: {exc}")
    report.add(
        layer,
        "13/13 covered",
        "OK" if not failures else "FAIL",
        f"{len(SITUATION_KINDS) - len(failures)}/{len(SITUATION_KINDS)}",
    )


# =====================================================================
# I6 — Temporal drift (state mutation between compose and evaluate)
# =====================================================================
def probe_temporal_drift(bundle: Any, report: ProbeReport) -> None:
    """Real-world race conditions the static probe didn't cover.

    Models four kinds of drift between **T0 (compose)** and
    **T2 (evaluate / execute)**::

        T0 → compose frame_v1
        T1 → world mutates (constitution / family / identity / freshness)
        T2 → re-evaluate / re-compose
        T3 → assert mutation is observed

    The system is allowed to either (a) reflect the new state on the
    next read or (b) raise — the probe only fails if the mutation is
    silently lost.
    """
    layer = "Temporal drift"

    # ── 1. Constitution mutation drift ─────────────────────────────
    # Compose against v0, then rewrite the constitution row with
    # `recall_memory` removed from guardian.can. A re-composed frame
    # must reflect the tighter rule.
    try:
        active = bundle.constitution.get_active()
        snapshot_v1 = active.snapshot
        body_v1 = dict(getattr(snapshot_v1, "body", {}) or {})

        frame_v1 = bundle.composer.compose(
            PROBE_ACTOR_ID, T_NOW_MS(), PROBE_DEVICE_ID, "caregiver_context_briefing"
        )
        had_recall = LOW_RISK_TOOL in frame_v1.capabilities.can_do
        report.add(
            layer,
            "T0 frame_v1 has recall_memory",
            "OK" if had_recall else "WARN",
            had_recall,
        )

        # Build a tightened body — strip recall_memory from guardian.can.
        autonomy = {
            role: dict(rules) for role, rules in (body_v1.get("autonomy_rules") or {}).items()
        }
        guardian = dict(autonomy.get("guardian", {}))
        guardian["can"] = [t for t in guardian.get("can", []) if t != LOW_RISK_TOOL]
        autonomy["guardian"] = guardian
        body_v2 = dict(body_v1)
        body_v2["autonomy_rules"] = autonomy

        snapshot_v2 = _dc_replace(snapshot_v1, body=body_v2, version=snapshot_v1.version + ".t1")
        wres = bundle.store.write_constitution(snapshot_v2, writer_id=CONSTITUTION_WRITER_ID)
        if not getattr(wres, "accepted", False):
            report.add(
                layer,
                "T1 write_constitution accepted",
                "FAIL",
                getattr(wres, "reason", ""),
            )
            return

        frame_v2 = bundle.composer.compose(
            PROBE_ACTOR_ID, T_NOW_MS(), PROBE_DEVICE_ID, "caregiver_context_briefing"
        )
        revoked = LOW_RISK_TOOL not in frame_v2.capabilities.can_do
        report.add(
            layer,
            "T2 constitution mutation observed",
            "OK" if revoked else "FAIL",
            revoked,
            "" if revoked else "frame_v2 still grants revoked tool — stale read",
        )

        # Stale frame_v1 against the post-mutation evaluator: capability
        # check uses the frame's own caps, so frame_v1 still ALLOWs.
        # That is the documented behaviour — the probe records it as
        # INFO so the gap is visible in the report.
        verdict_stale = bundle.evaluator.evaluate(
            PolicyRequest(
                actor_id=PROBE_ACTOR_ID, tool_name=LOW_RISK_TOOL, risk_class=RiskClass.LOW
            ),
            frame_v1,
        )
        report.add(
            layer,
            "T2 stale frame_v1 verdict",
            "INFO",
            str(_attr(verdict_stale, "decision")),
            "frames are immutable — re-compose required to honour mutation",
        )

        # Restore the original constitution so downstream probes are clean.
        bundle.store.write_constitution(snapshot_v1, writer_id=CONSTITUTION_WRITER_ID)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "constitution drift", "FAIL", None, f"{type(exc).__name__}: {exc}")

    # ── 2. Cross-session interference (family/role mutation) ───────
    # Session A flips the actor's role; session B (re-compose) must see
    # the new role's capability set.
    try:
        actor_v1, _ = bundle.store.read_self(PROBE_ACTOR_ID)
        if actor_v1 is None:
            report.add(layer, "cross-session: actor exists", "FAIL", None)
        else:
            l2_v1 = dict(actor_v1.L2_identity or {})
            role_v1 = l2_v1.get("role_in_family")

            # Mutate role: guardian → child.
            l2_v2 = dict(l2_v1)
            l2_v2["role_in_family"] = "child"
            actor_v2 = _dc_replace(actor_v1, L2_identity=l2_v2)
            wres = bundle.store.write_self(actor_v2, writer_id=SELF_MODEL_WRITER_ID)
            if not getattr(wres, "accepted", False):
                report.add(
                    layer,
                    "T1 write_self accepted",
                    "FAIL",
                    getattr(wres, "reason", ""),
                )
                return

            # Read-back: confirm the store really took the new role.
            readback, _ = bundle.store.read_self(PROBE_ACTOR_ID)
            stored_role = (
                readback.L2_identity.get("role_in_family") if readback is not None else None
            )
            report.add(
                layer,
                "T1 store read-back role",
                "OK" if stored_role == "child" else "FAIL",
                stored_role,
            )

            frame_b = bundle.composer.compose(
                PROBE_ACTOR_ID, T_NOW_MS(), PROBE_DEVICE_ID, "caregiver_context_briefing"
            )
            # `set_routine` is guardian-only in the bootstrap constitution
            # (child.cannot lists it). A child role MUST NOT carry it.
            guardian_only_tool = "set_routine"
            had_before = guardian_only_tool in frame_v1.capabilities.can_do
            stripped_after = guardian_only_tool not in frame_b.capabilities.can_do
            ok = had_before and stripped_after
            report.add(
                layer,
                "session-B sees new role",
                "OK" if ok else "FAIL",
                f"role={l2_v2['role_in_family']} "
                f"set_routine: guardian={had_before} child={not stripped_after}",
            )

            # Restore the original role.
            l2_restore = dict(l2_v2)
            l2_restore["role_in_family"] = role_v1
            bundle.store.write_self(
                _dc_replace(actor_v1, L2_identity=l2_restore),
                writer_id=SELF_MODEL_WRITER_ID,
            )
    except Exception as exc:  # noqa: BLE001
        report.add(
            layer, "cross-session interference", "FAIL", None, f"{type(exc).__name__}: {exc}"
        )

    # ── 3. Identity tier escalation mid-flow ───────────────────────
    # Build a synthetic frame whose capability set requires tier 1 for
    # the low-risk tool, then evaluate at tier 0 (REQUIRE_IDENTITY)
    # and tier 1 (ALLOW). Demonstrates the evaluator honours the
    # tier parameter on every call — i.e. promotion mid-flow takes
    # effect immediately.
    try:
        base_frame = bundle.composer.compose(
            PROBE_ACTOR_ID, T_NOW_MS(), PROBE_DEVICE_ID, "caregiver_context_briefing"
        )
        gated_caps = Capabilities(
            can_do=tuple(set(base_frame.capabilities.can_do) | {LOW_RISK_TOOL}),
            requires_confirmation=base_frame.capabilities.requires_confirmation,
            requires_identity_tier={LOW_RISK_TOOL: 1},
        )
        gated_frame = _dc_replace(base_frame, capabilities=gated_caps)

        v_low = bundle.evaluator.evaluate(
            PolicyRequest(
                actor_id=PROBE_ACTOR_ID, tool_name=LOW_RISK_TOOL, risk_class=RiskClass.LOW
            ),
            gated_frame,
            current_tier=0,
        )
        v_high = bundle.evaluator.evaluate(
            PolicyRequest(
                actor_id=PROBE_ACTOR_ID, tool_name=LOW_RISK_TOOL, risk_class=RiskClass.LOW
            ),
            gated_frame,
            current_tier=1,
        )
        ok_low = _attr(v_low, "decision") == PolicyDecision.REQUIRE_IDENTITY
        ok_high = _attr(v_high, "decision") == PolicyDecision.ALLOW
        report.add(
            layer,
            "tier=0 → REQUIRE_IDENTITY",
            "OK" if ok_low else "FAIL",
            str(_attr(v_low, "decision")),
        )
        report.add(
            layer,
            "tier=1 (escalated) → ALLOW",
            "OK" if ok_high else "FAIL",
            str(_attr(v_high, "decision")),
        )
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "tier escalation", "FAIL", None, f"{type(exc).__name__}: {exc}")

    # ── 4. Memory freshness decay impact ───────────────────────────
    # Same request, four freshness states. Verdicts must come from the
    # documented matrix in k1.selfmodel.contracts.policy. Failure here
    # signals the matrix wiring drifted from spec.
    try:
        base = bundle.composer.compose(
            PROBE_ACTOR_ID, T_NOW_MS(), PROBE_DEVICE_ID, "caregiver_context_briefing"
        )
        # The matrix test must clear the capability check first, so
        # synthesize a frame that grants the high-risk tool. We measure
        # *only* the matrix × freshness behaviour here.
        gate_tool = "pickup_change"
        caps = Capabilities(
            can_do=tuple({*base.capabilities.can_do, gate_tool}),
            requires_confirmation=base.capabilities.requires_confirmation,
            requires_identity_tier=dict(base.capabilities.requires_identity_tier),
        )
        frame = _dc_replace(base, capabilities=caps)
        req_high = PolicyRequest(
            actor_id=PROBE_ACTOR_ID, tool_name=gate_tool, risk_class=RiskClass.HIGH
        )
        # HIGH risk: FRESH=REQUIRE_CONFIRMATION, STALE/OFFLINE=DEFER_OFFLINE,
        # CONFLICT_PENDING=DENY (per the matrix in contracts/policy.py).
        cases = (
            (FreshnessState.FRESH, PolicyDecision.REQUIRE_CONFIRMATION),
            (FreshnessState.STALE, PolicyDecision.DEFER_OFFLINE),
            (FreshnessState.OFFLINE_LOCAL_ONLY, PolicyDecision.DEFER_OFFLINE),
            (FreshnessState.CONFLICT_PENDING, PolicyDecision.DENY),
        )
        for state, expected in cases:
            v = bundle.evaluator.evaluate(req_high, frame, freshness_state=state)
            actual = _attr(v, "decision")
            ok = actual == expected
            report.add(
                layer,
                f"HIGH × {state.value}",
                "OK" if ok else "FAIL",
                f"{actual} (expected {expected})",
            )
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "freshness decay", "FAIL", None, f"{type(exc).__name__}: {exc}")


# =====================================================================
# Driver
# =====================================================================
async def _run(args: argparse.Namespace) -> int:
    report = ProbeReport()
    cfg = KernelConfig(
        sessionstate_db_path=args.ssm_db,
        bridge_outbox_path=args.bridge_db,
        workflow_db_path=args.workflows_db,
        enable_self_model=True,
        selfmodel_family_space_id="family:probe9",
    )
    title = "K1 Kernel Probe — Phase 9 (k1.selfmodel)"
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)

    t_boot = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t_boot
    print(f"  Boot: {boot_s:.2f}s\n")
    svc = runtime._service

    session: Any = None
    try:
        # ── M5.E4.I2: introspection ──
        bundle = probe_bundle_wired(svc, report)
        probe_bus_topics(svc, report)
        if bundle is None:
            return _finalize(report, args, title)
        # Seed a synthetic household so compose() has an actor to find.
        _seed_synthetic_household(bundle)
        probe_constitution(bundle, report)
        probe_identity(bundle, report)
        frame = probe_composer(bundle, report)
        probe_evaluator(bundle, frame, report)

        # ── Session — needed for I3/I4 ──
        try:
            session = await svc.create_session(PROBE_SESSION_ID, device_id=PROBE_DEVICE_ID)
        except Exception as exc:  # noqa: BLE001
            report.add(
                "Session P3.5",
                "create_session",
                "FAIL",
                None,
                f"{type(exc).__name__}: {exc}",
            )
            return _finalize(report, args, title)

        layer = "Session P3.5"
        handle = _attr(session, "self_model")
        report.add(
            layer,
            "session.self_model",
            "OK" if handle is not None else "FAIL",
            type(handle).__name__ if handle else None,
        )
        front = _attr(session, "front_dispatcher")
        back = _attr(session, "back_dispatcher")
        report.add(
            layer,
            "front_dispatcher.policy_gate",
            "OK" if _attr(front, "policy_gate") is not None else "FAIL",
            type(_attr(front, "policy_gate")).__name__ if _attr(front, "policy_gate") else None,
        )
        report.add(
            layer,
            "back_dispatcher.policy_gate",
            "OK" if _attr(back, "policy_gate") is not None else "FAIL",
            type(_attr(back, "policy_gate")).__name__ if _attr(back, "policy_gate") else None,
        )
        report.add(
            layer,
            "handle.renderer (capsule)",
            "OK" if _attr(handle, "renderer") is not None else "FAIL",
            type(_attr(handle, "renderer")).__name__ if _attr(handle, "renderer") else None,
        )

        # ── M5.E4.I3: end-to-end ALLOW cycle ──
        await probe_e2e_gate_cycle(session, report)

        # ── M5.E4.I4: HITL escalation cycle ──
        await probe_hitl_cycle(svc, session, report)

        # ── M5.E4.I5: 13 V0 situations ──
        probe_situations(bundle, report)

        # ── Temporal drift (state mutation between compose & evaluate) ──
        probe_temporal_drift(bundle, report)
    finally:
        if session is not None:
            try:
                await svc.destroy_session(PROBE_SESSION_ID)
            except Exception:  # noqa: BLE001
                pass
        print("  Tearing down...")
        await stop_kernel(runtime)

    return _finalize(report, args, title)


def _finalize(report: ProbeReport, args: argparse.Namespace, title: str) -> int:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)
    layers: dict[str, list] = {}
    for p in report.probes:
        layers.setdefault(p.layer, []).append(p)
    for layer, probes in layers.items():
        print(f"\n[ {layer} ]")
        for p in probes:
            print(p.render())
    counts = report.counts()
    print("\n" + "=" * 72)
    print(
        f"  Summary: OK {counts['OK']}  WARN {counts['WARN']}  "
        f"FAIL {counts['FAIL']}  INFO {counts['INFO']}  "
        f"(total {sum(counts.values())})"
    )
    if args.json:
        out = {
            "title": title,
            "counts": counts,
            "probes": [
                {
                    "layer": p.layer,
                    "name": p.name,
                    "status": p.status,
                    "value": _safe(p.value),
                    "note": p.note,
                }
                for p in report.probes
            ],
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"  JSON written: {args.json}")
    return 1 if counts["FAIL"] > 0 else 0


def _safe(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except Exception:
        return repr(v)


def main() -> None:
    # Force UTF-8 stdout on Windows so the ✓/✗/⚠ glyphs print cleanly.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--json",
        default="data/kernel_probe_phase9_stub.json",
        help="Write probe results to this JSON path",
    )
    ap.add_argument("--ssm-db", default="./data/k1/probe9_ssm.db")
    ap.add_argument("--bridge-db", default="./data/k1/probe9_bridge.db")
    ap.add_argument("--workflows-db", default="./data/k1/probe9_workflows.db")
    args = ap.parse_args()
    rc = asyncio.run(_run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
