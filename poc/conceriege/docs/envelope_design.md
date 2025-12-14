# 📨 Concierge PoC: Cognitive Envelope Design

## Overview

This document specifies the **Cognitive Envelope** for the Concierge PoC's reactive-proactive loop pattern. It builds on the existing `envelope.schema.json` while adding domain-specific fields for:

1. **Intent Classification** (PATH 1 vs PATH 2 routing)
2. **Conversation State** (QUD, scoreboard, affect)
3. **Proactive Prompts** (information gaps, strategies)
4. **Specialist Spawning** (task coordination)
5. **Progress Policies** (milestone updates)
6. **Performance Budgets** (latency tracking)

---

## Design Principles

### **1. Envelope as Cognitive Trace**

- **Every message** carries full cognitive context
- **Traceable:** `cognitive_trace_id` links all messages in a conversation turn
- **Auditable:** Research patterns documented in envelope metadata

### **2. Research Alignment**

- **Actor Model (Hewitt 1973):** Envelope = message between actors
- **Conversational Grounding (Clark 1991):** QUD + scoreboard track common ground
- **Mixed-Initiative (Allen 1999):** Intent + spawn fields enable proactive behavior
- **Progressive Disclosure (Norman 1988):** Progress policy controls information flow

### **3. Performance-First**

- **Lightweight:** Core fields <2KB serialized
- **Lazy enrichment:** Expensive fields (vector_clock, registry_snapshot) optional
- **Budget enforcement:** `telemetry.latency_budget_ms` enforced at every hop

### **4. Privacy & Safety**

- **Policy-aware:** `policy.band` (GREEN/AMBER/RED) controls data access
- **Capability-based:** `policy.caps` lists allowed operations
- **Consent-aware:** `consent_receipt_id` tracks user permissions

---

## Envelope Structure

### **Base Fields (from envelope.schema.json)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9K",
  "ts": "2025-11-07T10:30:00.123Z",
  "sender": "concierge.agent",
  "receiver": "nutritionist.agent",
  "kind": "spawn_specialist",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "priority": "interactive",
  "delivery_semantics": "at_least_once"
}
```

**Key Decisions:**

- `envelope_id`: UUIDv7 (time-ordered, K-sortable)
- `cognitive_trace_id`: Unique per conversation turn (all messages share same trace)
- `kind`: Semantic type (see Kind Taxonomy below)
- `priority`: "interactive" for reactive/proactive, "background" for specialist work

---

### **Concierge-Specific Extensions**

#### **1. Actor Context**

```json
{
  "actor": {
    "agent": "concierge",           // Agent identifier
    "user_id": "user_123",           // FamilyOS user ID
    "space_id": "personal:user_123", // Data access scope
    "session_id": "sess_abc123"      // Browser/app session
  }
}
```

**Purpose:** Identity and authorization context

**Research Basis:** Capability-based security (Dennis 1966)

---

#### **2. Policy & Capabilities**

```json
{
  "policy": {
    "band": "GREEN",                     // GREEN/AMBER/RED
    "caps": [
      "read.k0",                         // Read K0 data
      "spawn.nutritionist",              // Spawn NutritionistAgent
      "spawn.psychiatrist",              // Spawn PsychiatristAgent
      "write.memory"                     // Write to memory store
    ],
    "budget_ceiling_usd": 0.10,          // Max LLM cost per turn
    "human_approval_required": false     // No HITL needed for GREEN band
  }
}
```

**Purpose:** Safety and cost controls

**Research Basis:** Least privilege (Saltzer 1975), Guardrails (ADR-0052)

**Band Definitions:**

- **GREEN:** Safe queries, no PII, no actions (read-only)
- **AMBER:** PII access, non-destructive actions (needs audit)
- **RED:** Destructive actions, financial transactions (needs HITL)

---

#### **3. Intent Classification**

```json
{
  "intent": {
    "type": "QUERY",                   // QUERY or ACTION
    "domain": "health",                // health, finance, social, general
    "complexity": "simple",            // simple (PATH 1) or multi_step (PATH 2)
    "specialist_type": "nutritionist", // Target specialist
    "confidence": 0.92,                // LLM classification confidence
    "entities": ["milk", "GERD", "pain"], // Extracted entities
    "routing": "PATH1"                 // PATH1 (specialist) or PATH2 (orchestrator)
  }
}
```

**Purpose:** Intent classification result from LLM Call #1

**Research Basis:** Intent classification (Allen 1999, Purver 2004)

**Routing Logic:**

- `complexity: "simple"` → PATH 1 (single specialist)
- `complexity: "multi_step"` → PATH 2 (PlannerAgent + Orchestrator)

---

#### **4. Conversation State (QUD + Scoreboard)**

```json
{
  "conversation": {
    "qud": "What is causing my GERD symptoms?",  // Question Under Discussion (Roberts 2012)
    "scoreboard": {
      "referents": {
        "milk": {
          "first_mentioned": "2025-11-07T10:29:45Z",
          "salience": 0.9,
          "user_hypothesis": true,
          "sentiment": "negative"
        },
        "GERD": {
          "first_mentioned": "2025-11-07T10:29:30Z",
          "salience": 1.0,
          "medical_condition": true
        }
      },
      "pending_specialists": ["nutritionist"],   // Active background tasks
      "completed_tasks": [],                     // Completed in this turn
      "proactive_prompts_sent": 0,               // Count of proactive prompts
      "last_proactive_at": null                  // Timestamp of last proactive prompt
    },
    "affect": {
      "label": "concerned",                      // Detected emotion
      "confidence": 0.78,                        // Detection confidence
      "source": "rule_based"                     // "rule_based" or "llm"
    }
  }
}
```

**Purpose:** Track conversation common ground and emotional state

**Research Basis:**

- **QUD (Roberts 2012):** Question Under Discussion from formal semantics
- **Scoreboard (Clark 1991):** Common ground tracking
- **Affect Detection:** Emotion detection for empathy generation

**QUD Updates:**

- Initial QUD set from user's first message
- Updated when user asks new question
- Used for proactive prompt generation (stay on-topic)

**Scoreboard Updates:**

- `referents`: Track mentioned entities (salience decay over time)
- `pending_specialists`: List of background tasks (for progress tracking)
- `completed_tasks`: History for this turn (for synthesis)
- `proactive_prompts_sent`: Cooldown enforcement (max 3 per turn)

---

#### **5. Specialist Spawn Request**

```json
{
  "spawn": {
    "requested": true,                   // Should spawn specialist?
    "specialist": "nutritionist",        // Specialist type
    "task_id": "task_abc123",            // Unique task ID
    "parent_trace_id": "trace_xyz789",   // Link to conversation trace
    "est_duration_ms": 800,              // Estimated duration (for proactive timing)
    "query": "What foods trigger my GERD?", // Specialist query
    "context": {
      "user_hypothesis": "milk",         // User's assumption
      "time_range": "last_30_days",      // Data query scope
      "min_confidence": 0.7              // Result threshold
    }
  }
}
```

**Purpose:** Coordinate specialist spawning from ConciergeAgent

**Research Basis:** Actor Model (Hewitt 1973), Contract Net (Smith 1980)

**Spawn Flow:**

1. ConciergeAgent creates envelope with `spawn.requested: true`
2. ActorFabric spawns specialist with `spawn.task_id`
3. Specialist emits progress events with same `task_id`
4. ConciergeAgent receives completion event, synthesizes results

---

#### **6. Progress Policy**

```json
{
  "progress_policy": {
    "max_updates_per_sec": 5,       // Rate limit for progress events
    "merge_window_ms": 120,         // Merge events within 120ms
    "milestones": [
      { "percent": 20, "message": "📊 Checking your diet history..." },
      { "percent": 40, "message": "🧠 Analyzing patterns..." },
      { "percent": 60, "message": "🔗 Finding correlations..." },
      { "percent": 80, "message": "💡 Generating insights..." },
      { "percent": 100, "message": "✅ Analysis complete" }
    ],
    "enable_streaming": true,       // Stream via SSE?
    "debounce_ms": 50               // Debounce rapid updates
  }
}
```

**Purpose:** Control progress update frequency and merging

**Research Basis:** Progressive Disclosure (Norman 1988), SEDA (Welsh 2001)

**Rate Limiting:**

- Max 5 updates/sec to avoid UI flooding
- Merge events within 120ms window (reduce SSE overhead)
- 50ms debounce for rapid updates

---

#### **7. Telemetry & Performance**

```json
{
  "telemetry": {
    "latency_budget_ms": 1200,          // P95 budget for this turn
    "perf_profile": "PATH1",            // PATH1 or PATH2
    "llm_calls": [
      {
        "operation": "intent_classification",
        "model": "gpt-4o-mini",
        "latency_ms": 28,
        "tokens": 95,
        "cost_usd": 0.0001,
        "cache_hit": false
      },
      {
        "operation": "proactive_prompt",
        "model": "gpt-4o-mini",
        "latency_ms": 105,
        "tokens": 220,
        "cost_usd": 0.0005,
        "cache_hit": false
      }
    ],
    "specialist_duration_ms": 850,      // Actual specialist runtime
    "total_latency_ms": 1180,           // End-to-end latency
    "budget_exceeded": false            // Did we exceed budget?
  }
}
```

**Purpose:** Performance tracking and budget enforcement

**Research Basis:** Performance budgets (K1 architecture)

**Metrics:**

- Track each LLM call separately (operation, model, latency, cost)
- Track specialist duration
- Enforce latency budget (reject if exceeded)

---

#### **8. Observability & Tracing**

```json
{
  "observability": {
    "trace_flags": [
      "sse.stream",           // Enable SSE streaming tracing
      "arbiter.skip",         // Skip arbiter (direct to specialist)
      "proactive.enabled"     // Enable proactive prompts
    ],
    "idempotency_key": "idem_abc123",  // Deduplication key
    "research_pattern": "reactive_proactive_loop",  // Pattern being used
    "validation_mode": false,          // User study mode?
    "stamps": [
      {
        "stage": "concierge.intent_classification",
        "rtt_ms": 28,
        "intent_conf": 0.92,
        "host": "concierge-pod-1",
        "pid": 12345
      },
      {
        "stage": "concierge.reactive_response",
        "rtt_ms": 18,
        "host": "concierge-pod-1"
      },
      {
        "stage": "specialist.spawn",
        "rtt_ms": 5,
        "note": "NutritionistAgent spawned"
      },
      {
        "stage": "concierge.proactive_prompt",
        "rtt_ms": 105,
        "note": "Generated proactive prompt (fill_gap strategy)"
      }
    ]
  }
}
```

**Purpose:** End-to-end tracing and research validation

**Research Basis:** Distributed tracing (Zipkin, Jaeger)

**Trace Flags:**

- `sse.stream`: Log SSE streaming events
- `arbiter.skip`: Bypass arbiter for direct specialist routing
- `proactive.enabled`: Enable proactive prompt generation

**Stamps:**

- Append-only breadcrumbs for each stage
- Include RTT, confidence, host, PID
- Used for latency breakdown analysis

---

## Envelope Kind Taxonomy

### **Concierge-Specific Kinds**

| Kind | Direction | Purpose | Contains |
|------|-----------|---------|----------|
| `user_utterance` | User → Concierge | User message | `body.text`, `intent` (after classification) |
| `reactive_response` | Concierge → User | Immediate empathy + action | `body.text`, `conversation.affect` |
| `proactive_prompt` | Concierge → User | Fill information gap | `body.text`, `body.strategy`, `body.information_target` |
| `spawn_specialist` | Concierge → ActorFabric | Request specialist spawn | `spawn.*` fields |
| `specialist_spawned` | ActorFabric → Concierge | Spawn confirmation | `spawn.task_id`, `spawn.specialist` |
| `progress_event` | Specialist → Concierge | Progress milestone | `body.milestone`, `body.percent`, `body.message` |
| `specialist_result` | Specialist → Concierge | Analysis complete | `body.insights`, `body.evidence`, `body.confidence` |
| `synthesis_response` | Concierge → User | Final integrated result | `body.text`, `body.specialist_type` |
| `user_additional_info` | User → Concierge | Response to proactive prompt | `body.text`, `conversation.qud` (updated) |

### **Standard Kinds (from envelope.schema.json)**

Reuse existing kinds for:

- `plan_patch` (PATH 2 orchestrator)
- `cnp_bid`, `cnp_award` (Contract Net Protocol)
- `hitl_approval_request` (RED band actions)
- `error`, `ack`, `nack` (control messages)

---

## Example: Complete GERD Conversation Flow

### **Message 1: User Utterance**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9K",
  "ts": "2025-11-07T10:30:00.000Z",
  "sender": "user:user_123",
  "receiver": "concierge.agent",
  "kind": "user_utterance",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "priority": "interactive",

  "actor": {
    "agent": null,
    "user_id": "user_123",
    "space_id": "personal:user_123",
    "session_id": "sess_abc123"
  },

  "policy": {
    "band": "GREEN",
    "caps": ["read.k0"],
    "budget_ceiling_usd": 0.10,
    "human_approval_required": false
  },

  "body": {
    "text": "remember we talked about reducing my gerd and milk is making me sick",
    "input_modality": "text",
    "channel": "web"
  },

  "telemetry": {
    "latency_budget_ms": 1200,
    "perf_profile": "PATH1"
  },

  "observability": {
    "trace_flags": ["sse.stream", "proactive.enabled"],
    "idempotency_key": "idem_msg1_abc123",
    "research_pattern": "reactive_proactive_loop"
  }
}
```

---

### **Message 2: Reactive Response (50ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9L",
  "ts": "2025-11-07T10:30:00.050Z",
  "sender": "concierge.agent",
  "receiver": "user:user_123",
  "kind": "reactive_response",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "caused_by": ["01JA1B2C3D4E5F6G7H8J9K"],

  "actor": {
    "agent": "concierge",
    "user_id": "user_123",
    "space_id": "personal:user_123"
  },

  "intent": {
    "type": "QUERY",
    "domain": "health",
    "complexity": "simple",
    "specialist_type": "nutritionist",
    "confidence": 0.92,
    "entities": ["milk", "GERD", "pain"],
    "routing": "PATH1"
  },

  "conversation": {
    "qud": "What is causing my GERD symptoms?",
    "scoreboard": {
      "referents": {
        "milk": { "first_mentioned": "2025-11-07T10:30:00.000Z", "salience": 0.9, "user_hypothesis": true },
        "GERD": { "first_mentioned": "2025-11-07T10:30:00.000Z", "salience": 1.0 }
      },
      "pending_specialists": [],
      "completed_tasks": [],
      "proactive_prompts_sent": 0
    },
    "affect": {
      "label": "concerned",
      "confidence": 0.78,
      "source": "rule_based"
    }
  },

  "body": {
    "text": "That's sad to hear. Looping in nutritionist.",
    "empathy": "That's sad to hear",
    "action_declaration": "Looping in nutritionist",
    "generation_method": "rule_based"
  },

  "telemetry": {
    "latency_budget_ms": 1200,
    "llm_calls": [
      {
        "operation": "intent_classification",
        "model": "gpt-4o-mini",
        "latency_ms": 28,
        "tokens": 95,
        "cost_usd": 0.0001
      }
    ],
    "total_latency_ms": 50
  },

  "observability": {
    "stamps": [
      { "stage": "concierge.intent_classification", "rtt_ms": 28, "intent_conf": 0.92 },
      { "stage": "concierge.reactive_response", "rtt_ms": 18 }
    ]
  }
}
```

---

### **Message 3: Spawn Specialist (100ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9M",
  "ts": "2025-11-07T10:30:00.100Z",
  "sender": "concierge.agent",
  "receiver": "actor_fabric.spawn_manager",
  "kind": "spawn_specialist",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "caused_by": ["01JA1B2C3D4E5F6G7H8J9K"],
  "priority": "background",

  "actor": {
    "agent": "concierge",
    "user_id": "user_123",
    "space_id": "personal:user_123"
  },

  "policy": {
    "band": "GREEN",
    "caps": ["read.k0", "spawn.nutritionist"]
  },

  "spawn": {
    "requested": true,
    "specialist": "nutritionist",
    "task_id": "task_nut_abc123",
    "parent_trace_id": "trace_xyz789",
    "est_duration_ms": 800,
    "query": "What foods trigger my GERD?",
    "context": {
      "user_hypothesis": "milk",
      "time_range": "last_30_days",
      "min_confidence": 0.7
    }
  },

  "progress_policy": {
    "max_updates_per_sec": 5,
    "merge_window_ms": 120,
    "milestones": [
      { "percent": 20, "message": "📊 Checking your diet history..." },
      { "percent": 40, "message": "🧠 Analyzing patterns..." },
      { "percent": 60, "message": "🔗 Finding correlations..." },
      { "percent": 80, "message": "💡 Generating insights..." },
      { "percent": 100, "message": "✅ Analysis complete" }
    ]
  },

  "telemetry": {
    "latency_budget_ms": 1000,
    "perf_profile": "PATH1"
  }
}
```

---

### **Message 4: Proactive Prompt (200ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9N",
  "ts": "2025-11-07T10:30:00.200Z",
  "sender": "concierge.agent",
  "receiver": "user:user_123",
  "kind": "proactive_prompt",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "caused_by": ["01JA1B2C3D4E5F6G7H8J9K"],

  "actor": {
    "agent": "concierge",
    "user_id": "user_123"
  },

  "conversation": {
    "qud": "What is causing my GERD symptoms?",
    "scoreboard": {
      "referents": {
        "milk": { "salience": 0.9, "user_hypothesis": true },
        "GERD": { "salience": 1.0 }
      },
      "pending_specialists": ["nutritionist"],
      "proactive_prompts_sent": 1,
      "last_proactive_at": "2025-11-07T10:30:00.200Z"
    }
  },

  "body": {
    "text": "Until nutritionist gathers data and sees triggers, why can't you tell me how uneasy it was?",
    "strategy": "fill_gap",
    "information_target": "pain_severity",
    "information_gaps": ["pain_severity", "pain_location", "duration"],
    "generation_method": "llm"
  },

  "telemetry": {
    "llm_calls": [
      {
        "operation": "gap_identification",
        "model": "gpt-4o-mini",
        "latency_ms": 45,
        "tokens": 50,
        "cost_usd": 0.0002
      },
      {
        "operation": "proactive_prompt",
        "model": "gpt-4o-mini",
        "latency_ms": 105,
        "tokens": 220,
        "cost_usd": 0.0005
      }
    ],
    "total_latency_ms": 200
  },

  "observability": {
    "stamps": [
      { "stage": "concierge.gap_identification", "rtt_ms": 45 },
      { "stage": "concierge.proactive_prompt", "rtt_ms": 105, "note": "fill_gap strategy" }
    ]
  }
}
```

---

### **Message 5: User Additional Info (300ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9P",
  "ts": "2025-11-07T10:30:00.300Z",
  "sender": "user:user_123",
  "receiver": "concierge.agent",
  "kind": "user_additional_info",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "caused_by": ["01JA1B2C3D4E5F6G7H8J9N"],

  "actor": {
    "user_id": "user_123"
  },

  "conversation": {
    "qud": "What is causing my GERD symptoms?",
    "scoreboard": {
      "referents": {
        "milk": { "salience": 0.9 },
        "GERD": { "salience": 1.0 },
        "left_side_pain": { "first_mentioned": "2025-11-07T10:30:00.300Z", "salience": 0.8 }
      }
    }
  },

  "body": {
    "text": "pain in left side",
    "responded_to_proactive": true,
    "filled_gap": "pain_location"
  }
}
```

---

### **Message 6: Progress Event (400ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9Q",
  "ts": "2025-11-07T10:30:00.400Z",
  "sender": "nutritionist.agent",
  "receiver": "concierge.agent",
  "kind": "progress_event",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "task_id": "task_nut_abc123",

  "body": {
    "milestone": 2,
    "percent": 40,
    "message": "🧠 Analyzing patterns...",
    "timestamp": "2025-11-07T10:30:00.400Z"
  }
}
```

---

### **Message 7: Specialist Result (1000ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9R",
  "ts": "2025-11-07T10:30:01.000Z",
  "sender": "nutritionist.agent",
  "receiver": "concierge.agent",
  "kind": "specialist_result",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "task_id": "task_nut_abc123",
  "caused_by": ["01JA1B2C3D4E5F6G7H8J9M"],

  "body": {
    "specialist_type": "nutritionist",
    "query": "What foods trigger my GERD?",
    "insights": [
      {
        "summary": "Strong trigger: late night coffee",
        "evidence": [
          "3 out of 5 GERD episodes occurred after evening coffee",
          "Correlation score: 60%"
        ],
        "severity": "strong",
        "confidence": 0.85
      }
    ],
    "evidence": [
      "2025-11-01: Coffee at 9pm → GERD at 10pm",
      "2025-11-03: Coffee at 8:30pm → GERD at 9:15pm",
      "2025-11-05: Coffee at 10pm → GERD at 11pm"
    ],
    "confidence": 0.85,
    "contradicts_user_hypothesis": true,
    "user_hypothesis": "milk",
    "actual_finding": "late night coffee"
  },

  "telemetry": {
    "specialist_duration_ms": 850,
    "k0_queries": [
      { "type": "diet_entries", "latency_ms": 180, "results": 45 },
      { "type": "health_events", "latency_ms": 160, "results": 5 }
    ]
  }
}
```

---

### **Message 8: Synthesis Response (1200ms)**

```json
{
  "schema_version": "1.0.0",
  "envelope_id": "01JA1B2C3D4E5F6G7H8J9S",
  "ts": "2025-11-07T10:30:01.200Z",
  "sender": "concierge.agent",
  "receiver": "user:user_123",
  "kind": "synthesis_response",
  "conversation_id": "conv_abc123",
  "cognitive_trace_id": "trace_xyz789",
  "caused_by": ["01JA1B2C3D4E5F6G7H8J9R"],

  "conversation": {
    "qud": "What is causing my GERD symptoms?",
    "scoreboard": {
      "referents": {
        "milk": { "salience": 0.5, "user_hypothesis": true, "contradicted": true },
        "coffee": { "first_mentioned": "2025-11-07T10:30:01.200Z", "salience": 1.0, "actual_trigger": true }
      },
      "pending_specialists": [],
      "completed_tasks": ["task_nut_abc123"]
    }
  },

  "body": {
    "text": "Interesting - the nutritionist analyzed your patterns and found that the trigger may actually be late night coffee, not the milk. The evidence shows 3 out of 5 GERD episodes occurred after evening coffee.",
    "specialist_type": "nutritionist",
    "contradiction_detected": true,
    "user_assumption": "milk",
    "actual_finding": "late night coffee",
    "generation_method": "llm"
  },

  "telemetry": {
    "latency_budget_ms": 1200,
    "llm_calls": [
      {
        "operation": "intent_classification",
        "latency_ms": 28,
        "cost_usd": 0.0001
      },
      {
        "operation": "proactive_prompt",
        "latency_ms": 105,
        "cost_usd": 0.0005
      },
      {
        "operation": "synthesis",
        "model": "gpt-4o-mini",
        "latency_ms": 185,
        "tokens": 420,
        "cost_usd": 0.001
      }
    ],
    "specialist_duration_ms": 850,
    "total_latency_ms": 1180,
    "budget_exceeded": false,
    "total_cost_usd": 0.0017
  },

  "observability": {
    "stamps": [
      { "stage": "concierge.intent_classification", "rtt_ms": 28 },
      { "stage": "concierge.reactive_response", "rtt_ms": 18 },
      { "stage": "specialist.spawn", "rtt_ms": 5 },
      { "stage": "concierge.proactive_prompt", "rtt_ms": 105 },
      { "stage": "nutritionist.analyze", "rtt_ms": 850 },
      { "stage": "concierge.synthesis", "rtt_ms": 185 }
    ],
    "research_pattern": "reactive_proactive_loop",
    "validation_metrics": {
      "proactive_prompts_sent": 1,
      "user_responded_to_proactive": true,
      "contradiction_handled": true,
      "naturalness_target": 0.8
    }
  }
}
```

---

## Implementation Guidelines

### **1. Envelope Creation**

```python
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

@dataclass
class CognitiveEnvelope:
    """Cognitive envelope for Concierge PoC"""

    schema_version: str = "1.0.0"
    envelope_id: str = None
    ts: str = None
    sender: str = None
    receiver: str = None
    kind: str = None
    conversation_id: str = None
    cognitive_trace_id: str = None
    priority: str = "interactive"

    actor: dict = None
    policy: dict = None
    intent: dict = None
    conversation: dict = None
    spawn: dict = None
    progress_policy: dict = None
    telemetry: dict = None
    observability: dict = None
    body: dict = None

    def __post_init__(self):
        if self.envelope_id is None:
            self.envelope_id = self._generate_ulid()
        if self.ts is None:
            self.ts = datetime.utcnow().isoformat() + "Z"

    def _generate_ulid(self) -> str:
        """Generate UUIDv7 (time-ordered)"""
        return str(uuid.uuid7())  # Python 3.12+

    def to_dict(self) -> dict:
        """Convert to dictionary, removing None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Serialize to JSON"""
        import json
        return json.dumps(self.to_dict())
```

### **2. Envelope Helpers**

```python
class EnvelopeFactory:
    """Factory for creating typed envelopes"""

    @staticmethod
    def create_reactive_response(
        user_message: str,
        intent: Intent,
        affect: dict,
        conversation_state: ConversationState,
        trace_id: str
    ) -> CognitiveEnvelope:
        """Create reactive response envelope"""

        return CognitiveEnvelope(
            sender="concierge.agent",
            receiver=f"user:{conversation_state.user_id}",
            kind="reactive_response",
            conversation_id=conversation_state.conversation_id,
            cognitive_trace_id=trace_id,

            actor={
                "agent": "concierge",
                "user_id": conversation_state.user_id,
                "space_id": f"personal:{conversation_state.user_id}"
            },

            intent={
                "type": intent.type,
                "domain": intent.domain,
                "complexity": intent.complexity,
                "specialist_type": intent.specialist_type,
                "confidence": intent.confidence,
                "routing": "PATH1" if intent.complexity == "simple" else "PATH2"
            },

            conversation={
                "qud": conversation_state.qud,
                "scoreboard": conversation_state.scoreboard.to_dict(),
                "affect": affect
            },

            body={
                "text": f"{affect['empathy']}. {intent.action_declaration}.",
                "empathy": affect['empathy'],
                "action_declaration": intent.action_declaration,
                "generation_method": "rule_based"
            },

            telemetry={
                "latency_budget_ms": 1200,
                "llm_calls": [],
                "total_latency_ms": 0
            }
        )

    @staticmethod
    def create_proactive_prompt(
        proactive_prompt: ProactivePrompt,
        conversation_state: ConversationState,
        trace_id: str,
        llm_calls: list
    ) -> CognitiveEnvelope:
        """Create proactive prompt envelope"""

        return CognitiveEnvelope(
            sender="concierge.agent",
            receiver=f"user:{conversation_state.user_id}",
            kind="proactive_prompt",
            conversation_id=conversation_state.conversation_id,
            cognitive_trace_id=trace_id,

            actor={
                "agent": "concierge",
                "user_id": conversation_state.user_id
            },

            conversation={
                "qud": conversation_state.qud,
                "scoreboard": conversation_state.scoreboard.to_dict()
            },

            body={
                "text": proactive_prompt.text,
                "strategy": proactive_prompt.prompt_type,
                "information_target": proactive_prompt.information_target,
                "information_gaps": conversation_state.information_gaps,
                "generation_method": "llm"
            },

            telemetry={
                "llm_calls": llm_calls,
                "total_latency_ms": sum(call["latency_ms"] for call in llm_calls)
            }
        )
```

### **3. Envelope Validation**

```python
def validate_envelope(envelope: dict) -> tuple[bool, list[str]]:
    """Validate envelope against schema"""

    errors = []

    # Required fields
    required = ["schema_version", "envelope_id", "ts", "sender", "kind",
                "conversation_id", "cognitive_trace_id"]
    for field in required:
        if field not in envelope:
            errors.append(f"Missing required field: {field}")

    # Kind-specific validation
    kind = envelope.get("kind")

    if kind == "reactive_response":
        if "intent" not in envelope:
            errors.append("reactive_response requires intent field")
        if "conversation" not in envelope:
            errors.append("reactive_response requires conversation field")

    elif kind == "proactive_prompt":
        if "body" not in envelope or "strategy" not in envelope.get("body", {}):
            errors.append("proactive_prompt requires body.strategy")

    elif kind == "spawn_specialist":
        if "spawn" not in envelope or not envelope["spawn"].get("requested"):
            errors.append("spawn_specialist requires spawn.requested: true")

    # Budget enforcement
    if "telemetry" in envelope:
        telemetry = envelope["telemetry"]
        if "latency_budget_ms" in telemetry and "total_latency_ms" in telemetry:
            if telemetry["total_latency_ms"] > telemetry["latency_budget_ms"]:
                errors.append(f"Budget exceeded: {telemetry['total_latency_ms']}ms > {telemetry['latency_budget_ms']}ms")

    return len(errors) == 0, errors
```

---

## Migration from envelope.schema.json

### **Reused Fields (No Changes)**

✅ **Routing:** `ts`, `sender`, `receiver`, `priority`, `delivery_semantics`
✅ **Tracing:** `conversation_id`, `cognitive_trace_id`, `trace_id`, `span_id`, `caused_by`
✅ **Tasks:** `task_id`, `parent_task_id`, `plan_id`
✅ **QoS:** `deadline_ms`, `ttl_ms`, `expects_reply`, `retry_policy`
✅ **Safety:** `safety_band`, `privacy_band`, `guardrails`, `consent_receipt_id`
✅ **Observability:** `stamps`, `metrics`, `annotations`
✅ **Reliability:** `idempotency_key`, `dedupe_key`, `ack_required`
✅ **Body:** `body` (flexible payload), `artifacts`

### **New Concierge-Specific Fields**

🆕 **actor:** Identity and authorization context
🆕 **policy:** Capability-based access control
🆕 **intent:** Intent classification result
🆕 **conversation:** QUD + scoreboard + affect
🆕 **spawn:** Specialist spawn request
🆕 **progress_policy:** Progress update controls
🆕 **telemetry:** Performance tracking

### **Deprecated Fields (Not Used in PoC)**

❌ **Ordering:** `lamport_clock`, `vector_clock`, `watermark_ts` (not needed for PoC)
❌ **Model Lineage:** `model_id`, `model_version`, `temperature` (moved to `telemetry.llm_calls`)
❌ **i18n:** `locale`, `timezone`, `units`, `currency` (hardcoded to `en-US` for PoC)
❌ **Registries:** `registry_snapshot` (not implemented in PoC)
❌ **Concurrency:** `precondition_etag`, `resolution_policy` (not needed for simple conversations)
❌ **Streaming:** `partial_seq`, `partial_of`, `is_final` (SSE handles streaming)

---

## Performance Considerations

### **Envelope Size Budget**

| Section | Target Size | Notes |
|---------|-------------|-------|
| Base fields | <500 bytes | Routing, tracing, IDs |
| actor + policy | <200 bytes | Identity and capabilities |
| intent | <300 bytes | Classification result |
| conversation | <1KB | QUD + scoreboard (limit referents to top 10) |
| spawn | <500 bytes | Specialist request |
| telemetry | <1KB | LLM calls (limit to 10 entries) |
| body | <2KB | Message text + metadata |
| **Total** | **<5KB** | Reasonable for high-frequency messages |

### **Optimization Strategies**

1. **Lazy Enrichment:** Only add `telemetry.llm_calls` in synthesis response (not intermediate)
2. **Scoreboard Pruning:** Keep only top 10 referents by salience
3. **Stamp Compression:** Omit `host`, `pid` in production (only for debugging)
4. **Body Compression:** Use gzip for large bodies (>2KB)

---

## Validation Metrics

### **Research Validation Tracking**

Track these metrics in `observability.validation_metrics`:

```json
{
  "observability": {
    "validation_metrics": {
      "proactive_prompts_sent": 1,
      "user_responded_to_proactive": true,
      "proactive_relevance_score": 0.85,
      "contradiction_handled": true,
      "empathy_acknowledged": true,
      "naturalness_target": 0.8,
      "wait_perception_acceptable": true,
      "information_gathering_score": 0.9
    }
  }
}
```

**User Study Questions:**

1. **Naturalness:** "How natural did the conversation feel?" (1-5) → `naturalness_target`
2. **Wait Perception:** "Did you notice any awkward silences?" (Yes/No) → `wait_perception_acceptable`
3. **Proactive Relevance:** "Were the proactive questions relevant?" (1-5) → `proactive_relevance_score`
4. **Empathy:** "Did the agent acknowledge your concern?" (Yes/No) → `empathy_acknowledged`
5. **Information Gathering:** "Did the agent gather enough context?" (1-5) → `information_gathering_score`

---

## References

**Research Patterns:**

- Actor Model (Hewitt 1973)
- Conversational Grounding (Clark 1991)
- Mixed-Initiative Dialogue (Allen 1999, Horvitz 1999)
- Proactive Dialogue Systems (Yang 2018, Sun 2021)
- Progressive Disclosure (Norman 1988)
- Reactive-Proactive Loop (Our novel pattern)

**K1 Architecture:**

- ADR-0052: Enhanced HITL protocols
- ADR-0065c: Quick actions & suggested replies
- envelope.schema.json: Universal cognitive envelope

**Design Principles:**

- Capability-based security (Dennis 1966)
- Least privilege (Saltzer 1975)
- Performance budgets (K1 architecture)
- Contract Net Protocol (Smith 1980)

---

## Next Steps

1. ✅ **Envelope Schema:** Document complete envelope design (this file)
2. 🔜 **Update envelope.schema.json:** Add Concierge-specific fields as optional extensions
3. 🔜 **Implement EnvelopeFactory:** Python helpers for creating typed envelopes
4. 🔜 **Validation Tests:** pytest tests for envelope validation
5. 🔜 **SSE Integration:** Stream envelopes via Server-Sent Events
6. 🔜 **Observability:** Log envelope traces with OpenTelemetry

---

**Document Version:** 1.0.0
**Last Updated:** 2025-11-07
**Authors:** Concierge PoC Team
**Status:** Draft → Review → Approved
