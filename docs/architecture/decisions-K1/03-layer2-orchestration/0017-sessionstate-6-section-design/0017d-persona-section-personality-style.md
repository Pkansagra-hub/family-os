---
adr_number: 0017d
affected_layers:
- layer4_runtime
affected_modules: []
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- scalability
- security
- testing
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: IN_PROGRESS
propagation:
  affected_adrs:
  - ADR-0011
  - ADR-0017
  - ADR-0017a
  affected_tests: []
  triggers:
  - Personality trait schema modifications
  - LLM system prompt injection format changes
  - Tone/style preference enum updates
  - Persona conflict resolution policy adjustments
  - Size budget modifications for persona storage
related_adrs:
- ADR-0011
- ADR-0017
- ADR-0017a
- ADR-0019a
- ADR-0067
- ADR-0069
- ADR-0070
- ADR-0071
related_contracts:
- k1/contracts/flatbuffers/layer2_state/persona_section.fbs
related_diagrams: []
research_citations:
- OpenAI Custom Instructions (API Documentation, 2024)
- Character.AI Personality Sliders (Character.AI Documentation, 2024)
- Replika Personality Model (Replika Research, 2023)
status: PROPOSED
superseded_by: []
supersedes: []
title: Persona Section - Personality Model & Style
---

# ADR-0017d: Persona Section - Personality Model & Style

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

The **Persona Section** stores user personality preferences (tone, style, verbosity) to customize LLM responses:

- **Personality Traits:** Tone (formal, casual), style (concise, detailed), verbosity
- **Interaction Preferences:** Preferred format (text, voice), language
- **Static Data:** Rarely changes (low eviction priority)
- **Size Budget:** 2-4KB (50-100 preferences)
- **K0 Persistence:** Serialize to K0 for long-term storage

**Key Challenges:**

1. **Trait Representation:** How to store traits (enum, string, float scale)?
2. **LLM Integration:** Inject persona into system prompts
3. **Conflict Resolution:** User changes tone preference (overwrite or version)?
4. **Size Budget:** 2-4KB limit (50-100 traits)
5. **Eviction Policy:** Low priority (static, evict last)

### Current Landscape

**Industry Persona Management Patterns:**

1. **OpenAI Custom Instructions**:
   - **Pattern:** Free-form text for "About me" and "Response style"
   - **Advantage:** Flexible, user-friendly
   - **Disadvantage:** No structure, hard to parse

2. **Character.AI Personality Sliders**:
   - **Pattern:** Float sliders (0.0-1.0) for traits (humor, formality, creativity)
   - **Advantage:** Structured, easy to interpolate
   - **Disadvantage:** Limited expressiveness

3. **Replika Personality Model**:
   - **Pattern:** Big Five traits (OCEAN: Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism)
   - **Advantage:** Psychology-grounded
   - **Disadvantage:** Complex, user doesn't understand traits

4. **ChatGPT Tone Settings**:
   - **Pattern:** Simple dropdown (casual, professional, creative)
   - **Advantage:** Simple, user-friendly
   - **Disadvantage:** Coarse-grained (only 3 options)

### K1 Requirements

**Persona Section Properties:**

1. **Trait Storage:** Key-value pairs (trait_name → trait_value)
2. **Confidence Tracking:** 0.0-1.0 confidence (like beliefs)
3. **Low Eviction Priority:** Static data, evict last under pressure
4. **LLM Prompt Injection:** Format traits as system prompt text
5. **K0 Persistence:** Serialize to K0 for long-term storage

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `set_trait(name, value)` | <300μs | Fast trait update |
| `get_trait(name)` | <100μs | Fast trait lookup |
| `format_for_llm()` | <5ms | Format all traits as prompt |
| `serialize()` | <5ms | FlatBuffers serialization |

---

## Decision

We will implement **Persona Section** as:

1. **Trait Store:** HashMap with trait_name → PersonaTrait (value, confidence)
2. **Static Data:** Rarely changes (low eviction priority)
3. **FlatBuffers Schema:** PersonaTrait table with trait_name, trait_value, confidence
4. **LLM Integration:** Format traits as system prompt ("Respond in a casual tone...")
5. **K0 Persistence:** Serialize to K0 on session save

**Data Model:**

```
PersonaTrait:
  - trait_name: string (e.g., "tone", "verbosity", "style")
  - trait_value: string (e.g., "casual", "concise", "detailed")
  - confidence: float (0.0-1.0, from user or inferred)

PersonaSection:
  - traits: [PersonaTrait] (50-100 traits, 2-4KB)
  - preferred_language: string (e.g., "en-US", "es-ES")
  - preferred_format: string (e.g., "text", "voice")
```

---

## Implementation

### FlatBuffers Schema

```flatbuffers
// k1/session_state/schemas/persona_section.fbs
namespace K1.SessionState;

/// Personality trait (tone, style, verbosity, etc.)
table PersonaTrait {
  /// Trait name ("tone", "verbosity", "style", "humor", etc.)
  trait_name: string (required);

  /// Trait value ("casual", "formal", "concise", "detailed", etc.)
  trait_value: string (required);

  /// Confidence score (0.0 = uncertain, 1.0 = certain)
  confidence: float = 1.0;
}

/// Persona section (personality model & style preferences)
table PersonaSection {
  /// Personality traits (50-100 traits, 2-4KB)
  traits: [PersonaTrait] (required);

  /// Preferred language (e.g., "en-US", "es-ES")
  preferred_language: string = "en-US";

  /// Preferred format (e.g., "text", "voice")
  preferred_format: string = "text";

  /// Total size in bytes
  total_size_bytes: int;

  /// Last update timestamp
  last_updated_ms: long;
}

root_type PersonaSection;
```

---

### Python Implementation

```python
# k1/session_state/persona_manager.py
"""Persona Section Manager - Personality Model & Style

Research:
- Big Five Personality: "The Big Five Personality Traits" (Goldberg, 1993)
- Conversational Style: "The Handbook of Discourse Analysis" (Schiffrin et al., 2001)
"""

from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PersonaTraitData:
    """In-memory persona trait representation"""
    trait_name: str
    trait_value: str
    confidence: float


class PersonaManager:
    """Manage persona section (personality model & style)

    Responsibilities:
    - Store user personality preferences (tone, style, verbosity)
    - Format traits for LLM system prompt injection
    - Serialize to K0 for long-term persistence

    Performance:
    - set_trait: O(1) update, <300μs P95
    - get_trait: O(1) lookup, <100μs P95
    - format_for_llm: O(n) format, <5ms P95 (n = 50-100)
    """

    def __init__(self):
        """Initialize persona manager"""
        self.traits: Dict[str, PersonaTraitData] = {}
        self.preferred_language = "en-US"
        self.preferred_format = "text"

    def set_trait(
        self,
        trait_name: str,
        trait_value: str,
        confidence: float = 1.0,
    ):
        """Set personality trait

        Args:
            trait_name: Trait name (e.g., "tone", "verbosity")
            trait_value: Trait value (e.g., "casual", "concise")
            confidence: Confidence score (0.0-1.0)

        Performance: <300μs P95
        """
        trait = PersonaTraitData(
            trait_name=trait_name,
            trait_value=trait_value,
            confidence=confidence,
        )
        self.traits[trait_name] = trait
        logger.info(f"[PersonaManager] Set trait: {trait_name} = {trait_value}")

    def get_trait(self, trait_name: str) -> Optional[str]:
        """Get trait value

        Args:
            trait_name: Trait name

        Returns:
            Trait value if exists, None otherwise

        Performance: <100μs P95
        """
        trait = self.traits.get(trait_name)
        return trait.trait_value if trait else None

    def get_trait_with_confidence(self, trait_name: str) -> Optional[tuple]:
        """Get trait with confidence

        Args:
            trait_name: Trait name

        Returns:
            (trait_value, confidence) if exists, None otherwise
        """
        trait = self.traits.get(trait_name)
        return (trait.trait_value, trait.confidence) if trait else None

    def get_all_traits(self) -> Dict[str, str]:
        """Get all traits as dict

        Returns:
            Dict of trait_name → trait_value
        """
        return {name: trait.trait_value for name, trait in self.traits.items()}

    def set_preferred_language(self, language: str):
        """Set preferred language

        Args:
            language: Language code (e.g., "en-US", "es-ES")
        """
        self.preferred_language = language
        logger.info(f"[PersonaManager] Set preferred language: {language}")

    def set_preferred_format(self, format: str):
        """Set preferred format

        Args:
            format: Format type ("text", "voice")
        """
        self.preferred_format = format
        logger.info(f"[PersonaManager] Set preferred format: {format}")

    def format_for_llm(self) -> str:
        """Format persona traits for LLM system prompt

        Returns:
            Formatted prompt text

        Performance: <5ms P95

        Example Output:
            "Respond in a casual tone with concise answers. Use simple language and avoid technical jargon."
        """
        lines = []

        # Tone
        tone = self.get_trait("tone")
        if tone:
            lines.append(f"Respond in a {tone} tone.")

        # Verbosity
        verbosity = self.get_trait("verbosity")
        if verbosity:
            if verbosity == "concise":
                lines.append("Keep answers concise and to the point.")
            elif verbosity == "detailed":
                lines.append("Provide detailed explanations with examples.")

        # Style
        style = self.get_trait("style")
        if style:
            lines.append(f"Use a {style} writing style.")

        # Humor
        humor = self.get_trait("humor")
        if humor == "high":
            lines.append("Feel free to use humor and light jokes.")
        elif humor == "none":
            lines.append("Avoid humor and stay professional.")

        # Language complexity
        complexity = self.get_trait("language_complexity")
        if complexity == "simple":
            lines.append("Use simple language and avoid technical jargon.")
        elif complexity == "technical":
            lines.append("Use technical terminology when appropriate.")

        return " ".join(lines) if lines else "Respond naturally."

    def get_size_kb(self) -> int:
        """Estimate section size in KB

        Returns:
            Estimated size in KB
        """
        trait_bytes = sum(
            len(trait.trait_name) + len(trait.trait_value) + 8
            for trait in self.traits.values()
        )
        metadata_bytes = len(self.preferred_language) + len(self.preferred_format) + 16
        total_bytes = trait_bytes + metadata_bytes
        return total_bytes // 1024

    def serialize(self) -> bytes:
        """Serialize to FlatBuffers for K0 persistence

        Returns:
            FlatBuffers serialized bytes

        Performance: <5ms P95
        """
        import flatbuffers
        # FlatBuffers serialization code (similar to BeliefsManager)
        # ... (implementation details)
        pass

    @staticmethod
    def deserialize(data: bytes) -> "PersonaManager":
        """Deserialize from FlatBuffers

        Args:
            data: FlatBuffers serialized bytes

        Returns:
            PersonaManager instance
        """
        # FlatBuffers deserialization code
        # ... (implementation details)
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/test_persona_manager.py
from ward import test, fixture
from k1.session_state.persona_manager import PersonaManager

@fixture
def persona():
    """Fixture for PersonaManager"""
    return PersonaManager()

@test("set_trait stores trait with confidence")
def _(persona=persona):
    persona.set_trait("tone", "casual", confidence=0.9)

    value = persona.get_trait("tone")
    assert value == "casual"

    value_conf = persona.get_trait_with_confidence("tone")
    assert value_conf == ("casual", 0.9)

@test("format_for_llm generates system prompt")
def _(persona=persona):
    persona.set_trait("tone", "casual")
    persona.set_trait("verbosity", "concise")

    prompt = persona.format_for_llm()
    assert "casual" in prompt
    assert "concise" in prompt
```

---

## Research Citations

1. **Goldberg, L. R. (1993).** *"The Structure of Phenotypic Personality Traits."* American Psychologist. — Big Five personality model.

2. **Schiffrin, D., Tannen, D., Hamilton, H. E. (2001).** *"The Handbook of Discourse Analysis."* Blackwell. — Conversational style analysis.

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-12
**Target Completion:** 2025-11-09 (4 weeks)
**Blocked By:** 0017 (SessionState 6-Section Design)
**Blocks:** None

---

**END OF ADR-0017d**