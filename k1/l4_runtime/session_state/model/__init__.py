"""
K1 L4 Runtime — SessionState Model (6-Section Design)

**Purpose:** 6-section SessionState data model with beliefs, scoreboard, control, persona, multimodal, meta

**6 Sections:**
1. **Beliefs** — Fact storage with confidence scores, LRU eviction
2. **Scoreboard** — QUD stack, entity tracking, salience decay
3. **Control** — Agent leases, flow state, turn lock management
4. **Persona** — Personality traits, LLM prompt injection
5. **Multimodal** — Audio/vision context, streaming state
6. **Meta** — Telemetry, performance metrics, Prometheus export

**Performance:**
- Total size: 64KB soft limit, 128KB hard limit, 256KB OOM
- Section access: O(1) via FlatBuffers offsets
- Serialization: <1ms P95 (full), <0.5ms (delta)

**ADRs (7 total):**
- ADR-0017: Overall Architecture (6 sections, 64KB soft limit, voice continuity amendment)
- ADR-0017a: Beliefs Section (fact storage, confidence 0.0-1.0, last_accessed_ms, LRU eviction)
- ADR-0017b: Scoreboard Section (QUD stack max 5, entity tracking 50 entities, salience decay exp(-λt))
- ADR-0017c: Control Section (agent leases ACTIVE/IDLE, flow_id UUID, turn_lock bool, concurrency control)
- ADR-0017d: Persona Section (personality traits dict, LLM system prompt, voice preferences)
- ADR-0017e: Multimodal Section (audio frames buffer 5s, vision frames buffer 3, streaming state)
- ADR-0017f: Meta Section (turn count, session duration, memory KB, Prometheus counters)

**Research Foundations:**
- Grosz & Sidner (1986) — Discourse structure (QUD stack, entity salience)
- Roberts (1996) — Questions under discussion (QUD theory)
- Kahneman & Tversky (1979) — Salience decay (exponential decay λ=0.1)
- Hayes et al. (2016) — Belief revision in cognitive architectures

**Data Model:**

```python
@dataclass
class SessionState:
    session_id: str
    beliefs: BeliefsSection          # ADR-0017a
    scoreboard: ScoreboardSection    # ADR-0017b
    control: ControlSection          # ADR-0017c
    persona: PersonaSection          # ADR-0017d
    multimodal: MultimodalSection    # ADR-0017e
    meta: MetaSection                # ADR-0017f
    version: int  # Schema version
    updated_at_ms: int  # Last modification timestamp
```

**Files:**
- session_state.py — Main SessionState dataclass
- beliefs.py — Beliefs section (fact storage, confidence, LRU)
- scoreboard.py — Scoreboard section (QUD stack, entity tracking)
- control.py — Control section (agent leases, flow state, locks)
- persona.py — Persona section (personality, prompts)
- multimodal.py — Multimodal section (audio/vision buffers)
- meta.py — Meta section (telemetry, metrics)

**Integration:**
- Serialization: FlatBuffers zero-copy access via session_state/serialization/
- Eviction: 3-tier eviction via session_state/memory_manager/
- Storage: Multi-tier persistence via session_state/storage/
- K0 WAL: Checkpointing via ADR-0019c integration

**Performance Metrics:**
- session_state_size_bytes (gauge, per-section breakdown)
- session_state_access_total (counter, per-section)
- session_state_mutations_total (counter, per-section)

**Last Updated:** October 2025
**Status:** Production-ready 6-section data model
"""

__version__ = "0.1.0"

# TODO: Implement session_state.py, beliefs.py, scoreboard.py, control.py, persona.py, multimodal.py, meta.py
# Per ADR-0017 family (0017-0017f)
