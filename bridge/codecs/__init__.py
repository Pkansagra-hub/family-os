"""bridge.codecs -- back-compat re-export of the canonical codec layer.

The real implementation lives at :mod:`bridge.core.codecs` (added in
MS-4 Epic 4.1). This module is preserved only so any prior
``bridge.codecs`` imports keep working; new code SHOULD import from
``bridge.core.codecs`` directly.
"""

from __future__ import annotations

from bridge.core.codecs import (  # noqa: F401
    BODY_WRAPPER_B64_KEY,
    BODY_WRAPPER_CODEC_KEY,
    CODEC_NEGOTIATION_DEFAULT,
    CODEC_NEGOTIATION_FIXED,
    CBORCodec,
    Codec,
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

__all__ = [
    "Codec",
    "CodecError",
    "UnsupportedCodecError",
    "UnsupportedMediaTypeError",
    "JSONCodec",
    "MsgpackCodec",
    "CBORCodec",
    "CodecRegistry",
    "BODY_WRAPPER_CODEC_KEY",
    "BODY_WRAPPER_B64_KEY",
    "encode_wrapped_body",
    "decode_wrapped_body",
    "is_wrapped_body",
    "CODEC_NEGOTIATION_DEFAULT",
    "CODEC_NEGOTIATION_FIXED",
]
