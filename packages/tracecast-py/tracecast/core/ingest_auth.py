"""Auth helpers for the ingest HTTP surface.

Priority for clients:
  1. X-TraceCast-Token: <token>
  2. Authorization: Bearer <token>
  3. Authorization: Basic (TRACECAST_AUTH user:pass)

If TRACECAST_INGEST_TOKEN (or TRACECAST_HTTP_TOKEN) is set, token auth is required
for POST /api/ingest*. If unset, ingest stays open (dev / private network).
"""

from __future__ import annotations

import base64
import os
import secrets
from typing import Optional, Tuple


def ingest_token() -> Optional[str]:
    for key in ("TRACECAST_INGEST_TOKEN", "TRACECAST_HTTP_TOKEN"):
        raw = os.environ.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def basic_auth_pair() -> Optional[Tuple[str, str]]:
    raw = os.environ.get("TRACECAST_AUTH")
    if not raw or ":" not in raw:
        return None
    user, _, password = raw.partition(":")
    if not user:
        return None
    return user, password


def check_ingest_authorized(
    *,
    authorization: Optional[str] = None,
    x_token: Optional[str] = None,
) -> bool:
    """Return True if request may write traces."""
    expected = ingest_token()
    if expected is None:
        # No token configured → open (legacy private VM). Optional hard-require:
        if os.environ.get("TRACECAST_INGEST_AUTH_REQUIRED", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            return False
        return True

    if x_token is not None and secrets.compare_digest(str(x_token), expected):
        return True

    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        got = auth[7:].strip()
        if secrets.compare_digest(got, expected):
            return True

    pair = basic_auth_pair()
    if pair and auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8")
            user, _, password = decoded.partition(":")
            if secrets.compare_digest(user, pair[0]) and secrets.compare_digest(
                password, pair[1]
            ):
                return True
        except Exception:
            pass
    return False
