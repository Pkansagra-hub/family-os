# Epic 1.1 Discovery - Client to Concierge Path

## Baseline Guarantees

- **Dual kernel split** keeps client ingress isolated from durable state, enforcing bridge-only persistence per ADR-0001.
- **Actor fabric** underpins all coordination and mailbox routing inside K1, ensuring deterministic hand-offs to concierge actors per ADR-0002.
- **Five-layer module map** pins ingress logic to Layer 1 (streams, operators, intent router) and blocks cross-layer leakage into concierge execution per ADR-0004.
- **Performance envelope** budgets TTFT and ingress processing inside the <150ms/<50ms guardrails, with backpressure cascades tied to these ceilings per ADR-0024 and ADR-0061.

## Step 1 - Client Channel Initiation

- Web and mobile clients upgrade to WebSocket (RFC 6455) for full-duplex streaming; handshake negotiates FlatBuffers framing and compression per ADR-0040 and ADR-0015.
- Turn boundary and coalescing rules prevent premature concierge activation, blending implicit pause and explicit submit cues per ADR-0054 and ADR-0053.
- UX affordances (typing indicators, progressive rendering) maintain conversational responsiveness within Layer 1 budgets per ADR-0065.

## Step 2 - API Gateway & Security Envelope

- Gateway validates bearer tokens using RS256 JWT, extracting roles, privacy_band, and space_id to seed downstream auth context per ADR-0037.
- Capability tokens are minted/attenuated before ingress threads can enqueue work, preventing ambient authority as described in ADR-0010.
- Privacy bands, PII detectors, and RED-band encryption gates sit inline so regulated payloads are quarantined or wrapped before K1 intake per ADR-0032, ADR-0035, and ADR-0036.

## Step 3 - Layer 1 Ingress Middleware

- Stream switch normalizes modality (text, voice, sensor) and fans into intent router/operators, following the Layer 1 responsibilities catalogued in ADR-0004 and voice ingress specifics in ADR-0056/ADR-0057.
- Intent router applies the three-stage classification stack (rules -> SLM -> LLM) while honoring the TTFT slice and fast-lane heuristics per ADR-0006 and ADR-0024.
- SessionState bootstrap captures metadata (channel, privacy band, locale) before orchestration, safeguarding working memory policy fences per ADR-0017.

## Step 4 - Concierge Admission

- Negotiation flow advertises the user turn into the contract-net bus, letting concierge bid alongside specialist agents per ADR-0006 and ADR-0008.
- Mailbox admission control and weighted fair scheduling keep inbound load within green watermarks; overflow routes to DLQ with trace identifiers per ADR-0039b and ADR-0061.
- Concierge actor inherits the authenticated capability envelope and SessionState snapshot, enabling prompt construction without breaching bridge-only persistence guarantees from ADR-0001c and ADR-0001d.

## Step 5 - Concierge Meta-Intent Triage & Routing

- ConciergeAgent executes the always-on Tier 1 workflow from ADR-0093, decoding the incoming `concierge_message.fbs` envelope and classifying it against the 11 meta-intents enumerated in `whiteboard_chatexp.md` via `meta_intent.fbs`.
- ACKNOWLEDGMENT, STATUS_CHECK, SMALL_TALK, and other non-task meta-intents are resolved locally; concierge writes direct responses while updating `SessionState.scoreboard` and `SessionState.meta` through the FlatBuffers schema defined in `k1/contracts/flatbuffers/session_state.fbs` (ADR-0017, ADR-0019).
- For CANCELLATION, RETRY, AMENDMENT, and REFINEMENT patterns, concierge issues contract-net control messages (`k1/contracts/flatbuffers/layer2_orchestration/task_envelope.fbs`) to orchestrator components so wave execution can pause, compensate, or resume per ADR-0006f and ADR-0008.
- Task-bearing turns produce enriched `task_envelope.fbs` payloads that include privacy bands, capability tokens, and SessionState deltas; concierge appends these to the internal event bus so downstream planners inherit the authenticated context without rehydration (ADR-0010, ADR-0001d).
- Rapid corrections and batch bursts reuse the timeline heuristics from `whiteboard_chatexp.md`: concierge merges superseding messages, annotates the prior turn as superseded in `SessionState.scoreboard`, and forwards the consolidated task only after the debounce window closes, keeping adr-0053 turn-coalescing guarantees intact.

## Step 6 - Planner Pipeline & Flow Drafting

- Concierge packages the clarified intent, active constraints, and SessionState beliefs into a planning request on the internal event bus, triggering the four-stage planner pipeline defined in ADR-0007.
- Stage 1 (Sketch) invokes the Planner AI agent through Model Hub, using the prompt templates catalogued in `whiteboard_chatexp.md` to produce a structured FlowDef skeleton within the 500ms budget.
- Stage 2 (Expand) enriches each step with concrete tool schemas, capability tokens, and privacy bands from the registry without additional LLM calls, keeping deterministic latency under 1ms per ADR-0007.
- Stage 3 (Validate) runs dual-tier checks: rule-based guards for structure, budgets, and dependencies, followed by Safety Watch escalation for AMBER/RED bands, enforcing capability boundaries from ADR-0010 and the safety rails captured in the whiteboard notes.
- Stage 4 (Commit) signs the validated plan, emits a planner-commit event to the orchestrator, and persists the plan snapshot for audit via K0 bridge contracts, preserving TTFT headroom by completing within the <10ms goal.

## Step 7 - DAG Execution & Tool Waves

- Orchestrator receives the committed FlowDef and rebuilds it into a dependency graph, assigning wave identifiers through the parallel DAG engine described in ADR-0006c.
- Contract Net scoring selects the execution roster per wave, balancing capability fit, predicted latency, and cost as outlined in ADR-0006; specialist agents or pure actors obtain leases before entering execution.
- The execution phase runs each wave with bounded parallelism (max three concurrent calls), using asyncio barriers to ensure dependent steps respect data hazards while benefiting from parallel speedups.
- Intermediate outputs return to the orchestrator, which performs variable substitution before unlocking downstream steps, routing tool invocations through the batching policies of ADR-0078 when multiple writers queue.
- Failures trigger saga compensations or step retries based on the plan metadata, keeping the flow resilient without violating the 2s end-to-end budget noted in ADR-0024 and whiteboard_chatexp.md.

## Step 8 - SessionState Stewardship & Working Memory Access

- Throughout planning and execution, actors read and mutate the six SessionState sections defined in ADR-0017: beliefs capture refreshed facts, scoreboard tracks shared references, control manages active leases, persona reinforces tone, multimodal holds transient media buffers, and meta records telemetry.
- Reads are snapshot-based to avoid race conditions, while writes rely on delta serialization (ADR-0019) so only changed sections flow through the bridge, keeping the 64KB soft limit intact.
- Concierge and Planner consult beliefs and scoreboard to ground responses; orchestrator updates control as waves progress; tool results land in beliefs or multimodal before writers queue persistence intents.
- Critical state deltas persist asynchronously to K0 via P02 MemoryWrite, but the working copy stays resident in K1 for sub-millisecond access, matching the working-memory behavior described in whiteboard_chatexp.md.
- Eviction policies from ADR-0018 ensure long-running sessions shed meta or stale belief entries first, maintaining stable latency while preserving the conversational through-line for subsequent turns.

## Step 9 - MemoryWriter Agents & K0 Bridge Persistence

- MemoryWriterAgent runs as a Tier 3 background actor (whiteboard_chatexp.md) that attaches to the SessionState delta bus once orchestrator waves finish emitting tool results; it pulls the structured deltas produced in Step 8 and stamps writer-specific metadata (partial vs enriched, trigger candidates, agent roster) before handing them to the bridge pipeline.
- `k1/l5_infrastructure/bridge_k0/state_delta_emitter.py` computes field-level diffs (`StateDelta`, `DeltaOperation`) against the snapshot, tags each delta with the originating SessionState section, privacy band, and `cognitive_trace_id`, and feeds them into a bounded channel aligned with ADR-0019 and ADR-0001a so only minimal payloads cross the kernel boundary.
- The emitter forwards deltas to `k1/l5_infrastructure/bridge_k0/batch_client.py`, where `SessionStateDelta` batches follow ADR-0022: 250 ms flush window, 64 KB size guard, and 100-delta count trigger. The batch layer also encodes lane preference via `Priority` (from `command_client.py`) to respect the Fast vs Smart routing policy captured in ADR-0049.
- Lane decisions determine whether the batch takes the low-latency Fast lane (green privacy, user-visible responses) or the Smart lane (amber/red payloads needing additional policy checks). This policy lives alongside bridge configuration and keeps MemoryWriter traffic within privacy and latency budgets before the payload ever touches K0.
- Batches are serialized through `k1/l5_infrastructure/bridge_k0/command_client.py` as `CommandType.MEMORY_WRITE` calls over HTTP/2 (Port P02) with dual-format negotiation (JSON primary, FlatBuffers secondary) per ADR-0001a; receipts are awaited synchronously within the batching SLA and surfaced to the MemoryWriter actor so enrichment or retries follow the two-phase contract described in whiteboard_chatexp.md.
- Once K0 acknowledges the write, the MemoryWriter records the receipt and any saga hooks using `k1/l5_infrastructure/bridge_k0/wal_writer.py`, ensuring orchestration logs and compensations (ADR-0008/0008c) remain reversible. Downstream triggers (P06 Learning, P19 Personalization, P03 Consolidation) fire only after receipt confirmation, keeping the writer aligned with K0’s durability guarantees.
- Abort paths from orchestrator (e.g., user cancel, replan) raise signals on the same channel: MemoryWriter checks these before enrichment, drops in-flight batches if necessary, and logs an abort outcome instead of persisting (whiteboard_chatexp.md, ADR-0008), preventing stale or superseded state from leaking into K0.

## Step 10 - Fast/Smart Lane Router & Bridge Dispatch

- The bridge invokes the Fast/Smart Lane router defined in ADR-0049 before any command leaves the batching queue. The router’s four-factor score (`privacy_weight + obligation_weight + payload_weight + time_budget_weight`) produces a deterministic decision with GREEN deltas under 40 points flowing to the Fast lane while obligation-heavy or AMBER/RED payloads route to the Smart lane.
- Watermark-aware gating keeps Fast lane occupancy below the 70 % threshold; if the Fast queue is saturated or the score breaches policy, the router flips to Smart lane and annotates the envelope with the score breakdown for audit. This behaviour is captured in `architecture_diagrams/k0/project_architecture_part1.mmd`, where the `K0_BRIDGE` subgraph fans into parallel Fast (solid green) and Smart (dashed amber) dispatch paths.
- Each dispatched batch carries structured metadata (`lane_decision`, `watermark_snapshot`, `obligation_flags`) so `command_client.py` can emit RED metrics (ADR-0029) and the receipt validator can detect misroutes. Backpressure feedback from ADR-0039 integrates here, throttling MemoryWriter when Smart lane occupancy nears Hippocampus saturation.

## Step 11 - K0 Kernel Policy Gate, Hippocampus Pipelines, and Intent Router Feedback

- Fast-lane envelopes land in the low-latency dispatch queue while Smart-lane envelopes traverse an additional pre-processor that coalesces obligations before handing the payload to the K0 Command Port. In both paths the Policy Enforcement Module (K0 README, `k0/contracts/policy/bridge_policy.yml`) evaluates privacy bands, executes obligations (audit receipts, GDPR log), and only then commits the envelope to the WAL (`CommandType.MEMORY_WRITE`).
- WAL commit fans into P02 MemoryWrite inside the kernel, where `K0::st_sqlite[episodic_memories]` persists the raw payload and the hippocampal enrichment stage materializes semantic indices through `K0::st_sqlite[semantic_memories]` and `K0::st_vector`. `architecture_diagrams/k0/project_architecture_part2.mmd` details how the Hippocampus subgraph (Dentate → CA3 → CA1) collaborates with P06 Learning and P19 Personalization to score salience, schedule consolidation, and prime prospective triggers once the WAL receipt is durable.
- Completion events ride the kernel bus to the SSE Port, which is the only outward-facing channel (whiteboard_chatexp.md §§5238-5448). `k1/l5_infrastructure/bridge_k0/ports` SSE clients pull these notifications back into Layer 1, where the intent router subscribes to `memory.write.ack` and `prospective.*` topics via the event bus so future turns arrive pre-hydrated with relevant recall hints and planner constraints without violating ADR-0004’s layer boundaries.
- Hippocampus side effects (e.g., consolidation scheduling, alert flags) surface through the same SSE stream, giving Concierge meta-intent handlers and the SessionState steward real-time insight into long-term storage outcomes while respecting bridge-only persistence rules.

## Step 12 - P02 MemoryWrite Assimilation and Cross-Port Fan-Out

- Once the WAL frame is durable, the command dispatcher unwraps the `MEMORY_WRITE` envelope and feeds P02’s ingestion pipeline; Stage 1 validates schema versions, deduplicates recent submissions via the episodic WAL index, and applies capability-driven redaction before the payload is released to kernel storage (ADR-0001a, ADR-0022).
- Stage 2 persists the packet into `K0::st_sqlite[episodic_memories]` and materializes semantic projections into `K0::st_sqlite[semantic_memories]` plus `K0::st_vector`, indexing the record by `cognitive_trace_id`, privacy band, and agent roster so consolidation and replay queries remain sub-5 ms (architecture_diagrams/k0/project_architecture_part2.mmd, ADR-0022).
- Stage 3 publishes fan-out messages onto the kernel bus: Learning (P06) receives salience-scored updates, Personalization (P19) gets affect-annotated deltas, and Consolidation (P03) queues background compaction or decay jobs. These cross-port emissions reference the same receipt token, keeping saga compensation consistent with ADR-0008 and the P-port obligations table in whiteboard_architecture.md.
- Finalization emits post-commit hooks toward the SSE Port and the Intent Router feedback topic; acknowledgements include the storage addresses (`K0::st_sqlite[episodic_memories]`, `K0::st_sqlite[semantic_memories]`, `K0::st_vector`) and consolidation schedule, allowing K1 MemoryWriter actors to reconcile state and planner caches to prefetch future turns without breaching bridge-only persistence guarantees (ADR-0004, ADR-0029).

## Conversational Memory Loop (Text Visualization)

```text
                ┌─────────────────────┐
                │      K0 SSE Port    │
                └──────────▲──────────┘
                           │
          SSE recall • prospective triggers • receipts
                            │
                ┌──────────┴──────────┐
                │ K0 Query / Recall   │
                │  (P01 API Surface)  │
                └──────────▲──────────┘
                           │
                ┌──────────┴──────────┐
                │   Concierge Agent   │
                │ (Tier 1 Coordinator)│
                └──────────▲──────────┘
                           │
              conversational│turns + planner directives
                           │
┌───────────────┐      ┌────┴───────────────┐      ┌─────────────────────┐
│   User        │ ⇄⇄⇄ │ SessionState Hub   │ ⇄⇄⇄ │ Planner & Specialists│
│  Channel      │      │ beliefs • persona │      │ (Model Hub + Tools) │
└──────▲────────┘      │ scoreboard • meta │      └──────────▲──────────┘
       │               └───────▲────────────┘                 │
       │                      │                               │
       │   transcripts • deltas│ for persistence              │
       │                      │                               │
       │               ┌───────┴────────────┐                 │
       └──────────────►│ MemoryWriter +     │◄────────────────┘
                       │ K0 Bridge Clients  │
                       └───────▲────────────┘
                               │
                 batched write │ envelopes to Port P02
                               │
                ┌──────────────┴────────────┐
                │   K0 Port P02 & Storage   │
                │   K0::st_sqlite[episodic] │
                │   K0::st_sqlite[semantic] │
                └──────────────▲────────────┘
                               │
                 enriched snapshots • triggers
                               │
                               └───────(loop to SSE + Query APIs)───┘
## Chat Turn Timeline (User → Concierge → Orchestrator)

- **T0 (Ingress Socket)**: Client WebSocket upgrades complete with FlatBuffers framing negotiated via `k0/contracts/asyncapi.events.yaml` and compression hints from ADR-0040; ingress gateway stamps RS256 JWT claims and capability attenuations per ADR-0037 and ADR-0010.
- **T0+15ms (Layer 1 Intake)**: Intent router normalizes modality streams, tags locale/privacy_band inside `session_state.fbs`, and emits the canonical `concierge_message.fbs` packet towards the concierge mailbox (ADR-0004, ADR-0017).
- **T0+35ms (Concierge Classification)**: ConciergeAgent evaluates meta-intent using `meta_intent.fbs`; direct-resolve cases short-circuit with SessionState updates, while task intents are wrapped in `task_envelope.fbs` and annotated with cognitive_trace_id before entering contract-net negotiation (ADR-0093, ADR-0006a).
- **T0+55ms (Negotiation Broadcast)**: Orchestrator Negotiator advertises the task to active agents using the `negotiation.fbs` envelope and collects `proposal.fbs` bids; concierge, planner, and specialists submit proposals encoded by the same contract set per ADR-0006 and ADR-0006b.
- **T0+90ms (Selection & Agent Staffing)**: Weighted scoring from ADR-0006f selects the execution roster; if capabilities are missing, the AgentFactory spins up new workers using `agent_factory.fbs` and `agent_template.fbs` in accordance with ADR-0086 before execution begins.
- **T0+140ms (Planning Pipeline)**: Planner consumes the `task_envelope.fbs`, runs the Stage 1-4 sequence over `sketch_plan.fbs`, `expanded_plan.fbs`, `validated_plan.fbs`, and `committed_plan.fbs`, then commits the FlowDef to the orchestrator and WAL contracts (`planning_pipeline.fbs`, ADR-0007).
- **T0+220ms (Wave Launch)**: Orchestrator rebuilds the DAG through ADR-0006c, issuing per-wave execution orders via the `selection.fbs` directives and associated MCP messages; parallel steps respect the `max_concurrency` guard while dynamic retries and compensations follow ADR-0006d/ADR-0008.
- **T0+600ms (Tool & Model Returns)**: Specialist agents stream outputs via `model_response.fbs` or tool result contracts; orchestrator stitches intermediate data, updates SessionState deltas, and triggers MemoryWrite (P02) events across the bridge (ADR-0019, ADR-0001c).
- **T0+900ms (Response Assembly)**: Concierge collates orchestrator results, maps them onto conversational templates from `whiteboard_chatexp.md`, refreshes SessionState beliefs/persona, and emits the response turn to the streaming adapter while logging the end-to-end span (ADR-0093, ADR-0029).
- **T0+1001ms (MemoryWriter Persistence Loop)**: MemoryWriterAgent runs Phase 2 enrichment, classifies the delta batch (Fast vs Smart lane), and ships it through `state_delta_emitter.py` → `batch_client.py` → `command_client.py` as a `MEMORY_WRITE`; on receipt, `wal_writer.py` stores the acknowledgement and schedules downstream triggers (P06, P19, P03) per the whiteboard timeline and ADR-0022.
- **T0+1015ms (Lane Router Decision)**: ADR-0049 scoring executes inside the bridge; Fast-lane packets queue for immediate dispatch while Smart-lane packets aggregate obligations and attach audit context before kernel hand-off.
- **T0+1035ms (K0 Policy Gate & WAL Commit)**: The Policy Enforcement Module validates privacy bands, applies obligations, and commits the envelope to the WAL; P02 raw write persists the episodic frame and notifies Hippocampus orchestrators (whiteboard_architecture.md, Table 7).
- **T0+1075ms (Hippocampus & Pipeline Fan-Out)**: CA3 and CA1 components (see `architecture_diagrams/k0/project_architecture_part2.mmd`) run enrichment, update salience, and schedule consolidation/Learning triggers (P06/P19) once the receipt is durable.
- **T0+1100ms (SSE Feedback & Intent Router Priming)**: K0 SSE Port emits `memory.write.ack` and prospective events; bridge SSE clients relay them into Layer 1 where the intent router updates its feature cache and concierge meta-intent modules gain awareness of new long-term state.

## Infrastructure Anchors

- Circuit breaker and retry envelopes guard upstream dependencies (auth, capability registry) so concierge admission never stalls on repeated handshake faults per ADR-0009 and ADR-0022.
- Observability staples (cognitive_trace_id propagation, RED metrics) ensure every ingress hop is traceable from client socket to concierge inbox per ADR-0029 and ADR-0030.
- Thermal and QoS schedulers adjust ingress concurrency when device budgets tighten, deferring non-critical turns while keeping concierge latency inside SLOs per ADR-0026 and ADR-0024d.
