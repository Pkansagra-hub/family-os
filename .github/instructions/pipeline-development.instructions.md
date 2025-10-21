# Pipeline Development Instructions

## Purpose

Provide guardrails for creating or modifying memory pipelines (P01–P20) so they remain contract-driven, event-hub aligned, and focused on the Memory Module’s lifecycle.

## Pipeline Taxonomy

- **P01–P04 (Intake & Advisory)**: ingestion, classification, advisory responses.
- **P05–P08 (Contextualization)**: working memory fusion, personalization, QoS shaping.
- **P09–P12 (Execution & Sync)**: task execution, sync orchestration, device coordination.
- **P13–P16 (Analytics & Governance)**: metrics, rollups, feature flags, QoS.
- **P17–P20 (Safety & Habits)**: safety enforcement, abuse mitigation, personalization, procedures/habits.

Core infrastructure lives in `pipelines/memory_bus.py`, `pipelines/memory_registry.py`, `pipelines/memory_stages.py`, and per-stage modules `pipelines/memory_pXX.py`.

## Development Workflow

1. **Clarify intent**
   - Document the stage objective, upstream event, downstream consumer, and success metrics.
   - Validate the need for a new stage vs. extending an existing PXX module.
2. **Contract-first design**
   - Update or create contracts in `contracts/pipelines/` (events, schemas, storage manifests).
   - Provide concrete examples and acceptance criteria before implementation.
3. **Trace dependencies**
   - Use KG (`kg_paths`, `kg_neighbors`) to see how the stage connects to producers/consumers.
   - Confirm event hub wiring with `event-hub.instructions.md` and diagrams.
4. **Implement stage logic**
   - Add/extend `pipelines/memory_pXX.py` with pure functions or classes respecting side-effect boundaries.
   - Register the stage in `pipelines/memory_registry.py` and update `pipelines/memory_stages.py` if orchestration changes.
   - Ensure ingestion from `pipelines/memory_bus.py` honors ordering and cognitive trace propagation.
5. **Persistence & memory access**
   - Use stores under `storage/memory/` or `storage/events/` based on retention tier.
   - Preserve device-local assumptions and E2EE constraints; no unmanaged caches.
6. **Policy & safety checks**
   - Route decisions through `storage/governance/`, `storage/security/`, and `storage/policy/` as applicable.
   - Respect QoS budgets, idempotency ledgers, and safety monitors.
7. **Testing**
   - Write WARD integration tests hitting real stores and bus interactions (no mocks or sleeps).
   - Cover success, failure, retry, and idempotency scenarios.
8. **Documentation**
   - Update stage README/doc in `docs/development/storage/` or service-specific README.
   - Log diagram/KG updates when topology changes.

## Stage Addition Checklist

- [ ] Purpose + success metrics captured (ticket/ADR/doc).
- [ ] Contracts & examples merged for new/updated events.
- [ ] Stage module implemented with zero simulation and clean dependencies.
- [ ] Registry/bus wiring updated and reviewed.
- [ ] Policy, QoS, and safety hooks verified.
- [ ] Persistence tier selection documented; schema migrations generated if needed.
- [ ] WARD tests added/passing with real components.
- [ ] Documentation + diagram/KG usage logs updated.

## Tooling Tips

- `mmd_summary`, `diagram.flows` for visual validation of stage placement.
- `kg_search` to find existing nodes related to the stage domain.
- `python -m ward test --path Tests/storage` (narrow path as needed) for pipeline suites.

## Pitfalls to Avoid

- Creating bespoke queues or bypassing the event hub.
- Skipping idempotency, QoS, or backpressure integration.
- Failing to propagate `cognitive_trace_id` and telemetry.
- Moving state outside approved storage tiers.
- Shipping without contract examples or integration tests.
