I'll read the first 2000 lines of the whiteboard_chatexp.md file to analyze what new ADRs are required.

Read [](file:///d%3A/familyos/docs/whiteboard_chatexp.md#1-1), lines 1 to 2000

Based on my analysis of the first 2000 lines of whiteboard_chatexp.md, here are the **new ADRs required** organized by layer in the decisions folder structure:

## **Foundation Layer (01-foundation/)**

1. **ADR-XXXX: 20-Pipeline Memory Processing Architecture**
   - **Category**: 01-foundation
   - **Purpose**: Define the complete 20-pipeline architecture (P01-P20) that orchestrates all memory operations in K0
   - **Missing**: Comprehensive specification of how pipelines coordinate, message passing, event bus architecture

2. **ADR-XXXX: 8 Memory Type System Architecture**
   - **Category**: 01-foundation
   - **Purpose**: Define the 8 memory types (Episodic, Semantic, Procedural, Affect, Social, Self-Model, Vector, Knowledge Graph) and their storage drivers
   - **Missing**: Type definitions, storage schemas, query interfaces for each memory type

3. **ADR-XXXX: Dual Memory Source Architecture (Conversation + Connectors)**
   - **Category**: 01-foundation
   - **Purpose**: Define how memory is formed from both conversation streams AND external app connectors in parallel
   - **Missing**: Coordination protocol between P02 (Write) and P09 (Connector Ingestion)

4. **ADR-XXXX: K0-K1 Bridge Communication Protocol**
   - **Category**: 01-foundation
   - **Purpose**: Define the bridge between K0 (Memory) and K1 (Intelligence) kernels for bidirectional memory/learning signals
   - **Missing**: Event schema, latency guarantees, backpressure handling (P04 bridge mentioned but not specified)

## **Layer 2 - Orchestration (03-layer2-orchestration/)**

5. **ADR-XXXX: Three-Tier Agent Hierarchy (Concierge + Specialists + Writers)**
   - **Category**: 03-layer2-orchestration
   - **Purpose**: Define the complete agent hierarchy: Tier 1 (Concierge - always active), Tier 2 (Specialists - dynamic), Tier 3 (Writers - background)
   - **Missing**: Tier coordination protocol, responsibilities, creation policies

6. **ADR-XXXX: Message Queue with Cancellation Tokens**
   - **Category**: 03-layer2-orchestration
   - **Purpose**: Handle user corrections, rapid-fire messages, mid-response interruptions
   - **Missing**: Queue management, cancellation protocol, message batching windows (500ms buffer mentioned)

7. **ADR-XXXX: Task Amendment and Refinement Protocol**
   - **Category**: 03-layer2-orchestration
   - **Purpose**: Support UPDATE_TASK, REFINE_TASK, COMPENSATE_AND_AMEND operations for user corrections
   - **Missing**: Amendment detection, Saga pattern compensation for bookings/reservations

8. **ADR-XXXX: Multi-Step Workflow State Machine**
   - **Category**: 03-layer2-orchestration
   - **Purpose**: Chain dependent actions ("Find restaurants, book one, add to calendar")
   - **Missing**: WorkflowState design, step dependency resolution, result passing between steps

## **Layer 3 - Execution (04-layer3-execution/)**

9. **ADR-XXXX: Dynamic User Modeling Service (PersonaGraph)**
   - **Category**: 04-layer3-execution
   - **Purpose**: Dynamic user model extraction (goals, fears, values, learning style) that evolves with interactions
   - **Missing**: Complete implementation (listed as "Missing Concept #1" in doc)

10. **ADR-XXXX: Cross-Domain Context Fusion Engine**
    - **Category**: 04-layer3-execution
    - **Purpose**: Semantic integration of Health + Finance + Relationships + Calendar + Work contexts through KG
    - **Missing**: Fusion algorithm, conflict resolution, unified context representation (listed as "Missing Concept #2")

11. **ADR-XXXX: Proactive Anticipation System**
    - **Category**: 04-layer3-execution
    - **Purpose**: Proactive suggestions based on learned patterns + P03 consolidation + KG causal analysis
    - **Missing**: Trigger conditions, suggestion generation, user preference learning (listed as "Missing Concept #4")

12. **ADR-XXXX: Graceful Interruption Protocol for Streaming Responses**
    - **Category**: 04-layer3-execution
    - **Purpose**: Handle mid-response user interruptions with partial response saving
    - **Missing**: DialogueAgent.handle_interruption() implementation, partial response storage

## **Layer 4 - Runtime (05-layer4-runtime/)**

13. **ADR-XXXX: P03 Memory Consolidation Pipeline - 5-Phase Processing**
    - **Category**: 05-layer4-runtime
    - **Purpose**: Complete spec for sleep-like consolidation (Hippocampal Replay → Episodic→Semantic → KG Evolution → Synaptic Pruning → Dream-Like Exploration)
    - **Relates to**: ADR-0084 (Memory Consolidation) but needs full 5-phase detail from doc

14. **ADR-XXXX: P06 Learning Loop with Drift Detection**
    - **Category**: 05-layer4-runtime
    - **Purpose**: Advisory-only learning from K1 → authoritative validation in K0, with rollback on drift
    - **Relates to**: ADR-0059 (Learning Loop) but needs drift detection algorithm

15. **ADR-XXXX: P19 Personalization & Recommendation Pipeline**
    - **Category**: 05-layer4-runtime
    - **Purpose**: User modeling, contextual adaptation, preference learning
    - **Missing**: Complete implementation details for how P19 builds user models

16. **ADR-XXXX: P05 Prospective Memory & Trigger Scheduling**
    - **Category**: 05-layer4-runtime
    - **Purpose**: Future-oriented memories, proactive notifications, reminder scheduling
    - **Missing**: Trigger conditions, notification strategies, coordination with P03

17. **ADR-XXXX: P07 Multi-Device Sync with CRDT & E2EE**
    - **Category**: 05-layer4-runtime
    - **Purpose**: CRDT merge, conflict resolution, E2EE synchronization across family devices
    - **Missing**: CRDT algorithm choice, sync protocol, conflict resolution rules

18. **ADR-XXXX: P09 Connector Ingestion Pipeline (8 Data Sources)**
    - **Category**: 05-layer4-runtime
    - **Purpose**: Normalize & enrich data from Health, Finance, Calendar, Contacts, Work, Activity, Weather, Travel
    - **Missing**: Connector API specs, normalization rules, enrichment strategies

19. **ADR-XXXX: P10 PII Minimization & Privacy Enforcement**
    - **Category**: 05-layer4-runtime
    - **Purpose**: PII detection, GREEN/AMBER/RED privacy bands, redaction/encryption
    - **Missing**: Detection algorithms, band enforcement rules, audit trail schema

20. **ADR-XXXX: P08 Embedding Lifecycle & Semantic Indexing**
    - **Category**: 05-layer4-runtime
    - **Purpose**: Vector generation, similarity indexing, analogical reasoning
    - **Missing**: Embedding model choice, index maintenance, query optimization

## **Layer 5 - Infrastructure (06-layer5-infrastructure/)**

21. **ADR-XXXX: Affective Memory System (Emotional Grounding)**
    - **Category**: 06-layer5-infrastructure
    - **Purpose**: Emotional salience scoring, affect tagging, importance-driven consolidation
    - **Missing**: Complete implementation (listed as "Missing Concept #3")

22. **ADR-XXXX: Causality Graph (Separate from Knowledge Graph)**
    - **Category**: 06-layer5-infrastructure
    - **Purpose**: Causal reasoning ("If X, then Y because Z"), separate from structural KG
    - **Missing**: Complete implementation (listed as "Missing Concept #6")

23. **ADR-XXXX: Multi-Person Memory Model & Family Coordination**
    - **Category**: 06-layer5-infrastructure
    - **Purpose**: Per-person models (Alice, Mom, User) + shared family memory + private memory + coordination rules
    - **Missing**: Complete implementation (listed as "Missing Concept #5")

24. **ADR-XXXX: P20 Procedural Memory & Habit Formation Support**
    - **Category**: 06-layer5-infrastructure
    - **Purpose**: Skill storage, habit tracking, routine building, consistency monitoring
    - **Missing**: Complete implementation (listed as "Missing Concept #10")

## **Security & Privacy (08-security-privacy/)**

25. **ADR-XXXX: P11 DSAR/GDPR Compliance Pipeline**
    - **Category**: 08-security-privacy
    - **Purpose**: Right-to-access, right-to-erasure across all 20 pipelines
    - **Missing**: Export format, deletion propagation, 30-day compliance proof

26. **ADR-XXXX: P12 Device E2EE & Key Management**
    - **Category**: 08-security-privacy
    - **Purpose**: E2EE key management, encryption at rest, RED-band user-only decryption
    - **Missing**: Key rotation, device enrollment, emergency recovery

## **Communication (09-communication/)**

27. **ADR-XXXX: Emotional Regulation Coordination System**
    - **Category**: 09-communication
    - **Purpose**: User emotional state awareness (stress/celebration/overwhelm) with adaptive response style
    - **Missing**: Complete implementation (listed as "Missing Concept #9")

28. **ADR-XXXX: Conversational Intent Classification & Noise Handling**
    - **Category**: 09-communication
    - **Purpose**: Distinguish between tasks, acknowledgments ("ok"), small talk, meta-queries ("are you there?")
    - **Missing**: Intent classifier, noise filtering, social lubrication responses

## **Summary Statistics**
- **Total new ADRs needed**: 28
- **Foundation layer**: 4 ADRs
- **Layer 2 (Orchestration)**: 4 ADRs
- **Layer 3 (Execution)**: 4 ADRs
- **Layer 4 (Runtime)**: 8 ADRs
- **Layer 5 (Infrastructure)**: 4 ADRs
- **Security & Privacy**: 2 ADRs
- **Communication**: 2 ADRs

**Priority order**: Start with Foundation → Runtime (20 pipelines) → Orchestration (3-tier agents) → Execution (proactive systems) → Infrastructure (KG enhancements)
