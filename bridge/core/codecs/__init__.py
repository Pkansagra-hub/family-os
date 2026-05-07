"""Bridge wire-format codec layer (MS-4 Epic 4.1).

Three real codecs live behind a uniform :class:`Codec` Protocol:

* :class:`JSONCodec` — stdlib ``json`` (the always-available default).
* :class:`MsgpackCodec` — ``msgpack`` 1.0+ (``use_bin_type=True``).
* :class:`CBORCodec` — ``cbor2`` 5.6+ (RFC 8949).

Selection is **manifest-driven** at runtime via :class:`CodecRegistry`:

* ``registry.for_manifest(manifest)`` returns the per-contract default.
* ``registry.for_negotiation(manifest, accept)`` honours an HTTP
  ``Accept`` header against ``manifest.delivery.codecs_allowed`` and
  ``manifest.delivery.codec_negotiation`` (``fixed`` |
  ``client_choice_in_allowed``).

Wire-format invariant (see Bridge MS-4 plan): the **outer envelope
stays JSON** because envelope signing canonicalisation depends on
canonical JSON. Only the ``body`` field switches codec. When a
non-JSON codec is in effect, the body is wrapped as
``{"_codec": "msgpack"|"cbor", "_b64": "<base64>"}`` inside the JSON
envelope. The K0 ingress detects this wrapper and decodes accordingly.
This keeps signing logic untouched while delivering size wins on
high-volume topics.
"""

from __future__ import annotations

from bridge.core.codecs.base import (
    BODY_WRAPPER_B64_KEY,
    BODY_WRAPPER_CODEC_KEY,
    Codec,
    CodecError,
    UnsupportedCodecError,
    decode_wrapped_body,
    encode_wrapped_body,
    is_wrapped_body,
)
from bridge.core.codecs.cbor_codec import CBORCodec
from bridge.core.codecs.json_codec import JSONCodec
from bridge.core.codecs.msgpack_codec import MsgpackCodec
from bridge.core.codecs.registry import (
    CODEC_NEGOTIATION_DEFAULT,
    CODEC_NEGOTIATION_FIXED,
    CodecRegistry,
    UnsupportedMediaTypeError,
)

__all__ = [
    "Codec",
    "CodecError",
    "UnsupportedCodecError",
    "JSONCodec",
    "MsgpackCodec",
    "CBORCodec",
    "CodecRegistry",
    "UnsupportedMediaTypeError",
    "BODY_WRAPPER_CODEC_KEY",
    "BODY_WRAPPER_B64_KEY",
    "encode_wrapped_body",
    "decode_wrapped_body",
    "is_wrapped_body",
    "CODEC_NEGOTIATION_DEFAULT",
    "CODEC_NEGOTIATION_FIXED",
]
