"""VerificationPlanRunner — Epic 4.2.

Post-write verification.  After a write executes, the runner builds a plan
from the connector's constitution and runs it against the native provider.
A ``submit_result(completed)`` is only legal once verification passes.

Inputs the runner reads from its binding and observation are expressed as
``typing.Protocol`` ports (``BindingLike``, ``ObservationLike``).  The Epic 6.1
``CapabilityBinding`` and the Bridge ``InvocationObservation`` structurally
satisfy these ports — neither is part of Phase 1 Fabric, so the runner depends
on the documented field subset rather than the concrete classes.

The readback path is a ``NativeReadbackPort`` so the runner is not coupled to
a specific provider implementation (the kernel wires the real provider in
Epic 7.3; tests supply a fake).

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 4.2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import ConstitutionArtifact
from k1.fabric.stores.global_projection_store import GlobalProjectionStore

VERIFIED_STATUSES: frozenset[str] = frozenset({"verified", "degraded_verified"})


# ── Errors ─────────────────────────────────────────────────────────────


class ReadbackUnavailableError(RuntimeError):
    """Raised by a ``NativeReadbackPort`` when the readback capability or its
    provider is not available.  The runner maps this to ``status='unavailable'``.
    """


# ── Structural ports (satisfied by Epic 6.1 / Bridge types) ────────────


@runtime_checkable
class BindingLike(Protocol):
    """The subset of ``CapabilityBinding`` (Epic 6.1) the runner reads."""

    binding_id: str
    capability_name: str
    connector_id: str
    resource_id: str
    verifier_ref: str | None


@runtime_checkable
class ObservationLike(Protocol):
    """The subset of ``InvocationObservation`` (Bridge Contract H) the runner reads."""

    invocation_id: str
    structured_result: dict[str, Any]


@dataclass(frozen=True)
class ReadbackContext:
    """Minimal read context passed to the native readback port."""

    actor_id: str = "verifier"
    role: str = "system"
    safety_band: str = "GREEN"


@runtime_checkable
class NativeReadbackResult(Protocol):
    """Result shape from a readback dispatch — exposes ``data``."""

    @property
    def data(self) -> dict[str, Any]: ...


@runtime_checkable
class NativeReadbackPort(Protocol):
    """Port the runner uses to read a resource back after a write.

    Implementations dispatch the readback capability against the real
    resource store and return a result whose ``data`` reflects the
    persisted resource.  They raise ``ReadbackUnavailableError`` when the
    capability or provider is not found.
    """

    def dispatch(
        self,
        capability_name: str,
        params: dict[str, Any],
        context: ReadbackContext,
    ) -> NativeReadbackResult: ...


# ── Plan + observation dataclasses ─────────────────────────────────────


@dataclass(frozen=True)
class VerificationPlan:
    verification_plan_id: str
    resolution_id: str
    binding_id: str
    invocation_id: str
    verifier_ref: str | None
    verifier_method: (
        str  # 'read_after_write' | 'output_schema' | 'state_compare' | 'none_available'
    )
    expected_effect: str
    expected_resource_state: dict[str, Any]
    readback_capability_ref: str | None
    readback_params: dict[str, Any] | None
    degraded_completion_policy: str | None
    required_for_submit_status: str
    max_staleness_ms: int = 300_000


@dataclass(frozen=True)
class VerificationObservation:
    verification_id: str
    verification_plan_id: str
    status: str  # verified | degraded_verified | failed | inconclusive | skipped_by_policy | unavailable
    observed_effect: str | None
    observed_resource_state_ref: str | None
    mismatch_summary: str | None
    degraded_reason: str | None
    recovery_directive: dict[str, Any] | None
    proof_refs: list[str] = field(default_factory=list)


# ── Runner ─────────────────────────────────────────────────────────────


class VerificationPlanRunner:
    """Builds and runs post-write verification plans."""

    def __init__(
        self,
        native_provider: NativeReadbackPort,
        global_store: GlobalProjectionStore,
        constitution_loader: ConstitutionLoader,
    ) -> None:
        self.native_provider = native_provider
        self.global_store = global_store
        self.constitution_loader = constitution_loader

    # ── build_plan ─────────────────────────────────────────────────

    def build_plan(
        self,
        binding: BindingLike,
        observation: ObservationLike,
        constitution: ConstitutionArtifact | None,
        *,
        degraded_completion_policy: str | None = None,
        max_staleness_ms: int = 300_000,
    ) -> VerificationPlan:
        """Build a verification plan from the connector's constitution.

        Receives the typed ``ConstitutionArtifact`` (Epic 5), never a raw
        record.  The verifier method is chosen from
        ``constitution.verification_requirements`` (read_after_write preferred,
        then output_schema; otherwise none_available).
        """
        method = self._select_method(constitution)
        structured = observation.structured_result or {}

        if method == "read_after_write":
            readback_ref = binding.verifier_ref or self._find_readback_capability(
                binding.connector_id
            )
            if readback_ref is None:
                method = "none_available"
            else:
                id_fields = _identifying_fields(structured)
                readback_params = {"resource_id": binding.resource_id, **id_fields}
                return VerificationPlan(
                    verification_plan_id="vp-" + uuid.uuid4().hex[:12],
                    resolution_id=str(structured.get("resolution_id", "")),
                    binding_id=binding.binding_id,
                    invocation_id=observation.invocation_id,
                    verifier_ref=binding.verifier_ref,
                    verifier_method="read_after_write",
                    expected_effect="write",
                    expected_resource_state=dict(structured),
                    readback_capability_ref=readback_ref,
                    readback_params=readback_params,
                    degraded_completion_policy=degraded_completion_policy,
                    required_for_submit_status="completed",
                    max_staleness_ms=max_staleness_ms,
                )

        if method == "output_schema":
            required_fields = self._required_output_fields(binding.capability_name)
            return VerificationPlan(
                verification_plan_id="vp-" + uuid.uuid4().hex[:12],
                resolution_id=str(structured.get("resolution_id", "")),
                binding_id=binding.binding_id,
                invocation_id=observation.invocation_id,
                verifier_ref=binding.verifier_ref,
                verifier_method="output_schema",
                expected_effect="write",
                expected_resource_state={"required_output_fields": required_fields},
                readback_capability_ref=None,
                readback_params=None,
                degraded_completion_policy=degraded_completion_policy,
                required_for_submit_status="completed",
                max_staleness_ms=max_staleness_ms,
            )

        # none_available
        return VerificationPlan(
            verification_plan_id="vp-" + uuid.uuid4().hex[:12],
            resolution_id=str(structured.get("resolution_id", "")),
            binding_id=binding.binding_id,
            invocation_id=observation.invocation_id,
            verifier_ref=binding.verifier_ref,
            verifier_method="none_available",
            expected_effect="write",
            expected_resource_state={},
            readback_capability_ref=None,
            readback_params=None,
            degraded_completion_policy=degraded_completion_policy,
            required_for_submit_status="completed",
            max_staleness_ms=max_staleness_ms,
        )

    # ── run ────────────────────────────────────────────────────────

    def run(
        self,
        plan: VerificationPlan,
        observation: ObservationLike | None = None,
        *,
        now: datetime | None = None,
    ) -> VerificationObservation:
        """Execute a verification plan and produce a ``VerificationObservation``."""
        if plan.verifier_method == "read_after_write":
            return self._run_read_after_write(plan)
        if plan.verifier_method == "output_schema":
            return self._run_output_schema(plan, observation)
        return self._run_none_available(plan)

    # ── read_after_write ──────────────────────────────────────────

    def _run_read_after_write(self, plan: VerificationPlan) -> VerificationObservation:
        params = plan.readback_params or {}
        target_id = _primary_id(params, plan.expected_resource_state)
        if not target_id:
            return self._failed(plan, "no target id available for readback")

        try:
            result = self.native_provider.dispatch(
                str(plan.readback_capability_ref or ""),
                dict(params),
                ReadbackContext(),
            )
        except ReadbackUnavailableError as exc:
            return VerificationObservation(
                verification_id="ver-" + uuid.uuid4().hex[:12],
                verification_plan_id=plan.verification_plan_id,
                status="unavailable",
                observed_effect=None,
                observed_resource_state_ref=None,
                mismatch_summary=None,
                degraded_reason=f"readback capability not available: {exc}",
                recovery_directive={"action": "block_and_submit"},
                proof_refs=[],
            )

        data = result.data or {}
        if not _readback_found(data):
            return self._failed(plan, f"readback found no resource for id {target_id}")

        mismatch = _first_field_mismatch(plan.expected_resource_state, data)
        if mismatch is not None:
            field_name, expected_val, observed_val = mismatch
            return VerificationObservation(
                verification_id="ver-" + uuid.uuid4().hex[:12],
                verification_plan_id=plan.verification_plan_id,
                status="failed",
                observed_effect="write",
                observed_resource_state_ref=f"{plan.binding_id}:{target_id}",
                mismatch_summary=(
                    f"expected {field_name}='{expected_val}' but read '{observed_val}'"
                ),
                degraded_reason=None,
                recovery_directive={"action": "block_and_submit"},
                proof_refs=[f"resource:{target_id}"],
            )

        if plan.max_staleness_ms <= 0:
            return VerificationObservation(
                verification_id="ver-" + uuid.uuid4().hex[:12],
                verification_plan_id=plan.verification_plan_id,
                status="inconclusive",
                observed_effect="write",
                observed_resource_state_ref=f"{plan.binding_id}:{target_id}",
                mismatch_summary="readback exceeded max staleness window",
                degraded_reason=None,
                recovery_directive={"action": "block_and_submit"},
                proof_refs=[f"resource:{target_id}"],
            )

        return VerificationObservation(
            verification_id="ver-" + uuid.uuid4().hex[:12],
            verification_plan_id=plan.verification_plan_id,
            status="verified",
            observed_effect="write",
            observed_resource_state_ref=f"{plan.binding_id}:{target_id}",
            mismatch_summary=None,
            degraded_reason=None,
            recovery_directive=None,
            proof_refs=[f"resource:{target_id}"],
        )

    # ── output_schema ─────────────────────────────────────────────

    def _run_output_schema(
        self,
        plan: VerificationPlan,
        observation: ObservationLike | None,
    ) -> VerificationObservation:
        structured = observation.structured_result if observation is not None else {}
        structured = structured or {}
        required = list(plan.expected_resource_state.get("required_output_fields") or [])
        missing = [f for f in required if not structured.get(f)]
        if missing:
            return self._failed(plan, "output schema missing fields: " + ", ".join(missing))
        return VerificationObservation(
            verification_id="ver-" + uuid.uuid4().hex[:12],
            verification_plan_id=plan.verification_plan_id,
            status="verified",
            observed_effect="write",
            observed_resource_state_ref=None,
            mismatch_summary=None,
            degraded_reason=None,
            recovery_directive=None,
            proof_refs=[],
        )

    # ── none_available ────────────────────────────────────────────

    def _run_none_available(self, plan: VerificationPlan) -> VerificationObservation:
        if plan.degraded_completion_policy is not None:
            return VerificationObservation(
                verification_id="ver-" + uuid.uuid4().hex[:12],
                verification_plan_id=plan.verification_plan_id,
                status="degraded_verified",
                observed_effect="write",
                observed_resource_state_ref=None,
                mismatch_summary=None,
                degraded_reason=(f"degraded completion policy: {plan.degraded_completion_policy}"),
                recovery_directive=None,
                proof_refs=[],
            )
        # No verification requirement at all → skipped by policy.
        return VerificationObservation(
            verification_id="ver-" + uuid.uuid4().hex[:12],
            verification_plan_id=plan.verification_plan_id,
            status="skipped_by_policy",
            observed_effect=None,
            observed_resource_state_ref=None,
            mismatch_summary=None,
            degraded_reason=None,
            recovery_directive=None,
            proof_refs=[],
        )

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _select_method(constitution: ConstitutionArtifact | None) -> str:
        if constitution is None or not constitution.verification_requirements:
            return "none_available"
        methods = {vr.method for vr in constitution.verification_requirements}
        if "read_after_write" in methods:
            return "read_after_write"
        if "output_schema" in methods:
            return "output_schema"
        if "state_compare" in methods:
            # state_compare is deferred — treat as none_available for now.
            return "none_available"
        return "none_available"

    def _find_readback_capability(self, connector_id: str) -> str | None:
        """Find a read capability on the connector for read-after-write.

        Prefers ``get``/``read`` actions, then any ``list``/``search`` read.
        """
        caps = self.global_store.get_capabilities_by_connector(connector_id)
        reads = [c for c in caps if c.invocation_mode == "read"]
        if not reads:
            return None
        for preferred in ("get", "read"):
            for c in reads:
                if c.action_name == preferred:
                    return c.capability_name
        return reads[0].capability_name

    def _required_output_fields(self, capability_name: str) -> list[str]:
        """Derive required output fields from the capability's output schema."""
        record = self.global_store.get_capability(capability_name)
        if record is None:
            return []
        contract = record.contract_json or {}
        output_schema = contract.get("output_schema")
        if isinstance(output_schema, dict):
            required = output_schema.get("required")
            if isinstance(required, list):
                return [str(f) for f in required]
        return []

    def _failed(self, plan: VerificationPlan, summary: str) -> VerificationObservation:
        return VerificationObservation(
            verification_id="ver-" + uuid.uuid4().hex[:12],
            verification_plan_id=plan.verification_plan_id,
            status="failed",
            observed_effect=None,
            observed_resource_state_ref=None,
            mismatch_summary=summary,
            degraded_reason=None,
            recovery_directive={"action": "block_and_submit"},
            proof_refs=[],
        )


# ── Module helpers ─────────────────────────────────────────────────────

_ID_KEYS = ("event_id", "task_id", "reminder_id", "id", "resource_id", "record_id")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifying_fields(structured: dict[str, Any]) -> dict[str, Any]:
    """Extract id-like fields from a write's structured result for readback."""
    out: dict[str, Any] = {}
    for key in _ID_KEYS:
        if structured.get(key) is not None:
            out[key] = structured[key]
    return out


def _primary_id(params: dict[str, Any], expected: dict[str, Any]) -> str:
    for key in _ID_KEYS:
        if params.get(key):
            return str(params[key])
    for key in _ID_KEYS:
        if expected.get(key):
            return str(expected[key])
    return ""


def _readback_found(data: dict[str, Any]) -> bool:
    if not data:
        return False
    if data.get("found") is False:
        return False
    return True


# Fields that are not part of the persisted resource content and must not
# be compared during read-after-write.
_NON_CONTENT_KEYS = frozenset(
    {"found", "status", "resolution_id", "idempotency_key", "verifier_event_id"}
)


def _first_field_mismatch(
    expected: dict[str, Any],
    observed: dict[str, Any],
) -> tuple[str, Any, Any] | None:
    """Return the first (field, expected, observed) mismatch, or None.

    Only compares content fields that are present in BOTH the expected state
    and the readback, ignoring non-content bookkeeping keys.
    """
    for key, exp_val in expected.items():
        if key in _NON_CONTENT_KEYS or key in _ID_KEYS:
            continue
        if exp_val is None:
            continue
        if key not in observed:
            continue
        if observed.get(key) != exp_val:
            return (key, exp_val, observed.get(key))
    return None
