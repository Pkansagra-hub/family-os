"""ConstitutionArtifact — Epic 5.1.

The validated, typed shape every connector constitution must conform to
before entering the system.  This is the single source of truth that
``ConstitutionDefinition`` (Epic 2), ``ConstitutionRecord`` (Epic 1), and all
consumers reference.

Two-phase validation:
  1. ``validate_constitution(data)`` — structural (JSON Schema Draft-07).
  2. ``validate_constitution_semantics(artifact, known_resource_kinds)`` —
     references must resolve.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 5.1.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import jsonschema

# ── Known vocabularies (semantic validation) ───────────────────────────
KNOWN_VERIFIER_METHODS: frozenset[str] = frozenset(
    {"read_after_write", "output_schema", "state_compare"}
)
KNOWN_HIL_TRIGGERS: frozenset[str] = frozenset(
    {
        "missing_required_field",
        "time_conflict_detected",
        "ambiguous_person",
        "duplicate_detected",
        "conflict_detected",
    }
)


# ── Errors ─────────────────────────────────────────────────────────────


class ConstitutionValidationError(ValueError):
    """Raised when a constitution fails structural validation."""

    def __init__(self, message: str, *, field_path: str | None = None) -> None:
        self.field_path = field_path
        super().__init__(message)


# ── Typed sub-dataclasses ──────────────────────────────────────────────


@dataclass(frozen=True)
class PrerequisiteRead:
    operation: str
    resource_kind: str
    reason: str
    required: bool = True
    timeout_ms: int = 5000

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PrerequisiteRead:
        return cls(
            operation=str(d["operation"]),
            resource_kind=str(d["resource_kind"]),
            reason=str(d["reason"]),
            required=bool(d.get("required", True)),
            timeout_ms=int(d.get("timeout_ms", 5000)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConflictRule:
    check: str
    with_resource_kinds: list[str] = field(default_factory=list)
    description: str = ""
    resolution: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConflictRule:
        return cls(
            check=str(d["check"]),
            with_resource_kinds=list(d.get("with_resource_kinds", [])),
            description=str(d.get("description", "")),
            resolution=str(d.get("resolution", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompanionResourceRole:
    resource_kind: str
    role: str
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CompanionResourceRole:
        return cls(
            resource_kind=str(d["resource_kind"]),
            role=str(d["role"]),
            description=str(d.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HILGate:
    # NOTE: required fields (trigger, prompt) precede optional ones so the
    # dataclass is constructible.  ``options`` is declared before the
    # attribute literally named ``field`` so the ``field(default_factory=...)``
    # call is not shadowed by the ``field`` attribute name.
    trigger: str
    prompt: str
    options: list[str] = field(default_factory=list)
    field: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HILGate:
        return cls(
            trigger=str(d["trigger"]),
            prompt=str(d["prompt"]),
            field=(str(d["field"]) if d.get("field") is not None else None),
            options=list(d.get("options", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationStep:
    order: int
    phase: str  # which execution_phase: 'read' | 'mutate'
    operation: str  # which capability action_name: 'list' | 'create' | ...
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MutationStep:
        return cls(
            order=int(d["order"]),
            phase=str(d["phase"]),
            operation=str(d["operation"]),
            description=str(d.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationRequirement:
    method: str  # 'read_after_write' | 'output_schema' | 'state_compare'
    description: str = ""
    required_for_submit: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VerificationRequirement:
        return cls(
            method=str(d["method"]),
            description=str(d.get("description", "")),
            required_for_submit=bool(d.get("required_for_submit", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── ConstitutionArtifact ───────────────────────────────────────────────


@dataclass(frozen=True)
class ConstitutionArtifact:
    """The validated, canonical shape every constitution must conform to."""

    # Required identity fields (JSON Schema: required)
    connector_id: str
    constitution_id: str
    schema_version: str
    execution_phases: list[str]

    # Optional fields (default-safe)
    authored_by: str | None = None
    authored_at: str | None = None
    last_proven_at: str | None = None
    prerequisite_reads: list[PrerequisiteRead] = field(default_factory=list)
    conflict_analysis_rules: list[ConflictRule] = field(default_factory=list)
    companion_resource_roles: list[CompanionResourceRole] = field(default_factory=list)
    hil_gates: list[HILGate] = field(default_factory=list)
    mutation_sequencing: list[MutationStep] = field(default_factory=list)
    verification_requirements: list[VerificationRequirement] = field(default_factory=list)
    precondition_summary: str | None = None
    companion_resource_summary: str | None = None
    hil_trigger_summary: str | None = None
    degradation_policy: str | None = None

    # ── RES-015: Back-facing teaching surface (prose, 2026-06-17) ──
    how_to_sequence: list[str] = field(default_factory=list)
    what_to_verify: list[str] = field(default_factory=list)
    when_to_ask_human: list[dict] = field(default_factory=list)
    companion_connectors: list[dict] = field(default_factory=list)
    conflict_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a plain dict (roundtrip-safe)."""
        return {
            "connector_id": self.connector_id,
            "constitution_id": self.constitution_id,
            "schema_version": self.schema_version,
            "authored_by": self.authored_by,
            "authored_at": self.authored_at,
            "last_proven_at": self.last_proven_at,
            "execution_phases": list(self.execution_phases),
            "prerequisite_reads": [r.to_dict() for r in self.prerequisite_reads],
            "conflict_analysis_rules": [r.to_dict() for r in self.conflict_analysis_rules],
            "companion_resource_roles": [r.to_dict() for r in self.companion_resource_roles],
            "hil_gates": [g.to_dict() for g in self.hil_gates],
            "mutation_sequencing": [s.to_dict() for s in self.mutation_sequencing],
            "verification_requirements": [v.to_dict() for v in self.verification_requirements],
            "precondition_summary": self.precondition_summary,
            "companion_resource_summary": self.companion_resource_summary,
            "hil_trigger_summary": self.hil_trigger_summary,
            "degradation_policy": self.degradation_policy,
            # RES-015: teaching surface fields
            "how_to_sequence": list(self.how_to_sequence),
            "what_to_verify": list(self.what_to_verify),
            "when_to_ask_human": list(self.when_to_ask_human),
            "companion_connectors": list(self.companion_connectors),
            "conflict_rules": list(self.conflict_rules),
        }


# ── JSON Schema (Draft-07) ─────────────────────────────────────────────

CONSTITUTION_JSON_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": True,  # RES-000b: allow new teaching surface fields
    "required": ["connector_id", "constitution_id", "schema_version", "execution_phases"],
    "properties": {
        "connector_id": {"type": "string", "pattern": r"^[a-z]+\.[a-z][a-z0-9_]*$"},
        "constitution_id": {"type": "string"},
        "schema_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "authored_by": {"type": ["string", "null"]},
        "authored_at": {"type": ["string", "null"]},
        "last_proven_at": {"type": ["string", "null"]},
        "execution_phases": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "prerequisite_reads": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["operation", "resource_kind", "reason"],
                "properties": {
                    "operation": {"type": "string"},
                    "resource_kind": {"type": "string"},
                    "reason": {"type": "string"},
                    "required": {"type": "boolean"},
                    "timeout_ms": {"type": "integer", "minimum": 1000},
                },
            },
        },
        "conflict_analysis_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["check"],
                "properties": {
                    "check": {"type": "string"},
                    "with_resource_kinds": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "resolution": {"type": "string"},
                },
            },
        },
        "hil_gates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["trigger", "prompt"],
                "properties": {
                    "trigger": {"type": "string"},
                    "field": {"type": ["string", "null"]},
                    "prompt": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "verification_requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["method"],
                "properties": {
                    "method": {"type": "string"},
                    "description": {"type": "string"},
                    "required_for_submit": {"type": "boolean"},
                },
            },
        },
        "mutation_sequencing": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["order", "phase", "operation"],
                "properties": {
                    "order": {"type": "integer"},
                    "phase": {"type": "string"},
                    "operation": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "companion_resource_roles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["resource_kind", "role"],
                "properties": {
                    "resource_kind": {"type": "string"},
                    "role": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "precondition_summary": {"type": ["string", "null"]},
        "companion_resource_summary": {"type": ["string", "null"]},
        "hil_trigger_summary": {"type": ["string", "null"]},
        "degradation_policy": {"type": ["string", "null"]},
    },
}


# ── Validation ─────────────────────────────────────────────────────────


def validate_constitution(data: dict) -> ConstitutionArtifact:
    """Validate a raw dict against ``CONSTITUTION_JSON_SCHEMA``.

    On pass, parse into a ``ConstitutionArtifact`` with typed sub-objects.
    On fail, raise ``ConstitutionValidationError`` with field-level detail.
    """
    if not isinstance(data, dict):
        raise ConstitutionValidationError("constitution must be a dict")

    try:
        jsonschema.validate(instance=data, schema=CONSTITUTION_JSON_SCHEMA)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ConstitutionValidationError(f"{path}: {exc.message}", field_path=path) from exc

    return ConstitutionArtifact(
        connector_id=str(data["connector_id"]),
        constitution_id=str(data["constitution_id"]),
        schema_version=str(data["schema_version"]),
        execution_phases=list(data["execution_phases"]),
        authored_by=_opt_str(data.get("authored_by")),
        authored_at=_opt_str(data.get("authored_at")),
        last_proven_at=_opt_str(data.get("last_proven_at")),
        prerequisite_reads=[
            PrerequisiteRead.from_dict(r) for r in data.get("prerequisite_reads", [])
        ],
        conflict_analysis_rules=[
            ConflictRule.from_dict(r) for r in data.get("conflict_analysis_rules", [])
        ],
        companion_resource_roles=[
            CompanionResourceRole.from_dict(r) for r in data.get("companion_resource_roles", [])
        ],
        hil_gates=[HILGate.from_dict(g) for g in data.get("hil_gates", [])],
        mutation_sequencing=[
            MutationStep.from_dict(s) for s in data.get("mutation_sequencing", [])
        ],
        verification_requirements=[
            VerificationRequirement.from_dict(v) for v in data.get("verification_requirements", [])
        ],
        precondition_summary=_opt_str(data.get("precondition_summary")),
        companion_resource_summary=_opt_str(data.get("companion_resource_summary")),
        hil_trigger_summary=_opt_str(data.get("hil_trigger_summary")),
        degradation_policy=_opt_str(data.get("degradation_policy")),
        # RES-015/017: teaching surface fields (2026-06-17)
        how_to_sequence=[str(s) for s in data.get("how_to_sequence", [])],
        what_to_verify=[str(v) for v in data.get("what_to_verify", [])],
        when_to_ask_human=[dict(h) for h in data.get("when_to_ask_human", [])],
        companion_connectors=[dict(c) for c in data.get("companion_connectors", [])],
        conflict_rules=[str(r) for r in data.get("conflict_rules", [])],
    )


def validate_constitution_semantics(
    artifact: ConstitutionArtifact,
    known_resource_kinds: set[str],
) -> list[str]:
    """Semantic rules beyond JSON Schema.

    Returns a list of violation messages (empty = valid):
      - ``prerequisite_reads[].resource_kind`` must be known.
      - ``conflict_analysis_rules[].with_resource_kinds[]`` must be known.
      - ``companion_resource_roles[].resource_kind`` must be known.
      - ``mutation_sequencing[].phase`` must match a declared execution_phase.
      - ``verification_requirements[].method`` must be a known verifier method.
    """
    violations: list[str] = []
    phases = set(artifact.execution_phases)

    for i, pr in enumerate(artifact.prerequisite_reads):
        if pr.resource_kind not in known_resource_kinds:
            violations.append(
                f"prerequisite_reads[{i}].resource_kind: "
                f"'{pr.resource_kind}' not in known resource kinds"
            )

    for i, rule in enumerate(artifact.conflict_analysis_rules):
        for rk in rule.with_resource_kinds:
            if rk not in known_resource_kinds:
                violations.append(
                    f"conflict_analysis_rules[{i}].with_resource_kinds: "
                    f"'{rk}' not in known resource kinds"
                )

    for i, comp in enumerate(artifact.companion_resource_roles):
        if comp.resource_kind not in known_resource_kinds:
            violations.append(
                f"companion_resource_roles[{i}].resource_kind: "
                f"'{comp.resource_kind}' not in known resource kinds"
            )

    for i, step in enumerate(artifact.mutation_sequencing):
        if step.phase not in phases:
            violations.append(
                f"mutation_sequencing[{i}].phase: "
                f"'{step.phase}' not in declared execution_phases {sorted(phases)}"
            )

    for i, vr in enumerate(artifact.verification_requirements):
        if vr.method not in KNOWN_VERIFIER_METHODS:
            violations.append(
                f"verification_requirements[{i}].method: "
                f"'{vr.method}' is not a known verifier method"
            )

    return violations


# ── Helpers ────────────────────────────────────────────────────────────


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
