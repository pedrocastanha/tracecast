from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class SpanType(str, Enum):
    LLM   = "llm"
    TOOL  = "tool"
    AGENT = "agent"


@dataclass
class Span:
    span_id: str
    type: SpanType
    name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_in_cached: int = 0
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def latency_ms(self) -> Optional[int]:
        if self.finished_at:
            delta = self.finished_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "type": self.type.value,
            "name": self.name,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_in_cached": self.tokens_in_cached,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "metadata": self.metadata,
        }
