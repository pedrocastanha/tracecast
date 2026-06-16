from dataclasses import dataclass
from datetime import datetime
from typing import Optional

SORT_FIELDS = {
    "date": "started_at",
    "cost": "cost_usd",
    "tokens": "total_tokens",
    "duration": "latency_ms",
}


def sort_field(sort_by: str) -> str:
    return SORT_FIELDS.get(sort_by, "started_at")


@dataclass
class TraceFilter:
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    from_dt: Optional[datetime] = None
    to_dt: Optional[datetime] = None
