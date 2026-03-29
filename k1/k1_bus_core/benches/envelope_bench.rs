//! Envelope serialization benchmarks.
//!
//! Run with: `cargo bench --bench envelope_bench`

use criterion::{black_box, criterion_group, criterion_main, Criterion};

// Include the generated FlatBuffers code (same path as in envelope.rs)
#[allow(dead_code, unused_imports, clippy::all)]
mod generated {
    include!(concat!(env!("OUT_DIR"), "/envelope_generated.rs"));
}

use generated::k_1::bus::envelope as fb;

fn bench_serialize_small(c: &mut Criterion) {
    c.bench_function("envelope_serialize_small", |b| {
        b.iter(|| {
            let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256);
            let topic = builder.create_string("k1.test.bench.v1");
            let trace = builder.create_string("trace-bench");
            let session = builder.create_string("sess-bench");
            let request = builder.create_string("req-bench");
            let payload = builder.create_vector(b"bench-payload-data");

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
            black_box(builder.finished_data().len());
        })
    });
}

fn bench_deserialize_small(c: &mut Criterion) {
    // Pre-build the buffer
    let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(256);
    let topic = builder.create_string("k1.test.bench.v1");
    let trace = builder.create_string("trace-bench");
    let session = builder.create_string("sess-bench");
    let request = builder.create_string("req-bench");
    let payload = builder.create_vector(b"bench-payload-data");
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
    let buf = builder.finished_data().to_vec();

    c.bench_function("envelope_deserialize_small", |b| {
        b.iter(|| {
            let parsed = fb::root_as_bus_envelope(black_box(&buf)).unwrap();
            black_box(parsed.envelope_id());
            black_box(parsed.topic());
            black_box(parsed.payload());
        })
    });
}

fn bench_serialize_large_payload(c: &mut Criterion) {
    let big_payload: Vec<u8> = (0..=255u8).cycle().take(64 * 1024).collect();

    c.bench_function("envelope_serialize_64kb", |b| {
        b.iter(|| {
            let mut builder = flatbuffers::FlatBufferBuilder::with_capacity(64 * 1024 + 256);
            let topic = builder.create_string("k1.bulk.bench");
            let payload_off = builder.create_vector(&big_payload);
            let env = fb::BusEnvelope::create(
                &mut builder,
                &fb::BusEnvelopeArgs {
                    topic: Some(topic),
                    payload: Some(payload_off),
                    ..Default::default()
                },
            );
            builder.finish(env, None);
            black_box(builder.finished_data().len());
        })
    });
}

criterion_group!(
    benches,
    bench_serialize_small,
    bench_deserialize_small,
    bench_serialize_large_payload,
);
criterion_main!(benches);
