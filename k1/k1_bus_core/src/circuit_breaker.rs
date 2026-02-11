//! V2-M8-005/006/007: Per-handler Circuit Breaker.
//!
//! Classic three-state circuit breaker FSM applied to each bus handler:
//!
//! ```text
//! CLOSED --(failure_threshold consecutive failures)--> OPEN
//! OPEN   --(cooldown_ms elapsed)----------------------> HALF_OPEN
//! HALF_OPEN --(1 success)-----------------------------> CLOSED
//! HALF_OPEN --(1 failure)-----------------------------> OPEN
//! ```
//!
//! When a handler's circuit is OPEN, the bus skips that handler during
//! dispatch.  After the cooldown period, the circuit transitions to
//! HALF_OPEN and allows a single probe request through.  If the probe
//! succeeds, the circuit closes and normal dispatch resumes.
//!
//! ## Thread Safety
//!
//! `CircuitBreakerRegistry` uses `DashMap<u64, Mutex<CircuitBreaker>>`.
//! Each handler_id maps to its own breaker, and the DashMap provides
//! lock-free reads for the common case (handler exists, circuit closed).

use std::sync::OnceLock;
use std::time::Instant;

use dashmap::DashMap;
use parking_lot::Mutex;

// ---------------------------------------------------------------------------
// Monotonic clock
// ---------------------------------------------------------------------------

fn monotonic_ns() -> u64 {
    static EPOCH: OnceLock<Instant> = OnceLock::new();
    let epoch = EPOCH.get_or_init(Instant::now);
    epoch.elapsed().as_nanos() as u64
}

// ---------------------------------------------------------------------------
// CircuitState
// ---------------------------------------------------------------------------

/// Circuit breaker state.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CircuitState {
    /// Normal operation -- all calls allowed.
    Closed,
    /// Failing -- reject ALL calls until cooldown expires.
    Open,
    /// Probing -- allow a single call to test recovery.
    HalfOpen,
}

impl CircuitState {
    /// Stable string representation (used in Python dict).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Closed => "CLOSED",
            Self::Open => "OPEN",
            Self::HalfOpen => "HALF_OPEN",
        }
    }
}

// ---------------------------------------------------------------------------
// CircuitBreaker -- per-handler instance
// ---------------------------------------------------------------------------

/// Per-handler circuit breaker state machine.
pub(crate) struct CircuitBreaker {
    state: CircuitState,
    consecutive_failures: u32,
    failure_threshold: u32,
    cooldown_ns: u64,
    last_state_change_ns: u64,
}

impl CircuitBreaker {
    pub fn new(failure_threshold: u32, cooldown_ms: u64) -> Self {
        Self {
            state: CircuitState::Closed,
            consecutive_failures: 0,
            failure_threshold,
            cooldown_ns: cooldown_ms * 1_000_000,
            last_state_change_ns: monotonic_ns(),
        }
    }

    /// Check whether the handler call should proceed.
    ///
    /// Returns `true` if the call is allowed.
    ///
    /// Side effect: if OPEN and cooldown elapsed, transitions to HALF_OPEN.
    pub fn allow(&mut self) -> bool {
        match self.state {
            CircuitState::Closed => true,
            CircuitState::Open => {
                let now = monotonic_ns();
                if now.saturating_sub(self.last_state_change_ns) >= self.cooldown_ns {
                    self.state = CircuitState::HalfOpen;
                    self.last_state_change_ns = now;
                    true // Allow probe
                } else {
                    false
                }
            }
            CircuitState::HalfOpen => true, // Allow single probe
        }
    }

    /// Record a successful handler invocation.
    pub fn record_success(&mut self) {
        match self.state {
            CircuitState::Closed => {
                self.consecutive_failures = 0;
            }
            CircuitState::HalfOpen => {
                self.state = CircuitState::Closed;
                self.consecutive_failures = 0;
                self.last_state_change_ns = monotonic_ns();
            }
            CircuitState::Open => {
                // Should not happen if allow() was checked first
            }
        }
    }

    /// Record a failed handler invocation.
    pub fn record_failure(&mut self) {
        match self.state {
            CircuitState::Closed => {
                self.consecutive_failures += 1;
                if self.consecutive_failures >= self.failure_threshold {
                    self.state = CircuitState::Open;
                    self.last_state_change_ns = monotonic_ns();
                }
            }
            CircuitState::HalfOpen => {
                self.state = CircuitState::Open;
                self.consecutive_failures = 0;
                self.last_state_change_ns = monotonic_ns();
            }
            CircuitState::Open => {
                // Should not happen
            }
        }
    }

    /// Reset to CLOSED state.
    pub fn reset(&mut self) {
        self.state = CircuitState::Closed;
        self.consecutive_failures = 0;
        self.last_state_change_ns = monotonic_ns();
    }

    /// Current state.
    pub fn state(&self) -> CircuitState {
        self.state
    }

    /// Number of consecutive failures.
    pub fn consecutive_failures(&self) -> u32 {
        self.consecutive_failures
    }
}

// ---------------------------------------------------------------------------
// CircuitBreakerRegistry -- per-handler DashMap
// ---------------------------------------------------------------------------

/// Thread-safe registry of per-handler circuit breakers.
///
/// Breakers are lazily created on first `allow()` call for a handler_id.
/// Uses DashMap for lock-free reads plus parking_lot::Mutex per breaker.
pub(crate) struct CircuitBreakerRegistry {
    breakers: DashMap<u64, Mutex<CircuitBreaker>>,
    failure_threshold: u32,
    cooldown_ms: u64,
}

impl CircuitBreakerRegistry {
    pub fn new(failure_threshold: u32, cooldown_ms: u64) -> Self {
        Self {
            breakers: DashMap::new(),
            failure_threshold,
            cooldown_ms,
        }
    }

    /// Check if handler call is allowed.  Creates breaker lazily.
    pub fn allow(&self, handler_id: u64) -> bool {
        // Hot path: breaker exists
        if let Some(entry) = self.breakers.get(&handler_id) {
            return entry.value().lock().allow();
        }
        // Cold path: create breaker (first call for this handler)
        self.breakers.entry(handler_id).or_insert_with(|| {
            Mutex::new(CircuitBreaker::new(self.failure_threshold, self.cooldown_ms))
        });
        // Breaker starts Closed, so allow() always returns true initially
        true
    }

    /// Record a successful handler invocation.
    pub fn record_success(&self, handler_id: u64) {
        if let Some(entry) = self.breakers.get(&handler_id) {
            entry.value().lock().record_success();
        }
    }

    /// Record a failed handler invocation.
    pub fn record_failure(&self, handler_id: u64) {
        if let Some(entry) = self.breakers.get(&handler_id) {
            entry.value().lock().record_failure();
        }
        // If breaker doesn't exist yet, create it and record failure
        else {
            self.breakers.entry(handler_id).or_insert_with(|| {
                Mutex::new(CircuitBreaker::new(self.failure_threshold, self.cooldown_ms))
            });
            if let Some(entry) = self.breakers.get(&handler_id) {
                entry.value().lock().record_failure();
            }
        }
    }

    /// Reset a specific handler's circuit breaker.
    pub fn reset(&self, handler_id: u64) {
        if let Some(entry) = self.breakers.get(&handler_id) {
            entry.value().lock().reset();
        }
    }

    /// Get states for all tracked breakers.
    pub fn states(&self) -> Vec<(u64, CircuitState)> {
        self.breakers
            .iter()
            .map(|entry| (*entry.key(), entry.value().lock().state()))
            .collect()
    }

    /// Remove a handler's circuit breaker (called on unsubscribe).
    pub fn remove(&self, handler_id: u64) {
        self.breakers.remove(&handler_id);
    }

    /// Number of tracked breakers.
    #[allow(dead_code)]
    pub fn len(&self) -> usize {
        self.breakers.len()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    // ── CircuitBreaker state machine ────────────────────────────

    #[test]
    fn test_new_is_closed() {
        let cb = CircuitBreaker::new(5, 10000);
        assert_eq!(cb.state(), CircuitState::Closed);
        assert_eq!(cb.consecutive_failures(), 0);
    }

    #[test]
    fn test_allow_when_closed() {
        let mut cb = CircuitBreaker::new(5, 10000);
        assert!(cb.allow());
    }

    #[test]
    fn test_failures_open_circuit() {
        let mut cb = CircuitBreaker::new(3, 10000);
        // 3 consecutive failures should open the circuit
        for _ in 0..3 {
            assert!(cb.allow());
            cb.record_failure();
        }
        assert_eq!(cb.state(), CircuitState::Open);
        assert!(!cb.allow()); // Denied
    }

    #[test]
    fn test_success_resets_failure_count() {
        let mut cb = CircuitBreaker::new(3, 10000);
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.consecutive_failures(), 2);
        cb.record_success(); // Reset
        assert_eq!(cb.consecutive_failures(), 0);
        cb.record_failure(); // Start counting again
        assert_eq!(cb.consecutive_failures(), 1);
    }

    #[test]
    fn test_open_transitions_to_halfopen_after_cooldown() {
        let mut cb = CircuitBreaker::new(1, 1); // 1ms cooldown
        cb.record_failure(); // Opens
        assert_eq!(cb.state(), CircuitState::Open);

        // Wait for cooldown
        thread::sleep(std::time::Duration::from_millis(5));
        assert!(cb.allow()); // Should transition to HalfOpen
        assert_eq!(cb.state(), CircuitState::HalfOpen);
    }

    #[test]
    fn test_halfopen_success_closes() {
        let mut cb = CircuitBreaker::new(1, 1);
        cb.record_failure(); // Open
        thread::sleep(std::time::Duration::from_millis(5));
        cb.allow(); // Transition to HalfOpen

        cb.record_success(); // Probe succeeded
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_halfopen_failure_reopens() {
        let mut cb = CircuitBreaker::new(1, 1);
        cb.record_failure(); // Open
        thread::sleep(std::time::Duration::from_millis(5));
        cb.allow(); // HalfOpen

        cb.record_failure(); // Probe failed
        assert_eq!(cb.state(), CircuitState::Open);
    }

    #[test]
    fn test_reset() {
        let mut cb = CircuitBreaker::new(1, 10000);
        cb.record_failure(); // Open
        assert_eq!(cb.state(), CircuitState::Open);
        cb.reset();
        assert_eq!(cb.state(), CircuitState::Closed);
        assert_eq!(cb.consecutive_failures(), 0);
    }

    #[test]
    fn test_state_string() {
        assert_eq!(CircuitState::Closed.as_str(), "CLOSED");
        assert_eq!(CircuitState::Open.as_str(), "OPEN");
        assert_eq!(CircuitState::HalfOpen.as_str(), "HALF_OPEN");
    }

    // ── CircuitBreakerRegistry ──────────────────────────────────

    #[test]
    fn test_registry_lazy_creation() {
        let reg = CircuitBreakerRegistry::new(5, 10000);
        assert_eq!(reg.len(), 0);
        assert!(reg.allow(42)); // Lazily creates
        assert_eq!(reg.len(), 1);
    }

    #[test]
    fn test_registry_failure_threshold() {
        let reg = CircuitBreakerRegistry::new(2, 10000);
        reg.allow(1); // Create
        reg.record_failure(1);
        assert!(reg.allow(1)); // Still closed (1 failure < 2 threshold)
        reg.record_failure(1);
        assert!(!reg.allow(1)); // Open after 2 failures
    }

    #[test]
    fn test_registry_reset() {
        let reg = CircuitBreakerRegistry::new(1, 10000);
        reg.allow(1);
        reg.record_failure(1);
        assert!(!reg.allow(1)); // Open
        reg.reset(1);
        assert!(reg.allow(1)); // Closed again
    }

    #[test]
    fn test_registry_remove() {
        let reg = CircuitBreakerRegistry::new(5, 10000);
        reg.allow(1);
        assert_eq!(reg.len(), 1);
        reg.remove(1);
        assert_eq!(reg.len(), 0);
    }

    #[test]
    fn test_registry_states() {
        let reg = CircuitBreakerRegistry::new(1, 10000);
        reg.allow(1);
        reg.allow(2);
        reg.record_failure(2); // Open handler 2

        let states = reg.states();
        assert_eq!(states.len(), 2);

        let h1 = states.iter().find(|(id, _)| *id == 1).unwrap();
        assert_eq!(h1.1, CircuitState::Closed);

        let h2 = states.iter().find(|(id, _)| *id == 2).unwrap();
        assert_eq!(h2.1, CircuitState::Open);
    }

    #[test]
    fn test_registry_concurrent_access() {
        use std::sync::Arc;

        let reg = Arc::new(CircuitBreakerRegistry::new(100, 10000));
        let n_threads = 4;
        let n_per_thread = 100;

        let mut handles = Vec::new();
        for t in 0..n_threads {
            let r = reg.clone();
            handles.push(thread::spawn(move || {
                for i in 0..n_per_thread {
                    let hid = (t * 1000 + i) as u64;
                    r.allow(hid);
                    r.record_success(hid);
                }
            }));
        }

        for h in handles {
            h.join().unwrap();
        }

        assert_eq!(reg.len(), n_threads * n_per_thread);
    }
}
