import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


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
class PromptVersion:
    name: str
    version: int
    template: str
    labels: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    prompt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "name": self.name,
            "version": self.version,
            "template": self.template,
            "labels": list(self.labels),
            "config": self.config,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptVersion":
        return cls(
            name=d.get("name", ""),
            version=int(d.get("version", 1)),
            template=d.get("template", ""),
            labels=list(d.get("labels", [])),
            config=d.get("config", {}),
            prompt_id=d.get("prompt_id") or str(uuid.uuid4()),
            created_at=_parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
        )
