from __future__ import annotations

import os
from typing import Any, Optional

DEFAULT_MAX_PAYLOAD_CHARS = 2000


def max_payload_chars() -> int:
    raw = os.environ.get("TRACECAST_MAX_PAYLOAD_CHARS")
    if raw is None or raw == "":
        return DEFAULT_MAX_PAYLOAD_CHARS
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_MAX_PAYLOAD_CHARS


def truncate_payload(value: Any, limit: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    if limit is None:
        limit = max_payload_chars()
    if limit == 0:
        return None
    text = value if isinstance(value, str) else repr(value)
    if limit < 0 or len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[:limit] + "..."
