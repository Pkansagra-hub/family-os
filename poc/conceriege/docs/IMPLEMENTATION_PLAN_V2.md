# 🚀 Concierge PoC: Implementation Plan (End-to-End)

**Version:** 2.0
**Target Duration:** 14 days
**Delivery:** Working CLI chat interface demonstrating reactive-proactive loop

---

## 📋 Executive Summary

**Goal:** Build a working Concierge PoC that demonstrates the reactive-proactive conversation loop with:

- CLI chat interface for live demonstrations
- Real K0 data integration (diet history, GERD episodes)
- LLM-powered intent classification and proactive prompts
- Background specialist agents with progress updates
- Performance metrics tracking (<1500ms P95 latency)

**Non-Goals (Out of Scope):**

- Docker deployment (local Python environment only)
- Web UI (CLI is sufficient for demo)
- Multi-user support (single-user demo)
- Production-grade error handling
- Full K1 integration (standalone PoC)

**Success Criteria:**

- User can type "milk is making me sick" and see reactive-proactive flow
- Specialist completes in 500-1000ms with progress updates
- Proactive prompts feel natural (80%+ perceived naturalness)
- CLI interface is simple and demo-ready

---

## 🏗️ Architecture Overview

### **Directory Structure**

```
poc/conceriege/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseAgent class
│   │   ├── concierge.py               # ConciergeAgent (main orchestrator)
│   │   ├── reactive_handler.py        # ReactiveHandler
│   │   ├── proactive_generator.py     # ProactiveGenerator
│   │   ├── synthesis_engine.py        # SynthesisEngine
│   │   ├── nutritionist.py            # NutritionistAgent
│   │   ├── psychiatrist.py            # PsychiatristAgent (simpler)
│   │   └── planner.py                 # PlannerAgent (PATH 2, minimal)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── envelope.py                # CognitiveEnvelope dataclass
│   │   ├── intent.py                  # Intent dataclass
│   │   ├── conversation_state.py      # ConversationState, Scoreboard
│   │   ├── proactive_prompt.py        # ProactivePrompt
│   │   ├── analysis_result.py         # AnalysisResult, Insight
│   │   └── progress_event.py          # ProgressEvent
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_client.py              # OpenAI/Azure LLM client
│   │   ├── k0_query_service.py        # K0 data access (mock + real)
│   │   ├── conversation_store.py      # In-memory conversation history
│   │   └── metrics_collector.py       # Performance metrics
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── chat.py                    # Main CLI chat interface
│   │   └── display.py                 # Pretty printing (colors, progress)
│   └── config/
│       ├── __init__.py
│       ├── settings.py                # Configuration loading
│       └── llm_config.yaml            # LLM model settings
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # pytest fixtures
│   ├── test_agents/
│   │   ├── test_concierge.py
│   │   ├── test_reactive_handler.py
│   │   ├── test_proactive_generator.py
│   │   └── test_nutritionist.py
│   ├── test_integration/
│   │   ├── test_gerd_flow.py          # Full GERD scenario
│   │   └── test_performance.py        # Latency validation
│   └── fixtures/
│       ├── mock_k0_data.py            # Mock diet/GERD data
│       └── mock_llm_responses.py      # Mock LLM responses
├── requirements.md                     # Phase 1 & 2 specs
├── DESIGN_RATIONALE.md                 # Research foundation + system design
├── envelope_design.md                  # Cognitive envelope spec
├── IMPLEMENTATION_PLAN_V2.md           # This file
└── README.md                           # Quick start guide
```

---

## 📅 Milestone Overview

| Milestone | Duration | Deliverable | Validation |
|-----------|----------|-------------|------------|
| **M1: Foundation** | Days 1-3 | Data models, LLM client, K0 mock service | Unit tests pass, LLM calls work |
| **M2: Reactive Loop** | Days 4-5 | ReactiveHandler with intent classification + empathy | CLI shows reactive responses |
| **M3: Specialist Agents** | Days 6-7 | NutritionistAgent with progress updates | Background tasks complete with milestones |
| **M4: Proactive Loop** | Days 8-9 | ProactiveGenerator with gap identification | CLI shows proactive prompts during wait |
| **M5: Synthesis** | Days 10-11 | SynthesisEngine with contradiction handling | CLI shows final integrated results |
| **M6: CLI Interface** | Day 12 | Full CLI chat with pretty printing | Demo-ready interface |
| **M7: Testing & Polish** | Day 13 | Integration tests, performance validation | All tests pass, P95 <1500ms |
| **M8: Demo Prep** | Day 14 | Real K0 integration, demo scenarios | Ready to show to stakeholders |

---

## 🎯 Milestone 1: Foundation (Days 1-3)

**Goal:** Build foundational data models, services, and configuration infrastructure

### **Epic 1.1: Data Models & Envelopes**

**Objective:** Create all dataclass models for type safety and serialization

#### **Issue 1.1.1: Core Data Models**

**Files to Create:**

- `backend/models/__init__.py`
- `backend/models/intent.py`
- `backend/models/conversation_state.py`
- `backend/models/proactive_prompt.py`
- `backend/models/analysis_result.py`
- `backend/models/progress_event.py`

**Classes to Implement:**

**`Intent` (intent.py):**

- Fields: `type` (QUERY|ACTION), `domain` (health|finance|social), `complexity` (simple|multi_step), `specialist_type`, `confidence`, `entities`, `routing` (PATH1|PATH2)
- Methods: `to_dict()`, `from_dict()`, `is_simple()`, `requires_orchestrator()`

**`ConversationState` (conversation_state.py):**

- Fields: `user_id`, `conversation_id`, `qud` (Question Under Discussion), `scoreboard`, `recent_history` (last 10 turns), `information_gaps`, `proactive_prompts_sent`, `last_proactive_at`
- Methods: `add_turn()`, `add_proactive_prompt()`, `update_qud()`, `update_gaps()`, `get_referents()`, `to_dict()`

**`Scoreboard` (conversation_state.py):**

- Fields: `referents` (dict), `pending_specialists` (list), `completed_tasks` (list)
- Methods: `add_referent()`, `update_salience()`, `get_top_referents()`, `to_dict()`

**`Referent` (conversation_state.py):**

- Fields: `entity`, `first_mentioned`, `salience`, `user_hypothesis`, `sentiment`, `medical_condition`, `contradicted`
- Methods: `decay_salience()`, `to_dict()`

**`ProactivePrompt` (proactive_prompt.py):**

- Fields: `text`, `prompt_type` (fill_gap|future_action|clarify), `information_target`, `sent_at`, `user_responded`, `response_text`
- Methods: `to_dict()`, `mark_responded()`

**`AnalysisResult` (analysis_result.py):**

- Fields: `specialist_type`, `query`, `insights` (list of Insight), `evidence` (list), `confidence`, `duration_ms`, `contradicts_user_hypothesis`, `user_hypothesis`, `actual_finding`
- Methods: `to_dict()`, `get_primary_insight()`, `has_contradiction()`

**`Insight` (analysis_result.py):**

- Fields: `summary`, `evidence` (list), `severity` (strong|moderate|weak), `confidence`
- Methods: `to_dict()`

**`ProgressEvent` (progress_event.py):**

- Fields: `task_id`, `milestone` (1-5), `percent` (0-100), `message`, `timestamp`
- Methods: `to_dict()`, `is_complete()`

**`Turn` (conversation_state.py):**

- Fields: `timestamp`, `user_message`, `agent_response`, `turn_type` (user|reactive|proactive|synthesis)
- Methods: `to_dict()`

**Acceptance Criteria:**

- All dataclasses use `@dataclass` decorator
- All have `to_dict()` methods for JSON serialization
- All have type hints
- Can serialize/deserialize without loss
- Unit tests: `tests/test_models/test_intent.py`, `tests/test_models/test_conversation_state.py`

**Estimated Time:** 1 day

---

#### **Issue 1.1.2: Cognitive Envelope**

**File to Create:**

- `backend/models/envelope.py`

**Classes to Implement:**

**`CognitiveEnvelope` (envelope.py):**

- Fields: All fields from `envelope_design.md` (schema_version, envelope_id, ts, sender, receiver, kind, conversation_id, cognitive_trace_id, actor, policy, intent, conversation, spawn, progress_policy, telemetry, observability, body)
- Methods: `to_dict()`, `to_json()`, `from_dict()`, `validate()`, `_generate_ulid()`

**`EnvelopeFactory` (envelope.py):**

- Static methods:
  - `create_user_utterance()` → Creates user message envelope
  - `create_reactive_response()` → Creates reactive response envelope
  - `create_proactive_prompt()` → Creates proactive prompt envelope
  - `create_spawn_specialist()` → Creates specialist spawn envelope
  - `create_progress_event()` → Creates progress update envelope
  - `create_specialist_result()` → Creates result envelope
  - `create_synthesis_response()` → Creates synthesis envelope

**`EnvelopeValidator` (envelope.py):**

- Method: `validate_envelope(envelope_dict) -> tuple[bool, list[str]]`
- Validates:
  - Required fields present
  - Kind-specific field validation
  - Budget enforcement (latency, cost)
  - Policy constraints (capabilities, bands)

**Acceptance Criteria:**

- Envelope can be created with factory methods
- Validation catches missing required fields
- Validation enforces kind-specific rules
- Can serialize to JSON matching `envelope_design.md` examples
- Unit tests: `tests/test_models/test_envelope.py`

**Estimated Time:** 1 day

---

### **Epic 1.2: LLM Client & Configuration**

**Objective:** Implement LLM client for OpenAI/Azure with caching and error handling

#### **Issue 1.2.1: Configuration System**

**Files to Create:**

- `backend/config/__init__.py`
- `backend/config/settings.py`
- `backend/config/llm_config.yaml`

**Classes to Implement:**

**`Settings` (settings.py):**

- Loads from environment variables and YAML
- Fields: `OPENAI_API_KEY`, `OPENAI_MODEL_FAST`, `OPENAI_MODEL_SYNTHESIS`, `OPENAI_TIMEOUT_MS`, `K0_API_URL`, `MAX_CONVERSATION_HISTORY`, `PROACTIVE_COOLDOWN_SECONDS`, `MIN_BACKGROUND_DURATION_MS`, `LOG_LEVEL`
- Methods: `load_from_env()`, `load_from_yaml()`, `get_llm_config()`

**`llm_config.yaml` structure:**

```yaml
llm_clients:
  fast:
    model: "gpt-4o-mini"
    temperature: 0.0
    max_tokens: 100
    timeout_ms: 50
    use_case: ["intent_classification", "emotion_detection"]
  creative:
    model: "gpt-4o-mini"
    temperature: 0.8
    max_tokens: 50
    timeout_ms: 150
    use_case: ["empathy_generation", "proactive_prompts"]
  synthesis:
    model: "gpt-4o-mini"
    temperature: 0.7
    max_tokens: 100
    timeout_ms: 300
    use_case: ["result_synthesis"]
```

**Acceptance Criteria:**

- Settings loads from `.env` file
- YAML config parses correctly
- Can access settings via `Settings.get_llm_config("fast")`
- Unit tests: `tests/test_config/test_settings.py`

**Estimated Time:** 0.5 days

---

#### **Issue 1.2.2: LLM Client Implementation**

**File to Create:**

- `backend/services/llm_client.py`

**Classes to Implement:**

**`LLMClient` (llm_client.py):**

- Constructor: Takes `Settings`, initializes OpenAI client
- Methods:
  - `generate(prompt, model_profile="fast", **kwargs) -> str` - Main generation method
  - `generate_with_timeout(prompt, timeout_ms) -> str` - With timeout enforcement
  - `_call_openai(prompt, model, temperature, max_tokens) -> str` - Actual API call
  - `_cache_key(prompt, model) -> str` - Generate cache key
  - `_get_cached_response(key) -> Optional[str]` - Check cache
  - `_set_cached_response(key, response, ttl) -> None` - Store in cache
  - `get_metrics() -> dict` - Return call count, latency, cost

**`LLMMetrics` (llm_client.py):**

- Tracks: `total_calls`, `total_tokens`, `total_cost_usd`, `cache_hits`, `cache_misses`, `avg_latency_ms`
- Methods: `record_call()`, `to_dict()`

**Caching Strategy:**

- Use `functools.lru_cache` or `cachetools.TTLCache`
- Cache intent classification (same message → same intent)
- Cache emotion detection
- Cache key: `hash(prompt + model + temperature)`
- TTL: 1 hour (3600 seconds)

**Error Handling:**

- Catch `openai.RateLimitError` → Return cached response or error
- Catch `openai.APIError` → Retry with exponential backoff
- Catch `asyncio.TimeoutError` → Return timeout error

**Acceptance Criteria:**

- Can call OpenAI API successfully
- Caching works (second call is instant)
- Timeout enforcement works
- Metrics tracked correctly
- Integration tests: `tests/test_services/test_llm_client.py`

**Estimated Time:** 1 day

---

### **Epic 1.3: K0 Query Service (Mock + Real)**

**Objective:** Implement generic K0 data access layer simulating 8 memory types with discoverable schema

#### **Issue 1.3.1: Mock K0 Service with Memory Types**

**Files to Create:**

- `backend/services/k0_query_service.py`
- `tests/fixtures/mock_k0_data.py`
- `tests/fixtures/k0_schema.py`

**K0 Memory Architecture (to simulate):**

K0 has 8 memory types, each with multiple tables:

1. **Episodic**: Time-stamped events (diet_logs, health_events, activities, sleep_logs)
2. **Semantic**: General knowledge (food_nutrition, health_conditions, medications, symptoms)
3. **Autobiographical**: Personal history (user_profile, life_events, family_history)
4. **Working**: Recent context (recent_conversations, active_goals, pending_tasks)
5. **Prospective**: Future-oriented (reminders, appointments, planned_activities)
6. **Spatial**: Location data (places_visited, activity_locations, home_zones)
7. **Emotional**: Affective states (mood_logs, stress_events, emotional_triggers)
8. **Procedural**: Skills/habits (routines,習慣_patterns, learned_behaviors)

**Classes to Implement:**

**`K0Schema` (k0_schema.py):**

```python
# Schema definition for K0 memory system
MEMORY_TYPES = {
    "episodic": {
        "tables": ["diet_logs", "health_events", "activities", "sleep_logs"],
        "description": "Time-stamped personal events and experiences"
    },
    "semantic": {
        "tables": ["food_nutrition", "health_conditions", "medications", "symptoms"],
        "description": "General knowledge and facts"
    },
    # ... all 8 memory types
}

TABLE_SCHEMAS = {
    "episodic.diet_logs": {
        "columns": ["id", "timestamp", "food_item", "meal_type", "portion", "location"],
        "filters": ["food_item", "meal_type", "time_range"]
    },
    "episodic.health_events": {
        "columns": ["id", "timestamp", "event_type", "severity", "symptoms", "duration_minutes"],
        "filters": ["event_type", "severity", "time_range"]
    },
    # ... all tables
}
```

**`K0QueryService` (k0_query_service.py):**

- Abstract base class
- Methods (abstract):
  - `query(user_id, table_name, filters={}, time_range="last_30_days", limit=100) -> list[dict]` - Generic query
  - `get_schema(memory_type=None) -> dict` - Return available tables/columns
  - `search_tables(keywords: list[str]) -> list[str]` - Discover relevant tables by keywords
  - `list_memory_types() -> list[str]` - List all 8 memory types

**`MockK0QueryService` (k0_query_service.py):**

- Inherits from `K0QueryService`
- Uses mock data from `mock_k0_data.py` organized by memory type
- Methods:
  - `query(user_id, table_name, filters, time_range, limit)` - Returns filtered mock data
  - `get_schema(memory_type)` - Returns schema for discovery
  - `search_tables(keywords)` - LLM-powered table discovery (e.g., "diet" → ["episodic.diet_logs", "semantic.food_nutrition"])
  - `list_memory_types()` - Returns all 8 types

**Example Specialist Queries:**

```python
# Nutritionist analyzing GERD triggers
diet_data = k0.query("user_123", "episodic.diet_logs",
                     filters={"meal_type": "dinner"},
                     time_range="last_30_days")
gerd_events = k0.query("user_123", "episodic.health_events",
                       filters={"event_type": "GERD"},
                       time_range="last_30_days")
nutrition_info = k0.query("user_123", "semantic.food_nutrition",
                          filters={"food_item": "coffee"})

# Psychiatrist analyzing mood patterns
mood_data = k0.query("user_123", "emotional.mood_logs",
                     time_range="last_30_days")
stress_events = k0.query("user_123", "emotional.stress_events",
                         time_range="last_30_days")
```

**Mock Data Organization (mock_k0_data.py):**

```python
MOCK_DATA = {
    "episodic": {
        "diet_logs": [
            {"id": 1, "timestamp": "2025-11-01T20:00:00", "food_item": "coffee", "meal_type": "dinner", ...},
            # 45 entries over 30 days
        ],
        "health_events": [
            {"id": 1, "timestamp": "2025-11-01T22:00:00", "event_type": "GERD", "severity": "moderate", ...},
            # 5 GERD episodes
        ],
    },
    "semantic": {
        "food_nutrition": [
            {"food_item": "coffee", "caffeine_mg": 95, "acidity": "high", "gerd_risk": "high"},
            # Nutrition database
        ],
    },
    "emotional": {
        "mood_logs": [
            {"timestamp": "2025-11-01T09:00:00", "mood": "anxious", "energy": 3, ...},
            # 30 days of mood entries
        ],
    },
    # ... all 8 memory types with realistic data
}
```

**Schema Discovery Workflow:**

1. Specialist receives task: "Analyze GERD triggers"
2. Specialist queries schema: `k0.search_tables(["diet", "digestive", "health"])`
3. Returns: `["episodic.diet_logs", "episodic.health_events", "semantic.food_nutrition"]`
4. Specialist examines schema: `k0.get_schema("episodic")`
5. Specialist makes targeted queries to each table
6. Specialist correlates results

**Data Patterns (for GERD scenario):**

- **Correlation**: 3/5 GERD episodes occur 1-2 hours after evening coffee (8pm → 10pm)
- **Red herring**: Milk appears 8 times in diet but 0 GERD correlation
- **Cross-memory insight**: semantic.food_nutrition shows coffee has high acidity + caffeine
- **Emotional context**: emotional.stress_events shows stress on 2/5 GERD days (confounding variable)

**Acceptance Criteria:**

- Generic `query()` method works for all tables
- Schema discovery returns accurate table names
- Mock data organized by 8 memory types
- Specialists can discover relevant tables without hardcoding
- Correlation pattern detectable across episodic.diet_logs + episodic.health_events
- Cross-memory queries work (episodic + semantic + emotional)
- Unit tests: `tests/test_services/test_k0_query_service.py`

**Estimated Time:** 1.5 days

---

#### **Issue 1.3.2: Real K0 Integration (Day 14)**

**File to Update:**

- `backend/services/k0_query_service.py`

**Classes to Implement:**

**`RealK0QueryService` (k0_query_service.py):**

- Inherits from `K0QueryService`
- Uses actual K0 REST API
- Methods:
  - `query()` - Calls K0 HTTP endpoints
  - `_make_request(endpoint, params) -> dict` - HTTP request wrapper
  - Error handling for network issues, K0 downtime

**Acceptance Criteria:**

- Can connect to running K0 instance
- Returns real user data
- Graceful degradation if K0 unavailable (fallback to mock)
- Integration tests with real K0 (Day 14 only)

**Estimated Time:** 0.5 days (Day 14)

---

### **Epic 1.4: Conversation Store & Metrics**

**Objective:** In-memory storage for conversation history and performance metrics

#### **Issue 1.4.1: Conversation Store**

**File to Create:**

- `backend/services/conversation_store.py`

**Classes to Implement:**

**`ConversationStore` (conversation_store.py):**

- In-memory dict: `{user_id: ConversationState}`
- Methods:
  - `get_or_create(user_id) -> ConversationState` - Get existing or new conversation
  - `update(user_id, state) -> None` - Update conversation state
  - `add_turn(user_id, turn) -> None` - Add turn to history
  - `get_history(user_id, limit=10) -> list[Turn]` - Get recent turns
  - `clear(user_id) -> None` - Clear conversation (for new demo)

**Acceptance Criteria:**

- Can store and retrieve conversation state
- History limited to last 10 turns (memory management)
- Unit tests: `tests/test_services/test_conversation_store.py`

**Estimated Time:** 0.5 days

---

#### **Issue 1.4.2: Metrics Collector**

**File to Create:**

- `backend/services/metrics_collector.py`

**Classes to Implement:**

**`MetricsCollector` (metrics_collector.py):**

- Tracks performance metrics per conversation turn
- Methods:
  - `record_llm_call(operation, model, latency_ms, tokens, cost_usd)` - Track LLM call
  - `record_specialist_duration(specialist_type, duration_ms)` - Track specialist time
  - `record_turn_latency(total_ms)` - Track end-to-end latency
  - `get_metrics() -> dict` - Get all metrics
  - `get_summary() -> dict` - Get P50/P95/P99 stats
  - `export_prometheus()` - Export to Prometheus format (optional)

**Metrics Tracked:**

- LLM calls: count, total_tokens, total_cost, avg_latency
- Specialist: count, avg_duration, P95_duration
- Turns: count, avg_latency, P95_latency, budget_exceeded_count
- Proactive: prompts_sent, user_responses, response_rate

**Acceptance Criteria:**

- Can record all metric types
- Can calculate P50/P95/P99
- Can export summary report
- Unit tests: `tests/test_services/test_metrics_collector.py`

**Estimated Time:** 0.5 days

---

### **M1 Deliverable: Foundation Complete**

**Validation:**

- [ ] All data models created with type hints
- [ ] Envelope factory creates valid envelopes
- [ ] LLM client makes successful API calls
- [ ] Mock K0 service returns realistic data
- [ ] Conversation store persists state
- [ ] Metrics collector tracks performance
- [ ] All unit tests pass (`pytest tests/`)

**Demo Checkpoint:**

```python
# Can run this script to validate M1:
from backend.models.intent import Intent
from backend.models.envelope import EnvelopeFactory
from backend.services.llm_client import LLMClient
from backend.services.k0_query_service import MockK0QueryService

# Create intent
intent = Intent(type="QUERY", domain="health", complexity="simple")
print(intent.to_dict())

# Create envelope
envelope = EnvelopeFactory.create_reactive_response(...)
print(envelope.to_json())

# Call LLM
llm_client = LLMClient(settings)
response = llm_client.generate("Classify intent: milk is making me sick")
print(response)

# Query K0
k0_service = MockK0QueryService()
diet = k0_service.get_diet_entries("user_123", "last_30_days")
print(f"Found {len(diet)} diet entries")
```

---

## 🎯 Milestone 2: Reactive Loop (Days 4-5)

**Goal:** Implement intent classification and immediate reactive responses

### **Epic 2.1: ReactiveHandler Implementation**

**Objective:** Build the reactive response system (empathy + action declaration)

#### **Issue 2.1.1: Intent Classification**

**File to Create:**

- `backend/agents/reactive_handler.py`

**Classes to Implement:**

**`ReactiveHandler` (reactive_handler.py):**

- Constructor: Takes `llm_client`, `conversation_store`, `metrics_collector`
- Methods:
  - `classify_intent(user_message, context) -> Intent` - Main classification method
  - `_build_intent_prompt(user_message, context) -> str` - Build LLM prompt
  - `_parse_intent_response(llm_response) -> Intent` - Parse JSON response
  - `_determine_routing(intent) -> str` - Decide PATH1 vs PATH2

**Intent Classification Prompt Template:**

```
You are an intent classifier for a health assistant.

Previous conversation:
{recent_history}

Current user message: "{user_message}"

Classify the intent:
- Type: QUERY (data analysis) or ACTION (execute task)
- Domain: health, finance, social, general
- Complexity: simple (one specialist) or multi_step (orchestrator needed)
- Specialist: nutritionist, psychiatrist, finance_analyst, or orchestrator

Output JSON:
{
  "type": "QUERY|ACTION",
  "domain": "health|finance|social|general",
  "complexity": "simple|multi_step",
  "specialist_type": "nutritionist|psychiatrist|...",
  "confidence": 0.0-1.0,
  "entities": ["entity1", "entity2"]
}
```

**Routing Logic:**

- `complexity == "simple"` → PATH 1 (single specialist)
- `complexity == "multi_step"` → PATH 2 (orchestrator)
- Multiple specialists mentioned → PATH 2
- Simple health query → PATH 1 (nutritionist)

**Acceptance Criteria:**

- Can classify GERD query as PATH 1 (nutritionist)
- Can classify complex queries as PATH 2
- Confidence threshold: 0.7 (reject if lower)
- Latency: P95 <30ms (with caching)
- Unit tests: `tests/test_agents/test_reactive_handler.py`

**Estimated Time:** 1 day

---

#### **Issue 2.1.2: Emotion Detection & Empathy**

**File to Update:**

- `backend/agents/reactive_handler.py`

**Classes to Add:**

**`EmotionDetector` (reactive_handler.py):**

- Methods:
  - `detect(user_message) -> dict` - Returns {label, confidence, source}
  - `_rule_based_detect(message) -> Optional[str]` - Fast pattern matching
  - `_llm_detect(message) -> str` - LLM fallback

**Rule-Based Emotion Patterns:**

```python
EMOTION_PATTERNS = {
    "frustrated": ["frustrated", "annoyed", "irritated", "fed up"],
    "concerned": ["worried", "concerned", "nervous", "anxious"],
    "sad": ["sad", "upset", "down", "depressed"],
    "pain": ["pain", "hurt", "ache", "sore", "uncomfortable"],
    "confused": ["confused", "don't understand", "unclear", "lost"],
}
```

**`EmpathyGenerator` (reactive_handler.py):**

- Methods:
  - `generate(user_message, emotion) -> str` - Generate empathy response
  - `_rule_based_empathy(emotion) -> str` - Fast template
  - `_llm_empathy(user_message, emotion) -> str` - LLM fallback

**Rule-Based Empathy Templates:**

```python
EMPATHY_MAP = {
    "frustrated": ["That must be frustrating", "I understand your frustration"],
    "concerned": ["I understand your concern", "That's concerning"],
    "sad": ["That's sad to hear", "I'm sorry to hear that"],
    "pain": ["That sounds painful", "That's tough to deal with"],
}
```

**Acceptance Criteria:**

- Rule-based detection covers 80% of cases
- LLM fallback handles edge cases
- Empathy responses feel natural
- Latency: P95 <20ms (rule-based), <50ms (LLM)
- Unit tests: Emotion detection accuracy, empathy naturalness

**Estimated Time:** 1 day

---

#### **Issue 2.1.3: Reactive Response Generation**

**File to Update:**

- `backend/agents/reactive_handler.py`

**Methods to Add to `ReactiveHandler`:**

- `generate_response(user_message, intent, context) -> str` - Main method
- `_get_action_declaration(intent) -> str` - Get specialist action phrase
- `_format_response(empathy, action) -> str` - Combine into response

**Action Declaration Templates:**

```python
ACTION_TEMPLATES = {
    "nutritionist": "Looping in nutritionist",
    "psychiatrist": "Connecting you with psychiatrist",
    "finance_analyst": "Checking with finance analyst",
    "orchestrator": "Creating a plan for you",
}
```

**Response Format:**

```
{empathy}. {action_declaration}.

Example: "That's sad to hear. Looping in nutritionist."
```

**Acceptance Criteria:**

- Response format: "{empathy}. {action}."
- Natural language (not robotic)
- Latency: P95 <50ms (total for intent + empathy + action)
- Unit tests: Response format validation

**Estimated Time:** 0.5 days

---

### **M2 Deliverable: Reactive Loop Complete**

**Validation:**

- [ ] Intent classification works (PATH 1 vs PATH 2)
- [ ] Emotion detection: 80% rule-based, 20% LLM
- [ ] Empathy generation feels natural
- [ ] Reactive response: "{empathy}. {action}."
- [ ] Latency: P95 <50ms for full reactive flow
- [ ] All unit tests pass

**Demo Checkpoint:**

```python
# Test reactive handler:
reactive_handler = ReactiveHandler(llm_client, conversation_store, metrics)

user_message = "milk is making me sick"
intent = reactive_handler.classify_intent(user_message, context)
print(f"Intent: {intent.type}, Routing: {intent.routing}")

response = reactive_handler.generate_response(user_message, intent, context)
print(f"Response: {response}")
# Expected: "That's sad to hear. Looping in nutritionist."
```

---

## 🎯 Milestone 3: Specialist Agents (Days 6-7)

**Goal:** Implement NutritionistAgent with background processing and progress updates

### **Epic 3.1: Base Agent Infrastructure**

**Objective:** Create BaseAgent class for all specialist agents

#### **Issue 3.1.1: BaseAgent Class**

**File to Create:**

- `backend/agents/base.py`

**Classes to Implement:**

**`BaseAgent` (base.py):**

- Abstract base class for all agents
- Constructor: Takes `agent_id`, `agent_type`, `k0_query_service`, `metrics_collector`
- Methods (abstract):
  - `analyze(query, user_id, context) -> AnalysisResult` - Main analysis method
  - `get_progress_milestones() -> list[dict]` - Return 5 milestone definitions
- Methods (concrete):
  - `emit_progress(task_id, milestone, percent, message)` - Emit progress event
  - `_create_task_id() -> str` - Generate unique task ID
  - `get_capabilities() -> list[str]` - Return agent capabilities

**Progress Milestone Structure:**

```python
MILESTONES = [
    {"milestone": 1, "percent": 20, "message": "📊 Starting analysis..."},
    {"milestone": 2, "percent": 40, "message": "🔍 Processing data..."},
    {"milestone": 3, "percent": 60, "message": "🧠 Finding patterns..."},
    {"milestone": 4, "percent": 80, "message": "💡 Generating insights..."},
    {"milestone": 5, "percent": 100, "message": "✅ Complete"},
]
```

**Acceptance Criteria:**

- BaseAgent is abstract (cannot instantiate directly)
- Progress emission works with asyncio
- Task ID generation is unique
- Unit tests: `tests/test_agents/test_base.py`

**Estimated Time:** 0.5 days

---

### **Epic 3.2: NutritionistAgent Implementation**

**Objective:** Build fully functional nutritionist with K0 integration and correlation analysis

#### **Issue 3.2.1: NutritionistAgent Core**

**File to Create:**

- `backend/agents/nutritionist.py`

**Classes to Implement:**

**`NutritionistAgent` (nutritionist.py):**

- Inherits from `BaseAgent`
- Constructor: Takes `k0_query_service`, `metrics_collector`
- Methods:
  - `analyze(query, user_id, context) -> AnalysisResult` - Main analysis
  - `get_progress_milestones() -> list` - 5 nutrition-specific milestones
  - `_query_diet_history(user_id, time_range) -> list` - Get diet entries
  - `_query_gerd_episodes(user_id, time_range) -> list` - Get GERD events
  - `_correlate_diet_with_gerd(diet, gerd) -> list[Correlation]` - Correlation algorithm
  - `_generate_insights(correlations) -> list[Insight]` - Convert to insights
  - `_calculate_confidence(correlations) -> float` - Overall confidence score
  - `_detect_contradiction(context, correlations) -> dict` - Check user hypothesis

**Progress Milestones (Nutrition-Specific):**

```python
MILESTONES = [
    {"milestone": 1, "percent": 20, "message": "📊 Checking your diet history..."},
    {"milestone": 2, "percent": 40, "message": "🧠 Analyzing patterns..."},
    {"milestone": 3, "percent": 60, "message": "🔗 Finding correlations..."},
    {"milestone": 4, "percent": 80, "message": "💡 Generating insights..."},
    {"milestone": 5, "percent": 100, "message": "✅ Analysis complete"},
]
```

**Acceptance Criteria:**

- Can analyze GERD trigger query
- Finds correct correlation (coffee, not milk)
- Detects contradiction with user hypothesis
- Emits 5 progress events
- Duration: 500-1000ms target
- Unit tests: `tests/test_agents/test_nutritionist.py`

**Estimated Time:** 1 day

---

#### **Issue 3.2.2: Correlation Algorithm**

**File to Update:**

- `backend/agents/nutritionist.py`

**Method to Implement:**

**`_correlate_diet_with_gerd(diet_history, gerd_episodes)`:**

**Algorithm:**

1. For each food item in diet:
   - Count total occurrences
   - Count GERD episodes within 2 hours after consumption
   - Calculate correlation score: gerd_count / total_occurrences
2. Filter: Minimum 3 occurrences required
3. Rank by correlation score (descending)
4. Return top 5 triggers

**Correlation Dataclass:**

```python
@dataclass
class Correlation:
    food_item: str
    gerd_episodes: int           # Count of GERD after this food
    total_occurrences: int       # Total times food was eaten
    score: float                 # gerd_episodes / total_occurrences
    timestamps: list[datetime]   # When GERD occurred
```

**Example Output (for mock data):**

```python
[
    Correlation(food_item="late night coffee", gerd_episodes=3, total_occurrences=5, score=0.60),
    Correlation(food_item="pizza", gerd_episodes=1, total_occurrences=4, score=0.25),
    Correlation(food_item="milk", gerd_episodes=0, total_occurrences=8, score=0.00),
]
```

**Acceptance Criteria:**

- Correctly identifies coffee as trigger (3/5 = 60%)
- Milk has 0% correlation (red herring)
- Algorithm is deterministic (same input → same output)
- Runs in <100ms for 45 diet entries + 5 GERD episodes
- Unit tests: Known input → known output

**Estimated Time:** 0.5 days

---

#### **Issue 3.2.3: Insight Generation**

**File to Update:**

- `backend/agents/nutritionist.py`

**Method to Implement:**

**`_generate_insights(correlations)`:**

**Insight Classification:**

- `score > 0.5` → severity: "strong"
- `0.3 < score <= 0.5` → severity: "moderate"
- `score <= 0.3` → severity: "weak"

**Insight Format:**

```python
Insight(
    summary=f"{severity.title()} trigger: {correlation.food_item}",
    evidence=[
        f"{corr.gerd_episodes} out of {corr.total_occurrences} times led to GERD",
        f"Correlation score: {corr.score:.0%}",
        f"Last occurrence: {corr.timestamps[-1]}"
    ],
    severity=severity,
    confidence=corr.score
)
```

**Example Output:**

```python
[
    Insight(
        summary="Strong trigger: late night coffee",
        evidence=[
            "3 out of 5 times led to GERD",
            "Correlation score: 60%",
            "Last occurrence: 2025-11-05 10:00pm"
        ],
        severity="strong",
        confidence=0.60
    )
]
```

**Acceptance Criteria:**

- Insights are human-readable
- Evidence includes timestamps and percentages
- Severity classification correct
- Unit tests: Correlation → Insight transformation

**Estimated Time:** 0.5 days

---

#### **Issue 3.2.4: Progress Event Emitter**

**File to Update:**

- `backend/agents/nutritionist.py`

**Integration:**

**Progress Event Flow:**

1. Milestone 1 (0ms): Emit "Checking diet history"
2. Query K0 diet (200ms delay)
3. Milestone 2 (200ms): Emit "Analyzing patterns"
4. Query K0 GERD (200ms delay)
5. Milestone 3 (400ms): Emit "Finding correlations"
6. Run correlation algorithm (100ms)
7. Milestone 4 (600ms): Emit "Generating insights"
8. Generate insights (200ms)
9. Milestone 5 (1000ms): Emit "Complete"

**Implementation:**

```python
async def analyze(self, query, user_id, context):
    task_id = self._create_task_id()

    # Milestone 1
    await self.emit_progress(task_id, 1, 20, "📊 Checking your diet history...")

    # Query K0 (200ms)
    diet = await self.k0_query_service.get_diet_entries(user_id, "last_30_days")
    await asyncio.sleep(0.2)  # Simulate K0 latency

    # Milestone 2
    await self.emit_progress(task_id, 2, 40, "🧠 Analyzing patterns...")

    # ... continue for all 5 milestones
```

**Acceptance Criteria:**

- Progress events emitted at correct intervals
- Events contain task_id for correlation
- Events can be streamed to CLI
- Unit tests: Event emission timing

**Estimated Time:** 0.5 days

---

### **Epic 3.3: Progress Publisher**

**Objective:** Implement progress event streaming for CLI display

#### **Issue 3.3.1: Progress Publisher**

**File to Create:**

- `backend/services/progress_publisher.py`

**Classes to Implement:**

**`ProgressPublisher` (progress_publisher.py):**

- Manages progress event subscriptions
- Methods:
  - `subscribe(task_id) -> AsyncGenerator[ProgressEvent]` - Subscribe to task progress
  - `publish(task_id, event) -> None` - Publish progress event
  - `unsubscribe(task_id) -> None` - Clean up subscription
  - `_get_queue(task_id) -> asyncio.Queue` - Get or create queue for task

**Implementation Strategy:**

- Use `asyncio.Queue` per task_id
- Publisher puts events in queue
- Subscribers consume via async generator
- Auto-cleanup when task completes

**Acceptance Criteria:**

- Can subscribe to task before it starts
- Receives all progress events in order
- No events lost
- Cleanup on task completion
- Unit tests: `tests/test_services/test_progress_publisher.py`

**Estimated Time:** 0.5 days

---

### **M3 Deliverable: Specialist Agents Complete**

**Validation:**

- [ ] NutritionistAgent can analyze GERD triggers
- [ ] Correlation algorithm identifies coffee (not milk)
- [ ] Detects contradiction with user hypothesis
- [ ] Emits 5 progress events at correct intervals
- [ ] Duration: 500-1000ms (target met)
- [ ] Progress publisher streams events correctly
- [ ] All unit tests pass

**Demo Checkpoint:**

```python
# Test nutritionist agent:
nutritionist = NutritionistAgent(k0_service, metrics)

# Subscribe to progress
async for event in progress_publisher.subscribe(task_id):
    if event.type == "progress":
        print(f"[{event.percent}%] {event.message}")
    elif event.type == "result":
        result = event.data
        print(f"Primary insight: {result.insights[0].summary}")
        print(f"Contradiction: {result.contradicts_user_hypothesis}")
        break

# Expected output:
# [20%] 📊 Checking your diet history...
# [40%] 🧠 Analyzing patterns...
# [60%] 🔗 Finding correlations...
# [80%] 💡 Generating insights...
# [100%] ✅ Analysis complete
# Primary insight: Strong trigger: late night coffee
# Contradiction: True (user thought it was milk)
```

---

## 🎯 Milestone 4: Proactive Loop (Days 8-9)

**Goal:** Implement proactive prompt generation during background work

### **Epic 4.1: ProactiveGenerator Implementation**

**Objective:** Generate contextual proactive prompts using LLM

#### **Issue 4.1.1: Information Gap Identification**

**File to Create:**

- `backend/agents/proactive_generator.py`

**Classes to Implement:**

**`ProactiveGenerator` (proactive_generator.py):**

- Constructor: Takes `llm_client`, `metrics_collector`
- Fields: `last_proactive_time`, `COOLDOWN_SECONDS` (5), `MIN_BACKGROUND_DURATION` (0.3)
- Methods:
  - `identify_gaps(user_message, specialist_type, context) -> list[str]` - Find missing info
  - `generate_prompt(context, background_task, strategy) -> ProactivePrompt` - Generate prompt
  - `choose_strategy(gaps, context) -> str` - Pick fill_gap, future_action, or clarify
  - `_check_cooldown() -> bool` - Enforce 5-second cooldown
  - `_build_gap_identification_prompt() -> str` - LLM prompt for gaps
  - `_build_proactive_prompt() -> str` - LLM prompt for proactive question

**Gap Identification Prompt:**

```
Identify missing information for a {specialist_type} analysis.

User message: "{user_message}"

Conversation history:
{recent_history}

Common information gaps for {specialist_type}:
- pain_location: Where exactly is the pain?
- pain_severity: How severe? (scale 1-10)
- pain_duration: How long has this been happening?
- symptoms: What symptoms are you experiencing?
- triggers: What makes it worse?
- timing: When did it start?

Which gaps are present? List up to 3 most important gaps.

Output JSON array:
["gap1", "gap2", "gap3"]
```

**Acceptance Criteria:**

- Can identify 1-3 information gaps
- Gaps are relevant to specialist type
- LLM call latency: <50ms (target)
- Unit tests: `tests/test_agents/test_proactive_generator.py`

**Estimated Time:** 1 day

---

#### **Issue 4.1.2: Proactive Prompt Generation**

**File to Update:**

- `backend/agents/proactive_generator.py`

**Method to Implement:**

**`generate_prompt(context, background_task, strategy)`:**

**Three Strategies:**

**1. fill_gap:**

```
You are a conversational AI that maintains natural dialogue during background work.

Context:
- User mentioned: "{recent_concern}"
- Specialist working: {specialist_name} is {action} (will take ~1 second)
- Missing information: {gaps}

Generate a natural proactive prompt that:
1. Acknowledges the specialist is working ("Until {specialist_name} {action}...")
2. Naturally transitions to asking for missing info
3. Sounds conversational, not robotic
4. Fills the wait time productively

Examples of GOOD prompts:
- "Until nutritionist gathers data and sees triggers, why can't you tell me how uneasy it was?"
- "While they're analyzing patterns, could you describe where exactly the pain is?"

Generate ONE natural proactive prompt (15-25 words):
```

**2. future_action:**

```
Generate a brief future action promise that builds user trust.

Context:
- User mentioned concern: "{recent_concern}"
- Specialist working: {specialist_name}

Generate a promise to remember and act on this later (10-15 words):

Examples:
- "I'll take a note about {concern} and remind you at your next doctor visit."
- "I'll flag {concern} for when you see your doctor next."

Natural promise:
```

**3. clarify:**

```
User's last message was ambiguous. Generate a clarifying question.

Context:
- User message: "{user_message}"
- Ambiguity: {what_is_unclear}

Generate a natural clarifying question (10-15 words):

Example: "Just to clarify - do you mean {interpretation_A} or {interpretation_B}?"
```

**Acceptance Criteria:**

- Prompts feel natural (not robotic)
- Strategy selection appropriate for context
- Cooldown enforced (5 seconds between prompts)
- Only generates if background task >300ms
- LLM call latency: <100ms (target)
- Unit tests: Prompt naturalness, strategy selection

**Estimated Time:** 1 day

---

#### **Issue 4.1.3: Timing & Cooldown Logic**

**File to Update:**

- `backend/agents/proactive_generator.py`

**Methods to Implement:**

**`_check_cooldown() -> bool`:**

- Check if 5 seconds elapsed since last proactive prompt
- Return `True` if can send, `False` if in cooldown

**`_check_background_duration(est_duration_ms) -> bool`:**

- Check if background task estimated duration >300ms
- Return `True` if worth sending proactive prompt

**Cooldown Tracking:**

```python
def _check_cooldown(self) -> bool:
    if self.last_proactive_time is None:
        return True

    elapsed = time.time() - self.last_proactive_time
    return elapsed >= self.COOLDOWN_SECONDS

def generate_prompt(self, ...):
    # Check cooldown
    if not self._check_cooldown():
        return None  # Skip proactive prompt

    # Check duration
    if not self._check_background_duration(background_task.est_duration_ms):
        return None  # Task too short

    # Generate prompt
    prompt = ...

    # Update cooldown timer
    self.last_proactive_time = time.time()

    return prompt
```

**Acceptance Criteria:**

- Cooldown prevents spam (max 1 per 5 seconds)
- Short tasks (<300ms) don't trigger proactive prompts
- Timing tracked accurately
- Unit tests: Cooldown enforcement

**Estimated Time:** 0.5 days

---

### **M4 Deliverable: Proactive Loop Complete**

**Validation:**

- [ ] Can identify 1-3 information gaps
- [ ] Generates natural proactive prompts
- [ ] Three strategies implemented (fill_gap, future_action, clarify)
- [ ] Cooldown enforced (5 seconds)
- [ ] Only triggers for tasks >300ms
- [ ] LLM latency: <100ms (target)
- [ ] All unit tests pass

**Demo Checkpoint:**

```python
# Test proactive generator:
proactive_gen = ProactiveGenerator(llm_client, metrics)

# Identify gaps
gaps = proactive_gen.identify_gaps(
    "milk is making me sick",
    "nutritionist",
    context
)
print(f"Gaps: {gaps}")
# Expected: ["pain_severity", "pain_location", "duration"]

# Generate proactive prompt
prompt = proactive_gen.generate_prompt(
    context,
    BackgroundTask(specialist="nutritionist", est_duration_ms=800),
    strategy="fill_gap"
)
print(f"Proactive: {prompt.text}")
# Expected: "Until nutritionist gathers data and sees triggers,
#            why can't you tell me how uneasy it was?"
```

---

## 🎯 Milestone 5: Synthesis & ConciergeAgent (Days 10-11)

**Goal:** Implement result synthesis and main orchestrator

### **Epic 5.1: SynthesisEngine Implementation**

**Objective:** Generate natural synthesis of specialist results

#### **Issue 5.1.1: Synthesis Engine Core**

**File to Create:**

- `backend/agents/synthesis_engine.py`

**Classes to Implement:**

**`SynthesisEngine` (synthesis_engine.py):**

- Constructor: Takes `llm_client`, `metrics_collector`
- Methods:
  - `synthesize(specialist_result, context) -> str` - Main synthesis method
  - `_detect_contradiction(user_assumption, finding) -> bool` - Check contradiction
  - `_build_synthesis_prompt(result, context, has_contradiction) -> str` - Build LLM prompt
  - `_format_evidence(evidence, max_items=3) -> str` - Format evidence list
  - `_extract_user_assumption(context) -> str` - Get user's hypothesis from context

**Synthesis LLM Prompt:**

```
You are synthesizing findings from a nutrition specialist into natural conversation.

Conversation context:
{recent_history}

Specialist findings:
- Main insight: {primary_insight.summary}
- Evidence: {evidence}
- Confidence: {confidence}%

User assumption: "{user_assumption}"
Actual finding: "{actual_finding}"
Contradiction detected: {has_contradiction}

Generate a natural synthesis that:
1. Acknowledges the specialist's work ("Interesting - the nutritionist found...")
2. Presents the key finding clearly
3. If contradiction exists, gently correct it ("actually", "interestingly")
4. Connects evidence to user's original concern
5. Sounds conversational, not like a report

Good example:
"Interesting - the nutritionist analyzed your patterns and found that the trigger
may actually be late night coffee, not the milk. The evidence shows 3 out of 5
GERD episodes occurred after evening coffee."

Natural synthesis (30-50 words):
```

**Acceptance Criteria:**

- Synthesis feels natural (not robotic)
- Contradictions handled gently
- Evidence presented clearly
- Confidence level communicated
- LLM latency: <200ms (target)
- Unit tests: `tests/test_agents/test_synthesis_engine.py`

**Estimated Time:** 1 day

---

#### **Issue 5.1.2: Contradiction Detection**

**File to Update:**

- `backend/agents/synthesis_engine.py`

**Method to Implement:**

**`_detect_contradiction(user_assumption, specialist_finding)`:**

**Detection Logic:**

1. Extract key entities from user assumption (e.g., "milk")
2. Extract key entities from specialist finding (e.g., "coffee")
3. Check overlap: If no common entities → Contradiction
4. Check sentiment: If user says X is bad, but specialist says Y is bad → Contradiction

**Entity Extraction:**

- Use simple keyword matching for PoC
- Extract nouns from user message (milk, coffee, pizza, etc.)
- Compare with specialist's primary insight food items

**Example:**

```python
user_assumption = "milk is making me sick"  # Entities: ["milk"]
specialist_finding = "late night coffee"    # Entities: ["coffee"]
# No overlap → Contradiction: True
```

**Acceptance Criteria:**

- Correctly detects GERD contradiction (milk vs coffee)
- Handles partial matches (e.g., "late night coffee" vs "coffee")
- Case-insensitive matching
- Unit tests: Known contradictions detected

**Estimated Time:** 0.5 days

---

### **Epic 5.2: ConciergeAgent Orchestration**

**Objective:** Build main orchestrator that ties everything together

#### **Issue 5.2.1: ConciergeAgent Core**

**File to Create:**

- `backend/agents/concierge.py`

**Classes to Implement:**

**`ConciergeAgent` (concierge.py):**

- Constructor: Takes `llm_client`, `k0_query_service`, `conversation_store`, `metrics_collector`
- Fields: `reactive_handler`, `proactive_generator`, `synthesis_engine`, `specialist_registry`, `progress_publisher`
- Methods:
  - `handle_message(user_message, user_id) -> AsyncGenerator` - Main message loop
  - `_handle_specialist_path(intent, user_message, user_id)` - PATH 1 flow
  - `_handle_orchestrator_path(intent, user_message, user_id)` - PATH 2 flow (minimal)
  - `_spawn_specialist(intent, user_message, user_id) -> tuple[Agent, Task]` - Spawn specialist
  - `_wait_for_specialist(task, emit_proactive=True)` - Wait with proactive prompts
  - `_synthesize_and_respond(result, context)` - Final synthesis

**Specialist Registry:**

```python
self.specialist_registry = {
    "nutritionist": NutritionistAgent,
    "psychiatrist": PsychiatristAgent,  # Simpler implementation
    "finance_analyst": None,  # Not implemented in PoC
}
```

**Acceptance Criteria:**

- Can orchestrate full reactive-proactive flow
- PATH 1 works (single specialist)
- PATH 2 stub exists (for future)
- All components integrated
- Unit tests: `tests/test_agents/test_concierge.py`

**Estimated Time:** 1 day

---

#### **Issue 5.2.2: Main Message Loop**

**File to Update:**

- `backend/agents/concierge.py`

**Method to Implement:**

**`handle_message(user_message, user_id) -> AsyncGenerator`:**

**Flow:**

1. Get or create conversation state
2. Classify intent (ReactiveHandler)
3. Generate reactive response (empathy + action)
4. Yield reactive response event
5. Update conversation state
6. Route to PATH 1 or PATH 2
7. **PATH 1:**
   - Spawn specialist
   - Identify information gaps (parallel)
   - Wait 100ms
   - Generate proactive prompt
   - Yield proactive prompt event
   - Subscribe to progress events
   - Yield progress events as they arrive
   - Wait for specialist completion
   - Synthesize results
   - Yield synthesis event
8. **PATH 2:**
   - Spawn PlannerAgent (minimal implementation)
   - Similar flow with planner instead of specialist

**Event Types Yielded:**

- `{"type": "message", "data": "..."}` - Reactive/synthesis response
- `{"type": "proactive", "data": "..."}` - Proactive prompt
- `{"type": "progress", "data": {"milestone": 1, "percent": 20, "message": "..."}}` - Progress update

**Acceptance Criteria:**

- Full GERD flow works end-to-end
- Events yielded in correct order
- Timing matches spec (50ms reactive, 200ms proactive, 1200ms total)
- Integration tests: `tests/test_integration/test_gerd_flow.py`

**Estimated Time:** 1 day

---

#### **Issue 5.2.3: PsychiatristAgent (Simple Version)**

**File to Create:**

- `backend/agents/psychiatrist.py`

**Classes to Implement:**

**`PsychiatristAgent` (psychiatrist.py):**

- Inherits from `BaseAgent`
- Simpler version than NutritionistAgent
- Methods:
  - `analyze(query, user_id, context) -> AnalysisResult` - Simple mood analysis
  - `get_progress_milestones() -> list` - 5 mental health milestones

**Implementation:**

- Query K0 for mood entries
- Simple pattern matching (no complex correlation)
- Return generic insights
- Purpose: Demonstrate multi-specialist capability

**Acceptance Criteria:**

- Can analyze simple mood query
- Emits 5 progress events
- Returns basic insights
- Unit tests: `tests/test_agents/test_psychiatrist.py`

**Estimated Time:** 0.5 days

---

### **M5 Deliverable: Synthesis & Orchestration Complete**

**Validation:**

- [ ] SynthesisEngine generates natural responses
- [ ] Contradiction detection works
- [ ] ConciergeAgent orchestrates full flow
- [ ] PATH 1 works (reactive → proactive → synthesis)
- [ ] PATH 2 stub exists
- [ ] PsychiatristAgent available for demos
- [ ] All integration tests pass

**Demo Checkpoint:**

```python
# Test full flow:
concierge = ConciergeAgent(llm_client, k0_service, conversation_store, metrics)

async for event in concierge.handle_message("milk is making me sick", "user_123"):
    if event["type"] == "message":
        print(f"Message: {event['data']}")
    elif event["type"] == "proactive":
        print(f"Proactive: {event['data']}")
    elif event["type"] == "progress":
        print(f"[{event['data']['percent']}%] {event['data']['message']}")

# Expected output:
# Message: That's sad to hear. Looping in nutritionist.
# Proactive: Until nutritionist gathers data, why can't you tell me how uneasy it was?
# [20%] 📊 Checking your diet history...
# [40%] 🧠 Analyzing patterns...
# [60%] 🔗 Finding correlations...
# [80%] 💡 Generating insights...
# [100%] ✅ Analysis complete
# Message: Interesting - the nutritionist found that the trigger may actually be
#          late night coffee, not the milk. The evidence shows 3 out of 5 GERD
#          episodes occurred after evening coffee.
```

---

## 🎯 Milestone 6: CLI Interface (Day 12)

**Goal:** Build demo-ready CLI chat interface

### **Epic 6.1: CLI Chat Interface**

**Objective:** Create interactive CLI for live demonstrations

#### **Issue 6.1.1: Core CLI Implementation**

**File to Create:**

- `backend/cli/chat.py`

**Classes to Implement:**

**`ChatCLI` (chat.py):**

- Constructor: Takes `concierge_agent`, `display_helper`
- Methods:
  - `start() -> None` - Main CLI loop
  - `_show_welcome() -> None` - Display welcome message
  - `_get_user_input() -> str` - Get user input with prompt
  - `_handle_command(command) -> bool` - Handle special commands (/help, /clear, /exit)
  - `_process_message(message) -> None` - Send message to concierge, display responses
  - `_display_event(event) -> None` - Display different event types

**CLI Features:**

- **Welcome message:** Show instructions and example queries
- **Prompt:** `You:` (colored)
- **Special commands:**
  - `/help` - Show available commands
  - `/clear` - Clear conversation history
  - `/exit` or `/quit` - Exit CLI
  - `/metrics` - Show performance metrics
  - `/demo` - Run pre-configured GERD demo
- **Async event streaming:** Display responses as they arrive
- **Pretty printing:** Colors, emojis, progress bars

**Acceptance Criteria:**

- CLI starts with welcome message
- Can type messages and get responses
- Special commands work
- Events display in real-time
- Clean exit on Ctrl+C or /exit

**Estimated Time:** 1 day

---

#### **Issue 6.1.2: Display Helper**

**File to Create:**

- `backend/cli/display.py`

**Classes to Implement:**

**`DisplayHelper` (display.py):**

- Uses `rich` library for pretty printing
- Methods:
  - `print_message(text, sender="Agent") -> None` - Print agent message
  - `print_proactive(text) -> None` - Print proactive prompt (distinct style)
  - `print_progress(percent, message) -> None` - Print progress bar
  - `print_error(text) -> None` - Print error message
  - `print_metrics(metrics) -> None` - Print metrics table
  - `print_welcome() -> None` - Print welcome banner

**Styling:**

- **Agent messages:** Green text
- **Proactive prompts:** Yellow text, italic
- **Progress:** Blue progress bar with emoji
- **Errors:** Red text
- **User input:** White text
- **Metrics:** Table format

**Progress Bar Example:**

```
[20%] ━━━━━━━━━━━━━━━━━━━━                                   📊 Checking your diet history...
[40%] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                   🧠 Analyzing patterns...
[60%] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 🔗 Finding correlations...
```

**Acceptance Criteria:**

- Pretty printing works
- Colors display correctly
- Progress bars update smoothly
- Emojis render correctly

**Estimated Time:** 0.5 days

---

#### **Issue 6.1.3: Demo Mode**

**File to Update:**

- `backend/cli/chat.py`

**Feature to Add:**

**`/demo` Command:**

- Runs pre-configured GERD scenario
- Automatically types messages with delay
- Demonstrates full reactive-proactive flow
- Useful for stakeholder presentations

**Demo Script:**

```python
DEMO_SCRIPT = [
    ("milk is making me sick", 2.0),  # Wait 2s before next message
    ("pain in left side", 3.0),       # User responds to proactive prompt
    # Wait for synthesis, then end
]
```

**Demo Flow:**

1. User types `/demo`
2. CLI prints: "Running GERD demo scenario..."
3. Auto-types first message: "milk is making me sick"
4. Wait for proactive prompt
5. Auto-types response: "pain in left side"
6. Wait for synthesis
7. Print: "Demo complete!"

**Acceptance Criteria:**

- Demo runs automatically
- Realistic typing delays
- Can interrupt with Ctrl+C
- Demonstrates full reactive-proactive loop

**Estimated Time:** 0.5 days

---

### **M6 Deliverable: CLI Interface Complete**

**Validation:**

- [ ] CLI starts and displays welcome
- [ ] Can chat interactively
- [ ] Pretty printing works (colors, emojis, progress bars)
- [ ] Special commands work (/help, /clear, /exit, /metrics, /demo)
- [ ] Demo mode runs automatically
- [ ] Clean exit on Ctrl+C

**Demo Checkpoint:**

```bash
$ python -m backend.cli.chat

╔══════════════════════════════════════════════════════════════╗
║          Welcome to Concierge PoC - Chat Interface          ║
╚══════════════════════════════════════════════════════════════╝

Commands:
  /help   - Show this message
  /clear  - Clear conversation history
  /exit   - Exit CLI
  /metrics - Show performance metrics
  /demo   - Run GERD demo scenario

Example queries:
  - "milk is making me sick"
  - "I'm feeling anxious lately"

You: milk is making me sick

Agent: That's sad to hear. Looping in nutritionist.

Agent: Until nutritionist gathers data and sees triggers, why can't you
       tell me how uneasy it was?

[20%] ━━━━━━━━━━━━━━━━━━━━ 📊 Checking your diet history...
[40%] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 🧠 Analyzing patterns...
[60%] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 🔗 Finding correlations...
[80%] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 💡 Generating insights...
[100%] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ✅ Complete

Agent: Interesting - the nutritionist analyzed your patterns and found that
       the trigger may actually be late night coffee, not the milk. The
       evidence shows 3 out of 5 GERD episodes occurred after evening coffee.

You: /metrics

Performance Metrics:
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Metric                      ┃ Value     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ Total Latency               │ 1180ms    │
│ Reactive Response           │ 50ms      │
│ Proactive Prompt            │ 200ms     │
│ Specialist Duration         │ 850ms     │
│ Synthesis                   │ 185ms     │
│ Total Cost                  │ $0.0017   │
│ Proactive Prompts Sent      │ 1         │
│ User Responded to Proactive │ Yes       │
└─────────────────────────────┴───────────┘

You: /exit

Thank you for using Concierge PoC!
```

---

## 🎯 Milestone 7: Testing & Performance (Day 13)

**Goal:** Comprehensive testing and performance validation

### **Epic 7.1: Integration Tests**

**Objective:** End-to-end tests for key scenarios

#### **Issue 7.1.1: GERD Flow Test**

**File to Create:**

- `tests/test_integration/test_gerd_flow.py`

**Tests to Implement:**

**`test_gerd_flow_end_to_end()`:**

- Send "milk is making me sick"
- Validate reactive response contains empathy + action
- Validate proactive prompt sent (200ms mark)
- Validate 5 progress events emitted
- Validate synthesis contains contradiction handling
- Validate total latency <1500ms (P95 budget)

**`test_user_responds_to_proactive()`:**

- Send initial message
- Wait for proactive prompt
- Send follow-up message ("pain in left side")
- Validate follow-up acknowledged
- Validate specialist result includes follow-up info

**`test_contradiction_detection()`:**

- User hypothesis: "milk"
- Specialist finding: "coffee"
- Validate synthesis mentions "actually" or "interestingly"
- Validate both foods mentioned in synthesis

**Acceptance Criteria:**

- All integration tests pass
- Tests use mock K0 data
- Tests validate timing
- Tests validate response format

**Estimated Time:** 1 day

---

#### **Issue 7.1.2: Performance Validation**

**File to Create:**

- `tests/test_integration/test_performance.py`

**Tests to Implement:**

**`test_reactive_response_latency()`:**

- Measure P50, P95, P99 for reactive response
- Assert P95 <50ms

**`test_proactive_prompt_latency()`:**

- Measure P50, P95, P99 for proactive prompt generation
- Assert P95 <150ms

**`test_specialist_duration()`:**

- Measure P50, P95, P99 for specialist analysis
- Assert P95 <1000ms

**`test_synthesis_latency()`:**

- Measure P50, P95, P99 for synthesis
- Assert P95 <300ms

**`test_total_turn_latency()`:**

- Measure P50, P95, P99 for full turn
- Assert P95 <1500ms

**`test_cost_budget()`:**

- Track total LLM cost per turn
- Assert <$0.03 per conversation (10 turns)

**Performance Tracking:**

- Run each test 100 times
- Calculate percentiles
- Export results to CSV
- Generate performance report

**Acceptance Criteria:**

- All performance tests pass
- P95 latencies within budget
- Cost within budget
- Performance report generated

**Estimated Time:** 0.5 days

---

### **Epic 7.2: Unit Test Coverage**

**Objective:** Ensure all components have unit tests

#### **Issue 7.2.1: Test Coverage Audit**

**Files to Audit:**

- `tests/test_models/` - All data models
- `tests/test_agents/` - All agents (reactive, proactive, synthesis, specialists)
- `tests/test_services/` - All services (LLM, K0, conversation store, metrics)

**Coverage Target:** >80% line coverage

**Tools:**

- `pytest-cov` for coverage reporting
- `pytest-asyncio` for async tests
- `pytest-mock` for mocking

**Acceptance Criteria:**

- All modules have unit tests
- Coverage >80%
- No critical paths untested

**Estimated Time:** 0.5 days

---

### **M7 Deliverable: Testing Complete**

**Validation:**

- [ ] All integration tests pass
- [ ] Performance budgets met (P95 latencies)
- [ ] Cost budget met (<$0.03 per conversation)
- [ ] Unit test coverage >80%
- [ ] Performance report generated

**Performance Report Example:**

```
Concierge PoC - Performance Report
===================================

Latency Metrics (100 runs):
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Component                   ┃ P50   ┃ P95   ┃ P99   ┃ Budget   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ Reactive Response           │ 42ms  │ 48ms  │ 55ms  │ <50ms ✅  │
│ Proactive Prompt            │ 95ms  │ 140ms │ 180ms │ <150ms ✅ │
│ Specialist (Nutritionist)   │ 820ms │ 980ms │ 1100ms│ <1000ms✅ │
│ Synthesis                   │ 180ms │ 250ms │ 320ms │ <300ms ❌ │
│ Total Turn                  │ 1150ms│ 1420ms│ 1650ms│ <1500ms✅ │
└─────────────────────────────┴───────┴───────┴───────┴──────────┘

Cost Metrics:
- Average cost per turn: $0.0018
- Average cost per 10-turn conversation: $0.018 ✅ (<$0.03 budget)

Proactive Prompt Metrics:
- Prompts sent: 87/100 turns (87%)
- User responses: 42/87 prompts (48% response rate)
- Cooldown violations: 0

Status: ✅ PASS (synthesis latency P99 slightly over, but P95 meets budget)
```

---

## 🎯 Milestone 8: Demo Prep & Real K0 Integration (Day 14)

**Goal:** Production-ready demo with real K0 data

### **Epic 8.1: Real K0 Integration**

**Objective:** Replace mock K0 service with real K0 API calls

#### **Issue 8.1.1: K0 API Client**

**File to Update:**

- `backend/services/k0_query_service.py`

**Class to Implement:**

**`RealK0QueryService` (k0_query_service.py):**

- Methods:
  - `query(user_id, data_type, filters, time_range)` - Call K0 HTTP API
  - `_make_request(endpoint, params)` - HTTP wrapper with retry
  - `_handle_error(error)` - Graceful degradation (fallback to mock if K0 down)

**K0 API Endpoints (Assumed):**

- `GET /api/v1/users/{user_id}/diet_entries?time_range=last_30_days`
- `GET /api/v1/users/{user_id}/health_events?condition=GERD&time_range=last_30_days`
- `GET /api/v1/users/{user_id}/profile`

**Error Handling:**

- Network timeout: Fallback to mock data
- K0 unavailable: Fallback to mock data
- Invalid user_id: Return empty results
- Log all fallbacks for debugging

**Acceptance Criteria:**

- Can query real K0 instance
- Graceful degradation if K0 unavailable
- Latency similar to mock (<200ms per query)
- Integration tests with real K0

**Estimated Time:** 0.5 days

---

### **Epic 8.2: Demo Scenarios**

**Objective:** Prepare 3 demo scenarios for stakeholder presentations

#### **Issue 8.2.1: Demo Scenario 1 - GERD (Contradiction)**

**User:** "milk is making me sick"

**Expected Flow:**

1. Reactive: "That's sad to hear. Looping in nutritionist."
2. Proactive: "Until nutritionist gathers data, why can't you tell me how uneasy it was?"
3. Progress: 5 milestones (20% → 100%)
4. Synthesis: "Interesting - the nutritionist found that the trigger may actually be late night coffee, not the milk..."

**Highlights:**

- Contradiction handling
- Proactive prompt during wait
- Progress transparency
- Natural synthesis

**Demo Script:**

- Type: "milk is making me sick"
- Wait for proactive prompt
- (Optional) Type: "pain is about 7/10"
- Wait for synthesis
- Type: "/metrics" to show performance

---

#### **Issue 8.2.2: Demo Scenario 2 - Anxiety (Future Action)**

**User:** "I'm feeling really anxious about work"

**Expected Flow:**

1. Reactive: "I understand your concern. Connecting you with psychiatrist."
2. Proactive: "I'll take a note about work anxiety and remind you at your next therapy session."
3. Progress: 5 milestones
4. Synthesis: "The psychiatrist noticed your anxiety has increased over the past week. Your mood entries show 4 days of elevated stress..."

**Highlights:**

- Future action proactive strategy
- Different specialist (psychiatrist)
- Multi-domain capability

---

#### **Issue 8.2.3: Demo Scenario 3 - Multi-Step (PATH 2)**

**User:** "I want to reduce my GERD and also see a doctor next week"

**Expected Flow:**

1. Reactive: "I understand. Creating a plan for you."
2. PlannerAgent generates 5-step plan
3. Orchestrator executes plan
4. Synthesis: "I've created a plan: 1) Nutritionist analyzes triggers, 2) Schedule doctor appointment, 3) Prepare summary for doctor..."

**Highlights:**

- PATH 2 routing (multi-step)
- Plan generation
- Multi-agent coordination

**Note:** PATH 2 is minimal in PoC, but demonstrates routing logic

---

### **Epic 8.3: Documentation & Handoff**

**Objective:** Prepare documentation for stakeholders

#### **Issue 8.3.1: README Update**

**File to Update:**

- `poc/conceriege/README.md`

**Sections to Add:**

- **Overview:** What is Concierge PoC?
- **Quick Start:** How to run CLI
- **Demo Scenarios:** 3 pre-configured demos
- **Architecture:** High-level diagram
- **Performance:** Metrics and budgets
- **Research Foundation:** Link to DESIGN_RATIONALE.md
- **Next Steps:** Production roadmap

**Acceptance Criteria:**

- README is complete and clear
- Non-technical stakeholders can understand
- Quick start works for new users

**Estimated Time:** 0.5 days

---

#### **Issue 8.3.2: Demo Video (Optional)**

**Tool:** Screen recording

**Content:**

1. Launch CLI
2. Run GERD demo
3. Show metrics
4. Run anxiety demo
5. Explain reactive-proactive loop

**Duration:** 3-5 minutes

**Purpose:** Async demo for stakeholders who can't attend live

---

### **M8 Deliverable: Demo-Ready PoC**

**Validation:**

- [ ] Real K0 integration works
- [ ] 3 demo scenarios tested
- [ ] README complete
- [ ] Demo video recorded (optional)
- [ ] Stakeholder presentation prepared

**Final Checklist:**

- [ ] CLI launches without errors
- [ ] GERD demo runs smoothly
- [ ] Metrics show budgets met
- [ ] Contradiction handling works
- [ ] Proactive prompts feel natural
- [ ] Progress updates display correctly
- [ ] All tests pass
- [ ] Documentation complete
- [ ] Ready to show to stakeholders

---

## 📊 Final Deliverables

**Code:**

- ~2000 lines of Python
- 52 files (models, agents, services, CLI, tests)
- >80% test coverage
- All performance budgets met

**Documentation:**

- requirements.md (Phase 1 & 2 specs)
- DESIGN_RATIONALE.md (Research foundation + system design)
- envelope_design.md (Cognitive envelope spec)
- IMPLEMENTATION_PLAN_V2.md (This file)
- README.md (Quick start guide)

**Demo Assets:**

- CLI chat interface
- 3 demo scenarios
- Performance metrics report
- (Optional) Demo video

**Research Validation:**

- Reactive-proactive loop demonstrated
- Performance budgets met
- Cost budget met
- Ready for user studies

---

## 🛠️ Development Environment Setup

**Prerequisites:**

- Python 3.11+
- OpenAI API key (or Azure OpenAI)
- K0 instance running (for Day 14)

**Setup Steps:**

1. Create virtual environment: `python -m venv .venv`
2. Activate: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux/Mac)
3. Install dependencies: `pip install -r requirements.txt`
4. Create `.env` file with API keys
5. Run tests: `pytest tests/`
6. Launch CLI: `python -m backend.cli.chat`

**Dependencies (requirements.txt):**

```
openai>=1.0.0
aiohttp>=3.9.0
pydantic>=2.0.0
python-dotenv>=1.0.0
rich>=13.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.12.0
```

---

## 🎯 Success Metrics

**Performance:**

- ✅ P95 reactive latency: <50ms (Target: 50ms)
- ✅ P95 proactive latency: <150ms (Target: 150ms)
- ✅ P95 total turn latency: <1500ms (Target: 1500ms)
- ✅ Cost per conversation: <$0.02 (Target: <$0.03)

**Quality:**

- ✅ Contradiction detection: 100% (GERD scenario)
- ✅ Proactive prompt naturalness: >80% (user study target)
- ✅ Test coverage: >80%
- ✅ All integration tests pass

**Demo Readiness:**

- ✅ CLI launches cleanly
- ✅ 3 scenarios work smoothly
- ✅ Metrics display correctly
- ✅ Documentation complete

---

**END OF IMPLEMENTATION PLAN**

**Next Step:** Begin Day 1 - Foundation (Milestone 1)
