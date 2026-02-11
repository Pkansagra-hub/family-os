//! V2-M8-008/009/010: Built-in Sweep Timer.
//!
//! Background thread that calls a user-supplied closure at a configurable
//! interval.  Designed for periodic timing-chain sweeps (gap buffer
//! timeout release, causal tracker timeouts) but generic enough for
//! any periodic task.
//!
//! ## Features
//!
//! - `parking_lot::Condvar`-based sleep for responsive shutdown
//! - Interval changeable at runtime via `AtomicU64`
//! - `Drop` impl signals thread and joins
//! - Thread-safe: start/stop/set_interval from any thread
//!
//! ## Python Interop
//!
//! ```python
//! from k1_bus_core import SweepTimer
//!
//! counter = {"n": 0}
//! def tick():
//!     counter["n"] += 1
//!
//! timer = SweepTimer(tick, interval_ms=100)
//! time.sleep(0.5)
//! timer.stop()
//! assert counter["n"] >= 3
//! ```

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use parking_lot::{Condvar, Mutex};
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// SweepTimer -- Rust-internal
// ---------------------------------------------------------------------------

/// Background thread that calls `callback()` every `interval_ms` milliseconds.
pub(crate) struct SweepTimer {
    running: Arc<AtomicBool>,
    interval_ms: Arc<AtomicU64>,
    wake: Arc<(Mutex<bool>, Condvar)>,
    handle: Option<thread::JoinHandle<()>>,
}

impl SweepTimer {
    /// Create and start a sweep timer.
    ///
    /// # Arguments
    ///
    /// * `interval_ms` - How often to call the callback (milliseconds).
    /// * `callback` - Closure invoked on each tick.  Must be `Send + 'static`.
    pub fn new(interval_ms: u64, callback: Box<dyn Fn() + Send + 'static>) -> Self {
        let running = Arc::new(AtomicBool::new(true));
        let interval = Arc::new(AtomicU64::new(interval_ms));
        let wake = Arc::new((Mutex::new(false), Condvar::new()));

        let r = running.clone();
        let i = interval.clone();
        let w = wake.clone();

        let handle = thread::Builder::new()
            .name("k1-sweep".into())
            .spawn(move || {
                while r.load(Ordering::Acquire) {
                    let ms = i.load(Ordering::Relaxed);
                    let dur = Duration::from_millis(ms);

                    // Sleep with responsive shutdown via Condvar
                    let (lock, cvar) = &*w;
                    let mut stopped = lock.lock();
                    let result = cvar.wait_for(&mut stopped, dur);

                    if *stopped || !r.load(Ordering::Acquire) {
                        break;
                    }

                    // Timed out normally -- invoke callback
                    if result.timed_out() {
                        callback();
                    }
                }
            })
            .expect("Failed to spawn sweep thread");

        Self {
            running,
            interval_ms: interval,
            wake,
            handle: Some(handle),
        }
    }

    /// Change the sweep interval (hot-reloadable).
    pub fn set_interval(&self, ms: u64) {
        self.interval_ms.store(ms, Ordering::Relaxed);
    }

    /// Current interval in milliseconds.
    pub fn interval(&self) -> u64 {
        self.interval_ms.load(Ordering::Relaxed)
    }

    /// Stop the timer and join the background thread.
    pub fn stop(&mut self) {
        self.running.store(false, Ordering::Release);
        // Signal the condvar to wake the thread immediately
        let (lock, cvar) = &*self.wake;
        let mut stopped = lock.lock();
        *stopped = true;
        cvar.notify_all();
        drop(stopped);

        if let Some(handle) = self.handle.take() {
            handle.join().ok();
        }
    }

    /// Whether the timer thread is still running.
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::Acquire)
    }
}

impl Drop for SweepTimer {
    fn drop(&mut self) {
        self.stop();
    }
}

// ---------------------------------------------------------------------------
// PySweepTimer -- #[pyclass] wrapper
// ---------------------------------------------------------------------------

/// Python-exposed sweep timer.
///
/// Takes a Python callable and invokes it periodically from a Rust
/// background thread.  The GIL is acquired for each callback invocation.
#[pyclass(name = "SweepTimer")]
pub(crate) struct PySweepTimer {
    inner: Option<SweepTimer>,
}

#[pymethods]
impl PySweepTimer {
    /// Create and start a sweep timer.
    ///
    /// Args:
    ///     callback: Python callable invoked on each tick (no arguments).
    ///     interval_ms: Tick interval in milliseconds (default 1000).
    #[new]
    #[pyo3(signature = (callback, interval_ms=1000))]
    fn new(callback: Py<PyAny>, interval_ms: u64) -> PyResult<Self> {
        if interval_ms == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "interval_ms must be > 0",
            ));
        }
        let timer = SweepTimer::new(
            interval_ms,
            Box::new(move || {
                Python::with_gil(|py| {
                    if let Err(e) = callback.call0(py) {
                        // Best-effort: print and continue
                        e.print(py);
                    }
                });
            }),
        );
        Ok(Self {
            inner: Some(timer),
        })
    }

    /// Stop the timer and join the background thread.
    fn stop(&mut self) {
        if let Some(ref mut t) = self.inner {
            t.stop();
        }
    }

    /// Whether the timer is still running.
    #[getter]
    fn is_running(&self) -> bool {
        self.inner.as_ref().map_or(false, |t| t.is_running())
    }

    /// Change the sweep interval (takes effect on next tick).
    fn set_interval(&self, ms: u64) -> PyResult<()> {
        if ms == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "interval_ms must be > 0",
            ));
        }
        if let Some(ref t) = self.inner {
            t.set_interval(ms);
        }
        Ok(())
    }

    /// Current interval in milliseconds.
    #[getter]
    fn interval(&self) -> u64 {
        self.inner.as_ref().map_or(0, |t| t.interval())
    }

    fn __repr__(&self) -> String {
        let running = self.inner.as_ref().map_or(false, |t| t.is_running());
        let interval = self.inner.as_ref().map_or(0, |t| t.interval());
        format!("SweepTimer(running={running}, interval_ms={interval})")
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;

    #[test]
    fn test_timer_ticks() {
        let counter = Arc::new(AtomicUsize::new(0));
        let c = counter.clone();

        let mut timer = SweepTimer::new(
            20, // 20ms interval
            Box::new(move || {
                c.fetch_add(1, Ordering::Relaxed);
            }),
        );

        thread::sleep(Duration::from_millis(150));
        timer.stop();

        let count = counter.load(Ordering::Relaxed);
        // Should have ticked at least 4 times in 150ms with 20ms interval
        assert!(count >= 4, "Expected >= 4 ticks, got {count}");
    }

    #[test]
    fn test_timer_stop() {
        let counter = Arc::new(AtomicUsize::new(0));
        let c = counter.clone();

        let mut timer = SweepTimer::new(
            10,
            Box::new(move || {
                c.fetch_add(1, Ordering::Relaxed);
            }),
        );

        thread::sleep(Duration::from_millis(50));
        timer.stop();
        let count_at_stop = counter.load(Ordering::Relaxed);

        // Wait more -- count should NOT increase
        thread::sleep(Duration::from_millis(50));
        let count_after = counter.load(Ordering::Relaxed);
        assert_eq!(count_at_stop, count_after, "Timer ticked after stop");
    }

    #[test]
    fn test_timer_is_running() {
        let mut timer = SweepTimer::new(100, Box::new(|| {}));
        assert!(timer.is_running());
        timer.stop();
        assert!(!timer.is_running());
    }

    #[test]
    fn test_timer_set_interval() {
        let timer = SweepTimer::new(100, Box::new(|| {}));
        assert_eq!(timer.interval(), 100);
        timer.set_interval(50);
        assert_eq!(timer.interval(), 50);
    }

    #[test]
    fn test_timer_drop_joins_thread() {
        let counter = Arc::new(AtomicUsize::new(0));
        let c = counter.clone();

        {
            let _timer = SweepTimer::new(
                10,
                Box::new(move || {
                    c.fetch_add(1, Ordering::Relaxed);
                }),
            );
            thread::sleep(Duration::from_millis(50));
            // Timer dropped here -- should stop the thread
        }

        let count_at_drop = counter.load(Ordering::Relaxed);
        thread::sleep(Duration::from_millis(50));
        let count_after = counter.load(Ordering::Relaxed);
        assert_eq!(count_at_drop, count_after, "Timer ticked after drop");
    }

    #[test]
    fn test_responsive_shutdown() {
        let mut timer = SweepTimer::new(
            10_000, // 10 second interval -- would block for 10s without responsive shutdown
            Box::new(|| {}),
        );

        let start = Instant::now();
        timer.stop();
        let elapsed = start.elapsed();

        // Stop should return quickly (< 1 second), not wait 10 seconds
        assert!(
            elapsed < Duration::from_secs(1),
            "Stop took {:?}, expected < 1s",
            elapsed,
        );
    }
}
