from __future__ import annotations

import argparse
import base64
import binascii

from nacl.signing import SigningKey


def _encode_base64url(data: bytes) -> str:
    """Return URL-safe base64 without trailing padding."""

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or format an Ed25519 keypair")
    parser.add_argument(
        "--hex",
        dest="hex_key",
        help="Optional 64-character hex secret key to format",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.hex_key:
        raw = args.hex_key.strip().lower()
        if raw.startswith("0x"):
            raw = raw[2:]
        try:
            key_bytes = binascii.unhexlify(raw)
        except (binascii.Error, ValueError) as exc:
            raise SystemExit(f"invalid hex secret: {exc}")
        if len(key_bytes) != 32:
            raise SystemExit("secret key must be exactly 32 bytes (64 hex chars)")
        signing_key = SigningKey(key_bytes)
    else:
        signing_key = SigningKey.generate()

    secret_b64 = _encode_base64url(bytes(signing_key))
    verify_b64 = _encode_base64url(bytes(signing_key.verify_key))
    print(secret_b64)
    print(verify_b64)


if __name__ == "__main__":
    main()
