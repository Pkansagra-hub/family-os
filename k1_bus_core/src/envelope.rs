//! Rust-side FlatBuffers envelope serialization.
//!
//! Provides `envelope_to_bytes` and `envelope_from_bytes` as PyO3 functions
//! that operate on the same wire format as the Python V2 envelope:
//!
//!     [4 bytes: b"FB02" magic] [N bytes: FlatBuffers BusEnvelope table]
//!
//! These functions are accelerators -- the Python Envelope dataclass is
//! still the canonical type.  The Rust functions accept/return plain Python
//! dicts and bytes, avoiding the need to expose a Rust Envelope struct to
//! Python at this stage (that comes in V2-M4).
//!
//! The generated FlatBuffers Rust bindings are produced by `build.rs`
//! running `flatc --rust` on `k1/bus/envelope/schema.fbs`.

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};

// Include the FlatBuffers generated code.
// build.rs generates this into OUT_DIR.
#[allow(dead_code, unused_imports, clippy::all)]
mod generated {
    include!(concat!(env!("OUT_DIR"), "/envelope_generated.rs"));
}

use generated::k1::bus::envelope as fb;

/// V2 wire-format magic prefix (must match Python's `_V2_MAGIC = b"FB02"`).
const V2_MAGIC: &[u8; 4] = b"FB02";

/// Serialize envelope fields to V2 FlatBuffers wire format.
///
/// Accepts a Python dict with the standard envelope fields and returns
/// `bytes` with the FB02 prefix + FlatBuffers table.
///
/// This is an accelerator for `Envelope._to_bytes_v2()` in Python.
///
/// # Arguments (via kwargs dict)
///
/// - `topic` (str)
/// - `priority` (int, 0-3)
/// - `envelope_id` (int)
/// - `sequence` (int)
/// - `cognitive_trace_id` (str)
/// - `session_id` (str)
/// - `request_id` (str)
/// - `parent_id` (int)
/// - `created_ns` (int)
/// - `payload` (bytes)
/// - `ttl_ms` (int, default 0)
/// - `payload_format` (int, default 0)
#[pyfunction]
#[pyo3(signature = (fields))]
pub fn envelope_to_bytes(py: Python<'_>, fields: &Bound<'_, PyDict>) -> PyResult<Py<PyBytes>> {
    // Extract fields from dict
    let topic: &str = fields
        .get_item("topic")?
        .map(|v| v.extract::<String>())
        .transpose()?
        .unwrap_or_default()
        .leak(); // Safe: short-lived, we just need &str for builder
    // ... actually let's use owned strings to avoid leak
    let topic: String = fields
        .get_item("topic")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or_default();
    let priority: u8 = fields
        .get_item("priority")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(2);
    let envelope_id: u64 = fields
        .get_item("envelope_id")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);
    let sequence: u64 = fields
        .get_item("sequence")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);
    let cognitive_trace_id: String = fields
        .get_item("cognitive_trace_id")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or_default();
    let session_id: String = fields
        .get_item("session_id")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or_default();
    let request_id: String = fields
        .get_item("request_id")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or_default();
    let parent_id: u64 = fields
        .get_item("parent_id")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);
    let created_ns: u64 = fields
        .get_item("created_ns")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);
    let payload: Vec<u8> = fields
        .get_item("payload")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or_default();
    let ttl_ms: u32 = fields
        .get_item("ttl_ms")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);
    let payload_format: u8 = fields
        .get_item("payload_format")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);

    // Build FlatBuffer
    let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256 + payload.len());

    let topic_off = builder.create_string(&topic);
    let trace_off = builder.create_string(&cognitive_trace_id);
    let session_off = builder.create_string(&session_id);
    let request_off = builder.create_string(&request_id);
    let payload_off = builder.create_vector(&payload);

    let env = fb::BusEnvelope::create(
        &mut builder,
        &fb::BusEnvelopeArgs {
            envelope_id,
            sequence,
            parent_id,
            created_ns,
            priority,
            ttl_ms,
            payload_format,
            topic: Some(topic_off),
            cognitive_trace_id: Some(trace_off),
            session_id: Some(session_off),
            request_id: Some(request_off),
            payload: Some(payload_off),
        },
    );

    builder.finish(env, None);
    let fb_bytes = builder.finished_data();

    // Prepend magic prefix
    let mut result = Vec::with_capacity(4 + fb_bytes.len());
    result.extend_from_slice(V2_MAGIC);
    result.extend_from_slice(fb_bytes);

    Ok(PyBytes::new(py, &result).into())
}

/// Deserialize V2 FlatBuffers wire format to a Python dict.
///
/// Accepts `bytes` with FB02 prefix + FlatBuffers table.
/// Returns a Python dict with all envelope fields.
///
/// This is an accelerator for `Envelope._from_bytes_v2()` in Python.
#[pyfunction]
#[pyo3(signature = (data))]
pub fn envelope_from_bytes(py: Python<'_>, data: &[u8]) -> PyResult<Py<PyDict>> {
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

    let dict = PyDict::new(py);
    dict.set_item("topic", env.topic().unwrap_or(""))?;
    dict.set_item("priority", env.priority())?;
    dict.set_item("envelope_id", env.envelope_id())?;
    dict.set_item("sequence", env.sequence())?;
    dict.set_item("cognitive_trace_id", env.cognitive_trace_id().unwrap_or(""))?;
    dict.set_item("session_id", env.session_id().unwrap_or(""))?;
    dict.set_item("request_id", env.request_id().unwrap_or(""))?;
    dict.set_item("parent_id", env.parent_id())?;
    dict.set_item("created_ns", env.created_ns())?;
    dict.set_item("ttl_ms", env.ttl_ms())?;
    dict.set_item("payload_format", env.payload_format())?;

    // Payload as bytes
    let payload = env.payload().map(|v| v.bytes()).unwrap_or(&[]);
    dict.set_item("payload", PyBytes::new(py, payload))?;

    Ok(dict.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verify round-trip at the Rust level (no Python).
    #[test]
    fn test_rust_native_roundtrip() {
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256);

        let topic = builder.create_string("k1.test.rust");
        let trace = builder.create_string("trace-rust");
        let session = builder.create_string("sess-rust");
        let request = builder.create_string("req-rust");
        let payload = builder.create_vector(b"rust-payload");

        let env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs {
                envelope_id: 42,
                sequence: 7,
                parent_id: 41,
                created_ns: 1_000_000,
                priority: 0,
                ttl_ms: 5000,
                payload_format: 1,
                topic: Some(topic),
                cognitive_trace_id: Some(trace),
                session_id: Some(session),
                request_id: Some(request),
                payload: Some(payload),
            },
        );
        builder.finish(env, None);
        let buf = builder.finished_data();

        // Deserialize
        let parsed = fb::root_as_bus_envelope(buf).unwrap();
        assert_eq!(parsed.topic(), Some("k1.test.rust"));
        assert_eq!(parsed.priority(), 0);
        assert_eq!(parsed.envelope_id(), 42);
        assert_eq!(parsed.sequence(), 7);
        assert_eq!(parsed.parent_id(), 41);
        assert_eq!(parsed.created_ns(), 1_000_000);
        assert_eq!(parsed.ttl_ms(), 5000);
        assert_eq!(parsed.payload_format(), 1);
        assert_eq!(parsed.cognitive_trace_id(), Some("trace-rust"));
        assert_eq!(parsed.session_id(), Some("sess-rust"));
        assert_eq!(parsed.request_id(), Some("req-rust"));
        assert_eq!(parsed.payload().unwrap().bytes(), b"rust-payload");
    }

    #[test]
    fn test_defaults() {
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(64);
        let env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs::default(),
        );
        builder.finish(env, None);
        let buf = builder.finished_data();

        let parsed = fb::root_as_bus_envelope(buf).unwrap();
        assert_eq!(parsed.envelope_id(), 0);
        assert_eq!(parsed.sequence(), 0);
        assert_eq!(parsed.parent_id(), 0);
        assert_eq!(parsed.created_ns(), 0);
        assert_eq!(parsed.priority(), 2); // INTERACTIVE default
        assert_eq!(parsed.ttl_ms(), 0);
        assert_eq!(parsed.payload_format(), 0);
        assert_eq!(parsed.topic(), None);
    }

    #[test]
    fn test_large_payload() {
        let big_payload: Vec<u8> = (0..=255u8).cycle().take(256 * 1024).collect();
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256 * 1024 + 256);
        let payload_off = builder.create_vector(&big_payload);
        let topic = builder.create_string("k1.bulk");
        let env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs {
                topic: Some(topic),
                payload: Some(payload_off),
                ..Default::default()
            },
        );
        builder.finish(env, None);
        let buf = builder.finished_data();

        let parsed = fb::root_as_bus_envelope(buf).unwrap();
        assert_eq!(parsed.payload().unwrap().bytes().len(), 256 * 1024);
        assert_eq!(parsed.payload().unwrap().bytes(), big_payload.as_slice());
    }

    #[test]
    fn test_max_uint64() {
        let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(128);
        let env = fb::BusEnvelope::create(
            &mut builder,
            &fb::BusEnvelopeArgs {
                envelope_id: u64::MAX,
                sequence: u64::MAX,
                parent_id: u64::MAX,
                created_ns: u64::MAX,
                ttl_ms: u32::MAX,
                ..Default::default()
            },
        );
        builder.finish(env, None);
        let buf = builder.finished_data();

        let parsed = fb::root_as_bus_envelope(buf).unwrap();
        assert_eq!(parsed.envelope_id(), u64::MAX);
        assert_eq!(parsed.sequence(), u64::MAX);
        assert_eq!(parsed.parent_id(), u64::MAX);
        assert_eq!(parsed.created_ns(), u64::MAX);
        assert_eq!(parsed.ttl_ms(), u32::MAX);
    }
}
