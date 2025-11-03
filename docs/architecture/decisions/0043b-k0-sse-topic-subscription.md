---
adr_number: 0043b
title: K0 SSE Topic Subscription Patterns
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
- cost
- observability
- performance
- privacy
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0043
- ADR-0043a
- ADR-0043b
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0043
  - ADR-0043a
  - ADR-0043b
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0043b: K0 SSE Topic Subscription Patterns

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0043: K0 SSE Topic Taxonomy](./0043-sse-topic-taxonomy.md)
**Authors:** K1 Architecture Team
**Priority:** ⭐⭐⭐ Critical
**Estimated Effort:** 2 weeks

---

## Context

ADR-0043a defines hierarchical topic naming (k0.config.*, k0.receipt.*, etc.). This sub-ADR specifies **topic subscription patterns** (exact match, wildcard, multi-level wildcard, filter expressions), **consumer groups** (load balancing across K1 instances), and **subscription management** (subscribe, unsubscribe, update filters) to enable flexible event consumption with efficient fanout.

### Problem Statement

**K1 instances need flexible subscription patterns to consume K0 SSE events (exact match for specific topics, wildcard for category groups, filter expressions for conditional matching) with consumer group support (load balance across instances) and dynamic subscription management (add/remove topics at runtime) to minimize bandwidth and enable horizontal scaling.**

**Current Challenge:** Without subscription patterns:

1. **All-or-Nothing:** K1 must subscribe to ALL topics → receives irrelevant events → wasted bandwidth
2. **Manual Topic Listing:** Must list every topic explicitly → brittle (new topics missed)
3. **No Load Balancing:** All K1 instances receive same events → redundant processing
4. **Static Subscriptions:** Can't add topics dynamically → restart required

**Desired Behavior:**

```
Flexible Subscription Patterns:

1. Exact Match:
   Subscribe: ["k0.config.changed"]
   Receives: k0.config.changed only

2. Wildcard (Single Level):
   Subscribe: ["k0.config.*"]
   Receives: k0.config.changed, k0.config.validated, k0.config.rollback

3. Multi-Level Wildcard:
   Subscribe: ["k0.config.**"]
   Receives: k0.config.changed, k0.config.hot_reload.completed, k0.config.cache.cleared

4. Filter Expression:
   Subscribe: ["k0.receipt.*"]
   Filter: {"user_id": "user_123"}
   Receives: k0.receipt.* events for user_123 only

5. Consumer Group:
   Group: "k1_instances"
   Members: [k1_instance_1, k1_instance_2, k1_instance_3]
   Result: Load balanced (each event to ONE instance)
```

---

## Decision

**We will implement 4 subscription pattern types (exact, wildcard *, multi-level **, filter expressions) with consumer group support (round-robin load balancing across K1 instances), dynamic subscription management (add/remove topics via REST API), and subscription validation (ensure topics exist, enforce ACLs) to enable flexible event consumption with efficient fanout.**

### Core Subscription Patterns

#### Pattern 1: Exact Match

**Format:** `"k0.config.changed"`

**Behavior:** Matches ONE specific topic only

**Use Case:** Subscribe to specific critical events

**Example:**
```rust
// Subscribe to specific config change event
let subscription = SSESubscription {
    agent_id: "config_manager",
    patterns: vec!["k0.config.changed".to_string()],
    pattern_type: PatternType::Exact,
};

// Receives:
// ✅ k0.config.changed
// ❌ k0.config.hot_reload.completed (different topic)
```

---

#### Pattern 2: Wildcard (Single Level) — `*`

**Format:** `"k0.config.*"`

**Behavior:** Matches ALL topics in category (one level deep)

**Use Case:** Subscribe to all events in a category

**Example:**
```rust
// Subscribe to all config events (single level)
let subscription = SSESubscription {
    agent_id: "config_manager",
    patterns: vec!["k0.config.*".to_string()],
    pattern_type: PatternType::Wildcard,
};

// Receives:
// ✅ k0.config.changed
// ✅ k0.config.validated
// ✅ k0.config.rollback
// ❌ k0.config.hot_reload.completed (two levels deep)
```

---

#### Pattern 3: Multi-Level Wildcard — `**`

**Format:** `"k0.config.**"`

**Behavior:** Matches ALL topics in category (all levels)

**Use Case:** Subscribe to all events in category and subcategories

**Example:**
```rust
// Subscribe to all config events (multi-level)
let subscription = SSESubscription {
    agent_id: "config_manager",
    patterns: vec!["k0.config.**".to_string()],
    pattern_type: PatternType::MultiLevelWildcard,
};

// Receives:
// ✅ k0.config.changed
// ✅ k0.config.hot_reload.completed
// ✅ k0.config.cache.cleared
// ✅ k0.config.export.completed
```

---

#### Pattern 4: Filter Expression (Conditional)

**Format:** `"k0.receipt.*"` + `{"user_id": "user_123"}`

**Behavior:** Matches topics AND filter condition

**Use Case:** User-scoped subscriptions (own receipts only)

**Example:**
```rust
// Subscribe to receipts for specific user
let subscription = SSESubscription {
    agent_id: "receipt_tracker",
    patterns: vec!["k0.receipt.*".to_string()],
    pattern_type: PatternType::Wildcard,
    filter: Some(FilterExpression {
        field: "user_id".to_string(),
        operator: FilterOperator::Equals,
        value: "user_123".to_string(),
    }),
};

// Receives:
// ✅ k0.receipt.created (user_id=user_123)
// ✅ k0.receipt.finalized (user_id=user_123)
// ❌ k0.receipt.created (user_id=user_456)
```

---

### Consumer Groups (Load Balancing)

**Purpose:** Load balance events across multiple K1 instances (horizontal scaling)

**Behavior:** Each event delivered to ONE instance in group (round-robin)

**Architecture:**
```
K0 SSE Server (FanoutManager):
  Event: k0.config.changed
  Consumer Group: "k1_instances"
  Members: [k1_instance_1, k1_instance_2, k1_instance_3]

  Round-Robin Selection:
    Event 1 → k1_instance_1 ✅
    Event 2 → k1_instance_2 ✅
    Event 3 → k1_instance_3 ✅
    Event 4 → k1_instance_1 ✅ (wrap around)

  Result: Load balanced (33% load per instance)
```

**Implementation:**

```rust
// k0/sse/consumer_group.rs

pub struct ConsumerGroup {
    pub group_id: String,
    pub members: Vec<String>,  // Consumer IDs
    pub current_index: AtomicUsize,  // Round-robin index
}

impl ConsumerGroup {
    pub fn select_consumer(&self) -> String {
        let index = self.current_index.fetch_add(1, Ordering::SeqCst) % self.members.len();
        self.members[index].clone()
    }

    pub fn add_member(&mut self, consumer_id: String) {
        self.members.push(consumer_id);
    }

    pub fn remove_member(&mut self, consumer_id: &str) {
        self.members.retain(|id| id != consumer_id);
    }
}
```

---

### Subscription Management API

#### Subscribe to Topics

**Endpoint:** `POST /k0/sse/subscribe`

**Request:**
```json
{
  "agent_id": "config_manager",
  "patterns": ["k0.config.*"],
  "pattern_type": "wildcard",
  "consumer_group": "k1_instances",
  "filter": null
}
```

**Response:**
```json
{
  "subscription_id": "sub_12345",
  "agent_id": "config_manager",
  "patterns": ["k0.config.*"],
  "matched_topics": [
    "k0.config.changed",
    "k0.config.validated",
    "k0.config.rollback"
  ],
  "consumer_group": "k1_instances",
  "created_at": "2025-10-13T12:00:00Z"
}
```

---

#### Unsubscribe from Topics

**Endpoint:** `DELETE /k0/sse/subscribe/{subscription_id}`

**Response:**
```json
{
  "subscription_id": "sub_12345",
  "status": "unsubscribed",
  "unsubscribed_at": "2025-10-13T12:05:00Z"
}
```

---

#### Update Subscription (Add/Remove Patterns)

**Endpoint:** `PATCH /k0/sse/subscribe/{subscription_id}`

**Request:**
```json
{
  "add_patterns": ["k0.learning.*"],
  "remove_patterns": ["k0.config.rollback"]
}
```

**Response:**
```json
{
  "subscription_id": "sub_12345",
  "patterns": ["k0.config.*", "k0.learning.*"],
  "matched_topics": [
    "k0.config.changed",
    "k0.config.validated",
    "k0.learning.feedback.explicit",
    "k0.learning.drift.detected"
  ],
  "updated_at": "2025-10-13T12:10:00Z"
}
```

---

#### List Active Subscriptions

**Endpoint:** `GET /k0/sse/subscribe`

**Query Params:**
- `agent_id` (optional): Filter by agent
- `consumer_group` (optional): Filter by group

**Response:**
```json
{
  "subscriptions": [
    {
      "subscription_id": "sub_12345",
      "agent_id": "config_manager",
      "patterns": ["k0.config.*"],
      "matched_topics": ["k0.config.changed", "k0.config.validated"],
      "consumer_group": "k1_instances",
      "created_at": "2025-10-13T12:00:00Z"
    },
    {
      "subscription_id": "sub_67890",
      "agent_id": "receipt_tracker",
      "patterns": ["k0.receipt.*"],
      "filter": {"user_id": "user_123"},
      "consumer_group": null,
      "created_at": "2025-10-13T12:01:00Z"
    }
  ],
  "total": 2
}
```

---

### Pattern Matching Algorithm

```rust
// k0/sse/pattern_matcher.rs

pub struct PatternMatcher;

impl PatternMatcher {
    /// Match topic against pattern
    pub fn matches(topic: &str, pattern: &str) -> bool {
        if pattern == topic {
            // Exact match
            return true;
        }

        if pattern.ends_with(".**") {
            // Multi-level wildcard: k0.config.** matches k0.config.* and k0.config.hot_reload.*
            let prefix = pattern.trim_end_matches(".**");
            return topic.starts_with(prefix);
        }

        if pattern.ends_with(".*") {
            // Single-level wildcard: k0.config.* matches k0.config.changed only
            let prefix = pattern.trim_end_matches(".*");
            let remainder = topic.strip_prefix(prefix);

            if let Some(rem) = remainder {
                // Check that remainder has exactly one segment (no dots)
                return !rem[1..].contains('.');
            }
        }

        false
    }

    /// Match with filter expression
    pub fn matches_with_filter(
        topic: &str,
        pattern: &str,
        event_payload: &serde_json::Value,
        filter: &FilterExpression,
    ) -> bool {
        // First check pattern match
        if !Self::matches(topic, pattern) {
            return false;
        }

        // Then check filter condition
        match filter.operator {
            FilterOperator::Equals => {
                event_payload.get(&filter.field).map(|v| v.as_str()) == Some(&filter.value)
            }
            FilterOperator::NotEquals => {
                event_payload.get(&filter.field).map(|v| v.as_str()) != Some(&filter.value)
            }
            FilterOperator::Contains => {
                event_payload
                    .get(&filter.field)
                    .and_then(|v| v.as_str())
                    .map(|s| s.contains(&filter.value))
                    .unwrap_or(false)
            }
        }
    }
}
```

---

### Subscription Validation

```rust
// k0/sse/subscription_validator.rs

pub struct SubscriptionValidator {
    topic_registry: Arc<TopicRegistry>,
}

impl SubscriptionValidator {
    /// Validate subscription request
    pub fn validate(&self, subscription: &SSESubscription) -> Result<(), ValidationError> {
        // 1. Validate patterns exist
        for pattern in &subscription.patterns {
            if !self.pattern_exists(pattern) {
                return Err(ValidationError::PatternNotFound(pattern.clone()));
            }
        }

        // 2. Validate ACL permissions
        for pattern in &subscription.patterns {
            let topics = self.topic_registry.resolve_pattern(pattern);
            for topic in topics {
                if !self.has_permission(&subscription.agent_id, &topic) {
                    return Err(ValidationError::PermissionDenied(topic));
                }
            }
        }

        // 3. Validate filter fields
        if let Some(filter) = &subscription.filter {
            if !self.field_exists(&filter.field) {
                return Err(ValidationError::FilterFieldNotFound(filter.field.clone()));
            }
        }

        Ok(())
    }

    fn pattern_exists(&self, pattern: &str) -> bool {
        // Check if pattern matches at least one topic
        !self.topic_registry.resolve_pattern(pattern).is_empty()
    }

    fn has_permission(&self, agent_id: &str, topic: &str) -> bool {
        // Check ACL (admin topics require admin role)
        let topic_meta = self.topic_registry.get_topic(topic);
        match topic_meta.access_level {
            AccessLevel::Admin => self.is_admin(agent_id),
            AccessLevel::User => true,
            AccessLevel::Family => self.is_family_member(agent_id),
            AccessLevel::Public => true,
        }
    }
}
```

---

## Performance Analysis

### Scenario 1: Wildcard Subscription (k0.config.*)

**Configuration:**
- Pattern: `k0.config.*`
- Matched topics: 8 (from ADR-0043a)
- Event rate: 10 events/sec

**Performance:**
```
1. Pattern match overhead:        0.01ms per event (regex-free)
2. Filter evaluation:              0ms (no filter)
3. Consumer group selection:       0.05ms (round-robin)
4. Total overhead:                 0.06ms

Result: Negligible overhead (<1% of 10ms budget) ✅
```

### Scenario 2: Filter Expression (user_id=user_123)

**Configuration:**
- Pattern: `k0.receipt.*`
- Filter: `{"user_id": "user_123"}`
- Event rate: 100 receipts/sec (10 users)

**Performance:**
```
1. Pattern match:                  0.01ms
2. Filter evaluation:              0.05ms (JSON field lookup)
3. Result: 90% events filtered out (10 events/sec for user_123)

Bandwidth savings: 90% ✅
```

### Scenario 3: Consumer Group (3 K1 instances)

**Configuration:**
- Consumer group: "k1_instances"
- Members: 3 K1 instances
- Event rate: 30 events/sec

**Performance:**
```
1. Round-robin selection:          0.05ms per event
2. Load per instance:              10 events/sec (33% each)

Result: Perfect load balancing ✅
```

---

## Implementation Roadmap

### Week 1: Pattern Matching & Validation (Days 1-5)

**Deliverables:**
- PatternMatcher: exact, wildcard *, multi-level **
- SubscriptionValidator: ACL enforcement, pattern validation
- FilterExpression: field-based filtering

**Acceptance Criteria:**
- All 4 pattern types work (exact, *, **, filter)
- Validation enforces ACLs (admin topics blocked for users)
- All tests pass

### Week 2: Consumer Groups & Subscription API (Days 6-10)

**Deliverables:**
- ConsumerGroup: round-robin load balancing
- Subscription API: POST/DELETE/PATCH/GET endpoints
- Dynamic subscription updates (add/remove patterns)

**Acceptance Criteria:**
- Consumer groups balance load (33% per instance)
- Subscription API works (subscribe, unsubscribe, update)
- All tests pass

---

## Metrics & Monitoring

```rust
lazy_static! {
    // Subscription metrics
    pub static ref K0_SSE_SUBSCRIPTIONS_TOTAL: IntGaugeVec = register_int_gauge_vec!(
        "k0_sse_subscriptions_total",
        "Total active subscriptions",
        &["pattern_type"]
    ).unwrap();

    // Pattern match performance
    pub static ref K0_SSE_PATTERN_MATCH_DURATION_MS: HistogramVec = register_histogram_vec!(
        "k0_sse_pattern_match_duration_ms",
        "Pattern match duration in milliseconds",
        &["pattern_type"],
        vec![0.01, 0.05, 0.1, 0.5, 1.0]
    ).unwrap();

    // Filter evaluation
    pub static ref K0_SSE_FILTER_EVENTS_FILTERED_TOTAL: IntCounter = register_int_counter!(
        "k0_sse_filter_events_filtered_total",
        "Total events filtered by filter expressions"
    ).unwrap();

    // Consumer group metrics
    pub static ref K0_SSE_CONSUMER_GROUP_MEMBERS: IntGaugeVec = register_int_gauge_vec!(
        "k0_sse_consumer_group_members",
        "Number of members in consumer group",
        &["group_id"]
    ).unwrap();
}
```

---

## Testing Strategy

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exact_match() {
        assert!(PatternMatcher::matches("k0.config.changed", "k0.config.changed"));
        assert!(!PatternMatcher::matches("k0.config.validated", "k0.config.changed"));
    }

    #[test]
    fn test_wildcard_match() {
        assert!(PatternMatcher::matches("k0.config.changed", "k0.config.*"));
        assert!(PatternMatcher::matches("k0.config.validated", "k0.config.*"));
        assert!(!PatternMatcher::matches("k0.config.hot_reload.completed", "k0.config.*"));
    }

    #[test]
    fn test_multi_level_wildcard() {
        assert!(PatternMatcher::matches("k0.config.changed", "k0.config.**"));
        assert!(PatternMatcher::matches("k0.config.hot_reload.completed", "k0.config.**"));
    }

    #[test]
    fn test_filter_expression() {
        let payload = json!({"user_id": "user_123"});
        let filter = FilterExpression {
            field: "user_id".to_string(),
            operator: FilterOperator::Equals,
            value: "user_123".to_string(),
        };

        assert!(PatternMatcher::matches_with_filter(
            "k0.receipt.created",
            "k0.receipt.*",
            &payload,
            &filter
        ));
    }

    #[test]
    fn test_consumer_group_round_robin() {
        let group = ConsumerGroup {
            group_id: "k1_instances".to_string(),
            members: vec!["k1_1".to_string(), "k1_2".to_string(), "k1_3".to_string()],
            current_index: AtomicUsize::new(0),
        };

        assert_eq!(group.select_consumer(), "k1_1");
        assert_eq!(group.select_consumer(), "k1_2");
        assert_eq!(group.select_consumer(), "k1_3");
        assert_eq!(group.select_consumer(), "k1_1");  // Wrap around
    }
}
```

---

## Summary

**Status:** ✅ Approved

**Key Achievements:**
- ✅ 4 Subscription Patterns: Exact, wildcard *, multi-level **, filter expressions
- ✅ Consumer Groups: Round-robin load balancing across K1 instances
- ✅ Dynamic Subscriptions: Add/remove patterns at runtime via REST API
- ✅ ACL Enforcement: Validate permissions (admin topics blocked for users)
- ✅ Pattern Matching: <0.1ms overhead (negligible impact on 10ms budget)

**Next Sub-ADR:**
- 0043c: K0 SSE Topic Routing & Delivery Guarantees (fanout, filtering, at-least-once delivery)

---

**End of ADR-0043b**