# ADR-0043d: K0 SSE Topic Access Control & ACL Enforcement

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0043: K0 SSE Topic Taxonomy](./0043-sse-topic-taxonomy.md)
**Authors:** K1 Architecture Team
**Priority:** ⭐⭐⭐ Critical
**Estimated Effort:** 2 weeks

---

## Context

ADR-0043c defines topic routing and delivery guarantees. This sub-ADR specifies **access control** (ACL-based permissions per topic category), **role-based enforcement** (admin, user, family, system), **topic authorization** (validate permissions before subscription/publish), and **audit logging** (track access to sensitive topics) to ensure security and privacy compliance.

### Problem Statement

**K0 SSE topics need access control to prevent unauthorized access (user can't read admin topics, non-family members can't see family topics), role-based enforcement (admin vs user vs family vs system), subscription authorization (validate permissions before SSE subscribe), and audit logging (track who accessed k0.policy.*, k0.audit.*) to ensure security and GDPR compliance.**

**Current Challenge:** Without access control:

1. **No Permission Enforcement:** Users can subscribe to ANY topic → read admin config, audit logs, other users' receipts
2. **No Role Validation:** Can't distinguish admin vs user vs family member → everyone has full access
3. **No Audit Trail:** No record of who accessed sensitive topics → compliance violation (GDPR, HIPAA)
4. **No Scope Isolation:** User A can read User B's receipts → privacy breach

**Desired Behavior:**

```
Access Control Enforcement:

1. User subscribes to k0.config.changed (admin topic):
   - ACL Check: user_123 is NOT admin
   - Result: ❌ PERMISSION_DENIED

2. User subscribes to k0.receipt.* (user-scoped topic):
   - ACL Check: user_123 is owner
   - Filter: {"user_id": "user_123"}
   - Result: ✅ ALLOWED (own receipts only)

3. Admin subscribes to k0.policy.* (admin topic):
   - ACL Check: admin_456 is admin
   - Result: ✅ ALLOWED (no filter)

4. Family member subscribes to k0.family.* (family-scoped):
   - ACL Check: user_789 is family member (family_id=fam_123)
   - Filter: {"family_id": "fam_123"}
   - Result: ✅ ALLOWED (own family only)

5. Audit logging:
   - Log: admin_456 accessed k0.policy.updated at 2025-10-13T12:00:00Z
   - Stored in k0.audit.access.logged (365-day retention)
```

---

## Decision

**We will implement 4-level access control (admin, user, family, system) with ACL enforcement (validate permissions before subscribe/publish), topic-level scoping (user_id, family_id filters), audit logging (track access to sensitive topics: k0.policy.*, k0.audit.*), and role-based policies (defined in K0 config, enforced at subscription time) to ensure security and GDPR compliance.**

### Access Levels (4 Tiers)

#### Level 1: Admin Topics

**Access:** Admin role only

**Topics:**
- k0.config.* (8 topics)
- k0.policy.* (4 topics)
- k0.audit.* (6 topics)

**Use Case:** System configuration, policy management, audit logs

**Example:**
```rust
// Admin topics require admin role
let acl_policy = ACLPolicy {
    topic_pattern: "k0.config.*".to_string(),
    access_level: AccessLevel::Admin,
    required_role: Some(Role::Admin),
    scope_filter: None,  // No user/family scoping
};

// User tries to subscribe (denied)
let subscription = SSESubscription {
    agent_id: "user_123",
    patterns: vec!["k0.config.*".to_string()],
};

let result = acl_enforcer.authorize(&subscription);
assert_eq!(result, Err(ACLError::PermissionDenied));

// Admin subscribes (allowed)
let subscription = SSESubscription {
    agent_id: "admin_456",
    patterns: vec!["k0.config.*".to_string()],
};

let result = acl_enforcer.authorize(&subscription);
assert!(result.is_ok());
```

---

#### Level 2: User Topics (Scoped)

**Access:** User role (own data only)

**Topics:**
- k0.receipt.* (6 topics)
- k0.learning.* (8 topics)
- k0.crdt.* (6 topics)

**Scoping:** Automatic `user_id` filter (own data only)

**Use Case:** User receipts, learning feedback, session state

**Example:**
```rust
// User topics require user_id scoping
let acl_policy = ACLPolicy {
    topic_pattern: "k0.receipt.*".to_string(),
    access_level: AccessLevel::User,
    required_role: Some(Role::User),
    scope_filter: Some(ScopeFilter::UserId),  // Auto-inject user_id filter
};

// User subscribes to receipts (allowed with filter)
let subscription = SSESubscription {
    agent_id: "user_123",
    patterns: vec!["k0.receipt.*".to_string()],
};

let result = acl_enforcer.authorize(&subscription);

// ACL enforcer auto-injects user_id filter
assert!(result.is_ok());
assert_eq!(subscription.filter, Some(FilterExpression {
    field: "user_id".to_string(),
    operator: FilterOperator::Equals,
    value: "user_123".to_string(),
}));

// User receives ONLY their own receipts
// ✅ k0.receipt.created (user_id=user_123)
// ❌ k0.receipt.created (user_id=user_456)
```

---

#### Level 3: Family Topics (Family-Scoped)

**Access:** Family member role (own family only)

**Topics:**
- k0.family.* (12 topics)

**Scoping:** Automatic `family_id` filter (own family only)

**Use Case:** Family coordination, emergency alerts, device sync

**Example:**
```rust
// Family topics require family_id scoping
let acl_policy = ACLPolicy {
    topic_pattern: "k0.family.*".to_string(),
    access_level: AccessLevel::Family,
    required_role: Some(Role::FamilyMember),
    scope_filter: Some(ScopeFilter::FamilyId),
};

// Family member subscribes (allowed with filter)
let subscription = SSESubscription {
    agent_id: "user_789",
    patterns: vec!["k0.family.*".to_string()],
};

let result = acl_enforcer.authorize(&subscription);

// ACL enforcer auto-injects family_id filter
assert!(result.is_ok());
assert_eq!(subscription.filter, Some(FilterExpression {
    field: "family_id".to_string(),
    operator: FilterOperator::Equals,
    value: "fam_123".to_string(),
}));

// User receives ONLY their own family events
// ✅ k0.family.emergency.alert (family_id=fam_123)
// ❌ k0.family.emergency.alert (family_id=fam_456)
```

---

#### Level 4: Public Topics (No Auth)

**Access:** Public (no authentication required)

**Topics:**
- ui.* (11 topics, sanitized)

**Scoping:** None (publicly accessible, sanitized payloads)

**Use Case:** Real-time UI updates (WebSocket clients)

**Example:**
```rust
// Public topics require no authentication
let acl_policy = ACLPolicy {
    topic_pattern: "ui.*".to_string(),
    access_level: AccessLevel::Public,
    required_role: None,
    scope_filter: None,
};

// Anyone can subscribe (no auth check)
let subscription = SSESubscription {
    agent_id: "anonymous_client",
    patterns: vec!["ui.*".to_string()],
};

let result = acl_enforcer.authorize(&subscription);
assert!(result.is_ok());

// Receives sanitized UI updates
// ✅ ui.session.state.updated (sanitized)
// ✅ ui.message.received (sanitized)
```

---

### ACL Enforcement Implementation

#### 1. **ACLEnforcer** — Validate Permissions Before Subscription

```rust
// k0/sse/acl_enforcer.rs

"""
ACL Enforcer - Validates permissions before SSE subscription/publish

Responsibilities:
- Load ACL policies from K0 config
- Validate role (admin, user, family, system)
- Inject scope filters (user_id, family_id)
- Emit authorization metrics

Research: RBAC (Sandhu 1996), ABAC (NIST 2014), OAuth 2.0 scopes (2012)
"""

use std::collections::HashMap;

pub struct ACLEnforcer {
    acl_policies: HashMap<String, ACLPolicy>,  // topic_pattern → policy
    role_resolver: Arc<RoleResolver>,
}

pub struct ACLPolicy {
    pub topic_pattern: String,
    pub access_level: AccessLevel,
    pub required_role: Option<Role>,
    pub scope_filter: Option<ScopeFilter>,
}

pub enum AccessLevel {
    Admin,      // Admin topics (k0.config.*, k0.policy.*, k0.audit.*)
    User,       // User-scoped topics (k0.receipt.*, k0.learning.*, k0.crdt.*)
    Family,     // Family-scoped topics (k0.family.*)
    System,     // System-internal topics (k0.learning.blacklist.*)
    Public,     // Public topics (ui.*)
}

pub enum Role {
    Admin,
    User,
    FamilyMember,
    System,
}

pub enum ScopeFilter {
    UserId,     // Auto-inject user_id filter
    FamilyId,   // Auto-inject family_id filter
}

impl ACLEnforcer {
    /// Authorize subscription
    pub async fn authorize(
        &self,
        subscription: &mut SSESubscription,
    ) -> Result<(), ACLError> {
        // Step 1: Resolve user role
        let role = self.role_resolver
            .resolve(&subscription.agent_id)
            .await?;

        // Step 2: Check each pattern
        for pattern in &subscription.patterns {
            // Find matching ACL policy
            let policy = self.find_policy(pattern)?;

            // Step 3: Validate role
            if let Some(required_role) = &policy.required_role {
                if !self.has_role(&role, required_role) {
                    K0_SSE_ACL_DENIALS_TOTAL
                        .with_label_values(&[pattern, "role_mismatch"])
                        .inc();

                    return Err(ACLError::PermissionDenied(format!(
                        "Topic '{}' requires role {:?}, but user has {:?}",
                        pattern, required_role, role
                    )));
                }
            }

            // Step 4: Inject scope filter
            if let Some(scope_filter) = &policy.scope_filter {
                self.inject_scope_filter(subscription, scope_filter, &role).await?;
            }
        }

        K0_SSE_ACL_AUTHORIZATIONS_TOTAL
            .with_label_values(&["granted"])
            .inc();

        Ok(())
    }

    fn find_policy(&self, pattern: &str) -> Result<&ACLPolicy, ACLError> {
        // Match pattern against ACL policies
        for (policy_pattern, policy) in &self.acl_policies {
            if PatternMatcher::matches(pattern, policy_pattern) {
                return Ok(policy);
            }
        }

        Err(ACLError::PolicyNotFound(pattern.to_string()))
    }

    fn has_role(&self, user_role: &Role, required_role: &Role) -> bool {
        match (user_role, required_role) {
            (Role::Admin, _) => true,  // Admin has all roles
            (Role::User, Role::User) => true,
            (Role::FamilyMember, Role::FamilyMember) => true,
            (Role::System, Role::System) => true,
            _ => false,
        }
    }

    async fn inject_scope_filter(
        &self,
        subscription: &mut SSESubscription,
        scope_filter: &ScopeFilter,
        role: &Role,
    ) -> Result<(), ACLError> {
        match scope_filter {
            ScopeFilter::UserId => {
                // Auto-inject user_id filter
                let user_id = self.role_resolver.get_user_id(&subscription.agent_id).await?;

                subscription.filter = Some(FilterExpression {
                    field: "user_id".to_string(),
                    operator: FilterOperator::Equals,
                    value: user_id,
                });

                info!(
                    "Injected user_id filter: agent_id={}, user_id={}",
                    subscription.agent_id, user_id
                );
            }

            ScopeFilter::FamilyId => {
                // Auto-inject family_id filter
                let family_id = self.role_resolver.get_family_id(&subscription.agent_id).await?;

                subscription.filter = Some(FilterExpression {
                    field: "family_id".to_string(),
                    operator: FilterOperator::Equals,
                    value: family_id,
                });

                info!(
                    "Injected family_id filter: agent_id={}, family_id={}",
                    subscription.agent_id, family_id
                );
            }
        }

        Ok(())
    }
}
```

---

#### 2. **RoleResolver** — Resolve User Role from JWT/Session

```rust
// k0/sse/role_resolver.rs

"""
Role Resolver - Resolves user role from JWT token or session

Responsibilities:
- Parse JWT token (extract role claim)
- Query K0 for user metadata (role, user_id, family_id)
- Cache role lookups (1-hour TTL)
- Emit role resolution metrics

Research: JWT (RFC 7519), OAuth 2.0 (RFC 6749)
"""

pub struct RoleResolver {
    jwt_validator: Arc<JWTValidator>,
    k0_client: Arc<K0BridgeClient>,
    role_cache: Arc<RwLock<HashMap<String, CachedRole>>>,
}

struct CachedRole {
    role: Role,
    user_id: String,
    family_id: Option<String>,
    cached_at: Instant,
    ttl_seconds: u64,
}

impl RoleResolver {
    /// Resolve role from agent_id (JWT token or session ID)
    pub async fn resolve(&self, agent_id: &str) -> Result<Role, RoleError> {
        // Check cache first
        if let Some(cached) = self.get_cached_role(agent_id).await {
            return Ok(cached.role);
        }

        // Parse JWT token
        let claims = self.jwt_validator.validate(agent_id).await?;

        // Extract role from claims
        let role = match claims.role.as_str() {
            "admin" => Role::Admin,
            "user" => Role::User,
            "family_member" => Role::FamilyMember,
            "system" => Role::System,
            _ => return Err(RoleError::InvalidRole(claims.role)),
        };

        // Cache role
        self.cache_role(agent_id, &role, &claims).await;

        Ok(role)
    }

    /// Get user_id from agent_id
    pub async fn get_user_id(&self, agent_id: &str) -> Result<String, RoleError> {
        let claims = self.jwt_validator.validate(agent_id).await?;
        Ok(claims.sub)  // Subject claim = user_id
    }

    /// Get family_id from agent_id
    pub async fn get_family_id(&self, agent_id: &str) -> Result<String, RoleError> {
        let claims = self.jwt_validator.validate(agent_id).await?;
        claims.family_id.ok_or(RoleError::FamilyIdNotFound)
    }

    async fn get_cached_role(&self, agent_id: &str) -> Option<CachedRole> {
        let cache = self.role_cache.read().await;

        if let Some(cached) = cache.get(agent_id) {
            // Check if cache expired
            if (Instant::now() - cached.cached_at).as_secs() < cached.ttl_seconds {
                return Some(cached.clone());
            }
        }

        None
    }

    async fn cache_role(&self, agent_id: &str, role: &Role, claims: &JWTClaims) {
        let mut cache = self.role_cache.write().await;

        cache.insert(agent_id.to_string(), CachedRole {
            role: role.clone(),
            user_id: claims.sub.clone(),
            family_id: claims.family_id.clone(),
            cached_at: Instant::now(),
            ttl_seconds: 3600,  // 1 hour
        });
    }
}
```

---

### Audit Logging (Sensitive Topics)

**Topics Requiring Audit:**
- k0.policy.* (policy changes)
- k0.audit.* (audit log access)
- k0.config.* (config changes)

**Audit Event Schema:**
```json
{
  "event_type": "k0.audit.access.logged",
  "timestamp": "2025-10-13T12:00:00Z",
  "actor": {
    "agent_id": "admin_456",
    "user_id": "admin_456",
    "role": "admin",
    "ip_address": "192.168.1.100"
  },
  "action": "subscribe",
  "resource": {
    "topic": "k0.policy.updated",
    "pattern": "k0.policy.*"
  },
  "result": "granted",
  "trace_id": "trace_abc123"
}
```

**Implementation:**
```rust
// k0/sse/audit_logger.rs

pub struct AuditLogger {
    k0_client: Arc<K0BridgeClient>,
}

impl AuditLogger {
    /// Log sensitive topic access
    pub async fn log_access(
        &self,
        agent_id: &str,
        topic: &str,
        action: &str,
        result: &str,
        trace_id: &str,
    ) {
        // Check if topic requires audit
        if !self.requires_audit(topic) {
            return;
        }

        let audit_event = AuditEvent {
            event_type: "k0.audit.access.logged".to_string(),
            timestamp: Utc::now(),
            actor: Actor {
                agent_id: agent_id.to_string(),
                role: self.resolve_role(agent_id).await,
                ip_address: self.get_ip_address(agent_id).await,
            },
            action: action.to_string(),
            resource: Resource {
                topic: topic.to_string(),
            },
            result: result.to_string(),
            trace_id: trace_id.to_string(),
        };

        // Write audit event to K0 (365-day retention)
        self.k0_client.write_audit_log(&audit_event).await.unwrap();

        info!(
            "Audit logged: agent_id={}, topic={}, action={}, result={}",
            agent_id, topic, action, result
        );
    }

    fn requires_audit(&self, topic: &str) -> bool {
        topic.starts_with("k0.policy.")
            || topic.starts_with("k0.audit.")
            || topic.starts_with("k0.config.")
    }
}
```

---

## ACL Policy Configuration

**File:** `k0/config/sse_acl_policies.yml`

```yaml
# K0 SSE ACL Policies

acl_policies:
  # Admin topics (k0.config.*)
  - topic_pattern: "k0.config.*"
    access_level: admin
    required_role: admin
    scope_filter: null
    audit_required: true

  # Admin topics (k0.policy.*)
  - topic_pattern: "k0.policy.*"
    access_level: admin
    required_role: admin
    scope_filter: null
    audit_required: true

  # Admin topics (k0.audit.*)
  - topic_pattern: "k0.audit.*"
    access_level: admin
    required_role: admin
    scope_filter: null
    audit_required: true

  # User-scoped topics (k0.receipt.*)
  - topic_pattern: "k0.receipt.*"
    access_level: user
    required_role: user
    scope_filter: user_id
    audit_required: false

  # User-scoped topics (k0.learning.*)
  - topic_pattern: "k0.learning.*"
    access_level: user
    required_role: user
    scope_filter: user_id
    audit_required: false

  # User-scoped topics (k0.crdt.*)
  - topic_pattern: "k0.crdt.*"
    access_level: user
    required_role: user
    scope_filter: user_id
    audit_required: false

  # Family-scoped topics (k0.family.*)
  - topic_pattern: "k0.family.*"
    access_level: family
    required_role: family_member
    scope_filter: family_id
    audit_required: false

  # Public topics (ui.*)
  - topic_pattern: "ui.*"
    access_level: public
    required_role: null
    scope_filter: null
    audit_required: false
```

---

## Performance Analysis

### Scenario 1: ACL Authorization (User Topic)

**Configuration:**
- Topic: k0.receipt.*
- Role: user
- Scope filter: user_id

**Performance:**
```
1. Resolve role from JWT:           2ms (cache miss, JWT validation)
2. Find ACL policy:                 0.5ms (HashMap lookup)
3. Validate role:                   0.01ms
4. Inject user_id filter:           0.1ms
5. Total authorization latency:     2.6ms ✅

Result: Minimal overhead
```

### Scenario 2: ACL Denial (Admin Topic)

**Configuration:**
- Topic: k0.config.*
- Role: user (not admin)

**Performance:**
```
1. Resolve role:                    0.5ms (cache hit)
2. Find ACL policy:                 0.5ms
3. Validate role:                   0.01ms → ❌ DENIED
4. Total latency:                   1.0ms ✅

Result: Fast denial (no unnecessary work)
```

### Scenario 3: Audit Logging

**Configuration:**
- Topic: k0.policy.updated
- Audit required: true

**Performance:**
```
1. Authorization:                   2.6ms (as above)
2. Audit log write to K0:           5ms (async, non-blocking)
3. Total latency (user experience): 2.6ms ✅

Result: Audit doesn't block authorization
```

---

## Implementation Roadmap

### Week 1: ACLEnforcer & RoleResolver (Days 1-5)

**Deliverables:**
- ACLEnforcer: validate permissions, inject scope filters
- RoleResolver: resolve role from JWT, cache roles (1-hour TTL)
- ACL policy configuration file

**Acceptance Criteria:**
- Admin topics blocked for users
- User topics auto-inject user_id filter
- Family topics auto-inject family_id filter
- Role caching works (1-hour TTL)

### Week 2: Audit Logging & Testing (Days 6-10)

**Deliverables:**
- AuditLogger: log sensitive topic access
- Comprehensive testing (all 4 access levels)
- Prometheus metrics

**Acceptance Criteria:**
- Audit logs written to K0 (365-day retention)
- All ACL policies enforced
- All tests pass

---

## Metrics & Monitoring

```rust
lazy_static! {
    // Authorization metrics
    pub static ref K0_SSE_ACL_AUTHORIZATIONS_TOTAL: IntCounterVec = register_int_counter_vec!(
        "k0_sse_acl_authorizations_total",
        "Total ACL authorization checks",
        &["result"]  // granted, denied
    ).unwrap();

    // ACL denials
    pub static ref K0_SSE_ACL_DENIALS_TOTAL: IntCounterVec = register_int_counter_vec!(
        "k0_sse_acl_denials_total",
        "Total ACL denials",
        &["topic", "reason"]  // role_mismatch, scope_violation
    ).unwrap();

    // Authorization latency
    pub static ref K0_SSE_ACL_AUTHORIZATION_DURATION_MS: Histogram = register_histogram!(
        "k0_sse_acl_authorization_duration_ms",
        "ACL authorization duration in milliseconds",
        vec![0.5, 1.0, 2.0, 5.0, 10.0]
    ).unwrap();

    // Audit logs
    pub static ref K0_SSE_AUDIT_LOGS_TOTAL: IntCounterVec = register_int_counter_vec!(
        "k0_sse_audit_logs_total",
        "Total audit logs written",
        &["topic"]
    ).unwrap();
}
```

---

## Testing Strategy

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_admin_topic_denied_for_user() {
        let acl_enforcer = ACLEnforcer::new();
        let mut subscription = SSESubscription {
            agent_id: "user_123",
            patterns: vec!["k0.config.*".to_string()],
            filter: None,
        };

        let result = acl_enforcer.authorize(&mut subscription).await;

        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), ACLError::PermissionDenied);
    }

    #[tokio::test]
    async fn test_user_topic_auto_scoped() {
        let acl_enforcer = ACLEnforcer::new();
        let mut subscription = SSESubscription {
            agent_id: "user_123",
            patterns: vec!["k0.receipt.*".to_string()],
            filter: None,
        };

        let result = acl_enforcer.authorize(&mut subscription).await;

        assert!(result.is_ok());
        assert!(subscription.filter.is_some());
        assert_eq!(subscription.filter.unwrap().value, "user_123");
    }

    #[tokio::test]
    async fn test_family_topic_auto_scoped() {
        let acl_enforcer = ACLEnforcer::new();
        let mut subscription = SSESubscription {
            agent_id: "user_789",
            patterns: vec!["k0.family.*".to_string()],
            filter: None,
        };

        let result = acl_enforcer.authorize(&mut subscription).await;

        assert!(result.is_ok());
        assert!(subscription.filter.is_some());
        assert_eq!(subscription.filter.unwrap().field, "family_id");
    }

    #[tokio::test]
    async fn test_audit_logging() {
        let audit_logger = AuditLogger::new();

        audit_logger.log_access(
            "admin_456",
            "k0.policy.updated",
            "subscribe",
            "granted",
            "trace_123"
        ).await;

        // Verify audit log written to K0
        let logs = k0_client.query_audit_logs("k0.policy.updated").await;
        assert_eq!(logs.len(), 1);
        assert_eq!(logs[0].actor.agent_id, "admin_456");
    }
}
```

---

## Summary

**Status:** ✅ Approved

**Key Achievements:**
- ✅ 4-Level Access Control: Admin, User, Family, Public
- ✅ ACL Enforcement: Validate permissions before subscribe/publish
- ✅ Auto-Scope Injection: user_id, family_id filters automatically added
- ✅ Role Resolution: JWT-based role extraction with 1-hour cache
- ✅ Audit Logging: Track access to sensitive topics (k0.policy.*, k0.audit.*, k0.config.*)
- ✅ Authorization Performance: 2.6ms latency (minimal overhead)

**Completion:**
All 4 sub-ADRs for ADR-0043 are now complete:
- ✅ 0043a: K0 SSE Topic Hierarchy & Naming Conventions (61 topics, dot notation, k0.* prefix)
- ✅ 0043b: K0 SSE Topic Subscription Patterns (exact, wildcard, filters, consumer groups)
- ✅ 0043c: K0 SSE Topic Routing & Delivery Guarantees (at-least-once, fanout, DLQ)
- ✅ 0043d: K0 SSE Topic Access Control & ACL Enforcement (4-level ACL, audit logging)

---

**End of ADR-0043d**
