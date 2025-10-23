"""
K1 L4 Runtime — SessionState Management

**Purpose:** 6-section SessionState design with 3-tier eviction, FlatBuffers serialization, multi-tier storage

**Components:**
- model/ — 6-section design (beliefs, scoreboard, control, persona, multimodal, meta)
- control/ — Locking, flow control, turn lock management
- memory_manager/ — 3-tier eviction (soft 64KB, hard 128KB, OOM 256KB)
- serialization/ — FlatBuffers serialization (full <1ms, delta <0.5ms)
- storage/ — Multi-tier storage (Hot L1 RAM, Warm L2 SSD, Cold L3 Object)

**Performance:**
- Serialize: <1ms P95 (64KB)
- Deserialize: <0.1ms P95
- Eviction: <5ms P95
- Size: 64KB soft, 128KB hard, 256KB OOM

**ADRs (22 total):**

**SessionState 6-Section Design (7 ADRs):**
- ADR-0017: Overall Architecture (6 sections, 64KB soft limit, voice continuity amendment)
- ADR-0017a: Beliefs Section (fact storage, confidence, LRU eviction)
- ADR-0017b: Scoreboard Section (QUD stack, entity tracking, salience decay)
- ADR-0017c: Control Section (agent leases, flow state, turn lock)
- ADR-0017d: Persona Section (personality traits, LLM prompt injection)
- ADR-0017e: Multimodal Section (audio/vision context, streaming state)
- ADR-0017f: Meta Section (telemetry, performance metrics, Prometheus export)

**3-Tier Eviction Strategy (4 ADRs):**
- ADR-0018: Eviction Architecture (soft 64KB, hard 128KB, OOM 256KB)
- ADR-0018a: Tier 1 Soft Eviction (LRU, priority eviction, <5ms)
- ADR-0018b: Tier 2 Hard Eviction (beliefs/scoreboard/multimodal, <3ms compression)
- ADR-0018c: Tier 3 OOM Prevention (critical state save, <10ms, session termination)

**SessionState Serialization (5 ADRs):**
- ADR-0019: Serialization Core (full <1ms, delta <0.5ms, zero-copy)
- ADR-0019a: Schema Definition (6 sections + delta schema)
- ADR-0019b: Serialization Core (dirty flag tracking, delta pipeline)
- ADR-0019c: K0 WAL Integration (5min checkpoint, sequence numbers)
- ADR-0019d: Serialization Core (zero-copy optimization, lazy proxies)

**Multi-Tier Storage (4 ADRs):**
- ADR-0020: Lifecycle Management (Hot→Warm→Cold migration)
- ADR-0020a: Hot Tier (L1 RAM: 56MB, <1ms access, LRU tracking)
- ADR-0020b: Warm Tier (L2 SSD: 100MB, <50ms, 30-day retention)
- ADR-0020c: Cold Tier (L3 Object: S3, <500ms, unlimited capacity)

**Performance Budgets:**
- ADR-0024c: Memory Budgets (64KB soft, 128KB hard, 256KB OOM)

**Planning Integration:**
- ADR-0007d: Stage 4 Commit (SessionState locking, flow_id, <0.1ms)

**Research Foundations:**
- Grosz & Sidner (1986) — Discourse structure (QUD stack, entity tracking)
- Kahneman & Tversky (1979) — Salience decay algorithms
- Hayes et al. (2016) — Belief revision in cognitive architectures

**Integration:**
- K0 Memory Kernel: WAL checkpointing, episodic storage, consolidation
- L3 Execution: Agent state queries, tool context, dialogue tracking
- L4 Protocol Monitor: State transitions, MPST validation
- L5 Thermal: Memory pressure signals, OOM prevention

**Last Updated:** October 2025
**Status:** Production-ready SessionState management
"""

__version__ = "0.1.0"
