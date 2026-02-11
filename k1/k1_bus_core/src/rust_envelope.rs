//! Rust `Envelope` -- #[pyclass(frozen)] matching all 12 bus envelope fields.
//!
//! This module provides a proper Rust Envelope struct exposed to Python via
//! PyO3.  Unlike the M2 dict-based accelerators (`envelope_to_bytes` /
//! `envelope_from_bytes`), this struct is a first-class Python object with
//! attribute access (`env.topic`, `env.priority`, etc.).
//!
//! ## Python interop
//!
//! ```python
//! from k1_bus_core import RustEnvelope
//!
//! env = RustEnvelope(topic="k1.test", priority=2, payload=b"hello")
//! wire = env.to_bytes()
//! restored = RustEnvelope.from_bytes(wire)
//! stamped = env.with_bus_fields(envelope_id=42, sequence=7, created_ns=12345)
//! ```
//!
//! ## Wire format
//!
//! Same FlatBuffers V2 format as the Python Envelope: `[4 bytes: b"FB02"] [FlatBuffers]`.
//! Cross-language compatible: `RustEnvelope.to_bytes()` -> Python `Envelope.from_bytes()`
//! and vice versa.

use pyo3::prelude::*;
use pyo3::types::PyBytes;

// Reuse the FlatBuffers generated code from envelope.rs
use crate::envelope::generated::k_1::bus::envelope as fb;
use flatbuffers;

/// V2 wire-format magic prefix.
const V2_MAGIC: &[u8; 4] = b"FB02";

// ─── Rust Envelope struct ───────────────────────────────────────────

/// Immutable bus envelope -- the unit of data flowing through IBus.
///
/// All 12 fields from the FlatBuffers schema are exposed as read-only
/// Python attributes via `#[pyo3(get)]`.
///
/// This is a `frozen` pyclass (immutable from Python).  The `with_bus_fields()`
/// method returns a new instance with stamped bus fields (~128 bytes copy in Rust).
#[pyclass(frozen, name = "RustEnvelope")]
#[derive(Clone, Debug)]
pub struct RustEnvelope {
    #[pyo3(get)]
    pub topic: String,
    #[pyo3(get)]
    pub priority: u8,
    #[pyo3(get)]
    pub envelope_id: u64,
    #[pyo3(get)]
    pub sequence: u64,
    #[pyo3(get)]
    pub cognitive_trace_id: String,
    #[pyo3(get)]
    pub session_id: String,
    #[pyo3(get)]
    pub request_id: String,
    #[pyo3(get)]
    pub parent_id: u64,
    #[pyo3(get)]
    pub created_ns: u64,
    #[pyo3(get)]
    pub payload: Vec<u8>,
    #[pyo3(get)]
    pub ttl_ms: u32,
    #[pyo3(get)]
    pub payload_format: u8,
}

#[pymethods]
impl RustEnvelope {
    /// Construct a new RustEnvelope.
    ///
    /// All fields have defaults matching the FlatBuffers schema:
    ///   topic="", priority=2 (INTERACTIVE), envelope_id=0, sequence=0,
    ///   cognitive_trace_id="", session_id="", request_id="",
    ///   parent_id=0, created_ns=0, payload=b"", ttl_ms=0, payload_format=0
    #[new]
    #[pyo3(signature = (
        topic = String::new(),
        priority = 2,
        envelope_id = 0,
        sequence = 0,
        cognitive_trace_id = String::new(),
        session_id = String::new(),
        request_id = String::new(),
        parent_id = 0,
        created_ns = 0,
        payload = Vec::new(),
        ttl_ms = 0,
        payload_format = 0,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        topic: String,
        priority: u8,
        envelope_id: u64,
        sequence: u64,
        cognitive_trace_id: String,
        session_id: String,
        request_id: String,
        parent_id: u64,
        created_ns: u64,
        payload: Vec<u8>,
        ttl_ms: u32,
        payload_format: u8,
    ) -> PyResult<Self> {
        if priority > 3 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "priority must be 0-3, got {priority}"
            )));
        }
        if payload_format > 2 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "payload_format must be 0-2, got {payload_format}"
            )));
        }
        Ok(Self {
            topic,
            priority,
            envelope_id,
            sequence,
            cognitive_trace_id,
            session_id,
            request_id,
            parent_id,
            created_ns,
            payload,
            ttl_ms,
            payload_format,
        })
    }

    /// Payload byte count.
    #[getter]
    fn payload_len(&self) -> usize {
        self.payload.len()
    }

    /// True if this envelope has no causal parent (parent_id == 0).
    #[getter]
    fn is_root(&self) -> bool {
        self.parent_id == 0
    }

    /// True if ttl_ms > 0 (envelope has a finite lifetime).
    #[getter]
    fn is_expired(&self) -> bool {
        self.ttl_ms > 0
    }

    // ── Serialization ───────────────────────────────────────────────

    /// Serialize to V2 FlatBuffers wire format: [b"FB02"][FlatBuffers].
    fn to_bytes<'py>(&self, py: Python<'py>) -> Py<PyBytes> {
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256 + self.payload.len());

        let topic_off = builder.create_string(&self.topic);
        let trace_off = builder.create_string(&self.cognitive_trace_id);
        let session_off = builder.create_string(&self.session_id);
        let request_off = builder.create_string(&self.request_id);
        let payload_off = builder.create_vector(&self.payload);

        let env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs {
                envelope_id: self.envelope_id,
                sequence: self.sequence,
                parent_id: self.parent_id,
                created_ns: self.created_ns,
                priority: self.priority,
                ttl_ms: self.ttl_ms,
                payload_format: self.payload_format,
                topic: Some(topic_off),
                cognitive_trace_id: Some(trace_off),
                session_id: Some(session_off),
                request_id: Some(request_off),
                payload: Some(payload_off),
            },
        );

        builder.finish(env, None);
        let fb_bytes = builder.finished_data();

        let mut result = Vec::with_capacity(4 + fb_bytes.len());
        result.extend_from_slice(V2_MAGIC);
        result.extend_from_slice(fb_bytes);

        PyBytes::new(py, &result).into()
    }

    /// Deserialize from V2 FlatBuffers wire format.
    ///
    /// Auto-detects: data starting with b"FB02" is V2 FlatBuffers.
    /// Returns a new `RustEnvelope` with all 12 fields populated.
    #[staticmethod]
    fn from_bytes(data: &[u8]) -> PyResult<Self> {
        if data.len() < 4 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Envelope data too short: {} bytes (need >= 4)",
                data.len()
            )));
        }
        if &data[..4] != V2_MAGIC {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Not a V2 FlatBuffers envelope (missing FB02 magic prefix)",
            ));
        }

        let fb_data = &data[4..];
        let env = fb::root_as_bus_envelope(fb_data).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Malformed FlatBuffers data: {e}"))
        })?;

        let payload: Vec<u8> = env
            .payload()
            .map(|v| v.bytes().to_vec())
            .unwrap_or_default();

        Ok(Self {
            topic: env.topic().unwrap_or("").to_string(),
            priority: env.priority(),
            envelope_id: env.envelope_id(),
            sequence: env.sequence(),
            cognitive_trace_id: env.cognitive_trace_id().unwrap_or("").to_string(),
            session_id: env.session_id().unwrap_or("").to_string(),
            request_id: env.request_id().unwrap_or("").to_string(),
            parent_id: env.parent_id(),
            created_ns: env.created_ns(),
            payload,
            ttl_ms: env.ttl_ms(),
            payload_format: env.payload_format(),
        })
    }

    // ── Builder helpers ─────────────────────────────────────────────

    /// Return a new RustEnvelope with bus-assigned fields stamped.
    ///
    /// Cheap struct copy in Rust (~128 bytes). The publisher provides
    /// topic, priority, payload, trace IDs.  The bus stamps envelope_id,
    /// sequence, and created_ns.  All other fields are preserved.
    #[pyo3(signature = (envelope_id, sequence, created_ns))]
    fn with_bus_fields(&self, envelope_id: u64, sequence: u64, created_ns: u64) -> Self {
        Self {
            topic: self.topic.clone(),
            priority: self.priority,
            envelope_id,
            sequence,
            cognitive_trace_id: self.cognitive_trace_id.clone(),
            session_id: self.session_id.clone(),
            request_id: self.request_id.clone(),
            parent_id: self.parent_id,
            created_ns,
            payload: self.payload.clone(),
            ttl_ms: self.ttl_ms,
            payload_format: self.payload_format,
        }
    }

    // ── Python dunder methods ───────────────────────────────────────

    fn __repr__(&self) -> String {
        format!(
            "RustEnvelope(topic='{}', priority={}, envelope_id={}, sequence={}, \
             parent_id={}, ttl_ms={}, payload_len={})",
            self.topic,
            self.priority,
            self.envelope_id,
            self.sequence,
            self.parent_id,
            self.ttl_ms,
            self.payload.len(),
        )
    }

    fn __eq__(&self, other: &Self) -> bool {
        self.topic == other.topic
            && self.priority == other.priority
            && self.envelope_id == other.envelope_id
            && self.sequence == other.sequence
            && self.cognitive_trace_id == other.cognitive_trace_id
            && self.session_id == other.session_id
            && self.request_id == other.request_id
            && self.parent_id == other.parent_id
            && self.created_ns == other.created_ns
            && self.payload == other.payload
            && self.ttl_ms == other.ttl_ms
            && self.payload_format == other.payload_format
    }
}

// ─── Rust-native tests ──────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn make_full_envelope() -> RustEnvelope {
        RustEnvelope {
            topic: "k1.test.full".to_string(),
            priority: 0,
            envelope_id: 42,
            sequence: 7,
            cognitive_trace_id: "trace-abc".to_string(),
            session_id: "sess-xyz".to_string(),
            request_id: "req-123".to_string(),
            parent_id: 41,
            created_ns: 1_000_000,
            payload: b"hello-world".to_vec(),
            ttl_ms: 5000,
            payload_format: 1,
        }
    }

    #[test]
    fn test_default_fields() {
        let env = RustEnvelope {
            topic: String::new(),
            priority: 2,
            envelope_id: 0,
            sequence: 0,
            cognitive_trace_id: String::new(),
            session_id: String::new(),
            request_id: String::new(),
            parent_id: 0,
            created_ns: 0,
            payload: Vec::new(),
            ttl_ms: 0,
            payload_format: 0,
        };
        assert_eq!(env.topic, "");
        assert_eq!(env.priority, 2);
        assert_eq!(env.envelope_id, 0);
        assert_eq!(env.payload.len(), 0);
        assert_eq!(env.ttl_ms, 0);
        assert_eq!(env.payload_format, 0);
        assert!(env.is_root());
        assert!(!env.is_expired());
    }

    #[test]
    fn test_full_construction() {
        let env = make_full_envelope();
        assert_eq!(env.topic, "k1.test.full");
        assert_eq!(env.priority, 0);
        assert_eq!(env.envelope_id, 42);
        assert_eq!(env.sequence, 7);
        assert_eq!(env.cognitive_trace_id, "trace-abc");
        assert_eq!(env.session_id, "sess-xyz");
        assert_eq!(env.request_id, "req-123");
        assert_eq!(env.parent_id, 41);
        assert_eq!(env.created_ns, 1_000_000);
        assert_eq!(env.payload, b"hello-world");
        assert_eq!(env.ttl_ms, 5000);
        assert_eq!(env.payload_format, 1);
        assert!(!env.is_root());
        assert!(env.is_expired());
    }

    #[test]
    fn test_with_bus_fields() {
        let original = make_full_envelope();
        let stamped = original.with_bus_fields(100, 50, 999_999);

        // Bus-assigned fields updated
        assert_eq!(stamped.envelope_id, 100);
        assert_eq!(stamped.sequence, 50);
        assert_eq!(stamped.created_ns, 999_999);

        // Publisher fields preserved
        assert_eq!(stamped.topic, "k1.test.full");
        assert_eq!(stamped.priority, 0);
        assert_eq!(stamped.cognitive_trace_id, "trace-abc");
        assert_eq!(stamped.session_id, "sess-xyz");
        assert_eq!(stamped.request_id, "req-123");
        assert_eq!(stamped.parent_id, 41);
        assert_eq!(stamped.payload, b"hello-world");
        assert_eq!(stamped.ttl_ms, 5000);
        assert_eq!(stamped.payload_format, 1);
    }

    #[test]
    fn test_with_bus_fields_does_not_mutate_original() {
        let original = make_full_envelope();
        let _ = original.with_bus_fields(100, 50, 999);
        assert_eq!(original.envelope_id, 42);
        assert_eq!(original.sequence, 7);
        assert_eq!(original.created_ns, 1_000_000);
    }

    #[test]
    fn test_roundtrip_via_flatbuffers() {
        let env = make_full_envelope();

        // Serialize to FlatBuffers
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256 + env.payload.len());

        let topic_off = builder.create_string(&env.topic);
        let trace_off = builder.create_string(&env.cognitive_trace_id);
        let session_off = builder.create_string(&env.session_id);
        let request_off = builder.create_string(&env.request_id);
        let payload_off = builder.create_vector(&env.payload);

        let fb_env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs {
                envelope_id: env.envelope_id,
                sequence: env.sequence,
                parent_id: env.parent_id,
                created_ns: env.created_ns,
                priority: env.priority,
                ttl_ms: env.ttl_ms,
                payload_format: env.payload_format,
                topic: Some(topic_off),
                cognitive_trace_id: Some(trace_off),
                session_id: Some(session_off),
                request_id: Some(request_off),
                payload: Some(payload_off),
            },
        );
        builder.finish(fb_env, None);
        let fb_bytes = builder.finished_data();

        // Build wire format
        let mut wire = Vec::with_capacity(4 + fb_bytes.len());
        wire.extend_from_slice(V2_MAGIC);
        wire.extend_from_slice(fb_bytes);

        // Deserialize
        let restored = RustEnvelope::from_bytes(&wire).unwrap();
        assert_eq!(restored.topic, env.topic);
        assert_eq!(restored.priority, env.priority);
        assert_eq!(restored.envelope_id, env.envelope_id);
        assert_eq!(restored.sequence, env.sequence);
        assert_eq!(restored.cognitive_trace_id, env.cognitive_trace_id);
        assert_eq!(restored.session_id, env.session_id);
        assert_eq!(restored.request_id, env.request_id);
        assert_eq!(restored.parent_id, env.parent_id);
        assert_eq!(restored.created_ns, env.created_ns);
        assert_eq!(restored.payload, env.payload);
        assert_eq!(restored.ttl_ms, env.ttl_ms);
        assert_eq!(restored.payload_format, env.payload_format);
    }

    #[test]
    fn test_from_bytes_too_short() {
        let result = RustEnvelope::from_bytes(b"FB");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_bytes_wrong_magic() {
        let result = RustEnvelope::from_bytes(b"XXXX\x00\x00\x00\x00");
        assert!(result.is_err());
    }

    #[test]
    fn test_max_uint64_fields() {
        let env = RustEnvelope {
            topic: "k1.max".to_string(),
            priority: 3,
            envelope_id: u64::MAX,
            sequence: u64::MAX,
            cognitive_trace_id: String::new(),
            session_id: String::new(),
            request_id: String::new(),
            parent_id: u64::MAX,
            created_ns: u64::MAX,
            payload: Vec::new(),
            ttl_ms: u32::MAX,
            payload_format: 2,
        };
        assert_eq!(env.envelope_id, u64::MAX);
        assert_eq!(env.ttl_ms, u32::MAX);
    }

    #[test]
    fn test_large_payload_roundtrip() {
        let big_payload: Vec<u8> = (0..=255u8).cycle().take(256 * 1024).collect();
        let env = RustEnvelope {
            topic: "k1.bulk".to_string(),
            priority: 2,
            envelope_id: 0,
            sequence: 0,
            cognitive_trace_id: String::new(),
            session_id: String::new(),
            request_id: String::new(),
            parent_id: 0,
            created_ns: 0,
            payload: big_payload.clone(),
            ttl_ms: 0,
            payload_format: 0,
        };

        // Build wire
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256 * 1024 + 256);
        let topic_off = builder.create_string(&env.topic);
        let payload_off = builder.create_vector(&env.payload);
        let trace_off = builder.create_string("");
        let session_off = builder.create_string("");
        let request_off = builder.create_string("");
        let fb_env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs {
                topic: Some(topic_off),
                payload: Some(payload_off),
                cognitive_trace_id: Some(trace_off),
                session_id: Some(session_off),
                request_id: Some(request_off),
                ..Default::default()
            },
        );
        builder.finish(fb_env, None);
        let fb_bytes = builder.finished_data();
        let mut wire = Vec::with_capacity(4 + fb_bytes.len());
        wire.extend_from_slice(V2_MAGIC);
        wire.extend_from_slice(fb_bytes);

        let restored = RustEnvelope::from_bytes(&wire).unwrap();
        assert_eq!(restored.payload.len(), 256 * 1024);
        assert_eq!(restored.payload, big_payload);
    }

    #[test]
    fn test_eq() {
        let a = make_full_envelope();
        let b = make_full_envelope();
        assert!(a.__eq__(&b));
    }

    #[test]
    fn test_ne_different_topic() {
        let a = make_full_envelope();
        let mut b = make_full_envelope();
        b.topic = "k1.other".to_string();
        assert!(!a.__eq__(&b));
    }

    #[test]
    fn test_repr() {
        let env = make_full_envelope();
        let repr = env.__repr__();
        assert!(repr.contains("k1.test.full"));
        assert!(repr.contains("42"));
    }
}
