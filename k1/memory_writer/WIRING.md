# K1 Memory Writer — WIRING

---

## 1. Construction entry point

All construction goes through one of two factory methods:

### `MemoryWriterFactory.create()` (`factory.py`)

```
Inputs:
  bridge_port:  IBridgeCommandPort   # required
  event_port:   IEventSubscriptionPort  # required
  hub_port:     IModelHubPort        # required
  session_port: ISessionReadPort     # required
  health_port:  IHealthPort          # required
  config:       MWConfig             # optional; defaults to MWConfig()
```

Returns: `MemoryWriterService` (not yet started — call `service.start()` separately)

### `MemoryWriterFabricRegistration.create_for_session()` (`fabric_registration.py`)

Higher-level wrapper used by the kernel session setup (S-step). Creates the health adapter
internally, calls `MemoryWriterFactory.create()`, starts the service, and returns it ready.

```
Inputs:
  bridge_port:  IBridgeCommandPort
  event_port:   IEventSubscriptionPort
  hub_port:     IModelHubPort
  session_port: ISessionReadPort
  config:       MWConfig  # optional
```

Steps:
1. `CircuitBreaker(threshold, probe)` — internal health state
2. `HealthAdapter(cb, is_ready_fn, last_ms_fn)` — wraps the CB and two lambda probes
3. `MemoryWriterFactory.create(bridge, event, hub, session, health, config)`
4. `await service.start()` — subscribes to bus topic
5. Returns running `MemoryWriterService`

Teardown: `await MemoryWriterFabricRegistration.teardown_session(service)` → `await service.stop()`

---

## 2. `MemoryWriterFactory.create()` construction graph

Ordered dependency build — each node depends only on nodes above it.

```
config: MWConfig
  │
  ├── Stage 1: Filter
  │     RelevanceFilter(config)
  │       └── DedupRingBuffer(window=config.filter_dedup_window_seconds)
  │
  ├── Stage 2: SS Reading + Context
  │     PlaceResolver([])                  ← empty entities at construction (populated per-turn from SS)
  │     MWSessionReader(session_port, config)
  │     ContextBuilder(config)
  │
  ├── Stage 3: Extraction
  │     PersonResolver()                   ← stateless; no deps
  │     PromptLoader(prompts_dir)          ← lazy cache; loads memory_writer_persona.md on first call
  │     MemoryWriterAgent(hub_port, config, prompt_loader)
  │     ExtractionValidator(person_resolver, config)
  │     CircuitBreaker(
  │         failure_threshold=config.circuit_breaker_failure_threshold,
  │         recovery_probe_seconds=config.circuit_breaker_recovery_probe_seconds
  │     )
  │
  ├── Stage 4: Envelope + Privacy
  │     FieldMapper(place_resolver, config)
  │     EnvelopeBuilder(field_mapper)
  │     PrivacyEnforcer()                  ← stateless
  │
  ├── Stage 5: Batch
  │     DeltaAggregator(config)
  │     BatchEmitter(bridge_port)
  │
  └── MemoryWriterPipeline(
          relevance_filter,
          session_reader,
          context_builder,
          writer_agent,
          extraction_validator,
          circuit_breaker,
          envelope_builder,
          privacy_enforcer,
          delta_aggregator,
          batch_emitter,
          event_port,        ← for _publish_safe() observability topics
          config
      )

  if config.extraction_mode == "per_turn":
      dispatcher = TurnDispatcher(pipeline, event_port)
  else:  # "session_batch" (default)
      dispatcher = SessionBatchDispatcher(
          pipeline, event_port,
          flush_turn_threshold=config.flush_turn_threshold,  # default 20
          flush_idle_seconds=config.flush_idle_seconds        # default 300
      )

  return MemoryWriterService(pipeline, dispatcher, circuit_breaker, health_port, config)
```

---

## 3. Adapter construction and what they wrap

| Adapter | Constructor | Wraps |
|---|---|---|
| `BridgeCommandAdapter(kernel_cmd_port)` | `bridge_command_adapter.py` | Bridge `KernelCommandPort` via local `_IKernelCommandPort` structural Protocol (no direct import of Bridge) |
| `EventSubscriptionAdapter(fabric_bus)` | `event_subscription_adapter.py` | `FabricBusAdapter` from `k1.bus.adapters.fabric_adapter`; wraps async MW handlers using `loop.create_task()` |
| `ModelHubAdapter(hub_port)` | `model_hub_adapter.py` | `k1.model_hub.ports.hub_port.IModelHubPort`; translates `chat()` to `HubRequest(CHAT, ChatPayload, Priority.BACKGROUND)` |
| `SessionReadAdapter(ssm, cold_archive=None)` | `session_read_adapter.py` | `SessionStateManager.get_section()` + optional `LocalColdArchive` for `read_archived_history()` |
| `HealthAdapter(cb, is_ready_fn, last_ms_fn)` | `health_adapter.py` | `CircuitBreaker` instance + two callable probes (no external system) |

**Structural typing note:** `BridgeCommandAdapter` and `EventSubscriptionAdapter` use local
Protocol classes (`_IKernelCommandPort`, `_IFabricBus`) rather than importing the real Bridge/Bus
types. This means any object with the right methods is accepted — no hard import cycle.

---

## 4. Dispatcher subscription lifecycle

### `TurnDispatcher.start()`

1. `await event_port.subscribe("k1.session.turn.completed.v1", self._on_turn_complete)`
2. Stores `Subscription(subscription_id, topic)` as `self._subscription`

### `TurnDispatcher.stop()`

1. `await event_port.unsubscribe(self._subscription.subscription_id)`
2. Clears `self._subscription = None`

### `SessionBatchDispatcher.start()`

1. `await event_port.subscribe("k1.session.turn.completed.v1", self._on_turn_completed)`
2. Stores subscription handle
3. Launches `asyncio.create_task(self._idle_loop())` as `self._idle_task`

### `SessionBatchDispatcher.stop()`

1. Sets `_stopping = True`
2. `self._idle_task.cancel()` + `await` (ignores `CancelledError`)
3. `await event_port.unsubscribe(...)` — stops future turn events
4. `await self._flush_buffer(reason="session_end")` — submits any buffered turns
5. `await self._pipeline.flush_pending()` — drains any leftover aggregator envelopes

---

## 5. `MemoryWriterService.start()` / `stop()`

### `start()`

1. Asserts `not _started`
2. `await self._dispatcher.start()` — subscribes to bus, launches idle task (SBD only)
3. Sets `_started = True`

### `stop()`

1. Asserts `_started`
2. `await self._dispatcher.stop()` — flushes buffer, unsubscribes, cancels idle task
3. Sets `_started = False`

No teardown of pipeline internals (no DB to close, no threads to join).

---

## 6. Internal call graph per bus event

### `TurnDispatcher` path (`per_turn` mode)

```text
bus event: k1.session.turn.completed.v1
    ↓
TurnDispatcher._on_turn_complete(raw_payload: dict)
    ↓ deserialize to TurnCompletePayload
    ↓ dedup check (_processed_ids)
    ↓ if _processing: queue (newest wins, max depth 2)
       else: asyncio.create_task(_process_turn(payload))
           ↓
           MemoryWriterPipeline.process(payload)
               ↓ Stage 1: RelevanceFilter.evaluate()
               ↓ Stage 2: MWSessionReader.read_snapshot()
               ↓ Stage 3a: ContextBuilder.build()
               ↓ Stage 3b: MemoryWriterAgent.extract()
               ↓ Stage 4: ExtractionValidator.validate()
               ↓ Stage 5: EnvelopeBuilder.build() + PrivacyEnforcer.enforce()
               ↓ Stage 6: DeltaAggregator.add()
               ↓ Stage 7: BatchEmitter.emit(aggregator.flush())
               ↓ _publish_safe(k1.mw.batch.submitted.v1)
               ↓ returns PipelineResult
```

### `SessionBatchDispatcher` path (`session_batch` mode, default)

```text
bus event: k1.session.turn.completed.v1
    ↓
SessionBatchDispatcher._on_turn_completed(raw_payload: dict)
    ↓ acquire asyncio.Lock
    ↓ dedup check (_processed_ids)
    ↓ append to _buffer; update _last_arrival_ts
    ↓ release Lock
    ↓ if len(_buffer) >= flush_turn_threshold:
           asyncio.create_task(_flush_buffer())

parallel idle loop (asyncio.Task):
    every max(1, idle_seconds/4) seconds:
        if time.time() - _last_arrival_ts >= flush_idle_seconds:
            asyncio.create_task(_flush_buffer())

on stop() or explicit flush:
    _flush_buffer()
        ↓ acquire Lock; drain _buffer
        ↓ release Lock
        ↓ MemoryWriterPipeline.process_session(turns)
            ↓ Stage 2: MWSessionReader.read_snapshot_enriched(session_id, history_limit=50)
            ↓ Stage 3b: MemoryWriterAgent.extract_session(turns, context, trace_id)
               (one LLM call over full transcript, budget = llm_token_budget_session=4000)
            ↓ Stages 4–7: identical to per_turn path
```

---

## 7. Observability topic emission graph

These are emitted from within `MemoryWriterPipeline` via `_publish_safe()`:

```text
After Stage 1 (always):
    event_port.publish("k1.mw.filter.decision.v1", FilterDecisionEvent)

After Stage 3b LLM call (if stage reached):
    event_port.publish("k1.mw.extraction.complete.v1", ExtractionCompleteEvent)

After Stage 7 BatchEmitter.emit (if stage reached):
    event_port.publish("k1.mw.batch.submitted.v1", BatchSubmittedEvent)

On any exception in Stages 1–7:
    event_port.publish("k1.mw.pipeline.error.v1", PipelineErrorEvent)

When CircuitBreaker transitions CLOSED→OPEN:
    event_port.publish("k1.mw.circuit.open.v1", CircuitOpenEvent)
```

All calls wrapped in `try/except Exception: pass` — telemetry failures never surface.

---

## 8. Dependency graph (simplified)

```text
MemoryWriterService
    ├── MemoryWriterPipeline
    │       ├── RelevanceFilter         ← config only
    │       ├── MWSessionReader         ← ISessionReadPort
    │       ├── ContextBuilder          ← config only
    │       ├── MemoryWriterAgent       ← IModelHubPort, MWConfig, PromptLoader
    │       ├── ExtractionValidator     ← PersonResolver, MWConfig
    │       ├── CircuitBreaker          ← config only
    │       ├── EnvelopeBuilder         ← FieldMapper → PlaceResolver
    │       ├── PrivacyEnforcer         ← stateless
    │       ├── DeltaAggregator         ← config only
    │       ├── BatchEmitter            ← IBridgeCommandPort
    │       └── IEventSubscriptionPort  ← for _publish_safe
    │
    ├── TurnDispatcher | SessionBatchDispatcher
    │       ├── MemoryWriterPipeline    ← above
    │       └── IEventSubscriptionPort
    │
    ├── CircuitBreaker                  ← shared with pipeline (same instance)
    ├── IHealthPort                     ← from factory caller
    └── MWConfig
```

**Shared instance:** `CircuitBreaker` is created once in `MemoryWriterFactory.create()` and
passed to both `MemoryWriterPipeline` (Stage 3 gate) and `MemoryWriterService` (exposed via
`service.circuit_breaker` property). If `HealthAdapter` is constructed via
`MemoryWriterFabricRegistration`, it wraps the SAME `CircuitBreaker` instance.

---

## 9. K1 inter-component dependencies

| Dependency | Import path | Used by |
| --- | --- | --- |
| `k1.model_hub.ports.hub_port.IModelHubPort` | `ModelHubAdapter` constructor | `MemoryWriterAgent` via port |
| `k1.model_hub.types` (HubRequest, ChatPayload, Priority) | `model_hub_adapter.py` | Translates `chat()` call |
| `k1.sessionstate.manager.SessionStateManager` | `SessionReadAdapter` constructor | `MWSessionReader` via port |
| `k1.sessionstate.sizetracker.ALL_SECTIONS` | Lazy import in `SessionReadAdapter.list_sections()` | Dynamic section discovery |
| `k1.bus.adapters.fabric_adapter.FabricBusAdapter` | `EventSubscriptionAdapter` constructor | All bus sub/pub |
| `bridge.kernel.command_port` (via structural Protocol) | `BridgeCommandAdapter` constructor | `BatchEmitter` via port |
| `k1.sessionstate.cold_archive.LocalColdArchive` | Optional in `SessionReadAdapter` | `read_archived_history()` |

MW does NOT import from: `k1.orchestrator`, `k1.concierge`, `k1.planner`, `k1.fabric`.
