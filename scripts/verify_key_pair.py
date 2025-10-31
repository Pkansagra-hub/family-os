from __future__ import annotations

import base64

from nacl.signing import SigningKey

SECRET_B64 = "nQqbjH9uXUw7KhkI9-bVxLOikYBwYFBAMCAQD_7t3MA"

padding = "=" * (-len(SECRET_B64) % 4)
secret_bytes = base64.urlsafe_b64decode(SECRET_B64 + padding)
print("secret_hex", secret_bytes.hex())

signing_key = SigningKey(secret_bytes)
verify_key = signing_key.verify_key
verify_b64 = base64.urlsafe_b64encode(bytes(verify_key)).rstrip(b"=").decode("ascii")
print("verify_b64", verify_b64)
