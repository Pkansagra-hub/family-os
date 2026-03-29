//! LMAX Disruptor-pattern ring buffer for zero-alloc dispatch.
//!
//! Pre-allocated fixed-size slots, cache-line padded cursors, power-of-2
//! capacity for bitwise modulo.  Designed for single-producer,
//! multi-consumer fan-out with independent consumer cursors.
//!
//! ## Design (V2-M4-006 through V2-M4-010)
//!
//! - Fixed-size slots: each slot holds up to `slot_size` bytes (default 64KB).
//! - Power-of-2 capacity: `index = cursor & (capacity - 1)` (bitwise, no division).
//! - Cache-line padded cursors: `#[repr(align(64))]` to prevent false sharing.
//! - CAS-based publish: `publisher_cursor.compare_exchange`.
//! - Multi-consumer fan-out: each consumer group has its own cursor.
//! - Backpressure strategies: Error (default), Block (spin-wait), DropOldest.
//!
//! ## Thread Safety
//!
//! The ring buffer is `Send + Sync`.  Publisher uses CAS on the publisher
//! cursor.  Consumers advance their own cursors independently.
//!
//! ## Python interop
//!
//! Exposed as `#[pyclass]` for testing only (not part of the public bus API).

use std::sync::atomic::{AtomicU64, Ordering};

use pyo3::prelude::*;
use pyo3::types::PyBytes;

// ─── Backpressure strategy ──────────────────────────────────────────

/// What to do when the ring buffer is full.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackpressureStrategy {
    /// Return an error immediately.
    Error,
    /// Spin-wait until space becomes available.
    Block,
    /// Overwrite the oldest unread slot.
    DropOldest,
}

// ─── Cache-line padded cursor ───────────────────────────────────────

/// Cache-line padded atomic cursor to prevent false sharing.
///
/// On x86-64, a cache line is 64 bytes.  The AtomicU64 is 8 bytes,
/// so we pad to 64 bytes total.
#[repr(align(64))]
struct PaddedCursor {
    value: AtomicU64,
}

impl PaddedCursor {
    fn new(val: u64) -> Self {
        Self {
            value: AtomicU64::new(val),
        }
    }

    fn load(&self) -> u64 {
        self.value.load(Ordering::Acquire)
    }

    fn store(&self, val: u64) {
        self.value.store(val, Ordering::Release);
    }

    #[allow(dead_code)]
    fn compare_exchange(&self, current: u64, new: u64) -> Result<u64, u64> {
        self.value
            .compare_exchange(current, new, Ordering::AcqRel, Ordering::Acquire)
    }
}

// ─── Slot ───────────────────────────────────────────────────────────

/// A ring buffer slot holding variable-length data within a fixed-size allocation.
struct Slot {
    /// Pre-allocated buffer of `slot_size` bytes.
    data: Vec<u8>,
    /// How many bytes of `data` are actually used.
    len: usize,
}

impl Slot {
    fn new(slot_size: usize) -> Self {
        Self {
            data: vec![0u8; slot_size],
            len: 0,
        }
    }

    fn write(&mut self, bytes: &[u8]) -> Result<(), String> {
        if bytes.len() > self.data.len() {
            return Err(format!(
                "Data too large for slot: {} bytes > {} slot_size",
                bytes.len(),
                self.data.len()
            ));
        }
        self.data[..bytes.len()].copy_from_slice(bytes);
        self.len = bytes.len();
        Ok(())
    }

    fn read(&self) -> &[u8] {
        &self.data[..self.len]
    }
}

// ─── RingBuffer (Rust internal) ─────────────────────────────────────

/// LMAX Disruptor-pattern ring buffer.
///
/// Single-producer, multi-consumer.  The publisher writes to the next slot
/// via CAS on the publisher cursor.  Each consumer group has an independent
/// cursor and advances at its own pace.
pub struct RingBufferInner {
    slots: Vec<parking_lot::RwLock<Slot>>,
    capacity: usize,
    mask: u64, // capacity - 1, for bitwise modulo
    slot_size: usize,
    publisher_cursor: PaddedCursor,
    consumer_cursors: Vec<PaddedCursor>,
    backpressure: BackpressureStrategy,
    /// Total number of writes (may wrap past capacity for large volumes).
    total_writes: AtomicU64,
    /// Number of dropped messages (DropOldest strategy).
    total_drops: AtomicU64,
}

impl RingBufferInner {
    /// Create a new ring buffer.
    ///
    /// `capacity` is rounded up to the next power of 2.
    /// `slot_size` is the maximum bytes per slot (default 65536 = 64KB).
    /// `num_consumers` is the number of consumer groups.
    pub fn new(
        capacity: usize,
        slot_size: usize,
        num_consumers: usize,
        backpressure: BackpressureStrategy,
    ) -> Self {
        let capacity = capacity.next_power_of_two();
        let mask = (capacity - 1) as u64;

        let slots: Vec<_> = (0..capacity)
            .map(|_| parking_lot::RwLock::new(Slot::new(slot_size)))
            .collect();

        let consumer_cursors: Vec<_> = (0..num_consumers)
            .map(|_| PaddedCursor::new(0))
            .collect();

        Self {
            slots,
            capacity,
            mask,
            slot_size,
            publisher_cursor: PaddedCursor::new(0),
            consumer_cursors,
            backpressure,
            total_writes: AtomicU64::new(0),
            total_drops: AtomicU64::new(0),
        }
    }

    /// Write data to the ring buffer.
    ///
    /// Returns the slot sequence number on success.
    pub fn write(&self, data: &[u8]) -> Result<u64, String> {
        if data.len() > self.slot_size {
            return Err(format!(
                "Data too large: {} bytes > {} slot_size",
                data.len(),
                self.slot_size
            ));
        }

        loop {
            let pub_cursor = self.publisher_cursor.load();
            let next = pub_cursor + 1;

            // Check if ring is full (publisher would lap the slowest consumer)
            if !self.consumer_cursors.is_empty() {
                let min_consumer = self
                    .consumer_cursors
                    .iter()
                    .map(|c| c.load())
                    .min()
                    .unwrap_or(0);

                if next - min_consumer > self.capacity as u64 {
                    match self.backpressure {
                        BackpressureStrategy::Error => {
                            return Err("Ring buffer full".to_string());
                        }
                        BackpressureStrategy::Block => {
                            // Spin-wait (yield to reduce CPU burn)
                            std::thread::yield_now();
                            continue;
                        }
                        BackpressureStrategy::DropOldest => {
                            // Advance the slowest consumer to make room
                            for c in &self.consumer_cursors {
                                let cv = c.load();
                                if next - cv > self.capacity as u64 {
                                    c.store(next - self.capacity as u64);
                                }
                            }
                            self.total_drops.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                }
            }

            // CAS to claim the slot
            match self
                .publisher_cursor
                .compare_exchange(pub_cursor, next)
            {
                Ok(_) => {
                    let idx = (pub_cursor & self.mask) as usize;
                    let mut slot = self.slots[idx].write();
                    slot.write(data)?;
                    self.total_writes.fetch_add(1, Ordering::Relaxed);
                    return Ok(pub_cursor);
                }
                Err(_) => {
                    // Another writer got there first (shouldn't happen in single-producer,
                    // but handle gracefully).  Retry.
                    continue;
                }
            }
        }
    }

    /// Read data from the ring buffer for consumer `consumer_id`.
    ///
    /// Returns `None` if no new data is available.
    /// On success, returns the data bytes and advances the consumer cursor.
    pub fn read(&self, consumer_id: usize) -> Result<Option<Vec<u8>>, String> {
        if consumer_id >= self.consumer_cursors.len() {
            return Err(format!(
                "Invalid consumer_id: {} (have {})",
                consumer_id,
                self.consumer_cursors.len()
            ));
        }

        let consumer_cursor = self.consumer_cursors[consumer_id].load();
        let pub_cursor = self.publisher_cursor.load();

        if consumer_cursor >= pub_cursor {
            return Ok(None); // No new data
        }

        let idx = (consumer_cursor & self.mask) as usize;
        let slot = self.slots[idx].read();
        let data = slot.read().to_vec();

        // Advance consumer cursor
        self.consumer_cursors[consumer_id].store(consumer_cursor + 1);

        Ok(Some(data))
    }

    /// Add a new consumer group.  Returns the consumer_id.
    pub fn add_consumer(&mut self) -> usize {
        let id = self.consumer_cursors.len();
        // New consumer starts at the current publisher position
        // (won't see historical data)
        let pos = self.publisher_cursor.load();
        self.consumer_cursors.push(PaddedCursor::new(pos));
        id
    }

    /// Number of unread items for a specific consumer.
    pub fn pending(&self, consumer_id: usize) -> u64 {
        if consumer_id >= self.consumer_cursors.len() {
            return 0;
        }
        let pub_cursor = self.publisher_cursor.load();
        let con_cursor = self.consumer_cursors[consumer_id].load();
        pub_cursor.saturating_sub(con_cursor)
    }

    /// Ring buffer utilization (0.0 to 1.0) based on slowest consumer.
    pub fn utilization(&self) -> f64 {
        if self.consumer_cursors.is_empty() {
            return 0.0;
        }
        let pub_cursor = self.publisher_cursor.load();
        let min_consumer = self
            .consumer_cursors
            .iter()
            .map(|c| c.load())
            .min()
            .unwrap_or(pub_cursor);
        let used = pub_cursor.saturating_sub(min_consumer);
        (used as f64) / (self.capacity as f64)
    }

    pub fn capacity(&self) -> usize {
        self.capacity
    }

    pub fn slot_size(&self) -> usize {
        self.slot_size
    }

    pub fn total_writes(&self) -> u64 {
        self.total_writes.load(Ordering::Relaxed)
    }

    pub fn total_drops(&self) -> u64 {
        self.total_drops.load(Ordering::Relaxed)
    }

    pub fn num_consumers(&self) -> usize {
        self.consumer_cursors.len()
    }
}

// ─── PyO3 wrapper (testing only) ────────────────────────────────────

/// Python-exposed ring buffer for testing and benchmarking.
///
/// Not part of the public bus API -- the ring buffer is used internally
/// by RustBus for dispatch batching.
#[pyclass(name = "RingBuffer")]
pub struct PyRingBuffer {
    inner: parking_lot::RwLock<RingBufferInner>,
}

#[pymethods]
impl PyRingBuffer {
    /// Create a ring buffer.
    ///
    /// Args:
    ///     capacity: Number of slots (rounded up to power of 2).
    ///     slot_size: Max bytes per slot (default 65536).
    ///     num_consumers: Number of consumer groups (default 1).
    ///     backpressure: Strategy when full -- "error" (default), "block", "drop_oldest".
    #[new]
    #[pyo3(signature = (capacity=1024, slot_size=65536, num_consumers=1, backpressure="error"))]
    fn new(
        capacity: usize,
        slot_size: usize,
        num_consumers: usize,
        backpressure: &str,
    ) -> PyResult<Self> {
        if capacity == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "capacity must be > 0",
            ));
        }
        if slot_size == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "slot_size must be > 0",
            ));
        }

        let strategy = match backpressure {
            "error" => BackpressureStrategy::Error,
            "block" => BackpressureStrategy::Block,
            "drop_oldest" => BackpressureStrategy::DropOldest,
            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Unknown backpressure strategy: '{}'. Use 'error', 'block', or 'drop_oldest'.",
                    backpressure
                )));
            }
        };

        Ok(Self {
            inner: parking_lot::RwLock::new(RingBufferInner::new(
                capacity,
                slot_size,
                num_consumers,
                strategy,
            )),
        })
    }

    /// Write data bytes to the ring buffer.
    ///
    /// Returns the slot sequence number on success.
    /// Raises RuntimeError if the ring is full (with "error" backpressure).
    fn write(&self, data: &[u8]) -> PyResult<u64> {
        self.inner
            .read()
            .write(data)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))
    }

    /// Read the next available item for the given consumer.
    ///
    /// Returns bytes or None if no new data is available.
    fn read<'py>(&self, py: Python<'py>, consumer_id: usize) -> PyResult<Option<Py<PyBytes>>> {
        match self
            .inner
            .read()
            .read(consumer_id)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?
        {
            Some(data) => Ok(Some(PyBytes::new(py, &data).into())),
            None => Ok(None),
        }
    }

    /// Add a new consumer group.  Returns the consumer_id.
    fn add_consumer(&self) -> usize {
        self.inner.write().add_consumer()
    }

    /// Number of unread items for a specific consumer.
    fn pending(&self, consumer_id: usize) -> u64 {
        self.inner.read().pending(consumer_id)
    }

    /// Ring buffer utilization (0.0 to 1.0).
    #[getter]
    fn utilization(&self) -> f64 {
        self.inner.read().utilization()
    }

    /// Actual capacity (power-of-2 rounded).
    #[getter]
    fn capacity(&self) -> usize {
        self.inner.read().capacity()
    }

    /// Max bytes per slot.
    #[getter]
    fn slot_size(&self) -> usize {
        self.inner.read().slot_size()
    }

    /// Total writes since creation.
    #[getter]
    fn total_writes(&self) -> u64 {
        self.inner.read().total_writes()
    }

    /// Total drops (DropOldest strategy).
    #[getter]
    fn total_drops(&self) -> u64 {
        self.inner.read().total_drops()
    }

    /// Number of consumer groups.
    #[getter]
    fn num_consumers(&self) -> usize {
        self.inner.read().num_consumers()
    }

    fn __repr__(&self) -> String {
        let inner = self.inner.read();
        format!(
            "RingBuffer(capacity={}, slot_size={}, consumers={}, writes={}, utilization={:.1}%)",
            inner.capacity(),
            inner.slot_size(),
            inner.num_consumers(),
            inner.total_writes(),
            inner.utilization() * 100.0,
        )
    }

    fn __len__(&self) -> usize {
        // Number of items available (based on slowest consumer)
        let inner = self.inner.read();
        if inner.num_consumers() == 0 {
            return 0;
        }
        inner.pending(0) as usize
    }
}

// ─── Rust tests ─────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_power_of_2_rounding() {
        let rb = RingBufferInner::new(10, 256, 1, BackpressureStrategy::Error);
        assert_eq!(rb.capacity(), 16); // 10 -> next power of 2 = 16
    }

    #[test]
    fn test_power_of_2_exact() {
        let rb = RingBufferInner::new(32, 256, 1, BackpressureStrategy::Error);
        assert_eq!(rb.capacity(), 32);
    }

    #[test]
    fn test_write_and_read_single() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::Error);
        let seq = rb.write(b"hello").unwrap();
        assert_eq!(seq, 0);
        assert_eq!(rb.total_writes(), 1);

        let data = rb.read(0).unwrap().unwrap();
        assert_eq!(data, b"hello");
    }

    #[test]
    fn test_read_empty() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::Error);
        let result = rb.read(0).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_write_multiple_read_in_order() {
        let rb = RingBufferInner::new(8, 256, 1, BackpressureStrategy::Error);
        rb.write(b"aaa").unwrap();
        rb.write(b"bbb").unwrap();
        rb.write(b"ccc").unwrap();

        assert_eq!(rb.pending(0), 3);

        assert_eq!(rb.read(0).unwrap().unwrap(), b"aaa");
        assert_eq!(rb.read(0).unwrap().unwrap(), b"bbb");
        assert_eq!(rb.read(0).unwrap().unwrap(), b"ccc");
        assert!(rb.read(0).unwrap().is_none());
    }

    #[test]
    fn test_multi_consumer_fan_out() {
        let rb = RingBufferInner::new(8, 256, 2, BackpressureStrategy::Error);
        rb.write(b"msg1").unwrap();
        rb.write(b"msg2").unwrap();

        // Consumer 0 reads both
        assert_eq!(rb.read(0).unwrap().unwrap(), b"msg1");
        assert_eq!(rb.read(0).unwrap().unwrap(), b"msg2");
        assert!(rb.read(0).unwrap().is_none());

        // Consumer 1 reads both independently
        assert_eq!(rb.read(1).unwrap().unwrap(), b"msg1");
        assert_eq!(rb.read(1).unwrap().unwrap(), b"msg2");
        assert!(rb.read(1).unwrap().is_none());
    }

    #[test]
    fn test_multi_consumer_independent_progress() {
        let rb = RingBufferInner::new(8, 256, 2, BackpressureStrategy::Error);
        rb.write(b"msg1").unwrap();
        rb.write(b"msg2").unwrap();

        // Consumer 0 reads one
        assert_eq!(rb.read(0).unwrap().unwrap(), b"msg1");
        assert_eq!(rb.pending(0), 1);

        // Consumer 1 reads both
        assert_eq!(rb.read(1).unwrap().unwrap(), b"msg1");
        assert_eq!(rb.read(1).unwrap().unwrap(), b"msg2");
        assert_eq!(rb.pending(1), 0);

        // Consumer 0 still has one pending
        assert_eq!(rb.read(0).unwrap().unwrap(), b"msg2");
    }

    #[test]
    fn test_backpressure_error() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::Error);
        // Fill all 4 slots without reading
        for i in 0..4 {
            rb.write(format!("msg{i}").as_bytes()).unwrap();
        }
        // Next write should fail
        let result = rb.write(b"overflow");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("full"));
    }

    #[test]
    fn test_backpressure_drop_oldest() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::DropOldest);
        // Fill all 4 slots
        for i in 0..4 {
            rb.write(format!("msg{i}").as_bytes()).unwrap();
        }
        // Overflow -- should drop oldest and succeed
        rb.write(b"overflow").unwrap();
        assert_eq!(rb.total_drops(), 1);

        // Consumer reads -- oldest messages were dropped, consumer cursor advanced
        let data = rb.read(0).unwrap();
        assert!(data.is_some());
    }

    #[test]
    fn test_data_too_large_for_slot() {
        let rb = RingBufferInner::new(4, 8, 1, BackpressureStrategy::Error);
        let result = rb.write(b"this is way too long for an 8 byte slot");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("too large"));
    }

    #[test]
    fn test_invalid_consumer_id() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::Error);
        let result = rb.read(5);
        assert!(result.is_err());
    }

    #[test]
    fn test_utilization() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::Error);
        assert_eq!(rb.utilization(), 0.0);

        rb.write(b"a").unwrap();
        rb.write(b"b").unwrap();
        assert!((rb.utilization() - 0.5).abs() < 0.01);

        // Read one
        rb.read(0).unwrap();
        assert!((rb.utilization() - 0.25).abs() < 0.01);
    }

    #[test]
    fn test_add_consumer() {
        let mut rb = RingBufferInner::new(8, 256, 1, BackpressureStrategy::Error);
        assert_eq!(rb.num_consumers(), 1);

        rb.write(b"before").unwrap();

        let new_id = rb.add_consumer();
        assert_eq!(new_id, 1);
        assert_eq!(rb.num_consumers(), 2);

        // New consumer starts at current pub cursor -- won't see old data
        assert!(rb.read(new_id).unwrap().is_none());

        // But old consumer can still read
        assert_eq!(rb.read(0).unwrap().unwrap(), b"before");
    }

    #[test]
    fn test_no_consumers_unlimited_write() {
        let rb = RingBufferInner::new(4, 256, 0, BackpressureStrategy::Error);
        // With 0 consumers, no backpressure check needed
        for i in 0..100 {
            rb.write(format!("msg{i}").as_bytes()).unwrap();
        }
        assert_eq!(rb.total_writes(), 100);
    }

    #[test]
    fn test_wrap_around() {
        let rb = RingBufferInner::new(4, 256, 1, BackpressureStrategy::Error);
        // Write 3, read 3, then write 3 more (wraps around)
        rb.write(b"a").unwrap();
        rb.write(b"b").unwrap();
        rb.write(b"c").unwrap();
        assert_eq!(rb.read(0).unwrap().unwrap(), b"a");
        assert_eq!(rb.read(0).unwrap().unwrap(), b"b");
        assert_eq!(rb.read(0).unwrap().unwrap(), b"c");

        // Now write wraps around
        rb.write(b"d").unwrap();
        rb.write(b"e").unwrap();
        assert_eq!(rb.read(0).unwrap().unwrap(), b"d");
        assert_eq!(rb.read(0).unwrap().unwrap(), b"e");
    }

    #[test]
    fn test_slot_size_property() {
        let rb = RingBufferInner::new(4, 1024, 1, BackpressureStrategy::Error);
        assert_eq!(rb.slot_size(), 1024);
    }

    #[test]
    fn test_sequential_writes_monotonic_sequence() {
        let rb = RingBufferInner::new(16, 256, 1, BackpressureStrategy::Error);
        for i in 0u64..10 {
            let seq = rb.write(format!("msg{i}").as_bytes()).unwrap();
            assert_eq!(seq, i);
        }
    }
}
