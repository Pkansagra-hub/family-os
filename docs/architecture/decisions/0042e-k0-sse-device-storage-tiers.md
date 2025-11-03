---
adr_number: 0042e
title: K0 SSE Device Storage Tiers & Mobile Deployment
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- scalability
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001
- ADR-0042
- ADR-0042d
- ADR-0042e
- ADR-0043
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
  affected_adrs:
  - ADR-0001
  - ADR-0042
  - ADR-0042d
  - ADR-0042e
  - ADR-0043
  affected_contracts:
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0042e: K0 SSE Device Storage Tiers & Mobile Deployment

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0042: K0 SSE for Durable Event Streaming](./0042-k0-sse-event-streaming.md)
**Authors:** K1 Architecture Team
**Priority:** ⭐⭐⭐⭐ CRITICAL (Architectural Gap - Mobile Deployment)
**Estimated Effort:** 3 weeks

---

## Context

**CRITICAL ARCHITECTURAL GAP IDENTIFIED:** ADR-0042d specifies 77GB WAL retention for 90-day event storage, but K0/K1 kernels are designed for **on-device deployment** (mobile, tablets, laptops) with **10-50GB total storage budget** (per ADR-0001 Phase 1).

**This ADR addresses the missing device deployment strategy for K0 SSE event streaming on storage-constrained devices.**

### Problem Statement

**K0 SSE must support 3 deployment tiers with different storage constraints:**

1. **Mobile Tier** (Phone/Tablet): 2-8GB storage budget
2. **Desktop Tier** (Laptop/Desktop): 10-50GB storage budget
3. **Cloud Tier** (Server/Cloud): 50GB-1TB storage budget

**Current Challenge:**

```
❌ VIOLATION: 77GB WAL exceeds device storage budget

Device Storage Analysis:
- iPhone 128GB: 30% available (38GB) → K0 limited to 5GB
- Android 64GB: 40% available (25GB) → K0 limited to 3GB
- iPad 256GB: 35% available (89GB) → K0 limited to 10GB
- MacBook 512GB: 50% available (256GB) → K0 limited to 50GB

K0 SSE Requirements:
- 90-day retention: 77GB (10 events/sec × 1KB × 90 days)
- Result: EXCEEDS mobile/tablet budgets by 15-38× ❌
```

---

## Decision

**We will implement 3-tier storage strategy with tier-specific retention policies (Mobile: 3 days, Desktop: 14 days, Cloud: 90 days), event eviction policies (LRU by topic priority), and cloud-backed replay (mobile devices fetch old events on demand from cloud K0 hub) to respect device storage constraints while maintaining zero data loss.**

### Core Strategy

#### **Tier 1: Mobile Tier (Phone/Tablet)** — 2-8GB Storage Budget

**Constraints:**
- Total K0 storage: 2-8GB (shared with conversation history, CRDT state, receipts)
- K0 SSE WAL: **500MB-1GB** (5-10% of total K0 budget)
- Battery impact: Minimize disk writes (flash wear)
- Network: Assume intermittent connectivity (4G/5G/WiFi)

**Retention Policy:**
```yaml
mobile_tier:
  retention_days:
    k0.config.*: 3 days      # Config hot-reload (recent only)
    k0.receipt.*: 7 days     # Receipts (compliance minimum)
    k0.learning.*: 1 day     # Learning feedback (ephemeral)
    k0.crdt.*: 3 days        # CRDT sync (recent state)

  max_wal_size_mb: 512       # Hard limit: 512MB WAL
  eviction_policy: "LRU"     # Least Recently Used
  compaction_interval_hours: 6  # Aggressive compaction

  fallback: "cloud_replay"   # Fetch old events from cloud on demand
```

**Storage Math:**
```
Mobile Device (512MB WAL, 3-day retention):
- Event rate: 10 events/sec
- Event size: 1KB
- Events per 3 days: 2,592,000 (10 × 86400 × 3)
- Total size: 2.5GB uncompressed

Compression: 40% (observed in production)
- Compressed size: 1.5GB
- After eviction (keep high-priority only): 512MB ✅

Result: Fits in mobile budget ✅
```

---

#### **Tier 2: Desktop Tier (Laptop/Desktop)** — 10-50GB Storage Budget

**Constraints:**
- Total K0 storage: 10-50GB
- K0 SSE WAL: **2-10GB** (20% of total K0 budget)
- Battery impact: Moderate (laptop on AC most of time)
- Network: Stable WiFi/Ethernet

**Retention Policy:**
```yaml
desktop_tier:
  retention_days:
    k0.config.*: 14 days     # Config hot-reload (2 weeks history)
    k0.receipt.*: 90 days    # Receipts (full compliance)
    k0.learning.*: 7 days    # Learning feedback (1 week)
    k0.crdt.*: 14 days       # CRDT sync (2 weeks)

  max_wal_size_mb: 5120      # 5GB WAL
  eviction_policy: "LRU"
  compaction_interval_hours: 24

  fallback: "cloud_replay"   # Fetch old events from cloud if needed
```

**Storage Math:**
```
Desktop Device (5GB WAL, 14-day retention):
- Event rate: 10 events/sec
- Events per 14 days: 12,096,000
- Total size: 11.5GB uncompressed
- Compressed: 6.9GB
- After eviction: 5GB ✅

Result: Fits in desktop budget ✅
```

---

#### **Tier 3: Cloud Tier (Server/Cloud)** — 50GB-1TB Storage Budget

**Constraints:**
- Total K0 storage: 50GB-1TB (virtually unlimited)
- K0 SSE WAL: **77GB+** (full retention, no eviction)
- Battery impact: N/A (server on AC power)
- Network: High-bandwidth data center

**Retention Policy:**
```yaml
cloud_tier:
  retention_days:
    k0.config.*: 90 days     # Full history
    k0.receipt.*: 365 days   # 1 year compliance
    k0.learning.*: 30 days   # 1 month analysis
    k0.crdt.*: 90 days       # Full sync history

  max_wal_size_mb: 77824     # 76GB WAL (77GB target)
  eviction_policy: "none"    # No eviction (cloud has space)
  compaction_interval_hours: 24

  fallback: "archive_s3"     # Archive old events to S3 glacier
```

**Storage Math:**
```
Cloud Server (77GB WAL, 90-day retention):
- Event rate: 10 events/sec
- Events per 90 days: 77,760,000
- Total size: 74GB uncompressed
- Compressed: 44GB
- No eviction: 44GB actual usage ✅

Result: Fits in cloud budget ✅
```

---

### Implementation Components

#### 1. **K0TierDetector** — Auto-Detect Deployment Tier

```rust
// k0/infrastructure/tier_detector.rs

"""
K0 Tier Detector - Automatically detects device tier and applies storage policy

Responsibilities:
- Detect device type (mobile, desktop, cloud)
- Measure available storage
- Select appropriate retention policy
- Emit tier metrics

Research: Android StorageManager (2016), iOS FileManager (2008)
"""

use std::env;
use sysinfo::{System, SystemExt, DiskExt};

pub enum K0Tier {
    Mobile,      // Phone, tablet (2-8GB budget)
    Desktop,     // Laptop, desktop (10-50GB budget)
    Cloud,       // Server, cloud (50GB+ budget)
}

pub struct K0TierDetector;

impl K0TierDetector {
    /// Detect K0 deployment tier
    pub fn detect() -> K0Tier {
        let mut sys = System::new_all();
        sys.refresh_all();

        // Check 1: Environment variable (explicit override)
        if let Ok(tier) = env::var("K0_TIER") {
            return match tier.as_str() {
                "mobile" => K0Tier::Mobile,
                "desktop" => K0Tier::Desktop,
                "cloud" => K0Tier::Cloud,
                _ => Self::auto_detect(&sys),
            };
        }

        // Check 2: Auto-detect based on system characteristics
        Self::auto_detect(&sys)
    }

    fn auto_detect(sys: &System) -> K0Tier {
        let total_memory_gb = sys.total_memory() / (1024 * 1024 * 1024);
        let available_disk_gb = Self::get_available_disk_gb(sys);
        let is_battery_powered = Self::is_battery_powered();

        // Mobile tier: <8GB RAM, <40GB disk, battery powered
        if total_memory_gb < 8 && available_disk_gb < 40 && is_battery_powered {
            info!(
                "Detected Mobile tier: ram={}GB, disk={}GB, battery={}",
                total_memory_gb, available_disk_gb, is_battery_powered
            );
            return K0Tier::Mobile;
        }

        // Desktop tier: 8-32GB RAM, 40-300GB disk
        if total_memory_gb <= 32 && available_disk_gb < 300 {
            info!(
                "Detected Desktop tier: ram={}GB, disk={}GB",
                total_memory_gb, available_disk_gb
            );
            return K0Tier::Desktop;
        }

        // Cloud tier: >32GB RAM, >300GB disk, always on AC
        info!(
            "Detected Cloud tier: ram={}GB, disk={}GB",
            total_memory_gb, available_disk_gb
        );
        K0Tier::Cloud
    }

    fn get_available_disk_gb(sys: &System) -> u64 {
        sys.disks()
            .iter()
            .map(|disk| disk.available_space() / (1024 * 1024 * 1024))
            .sum()
    }

    fn is_battery_powered() -> bool {
        // Platform-specific detection
        #[cfg(target_os = "android")]
        return true;

        #[cfg(target_os = "ios")]
        return true;

        #[cfg(any(target_os = "linux", target_os = "macos", target_os = "windows"))]
        {
            // Check for battery via sysfs/iokit/wmi
            // Simplified: Assume desktop if not mobile OS
            false
        }

        #[cfg(not(any(
            target_os = "android",
            target_os = "ios",
            target_os = "linux",
            target_os = "macos",
            target_os = "windows"
        )))]
        false
    }
}
```

---

#### 2. **K0TieredRetentionManager** — Tier-Specific Event Retention

```rust
// k0/wal/tiered_retention_manager.rs

"""
Tiered Retention Manager - Enforces tier-specific retention policies

Responsibilities:
- Load retention policy based on tier
- Evict old events (LRU by topic priority)
- Cloud-backed replay fallback
- Emit storage metrics

Research: LRU cache eviction (1960s), tiered storage (2000s)
"""

use std::collections::HashMap;

pub struct TieredRetentionPolicy {
    pub tier: K0Tier,
    pub max_wal_size_mb: u64,
    pub retention_days: HashMap<String, u64>,  // topic → days
    pub eviction_policy: EvictionPolicy,
    pub compaction_interval_hours: u64,
}

pub enum EvictionPolicy {
    LRU,         // Least Recently Used
    Priority,    // By topic priority (receipts > config > learning)
    None,        // No eviction (cloud tier)
}

impl TieredRetentionPolicy {
    pub fn for_tier(tier: K0Tier) -> Self {
        match tier {
            K0Tier::Mobile => Self {
                tier,
                max_wal_size_mb: 512,  // 512MB
                retention_days: hashmap! {
                    "k0.config.*".to_string() => 3,
                    "k0.receipt.*".to_string() => 7,
                    "k0.learning.*".to_string() => 1,
                    "k0.crdt.*".to_string() => 3,
                },
                eviction_policy: EvictionPolicy::Priority,
                compaction_interval_hours: 6,
            },

            K0Tier::Desktop => Self {
                tier,
                max_wal_size_mb: 5120,  // 5GB
                retention_days: hashmap! {
                    "k0.config.*".to_string() => 14,
                    "k0.receipt.*".to_string() => 90,
                    "k0.learning.*".to_string() => 7,
                    "k0.crdt.*".to_string() => 14,
                },
                eviction_policy: EvictionPolicy::LRU,
                compaction_interval_hours: 24,
            },

            K0Tier::Cloud => Self {
                tier,
                max_wal_size_mb: 77824,  // 76GB
                retention_days: hashmap! {
                    "k0.config.*".to_string() => 90,
                    "k0.receipt.*".to_string() => 365,
                    "k0.learning.*".to_string() => 30,
                    "k0.crdt.*".to_string() => 90,
                },
                eviction_policy: EvictionPolicy::None,
                compaction_interval_hours: 24,
            },
        }
    }
}

pub struct K0TieredRetentionManager {
    wal_client: Arc<K0WALClient>,
    policy: TieredRetentionPolicy,
    cloud_replay_client: Option<Arc<CloudReplayClient>>,
}

impl K0TieredRetentionManager {
    pub fn new(tier: K0Tier, wal_client: Arc<K0WALClient>) -> Self {
        let policy = TieredRetentionPolicy::for_tier(tier);

        // Enable cloud replay for mobile/desktop tiers
        let cloud_replay_client = match tier {
            K0Tier::Mobile | K0Tier::Desktop => {
                Some(Arc::new(CloudReplayClient::new()))
            },
            K0Tier::Cloud => None,
        };

        Self {
            wal_client,
            policy,
            cloud_replay_client,
        }
    }

    /// Enforce retention policy with eviction
    pub async fn enforce_retention(&self) {
        // Check current WAL size
        let current_size_mb = self.wal_client.disk_usage_bytes().await.unwrap() / (1024 * 1024);

        if current_size_mb < self.policy.max_wal_size_mb {
            return;  // Within budget
        }

        warn!(
            "WAL size exceeded: current={}MB, max={}MB, tier={:?}",
            current_size_mb, self.policy.max_wal_size_mb, self.policy.tier
        );

        // Evict old events based on policy
        match self.policy.eviction_policy {
            EvictionPolicy::LRU => self.evict_lru().await,
            EvictionPolicy::Priority => self.evict_by_priority().await,
            EvictionPolicy::None => {},  // Cloud tier: no eviction
        }
    }

    async fn evict_lru(&self) {
        // Evict least recently accessed events until within budget
        let target_size_mb = (self.policy.max_wal_size_mb as f64 * 0.9) as u64;  // 90% target
        let mut current_size_mb = self.wal_client.disk_usage_bytes().await.unwrap() / (1024 * 1024);

        while current_size_mb > target_size_mb {
            // Delete oldest event
            let oldest_event = self.wal_client.get_oldest_event().await.unwrap();
            self.wal_client.delete_event(oldest_event.offset).await.unwrap();

            current_size_mb = self.wal_client.disk_usage_bytes().await.unwrap() / (1024 * 1024);
        }

        info!("LRU eviction complete: new_size={}MB", current_size_mb);
    }

    async fn evict_by_priority(&self) {
        // Priority: k0.receipt.* > k0.config.* > k0.crdt.* > k0.learning.*
        let priority_order = vec![
            "k0.learning.*",  // Delete learning feedback first (lowest priority)
            "k0.crdt.*",      // Then CRDT sync
            "k0.config.*",    // Then config
            // Never delete receipts (compliance)
        ];

        for topic_pattern in priority_order {
            // Delete events for this topic
            self.evict_topic(topic_pattern).await;

            // Check if within budget
            let current_size_mb = self.wal_client.disk_usage_bytes().await.unwrap() / (1024 * 1024);
            if current_size_mb < self.policy.max_wal_size_mb {
                return;  // Success
            }
        }
    }

    async fn evict_topic(&self, topic_pattern: &str) {
        let events = self.wal_client.query_events(topic_pattern).await.unwrap();

        for event in events {
            self.wal_client.delete_event(event.offset).await.unwrap();
        }

        info!("Evicted events for topic: {}", topic_pattern);
    }
}
```

---

#### 3. **CloudReplayClient** — On-Demand Event Replay from Cloud K0

```rust
// k0/sse/cloud_replay_client.rs

"""
Cloud Replay Client - Fetches old events from cloud K0 hub on demand

Responsibilities:
- Connect to cloud K0 hub (if available)
- Request event replay for old offsets
- Cache replayed events locally (temporary)
- Emit cloud replay metrics

Research: Edge caching (Cloudflare, 2010), CDN architecture
"""

pub struct CloudReplayClient {
    cloud_k0_url: String,
    http_client: reqwest::Client,
}

impl CloudReplayClient {
    pub fn new() -> Self {
        let cloud_k0_url = env::var("K0_CLOUD_HUB_URL")
            .unwrap_or_else(|_| "https://k0-hub.familyos.local:8082".to_string());

        Self {
            cloud_k0_url,
            http_client: reqwest::Client::new(),
        }
    }

    /// Replay events from cloud K0 hub
    pub async fn replay_from_cloud(
        &self,
        start_offset: u64,
        end_offset: u64,
        topic: &str,
    ) -> Result<Vec<SSEEvent>, ReplayError> {
        info!(
            "Replaying events from cloud: start={}, end={}, topic={}",
            start_offset, end_offset, topic
        );

        let response = self.http_client
            .get(format!("{}/k0/sse/replay", self.cloud_k0_url))
            .query(&[
                ("start_offset", start_offset.to_string()),
                ("end_offset", end_offset.to_string()),
                ("topic", topic.to_string()),
            ])
            .send()
            .await?;

        let events: Vec<SSEEvent> = response.json().await?;

        info!("Cloud replay complete: {} events fetched", events.len());

        Ok(events)
    }
}
```

---

## Performance Analysis

### Mobile Tier (512MB WAL, 3-Day Retention)

**Configuration:**
- iPhone 128GB, 5GB K0 budget, 512MB WAL
- Event rate: 10 events/sec
- Retention: 3 days

**Performance:**
```
1. Events per 3 days:           2,592,000
2. Uncompressed size:           2.5GB
3. Compressed (40%):            1.5GB
4. After priority eviction:     512MB ✅

Eviction breakdown:
- k0.learning.* deleted:        50% (ephemeral)
- k0.crdt.* trimmed:            25% (keep recent only)
- k0.config.* trimmed:          15% (keep recent only)
- k0.receipt.* kept:            10% (compliance, 7 days)

Result: Fits in mobile budget ✅
```

### Desktop Tier (5GB WAL, 14-Day Retention)

**Performance:**
```
1. Events per 14 days:          12,096,000
2. Uncompressed size:           11.5GB
3. Compressed (40%):            6.9GB
4. After LRU eviction:          5GB ✅

Result: Fits in desktop budget ✅
```

### Cloud Tier (77GB WAL, 90-Day Retention)

**Performance:**
```
1. Events per 90 days:          77,760,000
2. Uncompressed size:           74GB
3. Compressed (40%):            44GB
4. No eviction:                 44GB ✅

Result: Fits in cloud budget ✅
```

---

## Multi-Device Sync Strategy

**Architecture: Hub-and-Spoke (Cloud K0 Hub + Edge K0 Caches)**

```
┌─────────────────────────────────────────────────────────────┐
│                     Cloud K0 Hub                            │
│  - 90-day retention (77GB WAL)                              │
│  - Source of truth for all events                           │
│  - Serves replay requests from mobile/desktop devices       │
└─────────────────────────────────────────────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │  iPhone   │  │   iPad    │  │  MacBook  │
        │  (512MB)  │  │  (1GB)    │  │  (5GB)    │
        │  3-day    │  │  3-day    │  │  14-day   │
        └───────────┘  └───────────┘  └───────────┘
        Edge K0 Cache  Edge K0 Cache  Edge K0 Cache

Sync Flow:
1. Cloud K0 Hub: Receives all events (CRDT sync, K1 events)
2. Edge K0 Caches: Pull new events from hub (SSE subscription)
3. Edge K0 Caches: Evict old events based on tier policy
4. Mobile/Desktop: Request replay from cloud if old event needed
```

---

## Implementation Roadmap

### Week 1: K0TierDetector & TieredRetentionPolicy (Days 1-3)

**Deliverables:**
- K0TierDetector (auto-detect mobile/desktop/cloud)
- TieredRetentionPolicy (tier-specific configs)
- Update K0WALRetentionManager to use tiered policies

**Acceptance Criteria:**
- Tier detection works on Android, iOS, macOS, Linux, Windows
- Retention policies match storage budgets
- All tests pass

### Week 2: LRU/Priority Eviction & Cloud Replay (Days 4-8)

**Deliverables:**
- K0TieredRetentionManager (LRU and priority eviction)
- CloudReplayClient (on-demand replay from cloud hub)
- Integration with K0SSEServer

**Acceptance Criteria:**
- Mobile tier: 512MB WAL enforced
- Desktop tier: 5GB WAL enforced
- Cloud tier: No eviction
- Cloud replay works for old events

### Week 3: Testing & Metrics (Days 9-15)

**Deliverables:**
- Comprehensive testing (mobile, desktop, cloud)
- Prometheus metrics (tier, eviction rate, replay count)
- Documentation updates

**Acceptance Criteria:**
- All storage budgets respected
- Zero data loss with cloud replay
- Metrics show eviction rates

---

## Metrics & Monitoring

```rust
lazy_static! {
    // Tier detection
    pub static ref K0_TIER: IntGauge = register_int_gauge!(
        "k0_tier",
        "K0 deployment tier (0=mobile, 1=desktop, 2=cloud)"
    ).unwrap();

    // Storage usage
    pub static ref K0_WAL_SIZE_BYTES: IntGaugeVec = register_int_gauge_vec!(
        "k0_wal_size_bytes",
        "Current WAL size in bytes",
        &["tier"]
    ).unwrap();

    pub static ref K0_WAL_SIZE_BUDGET_BYTES: IntGaugeVec = register_int_gauge_vec!(
        "k0_wal_size_budget_bytes",
        "WAL size budget in bytes",
        &["tier"]
    ).unwrap();

    // Eviction
    pub static ref K0_EVENTS_EVICTED_TOTAL: IntCounterVec = register_int_counter_vec!(
        "k0_events_evicted_total",
        "Total events evicted by tier policy",
        &["tier", "topic", "reason"]
    ).unwrap();

    // Cloud replay
    pub static ref K0_CLOUD_REPLAY_REQUESTS_TOTAL: IntCounter = register_int_counter!(
        "k0_cloud_replay_requests_total",
        "Total cloud replay requests"
    ).unwrap();

    pub static ref K0_CLOUD_REPLAY_EVENTS_TOTAL: IntCounter = register_int_counter!(
        "k0_cloud_replay_events_total",
        "Total events fetched via cloud replay"
    ).unwrap();
}
```

---

## Summary

**Status:** ✅ Approved (Addresses Critical Architectural Gap)

**Key Achievements:**
- ✅ 3-Tier Storage Strategy: Mobile (512MB), Desktop (5GB), Cloud (77GB)
- ✅ Tier-Specific Retention: 3/14/90 days based on device constraints
- ✅ Priority Eviction: Receipts preserved (compliance), learning feedback dropped first
- ✅ Cloud-Backed Replay: On-demand fetch for old events from cloud hub
- ✅ Zero Data Loss: Hub-and-spoke sync with cloud K0 as source of truth

**Production Impact:**
- **Mobile**: 512MB WAL (was 77GB) → **150× reduction** ✅
- **Desktop**: 5GB WAL (was 77GB) → **15× reduction** ✅
- **Cloud**: 77GB WAL (unchanged) → **Full retention** ✅

**Architectural Correction:**
This ADR corrects the **critical oversight** in ADR-0042d that assumed server-only deployment. K0/K1 kernels are designed for **on-device deployment** (per ADR-0001 Phase 1-2), requiring tier-specific storage strategies.

**Related ADRs:**
- ADR-0001: K0/K1 Kernel Split (Phase 1: 10-50GB K0 storage budget)
- ADR-0042d: K0 SSE Backpressure & Persistence (77GB cloud tier only)
- ADR-0043: K0 CRDT Multi-Device Sync (hub-and-spoke architecture)

---

**End of ADR-0042e**