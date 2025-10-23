"""
Orchestrator Module - 3-Phase Multi-Agent Coordination

**ADR Reference:** ADR-0006 (3-Phase Orchestration with Contract Net Protocol)
**Related ADRs:**
- ADR-0006a: Phase 1 Negotiation (Contract Net Protocol)
- ADR-0006b: Phase 2 Selection (MADM 6-factor scoring)
- ADR-0006c: Phase 3 Execution (DAG parallel execution)
- ADR-0006d: Saga Pattern Integration (LIFO compensation)
- ADR-0006e: Multi-Agent Coordination (wave independence)

**Purpose:**
Coordinate multi-agent task execution with 3-phase protocol:
1. Negotiation (broadcast + bidding) → Collect agent proposals
2. Selection (MADM scoring) → Select optimal agent per step
3. Execution (DAG waves) → Parallel execution with Saga rollback

**Performance Budget:** <250ms P95 (Negotiation 50ms + Selection 5ms + Execution variable)

**Location:** k1/l2_orchestration/orchestrator/ (Layer 2 - Orchestration)

**Architecture:**
The Orchestrator is a PURE ACTOR (deterministic logic, NO LLM calls).
It coordinates 4 AI agents + 48 pure actors via Actor Model message passing.

**Key Components:**
- negotiation.py: Phase 1 (Contract Net, broadcast TaskAnnouncement, collect Proposals)
- selection.py: Phase 2 (MADM scoring, 6-factor weighted selection)
- execution.py: Phase 3 (DAG builder, wave computation, parallel executor)
- saga.py: Saga Coordinator (LIFO compensation, error recovery)
"""

from .execution import Executor
from .negotiation import Negotiator
from .saga import SagaCoordinator
from .selection import Selector

__all__ = ["Negotiator", "Selector", "Executor", "SagaCoordinator"]
