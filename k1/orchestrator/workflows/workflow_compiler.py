"""
k1.orchestrator.workflows.workflow_compiler -- WorkflowCompiler (4.1.3).

Compiles a frozen WorkflowSpec into a live CommittedPlan at execution
time. DynamicExpr values are resolved to current clock/state, capabilities
are validated against the registry, and contract gaps are classified per
SPEC-9.

Design:
  - compile() is called at EXECUTION time (not at save time) to ensure
    DynamicExpr resolves to current values.
  - Idempotent: calling compile() twice with the same clock time
    produces the same result.
  - Never mutates the frozen WorkflowSpec -- creates new PlanStep
    instances with resolved params.
  - Gap detection: CAPABILITY_REMOVED and PERMISSION_CHANGE in V1.
    Schema-level gap detection (field added/removed/renamed) deferred
    to V2 when RegistryEntry gains schema fields.

Constructor deps (5):
  fabric      -- IFabricGatewayPort (query_registry)
  delta       -- IDeltaEmitPort (HIL notification on LARGE gaps)
  storage     -- IWorkflowStoragePort (save_gap)
  state_port  -- IStateReadPort (user.timezone, user.locale)
  clock       -- SystemClock (date.today, date.now)

Anti-hallucination rules:
  - compile() is called at EXECUTION time, NOT save time.
  - Uses deep copy of steps -- never mutates the frozen WorkflowSpec.
  - DynamicExpr resolution is idempotent.
  - state_port is used ONLY for user.timezone / user.locale resolution.
  - Uses ``zoneinfo`` (stdlib Python 3.9+), NOT ``pytz``.

References:
  - orchestrator-implementation-plan.md Issue 4.1.3
  - SPEC-9 (gap classification)

Exports:
  WorkflowCompiler
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Any, Dict, List, Tuple

from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.state_read_port import IStateReadPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import (
    CommittedPlan,
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    RegistryEntry,
)
from k1.orchestrator.workflows.system_clock import SystemClock
from k1.orchestrator.workflows.workflow_types import CompilationResult, DynamicExpr, WorkflowSpec

# ---------------------------------------------------------------------------
# Offset regex for DynamicExpr duration arithmetic
# ---------------------------------------------------------------------------
_OFFSET_RE = re.compile(r"^([+-])(\d+)([dhms])$")
_OFFSET_SECONDS: Dict[str, int] = {"d": 86400, "h": 3600, "m": 60, "s": 1}


class WorkflowCompiler:
    """Compile a frozen WorkflowSpec into a live CommittedPlan.

    Six-step ``compile()`` logic:

      1. Deep-copy ``spec.steps`` (frozen -> new PlanStep instances).
      2. Resolve DynamicExpr in step params (date, user namespaces).
      3. Validate capabilities via Fabric registry.
      4. Detect contract gaps (SPEC-9 classification).
      5. Build ``CommittedPlan`` from resolved steps + deps.
      6. Compute SHA-256 ``compiled_hash`` for RunManifest dedup.

    Consumers:
      - WorkflowRunSupervisor.start_run() (4.2.3)
      - ProactiveGapDetector (4.2.7) -- dry-run validation
    """

    def __init__(
        self,
        fabric: IFabricGatewayPort,
        delta: IDeltaEmitPort,
        storage: IWorkflowStoragePort,
        state_port: IStateReadPort,
        clock: SystemClock,
    ) -> None:
        self._fabric = fabric
        self._delta = delta
        self._storage = storage
        self._state_port = state_port
        self._clock = clock

    # ===================================================================
    # Public API
    # ===================================================================

    async def compile(
        self,
        spec: WorkflowSpec,
        session_id: str = "",
    ) -> CompilationResult:
        """Compile a WorkflowSpec into a CommittedPlan.

        Args:
            spec: Frozen workflow specification to compile.
            session_id: Optional session for user pref resolution.
                If empty, defaults are used (UTC / en-US).

        Returns:
            CompilationResult with success=True and a CommittedPlan
            if all gaps are SMALL/auto-resolved, or success=False
            with gap details if any LARGE gap is detected.
        """
        # -- Step 1 + 2: deep-copy steps + resolve DynamicExpr -----------
        resolved_steps = await self._resolve_steps(spec.steps, session_id)

        # -- Step 3 + 4: validate capabilities + gap detection -----------
        gaps: List[ProactiveGap] = []
        auto_resolved: List[str] = []

        for step in resolved_steps:
            entry = await self._fabric.query_registry(step.capability)
            if entry is None:
                # LARGE gap: capability removed entirely
                gaps.append(
                    ProactiveGap(
                        workflow_id=spec.workflow_id,
                        gap_type="CAPABILITY_REMOVED",
                        affected_step_id=step.id,
                        capability_name=step.capability,
                        old_contract_version=spec.version,
                        new_contract_version="N/A",
                        description=(
                            f"Capability '{step.capability}' is no longer "
                            f"available in the Fabric registry"
                        ),
                        justification=("Workflow cannot execute without this capability"),
                        status=ProactiveGapStatus.PENDING,
                    )
                )
            else:
                step_gaps, step_auto = self._detect_gaps(spec, step, entry)
                gaps.extend(step_gaps)
                auto_resolved.extend(step_auto)

        # -- Check for LARGE gaps (any PENDING -> fail) ------------------
        has_large = any(g.status == ProactiveGapStatus.PENDING for g in gaps)

        if has_large:
            # Persist PENDING gaps
            for gap in gaps:
                if gap.status == ProactiveGapStatus.PENDING:
                    await self._storage.save_gap(gap)
            # Emit HIL notification
            await self._delta.emit(
                "k1.orchestration.gap.detected",
                {
                    "workflow_id": spec.workflow_id,
                    "workflow_name": spec.name,
                    "gap_count": sum(1 for g in gaps if g.status == ProactiveGapStatus.PENDING),
                    "gap_types": list(
                        {g.gap_type for g in gaps if g.status == ProactiveGapStatus.PENDING}
                    ),
                },
                trace_id=spec.workflow_id,
            )
            return CompilationResult(
                success=False,
                compiled_plan=None,
                gaps=gaps,
                auto_resolved=auto_resolved,
                compiled_hash=None,
            )

        # -- Step 5: build CommittedPlan ---------------------------------
        plan = CommittedPlan(
            plan_id=f"compiled-{spec.workflow_id}-{spec.version}",
            request_id=spec.workflow_id,
            intent=f"Workflow: {spec.name}",
            steps=resolved_steps,
            trace_id=str(uuid.uuid4()),
            dependencies=dict(spec.dependencies),
            created_at=self._clock.utc_now(),
        )

        # -- Step 6: compute compiled_hash (SHA-256) ---------------------
        compiled_hash = self._compute_hash(plan)

        return CompilationResult(
            success=True,
            compiled_plan=plan,
            gaps=gaps,
            auto_resolved=auto_resolved,
            compiled_hash=compiled_hash,
        )

    # ===================================================================
    # Step 1 + 2: Deep-copy + DynamicExpr resolution
    # ===================================================================

    async def _resolve_steps(
        self,
        steps: List[PlanStep],
        session_id: str,
    ) -> List[PlanStep]:
        """Create new PlanStep instances with resolved DynamicExpr params."""
        user_prefs = await self._load_user_prefs(session_id)
        resolved: List[PlanStep] = []
        for step in steps:
            new_params = self._resolve_params(dict(step.params), user_prefs)
            resolved.append(replace(step, params=new_params))
        return resolved

    def _resolve_params(
        self,
        params: Dict[str, Any],
        user_prefs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Walk params dict and resolve any DynamicExpr values."""
        resolved: Dict[str, Any] = {}
        for key, value in params.items():
            expr = DynamicExpr.parse(value) if isinstance(value, str) else None
            if expr is not None:
                resolved[key] = self._resolve_expr(expr, user_prefs)
            else:
                resolved[key] = value
        return resolved

    def _resolve_expr(
        self,
        expr: DynamicExpr,
        user_prefs: Dict[str, Any],
    ) -> Any:
        """Resolve a single DynamicExpr to a concrete value.

        V1 namespaces:
          date.today  -> clock.utc_today()  ('YYYY-MM-DD')
          date.now    -> clock.utc_now()    (float timestamp)
          user.timezone -> user_prefs['timezone'] or 'UTC'
          user.locale   -> user_prefs['locale'] or 'en-US'
        """
        base: Any

        if expr.namespace == "date":
            if expr.field == "today":
                base = self._clock.utc_today()
            elif expr.field == "now":
                base = self._clock.utc_now()
            else:
                base = expr.raw  # unknown field -> pass through
        elif expr.namespace == "user":
            if expr.field == "timezone":
                base = user_prefs.get("timezone", "UTC")
            elif expr.field == "locale":
                base = user_prefs.get("locale", "en-US")
            else:
                base = expr.raw  # unknown field -> pass through
        else:
            base = expr.raw  # unknown namespace -> pass through

        if expr.offset:
            base = self._apply_offset(base, expr.offset)

        return base

    @staticmethod
    def _apply_offset(base_value: Any, offset: str) -> Any:
        """Apply time offset (+2d, -1h, +30m, -120s) to a resolved value.

        Float values: direct arithmetic (seconds).
        Date strings ('YYYY-MM-DD'): parse, add timedelta, format back.
        """
        m = _OFFSET_RE.fullmatch(offset)
        if m is None:
            return base_value

        sign = 1 if m.group(1) == "+" else -1
        amount = int(m.group(2))
        unit = m.group(3)
        total_seconds = sign * amount * _OFFSET_SECONDS[unit]

        if isinstance(base_value, (int, float)):
            return base_value + total_seconds

        if isinstance(base_value, str):
            try:
                dt = datetime.strptime(base_value, "%Y-%m-%d")
                dt = dt.replace(tzinfo=tz.utc)
                dt += timedelta(seconds=total_seconds)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return base_value

        return base_value

    async def _load_user_prefs(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """Load user preferences from SessionState for DynamicExpr resolution.

        Returns defaults (UTC / en-US) if no session or read fails.
        """
        _defaults: Dict[str, Any] = {"timezone": "UTC", "locale": "en-US"}
        if not session_id:
            return _defaults
        try:
            section = await self._state_port.read_section(session_id, "persona")
            if section is not None:
                return section
        except Exception:  # noqa: BLE001 -- graceful fallback
            pass
        return _defaults

    # ===================================================================
    # Step 3 + 4: Capability validation + gap detection
    # ===================================================================

    @staticmethod
    def _detect_gaps(
        spec: WorkflowSpec,
        step: PlanStep,
        entry: RegistryEntry,
    ) -> Tuple[List[ProactiveGap], List[str]]:
        """Detect gaps between step expectations and current registry entry.

        SPEC-9 classification:
          SMALL = auto-resolved (notification only).
          LARGE = pending (pause workflow + HIL).

        V1 scope: safety_band_min change detection. Schema-level gap
        detection deferred to V2 when RegistryEntry gains schema fields.
        """
        gaps: List[ProactiveGap] = []
        auto_resolved: List[str] = []

        # LARGE: safety_band_min changed
        if step.safety_band_min is not None and step.safety_band_min != entry.safety_band_min:
            gaps.append(
                ProactiveGap(
                    workflow_id=spec.workflow_id,
                    gap_type="PERMISSION_CHANGE",
                    affected_step_id=step.id,
                    capability_name=step.capability,
                    old_contract_version=step.safety_band_min,
                    new_contract_version=entry.safety_band_min,
                    description=(
                        f"Safety band changed for '{step.capability}': "
                        f"expected '{step.safety_band_min}', "
                        f"now '{entry.safety_band_min}'"
                    ),
                    justification="Safety band changes require human review",
                    status=ProactiveGapStatus.PENDING,
                )
            )

        return gaps, auto_resolved

    # ===================================================================
    # Step 6: SHA-256 compiled hash
    # ===================================================================

    @staticmethod
    def _compute_hash(plan: CommittedPlan) -> str:
        """SHA-256 of serialized plan for RunManifest dedup."""
        data = json.dumps(
            {
                "plan_id": plan.plan_id,
                "steps": [s.to_dict() for s in plan.steps],
                "dependencies": plan.dependencies,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
