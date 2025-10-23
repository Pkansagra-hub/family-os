"""
Planner Module - 4-Stage AI-Powered Planning Pipeline

**ADR Reference:** ADR-0007 (4-Stage Planning Pipeline)
**Related ADRs:**
- ADR-0007a: Sketch Stage (LLM prompt engineering)
- ADR-0007b: Expand Stage (tool registry integration)
- ADR-0007c: Validate Stage (2-tier validation)
- ADR-0007d: Commit Stage (K0 WAL integration)

**Purpose:**
Multi-stage pipeline for generating structured task execution plans:
1. Sketch (LLM inference) → JSON plan structure
2. Expand (tool registry lookup) → Enriched plan with metadata
3. Validate (rule-based + arbiter) → Safety/capability checks
4. Commit (K0 WAL write) → Persisted plan

**Performance Budget:** <2500ms P95 (Sketch 500ms + Expand 1ms + Validate 1ms + Commit 10ms)

**Location:** k1/l2_orchestration/planner/ (Layer 2 - Orchestration)

**Architecture:**
The Planner is an AI Agent (uses Model Hub for LLM reasoning) coordinated
by the Orchestrator (pure actor). Each stage is a deterministic function
except Sketch which calls LLM.
"""

__all__ = ["sketch", "expand", "validate", "commit"]
