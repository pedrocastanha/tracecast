import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

VALID_KINDS = {"human", "llm", "heuristic"}
VALID_DATA_TYPES = {"numeric", "boolean", "categorical"}


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (AttributeError, ValueError):
        return None


@dataclass
class Score:
    trace_id: str
    name: str
    value: float
    span_id: Optional[str] = None
    kind: str = "human"          # human | llm | heuristic
    data_type: str = "numeric"   # numeric | boolean | categorical
    string_value: Optional[str] = None
    comment: Optional[str] = None
    source: Optional[str] = None
    project_id: Optional[str] = None
    score_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ValueError(f"invalid kind: {self.kind}. Valid: {sorted(VALID_KINDS)}")
        if self.data_type not in VALID_DATA_TYPES:
            raise ValueError(f"invalid data_type: {self.data_type}. Valid: {sorted(VALID_DATA_TYPES)}")
        if not self.trace_id:
            raise ValueError("trace_id is required")
        if not self.name:
            raise ValueError("name is required")
        if self.data_type == "boolean" and self.value not in (0, 1):
            raise ValueError(f"boolean score value must be 0 or 1, got {self.value}")
        if self.data_type == "categorical" and not self.string_value:
            raise ValueError("categorical score requires string_value")

    def to_dict(self) -> dict:
        return {
            "score_id": self.score_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "value": self.value,
            "kind": self.kind,
            "data_type": self.data_type,
            "string_value": self.string_value,
            "comment": self.comment,
            "source": self.source,
            "project_id": self.project_id,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Score":
        return cls(
            trace_id=d.get("trace_id", ""),
            name=d.get("name", ""),
            value=d.get("value", 0),
            span_id=d.get("span_id"),
            kind=d.get("kind", "human"),
            data_type=d.get("data_type", "numeric"),
            string_value=d.get("string_value"),
            comment=d.get("comment"),
            source=d.get("source"),
            project_id=d.get("project_id"),
            score_id=d.get("score_id") or str(uuid.uuid4()),
            created_at=_parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
            metadata=d.get("metadata", {}),
        )
