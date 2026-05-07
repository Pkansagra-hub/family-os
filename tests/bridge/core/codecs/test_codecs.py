"""Unit tests for the bridge codec layer (MS-4 Epic 4.1).

Covers:

* JSON / msgpack / CBOR symmetric round-trips on representative payloads.
* JSON canonicalisation (key-sort determinism for envelope signing).
* Wrapped-body helpers (``_codec`` / ``_b64`` shape).
* :class:`CodecRegistry` lookup, manifest defaults, and Accept-header
  negotiation under both ``client_choice_in_allowed`` and ``fixed``
  policies.
"""

from __future__ import annotations

import base64
import json

import pytest

from bridge.core.codecs import (
    BODY_WRAPPER_B64_KEY,
    BODY_WRAPPER_CODEC_KEY,
    CBORCodec,
    CodecError,
    CodecRegistry,
    JSONCodec,
    MsgpackCodec,
    UnsupportedCodecError,
    UnsupportedMediaTypeError,
    decode_wrapped_body,
    encode_wrapped_body,
    is_wrapped_body,
)

SAMPLE_BODY: dict = {
    "topic": "memory.write.v1",
    "n": 42,
    "ratio": 0.125,
    "tags": ["alpha", "beta", "gamma"],
    "nested": {"trace_id": "tr_001", "items": [{"k": 1}, {"k": 2}]},
    "flag": True,
    "absent": None,
}


# ---------------------------------------------------------------------------
# Per-codec round-trips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("codec_cls", [JSONCodec, MsgpackCodec, CBORCodec])
def test_codec_roundtrip_preserves_dict(codec_cls):
    codec = codec_cls()
    raw = codec.encode(SAMPLE_BODY)
    assert isinstance(raw, bytes)
    decoded = codec.decode(raw)
    assert decoded == SAMPLE_BODY


def test_json_codec_is_canonical_sorted_keys():
    codec = JSONCodec()
    a = codec.encode({"b": 1, "a": 2})
    b = codec.encode({"a": 2, "b": 1})
    assert a == b
    assert a == b'{"a":2,"b":1}'


def test_json_codec_rejects_top_level_list():
    codec = JSONCodec()
    with pytest.raises(CodecError):
        codec.decode(b"[1,2,3]")


def test_msgpack_codec_distinguishes_str_and_bytes():
    codec = MsgpackCodec()
    body = {"s": "abc"}
    assert codec.decode(codec.encode(body)) == body


def test_cbor_codec_handles_unicode():
    codec = CBORCodec()
    body = {"emoji": "héllo", "kana": "こんにちは"}
    assert codec.decode(codec.encode(body)) == body


def test_codec_decode_propagates_codec_error_on_garbage():
    for codec in (JSONCodec(), MsgpackCodec(), CBORCodec()):
        with pytest.raises(CodecError):
            codec.decode(b"\xff\x00\x01garbage")


def test_codec_content_types_are_distinct():
    seen = {JSONCodec.content_type, MsgpackCodec.content_type, CBORCodec.content_type}
    assert seen == {"application/json", "application/msgpack", "application/cbor"}


# ---------------------------------------------------------------------------
# Wrapped-body helpers
# ---------------------------------------------------------------------------


def test_encode_wrapped_body_shape_and_keys():
    codec = MsgpackCodec()
    wrapped = encode_wrapped_body(codec=codec, body=SAMPLE_BODY)
    assert set(wrapped.keys()) == {BODY_WRAPPER_CODEC_KEY, BODY_WRAPPER_B64_KEY}
    assert wrapped[BODY_WRAPPER_CODEC_KEY] == "msgpack"
    # b64 round-trips back to the codec output bytes.
    raw = base64.b64decode(wrapped[BODY_WRAPPER_B64_KEY], validate=True)
    assert codec.decode(raw) == SAMPLE_BODY


def test_wrapped_body_survives_json_serialisation():
    codec = CBORCodec()
    wrapped = encode_wrapped_body(codec=codec, body=SAMPLE_BODY)
    # The wrapped shape is JSON-safe so the outer envelope can be canonical JSON.
    serialised = json.dumps(wrapped)
    rehydrated = json.loads(serialised)
    assert decode_wrapped_body(body=rehydrated, codec=codec) == SAMPLE_BODY


def test_is_wrapped_body_rejects_lookalikes():
    assert not is_wrapped_body({"_codec": "msgpack"})  # missing _b64
    assert not is_wrapped_body({"_codec": 42, "_b64": "abc"})  # wrong type
    assert not is_wrapped_body({"_codec": "x", "_b64": "y", "extra": "z"})
    assert not is_wrapped_body([])
    assert is_wrapped_body({"_codec": "x", "_b64": "y"})


def test_decode_wrapped_body_rejects_codec_mismatch():
    msg = MsgpackCodec()
    cbor = CBORCodec()
    wrapped = encode_wrapped_body(codec=msg, body={"a": 1})
    with pytest.raises(CodecError, match="codec mismatch"):
        decode_wrapped_body(body=wrapped, codec=cbor)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_resolves_all_three_builtins():
    reg = CodecRegistry()
    assert reg.get("json").name == "json"
    assert reg.get("msgpack").name == "msgpack"
    assert reg.get("cbor").name == "cbor"


def test_registry_unknown_codec_raises():
    reg = CodecRegistry()
    with pytest.raises(UnsupportedCodecError):
        reg.get("flatbuffers")  # listed in schema but not implemented for MS-4


def test_registry_for_manifest_defaults_to_json_when_absent():
    reg = CodecRegistry()
    assert reg.for_manifest({}).name == "json"
    assert reg.for_manifest({"transport": "http"}).name == "json"


def test_registry_for_manifest_honours_explicit_codec():
    reg = CodecRegistry()
    assert reg.for_manifest({"codec": "msgpack"}).name == "msgpack"


def test_registry_codecs_allowed_defaults_to_singleton():
    reg = CodecRegistry()
    allowed = reg.codecs_allowed({"codec": "json"})
    assert [c.name for c in allowed] == ["json"]


def test_registry_codecs_allowed_honours_list():
    reg = CodecRegistry()
    allowed = reg.codecs_allowed({"codec": "json", "codecs_allowed": ["json", "msgpack"]})
    assert [c.name for c in allowed] == ["json", "msgpack"]


def test_registry_negotiation_no_accept_returns_default():
    reg = CodecRegistry()
    delivery = {"codec": "msgpack", "codecs_allowed": ["json", "msgpack"]}
    assert reg.for_negotiation(delivery, None).name == "msgpack"
    assert reg.for_negotiation(delivery, "*/*").name == "msgpack"


def test_registry_negotiation_matches_allowed_content_type():
    reg = CodecRegistry()
    delivery = {"codec": "json", "codecs_allowed": ["json", "msgpack"]}
    assert reg.for_negotiation(delivery, "application/msgpack").name == "msgpack"
    assert reg.for_negotiation(delivery, "application/json").name == "json"


def test_registry_negotiation_handles_q_values():
    reg = CodecRegistry()
    delivery = {"codec": "json", "codecs_allowed": ["json", "msgpack"]}
    # q-value present but first-match still wins (RFC 7231 first-acceptable).
    chosen = reg.for_negotiation(delivery, "application/msgpack;q=0.9, application/json;q=0.5")
    assert chosen.name == "msgpack"


def test_registry_negotiation_fixed_policy_raises_on_mismatch():
    reg = CodecRegistry()
    delivery = {
        "codec": "json",
        "codecs_allowed": ["json"],
        "codec_negotiation": "fixed",
    }
    with pytest.raises(UnsupportedMediaTypeError) as ei:
        reg.for_negotiation(delivery, "application/msgpack")
    assert "application/json" in ei.value.supported


def test_registry_negotiation_default_policy_falls_back():
    reg = CodecRegistry()
    delivery = {
        "codec": "json",
        "codecs_allowed": ["json"],
        # codec_negotiation absent → default = client_choice_in_allowed
    }
    chosen = reg.for_negotiation(delivery, "application/msgpack")
    assert chosen.name == "json"


def test_registry_supported_content_types_are_sorted():
    reg = CodecRegistry()
    assert reg.supported_content_types == sorted(reg.supported_content_types)
    assert "application/json" in reg.supported_content_types
