# ADR-0017b: Scoreboard Section - Common Ground & QUD

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
**Category:** State Management (Layer 2)
**Related ADRs:**
- [ADR-0011 (FlatBuffers Serialization)](0011-flatbuffers-serialization.md)
- [ADR-0017a (Beliefs Section)](0017a-beliefs-section-user-facts-preferences.md)

---

## Context

### Problem Statement

The **Scoreboard Section** tracks common ground, referents, and Questions Under Discussion (QUD) for discourse coherence:

- **Common Ground:** Shared entities/events mentioned in conversation (for pronoun resolution)
- **Referents:** Pronoun-to-entity mappings ("it" → "report.pdf", "that" → "meeting")
- **QUD Stack:** Active questions user wants answered (Question Under Discussion)
- **Salience Tracking:** Which entities are currently active/relevant
- **Eviction Policy:** LRU with high priority (keep active discourse, evict resolved items)

**Key Challenges:**

1. **Referent Resolution:** "What's in it?" - must resolve "it" to last mentioned document
2. **QUD Priority:** Multiple questions active simultaneously (stack ordering)
3. **Salience Decay:** Entities mentioned 10 turns ago are less salient than recent ones
4. **Size Budget:** 4-8KB (50-100 items: entities, referents, QUDs)
5. **Grounding Integration:** Update salience when entities mentioned in grounding acts

### Current Landscape

**Industry Discourse Management Patterns:**

1. **Coreference Resolution (SpaCy, Hugging Face)**:
   - **Pattern:** NLP model resolves "it" → entity (neuralcoref)
   - **Advantage:** ML-based, handles complex cases
   - **Disadvantage:** Heavyweight (300MB model), slow (50ms per resolution)

2. **QUD Theory (Roberts 1996, Ginzburg 2012)**:
   - **Pattern:** Stack of questions (top = current focus)
   - **Advantage:** Formal semantics, theory-grounded
   - **Disadvantage:** Complex (formal logic), no production implementation

3. **Conversation State (Rasa, Dialogflow)**:
   - **Pattern:** Flat "slots" for entities (no salience, no QUD)
   - **Advantage:** Simple (key-value store)
   - **Disadvantage:** No discourse structure, no pronoun resolution

4. **Common Ground (Clark & Brennan 1991)**:
   - **Pattern:** Shared knowledge between speakers
   - **Advantage:** Well-studied (HCI research)
   - **Disadvantage:** No production system implementation

### K1 Requirements

**Scoreboard Section Properties:**

1. **Entity Tracking:** Store entities with salience (0.0-1.0), decay over time
2. **Referent Resolution:** Map pronouns ("it", "that") to entity IDs
3. **QUD Stack:** Priority-ordered questions (top = current focus)
4. **Salience Decay:** Entities lose salience over time (exponential decay)
5. **LRU Eviction:** Evict low-salience entities when size > 8KB

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `resolve_referent("it")` | <200μs | Fast resolution during grounding |
| `add_entity(name, type)` | <500μs | Fast entity tracking |
| `push_qud(question)` | <300μs | Fast QUD stack push |
| `decay_salience()` | <5ms | Periodic decay (every turn) |

---

## Decision

We will implement **Scoreboard Section** as:

1. **Entity Store:** HashMap with entity_id → Entity (name, type, salience, last_mentioned_turn)
2. **Referent Map:** HashMap with reference → entity_id ("it" → "entity_5")
3. **QUD Stack:** List of QUDs (ordered by priority, top = index 0)
4. **Salience Decay:** Exponential decay (salience *= 0.9 per turn not mentioned)
5. **LRU Eviction:** Evict low-salience entities when size > 8KB

**Data Model:**

```
Entity:
  - entity_id: string (e.g., "entity_1", "entity_2")
  - entity_type: string (e.g., "person", "document", "event")
  - name: string (e.g., "Alice", "report.pdf", "meeting")
  - last_mentioned_turn: int (turn number when last mentioned)
  - salience: float (0.0-1.0, current importance/relevance)

Referent:
  - reference: string (e.g., "it", "that", "the document")
  - entity_id: string (points to Entity.entity_id)
  - turn_mentioned: int (when referent was used)

QuestionUnderDiscussion (QUD):
  - qud_id: string (e.g., "qud_1")
  - question: string (e.g., "What is the weather?")
  - status: string ("active", "answered", "abandoned")
  - priority: int (stack priority, 0 = top of stack)

ScoreboardSection:
  - entities: [Entity] (50-80 entities, ~4KB)
  - referents: [Referent] (10-20 referents, ~1KB)
  - quds: [QUD] (5-10 QUDs, ~1KB)
```

---

## Implementation

### FlatBuffers Schema

```flatbuffers
// k1/session_state/schemas/scoreboard_section.fbs
namespace K1.SessionState;

/// Entity mentioned in conversation (person, document, event, etc.)
table Entity {
  /// Unique entity identifier
  entity_id: string (required);

  /// Entity type ("person", "document", "event", "location", etc.)
  entity_type: string (required);

  /// Entity name ("Alice", "report.pdf", "meeting", etc.)
  name: string (required);

  /// Turn number when entity was last mentioned
  last_mentioned_turn: int;

  /// Salience score (0.0 = not salient, 1.0 = highly salient)
  salience: float = 1.0;
}

/// Referent (pronoun or reference pointing to entity)
table Referent {
  /// Reference text ("it", "that", "the document", etc.)
  reference: string (required);

  /// Entity ID this reference points to
  entity_id: string (required);

  /// Turn number when referent was used
  turn_mentioned: int;
}

/// Question Under Discussion (QUD)
table QuestionUnderDiscussion {
  /// Unique QUD identifier
  qud_id: string (required);

  /// Question text ("What is the weather?", "How do I...?")
  question: string (required);

  /// Status ("active", "answered", "abandoned")
  status: string;

  /// Priority (0 = top of stack, higher = lower priority)
  priority: int;
}

/// Scoreboard section (common ground, referents, QUD)
table ScoreboardSection {
  /// Entities in common ground (50-80 entities)
  entities: [Entity] (required);

  /// Referents (pronouns → entities) (10-20 referents)
  referents: [Referent];

  /// Questions under discussion (5-10 QUDs)
  quds: [QuestionUnderDiscussion];

  /// Total size in bytes
  total_size_bytes: int;

  /// Last update timestamp
  last_updated_ms: long;
}

root_type ScoreboardSection;
```

---

### Python Implementation

```python
# k1/session_state/scoreboard_manager.py
"""Scoreboard Section Manager - Common Ground & QUD

Research:
- Common Ground: "Grounding in Communication" (Clark & Brennan, 1991)
- QUD Theory: "Information Structure and Noncanonical Syntax" (Roberts, 1996)
- Salience: "Centering Theory" (Grosz, Joshi, Weinstein, 1995)
"""

from typing import Dict, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class EntityData:
    """In-memory entity representation"""
    entity_id: str
    entity_type: str
    name: str
    last_mentioned_turn: int
    salience: float


@dataclass
class ReferentData:
    """In-memory referent representation"""
    reference: str
    entity_id: str
    turn_mentioned: int


@dataclass
class QUDData:
    """In-memory QUD representation"""
    qud_id: str
    question: str
    status: str  # "active", "answered", "abandoned"
    priority: int


class ScoreboardManager:
    """Manage scoreboard section (common ground, referents, QUD)

    Responsibilities:
    - Track entities mentioned in conversation
    - Resolve pronouns to entities (referent resolution)
    - Maintain QUD stack (questions under discussion)
    - Decay salience over time (entities lose relevance)
    - Evict low-salience entities under memory pressure

    Performance:
    - resolve_referent: O(1) lookup, <200μs P95
    - add_entity: O(1) insert, <500μs P95
    - push_qud: O(1) append, <300μs P95
    - decay_salience: O(n) scan, <5ms P95 (n = 50-80 entities)
    """

    def __init__(self, max_size_kb: int = 8):
        """Initialize scoreboard manager

        Args:
            max_size_kb: Max section size before eviction (default: 8KB)
        """
        self.max_size_kb = max_size_kb
        self.entities: Dict[str, EntityData] = {}
        self.referents: Dict[str, str] = {}  # reference → entity_id
        self.quds: List[QUDData] = []  # QUD stack (index 0 = top)
        self.current_turn = 0
        self.next_entity_id = 1
        self.next_qud_id = 1

    def add_entity(
        self,
        name: str,
        entity_type: str,
        turn: Optional[int] = None,
    ) -> str:
        """Add or update entity in common ground

        Args:
            name: Entity name ("Alice", "report.pdf", etc.)
            entity_type: Entity type ("person", "document", etc.)
            turn: Turn number when mentioned (default: current_turn)

        Returns:
            entity_id of created/updated entity

        Performance: <500μs P95
        """
        if turn is None:
            turn = self.current_turn

        # Check if entity already exists (by name)
        for entity_id, entity in self.entities.items():
            if entity.name == name and entity.entity_type == entity_type:
                # Update existing entity
                entity.last_mentioned_turn = turn
                entity.salience = min(entity.salience + 0.2, 1.0)  # Boost salience
                return entity_id

        # Create new entity
        entity_id = f"entity_{self.next_entity_id}"
        self.next_entity_id += 1

        entity = EntityData(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
            last_mentioned_turn=turn,
            salience=1.0,  # New entities start with full salience
        )
        self.entities[entity_id] = entity

        logger.info(f"[ScoreboardManager] Added entity: {entity_id} ({name}, {entity_type})")

        # Check size, evict if needed
        if self.get_size_kb() > self.max_size_kb:
            self._evict_low_salience()

        return entity_id

    def add_referent(self, reference: str, entity_id: str, turn: Optional[int] = None):
        """Add referent (pronoun → entity mapping)

        Args:
            reference: Reference text ("it", "that", "the document")
            entity_id: Entity this reference points to
            turn: Turn number when mentioned (default: current_turn)
        """
        if turn is None:
            turn = self.current_turn

        self.referents[reference] = entity_id
        logger.info(f"[ScoreboardManager] Added referent: '{reference}' → {entity_id}")

    def resolve_referent(self, reference: str) -> Optional[str]:
        """Resolve pronoun/reference to entity

        Args:
            reference: Reference text ("it", "that", etc.)

        Returns:
            entity_id if resolved, None otherwise

        Performance: <200μs P95
        """
        return self.referents.get(reference)

    def get_entity(self, entity_id: str) -> Optional[EntityData]:
        """Get entity by ID

        Args:
            entity_id: Entity identifier

        Returns:
            EntityData if exists, None otherwise
        """
        return self.entities.get(entity_id)

    def push_qud(self, question: str) -> str:
        """Push question onto QUD stack (becomes top priority)

        Args:
            question: Question text

        Returns:
            qud_id of created QUD

        Performance: <300μs P95
        """
        qud_id = f"qud_{self.next_qud_id}"
        self.next_qud_id += 1

        # Increment priority of existing QUDs (push down stack)
        for qud in self.quds:
            qud.priority += 1

        # Add new QUD at top (priority 0)
        qud = QUDData(
            qud_id=qud_id,
            question=question,
            status="active",
            priority=0,
        )
        self.quds.insert(0, qud)

        logger.info(f"[ScoreboardManager] Pushed QUD: {qud_id} ('{question}')")
        return qud_id

    def pop_qud(self) -> Optional[QUDData]:
        """Pop top QUD from stack (mark as answered)

        Returns:
            QUDData if stack not empty, None otherwise
        """
        if self.quds:
            qud = self.quds.pop(0)
            qud.status = "answered"
            logger.info(f"[ScoreboardManager] Popped QUD: {qud.qud_id} (answered)")
            return qud
        return None

    def get_top_qud(self) -> Optional[QUDData]:
        """Get top QUD without popping

        Returns:
            QUDData if stack not empty, None otherwise
        """
        return self.quds[0] if self.quds else None

    def decay_salience(self, decay_factor: float = 0.9):
        """Decay salience of all entities (call every turn)

        Args:
            decay_factor: Multiplicative decay (0.9 = 10% decay per turn)

        Performance: <5ms P95 for 50-80 entities
        """
        for entity in self.entities.values():
            if entity.last_mentioned_turn < self.current_turn:
                entity.salience *= decay_factor
                # Remove entities with very low salience
                if entity.salience < 0.01:
                    logger.info(f"[ScoreboardManager] Removing entity {entity.entity_id} (salience < 0.01)")
                    # Will be removed in next cleanup pass

        # Remove very low salience entities
        to_remove = [
            entity_id for entity_id, entity in self.entities.items()
            if entity.salience < 0.01
        ]
        for entity_id in to_remove:
            del self.entities[entity_id]

    def advance_turn(self):
        """Advance turn counter (call at start of each turn)"""
        self.current_turn += 1
        self.decay_salience()

    def _evict_low_salience(self):
        """Evict entity with lowest salience

        Performance: O(n) scan, <5ms P95
        """
        if not self.entities:
            return

        # Find entity with lowest salience
        min_salience_id = min(
            self.entities.keys(),
            key=lambda k: self.entities[k].salience
        )

        logger.info(
            f"[ScoreboardManager] Evicting entity: {min_salience_id} "
            f"(salience={self.entities[min_salience_id].salience})"
        )

        del self.entities[min_salience_id]

    def get_size_kb(self) -> int:
        """Estimate section size in KB

        Returns:
            Estimated size in KB
        """
        entity_bytes = sum(
            len(e.entity_id) + len(e.entity_type) + len(e.name) + 16
            for e in self.entities.values()
        )
        referent_bytes = sum(
            len(ref) + len(entity_id) + 8
            for ref, entity_id in self.referents.items()
        )
        qud_bytes = sum(
            len(q.qud_id) + len(q.question) + len(q.status) + 8
            for q in self.quds
        )

        total_bytes = entity_bytes + referent_bytes + qud_bytes
        return total_bytes // 1024

    def get_entity_count(self) -> int:
        """Get number of entities in common ground

        Returns:
            Number of entities
        """
        return len(self.entities)

    def serialize(self) -> bytes:
        """Serialize to FlatBuffers for K0 persistence

        Returns:
            FlatBuffers serialized bytes
        """
        import flatbuffers
        # FlatBuffers serialization code (similar to BeliefsManager)
        # ... (omitted for brevity)
        pass

    @staticmethod
    def deserialize(data: bytes) -> "ScoreboardManager":
        """Deserialize from FlatBuffers

        Args:
            data: FlatBuffers serialized bytes

        Returns:
            ScoreboardManager instance
        """
        # FlatBuffers deserialization code
        # ... (omitted for brevity)
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/test_scoreboard_manager.py
from ward import test, fixture
from k1.session_state.scoreboard_manager import ScoreboardManager

@fixture
def scoreboard():
    """Fixture for ScoreboardManager"""
    return ScoreboardManager(max_size_kb=8)

@test("add_entity creates entity with full salience")
def _(scoreboard=scoreboard):
    entity_id = scoreboard.add_entity("Alice", "person")

    entity = scoreboard.get_entity(entity_id)
    assert entity.name == "Alice"
    assert entity.entity_type == "person"
    assert entity.salience == 1.0

@test("resolve_referent maps pronoun to entity")
def _(scoreboard=scoreboard):
    entity_id = scoreboard.add_entity("report.pdf", "document")
    scoreboard.add_referent("it", entity_id)

    resolved_id = scoreboard.resolve_referent("it")
    assert resolved_id == entity_id

@test("push_qud adds question to top of stack")
def _(scoreboard=scoreboard):
    qud1 = scoreboard.push_qud("What is the weather?")
    qud2 = scoreboard.push_qud("How do I...?")

    top_qud = scoreboard.get_top_qud()
    assert top_qud.question == "How do I...?"
    assert top_qud.priority == 0

@test("decay_salience reduces salience over time")
def _(scoreboard=scoreboard):
    entity_id = scoreboard.add_entity("Alice", "person")
    scoreboard.advance_turn()  # Decay salience

    entity = scoreboard.get_entity(entity_id)
    assert entity.salience < 1.0  # Decayed
```

---

## Research Citations

1. **Clark, H. H., & Brennan, S. E. (1991).** *"Grounding in Communication."* Perspectives on Socially Shared Cognition. — Common ground theory, shared knowledge.

2. **Roberts, C. (1996).** *"Information Structure and Noncanonical Syntax."* Studies in Linguistics and Philosophy. — QUD theory, question-driven discourse.

3. **Grosz, B. J., Joshi, A. K., Weinstein, S. (1995).** *"Centering: A Framework for Modeling the Local Coherence of Discourse."* Computational Linguistics. — Salience, entity tracking, centering transitions.

4. **Ginzburg, J. (2012).** *"The Interactive Stance."* Oxford University Press. — QUD stack, dialogue coherence, question resolution.

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-12
**Target Completion:** 2025-11-09 (4 weeks)
**Blocked By:** 0017 (SessionState 6-Section Design)
**Blocks:** None

---

**END OF ADR-0017b**
