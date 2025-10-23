"""
Validate Stage - 2-Tier Validation (Stage 3 of 4)

**ADR Reference:** ADR-0007c (Validation Stage 2-Tier Implementation)

**Purpose:**
Validate plan with 2-tier strategy (rule-based + LLM arbiter).

**Tier 1: Rule-Based Validation (<1ms P95):**
1. Structural: Step count ≤10, unique step_ids, sequential IDs
2. Dependency: Kahn's algorithm DAG cycle detection, O(V+E)
3. Capability: Set intersection, missing capabilities check
4. Budget: Latency budget, cost budget checks
5. Band: Privacy band hierarchy (GREEN<AMBER<RED)
6. Schema: JSON Schema validation, step parameters vs tool schema_in

**Tier 2: LLM Arbiter (50-100ms, <15% invocation):**
- Invoked for: AMBER/RED band plans, child space, age<18
- Safety check: LLM reviews plan for safety/appropriateness
- Model: gpt-4o-mini (fast, cheap)
- Reject rate: <5% of reviewed plans

**Performance Target:** <1ms P95 (Tier 1 only, 85% of plans)

**Input:** ExpandedPlan (from Stage 2)
**Output:** ValidationResult (valid: bool, errors: List[str])

**Validation Checks:**
- Structural (<0.1ms): Basic plan structure correctness
- Dependency (<0.2ms): DAG acyclic, valid dependencies
- Capability (<0.05ms): Agent has required tools/models
- Budget (<0.05ms): Within latency/cost limits
- Band (<0.05ms): Privacy band hierarchy respected
- Schema (<0.5ms): Parameters match tool schema_in

**Error Handling:**
- Validation failure → Return ValidationResult with specific errors
- Arbiter timeout → Fall back to Tier 1 only (warn in logs)
- Multiple errors → Return all errors (not fail-fast)
"""

from .arbiter_validator import ArbiterValidator
from .band_validator import BandValidator
from .budget_validator import BudgetValidator
from .capability_validator import CapabilityValidator
from .dependency_validator import DependencyValidator
from .schema_validator import SchemaValidator
from .structural_validator import StructuralValidator

__all__ = [
    "StructuralValidator",
    "DependencyValidator",
    "CapabilityValidator",
    "BudgetValidator",
    "BandValidator",
    "SchemaValidator",
    "ArbiterValidator",
]
