"""Codec Protocol + wire-format wrapping helpers (MS-4 Epic 4.1)."""

from __future__ import annotations

import base64
from typing import Any, Protocol, runtime_checkable

# Stable wrapper keys for non-JSON body payloads inside a JSON envelope.
# These are the contract between K1 transport (encoding side) and K0
# ingress (decoding side); changing them is a wire-breaking change.
BODY_WRAPPER_CODEC_KEY: str = "_codec"
BODY_WRAPPER_B64_KEY: str = "_b64"


class CodecError(Exception):
    """Raised when an encode or decode operation fails."""


class UnsupportedCodecError(LookupError):
    """Raised when a codec name is not registered."""


@runtime_checkable
class Codec(Protocol):
    """Symmetrical wire-format encoder/decoder.

    Implementations MUST be **deterministic** (same input → same bytes)
    so envelope signing canonicalisation works. ``content_type`` is the
    HTTP media type used by the codec (used for ``Content-Type`` and
    ``Accept`` negotiation).
    """

    name: str
    content_type: str

    def encode(self, body: dict[str, Any]) -> bytes: ...
    def decode(self, raw: bytes) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Wrapped-body helpers — only used for non-JSON body codecs
# ---------------------------------------------------------------------------


def encode_wrapped_body(*, codec: "Codec", body: dict[str, Any]) -> dict[str, str]:
    """Return ``{"_codec": codec.name, "_b64": <base64>}`` JSON-wrapping.

    The outer envelope is always JSON because signing canonicalisation
    depends on canonical JSON; the body field carries the binary codec
    output base64-encoded so it survives JSON serialisation byte-for-byte.
    """
    raw = codec.encode(body)
    return {
        BODY_WRAPPER_CODEC_KEY: codec.name,
        BODY_WRAPPER_B64_KEY: base64.b64encode(raw).decode("ascii"),
    }


def is_wrapped_body(body: Any) -> bool:
    """Return True if ``body`` is the ``{"_codec","_b64"}`` wrapper shape."""
    if not isinstance(body, dict):
        return False
    if set(body.keys()) != {BODY_WRAPPER_CODEC_KEY, BODY_WRAPPER_B64_KEY}:
        return False
    return isinstance(body[BODY_WRAPPER_CODEC_KEY], str) and isinstance(
        body[BODY_WRAPPER_B64_KEY], str
    )


def decode_wrapped_body(*, body: dict[str, str], codec: "Codec") -> dict[str, Any]:
    """Reverse of :func:`encode_wrapped_body`. ``codec.name`` must match."""
    if not is_wrapped_body(body):
        raise CodecError("decode_wrapped_body: not a wrapped-body shape")
    declared = body[BODY_WRAPPER_CODEC_KEY]
    if declared != codec.name:
        raise CodecError(
            f"wrapped-body codec mismatch: wrapper says {declared!r}, "
            f"caller provided {codec.name!r}"
        )
    raw = base64.b64decode(body[BODY_WRAPPER_B64_KEY], validate=True)
    return codec.decode(raw)
