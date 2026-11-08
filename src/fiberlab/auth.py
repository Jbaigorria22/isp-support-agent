"""Session tokens that bind every account tool call to ONE verified customer.

Why: identity checks must live in code, not only in the prompt. A tool that needs
a verified customer accepts a signed token, never a raw customer_id, so the model
cannot be talked into reading or changing another customer's account.
"""

import base64
import hashlib
import hmac
import os
import time

TOKEN_TTL_SECONDS = 30 * 60


class AuthError(Exception):
    """Raised when a session token is missing, invalid or expired."""


def _secret() -> bytes:
    secret = os.environ.get("FIBERLAB_SESSION_SECRET")
    if not secret:
        # Development default. Production must set FIBERLAB_SESSION_SECRET.
        secret = "dev-only-insecure-secret"
    return secret.encode()


def issue_token(customer_id: str, now: float | None = None) -> str:
    expires = int((now or time.time()) + TOKEN_TTL_SECONDS)
    payload = f"{customer_id}:{expires}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def verify_token(token: str, now: float | None = None) -> str:
    """Return the customer_id bound to `token`, or raise AuthError."""
    try:
        customer_id, expires, signature = base64.urlsafe_b64decode(token.encode()).decode().split(":")
    except Exception as exc:  # malformed token
        raise AuthError("invalid session") from exc

    expected = hmac.new(_secret(), f"{customer_id}:{expires}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AuthError("invalid session")
    if (now or time.time()) > int(expires):
        raise AuthError("session expired, verify the customer again")
    return customer_id
