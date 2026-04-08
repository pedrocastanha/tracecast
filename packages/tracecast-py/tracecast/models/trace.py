from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from .span import Span, SpanType


@dataclass
class Trace:
    trace_id: str
    name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    model: Optional[str] = None
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_tokens_in_cached: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: Optional[int] = None
    tools_used: Dict[str, int] = field(default_factory=dict)
    spans: List[Span] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def _finalize(self) -> None:
        self.total_tokens_in        = sum(s.tokens_in         for s in self.spans)
        self.total_tokens_out       = sum(s.tokens_out        for s in self.spans)
        self.total_tokens_in_cached = sum(s.tokens_in_cached  for s in self.spans)
        self.total_tokens           = self.total_tokens_in + self.total_tokens_out
        self.cost_usd         = sum(s.cost_usd   for s in self.spans)

        if self.finished_at:
            delta = self.finished_at - self.started_at
            self.latency_ms = int(delta.total_seconds() * 1000)

        llm_spans = [s for s in self.spans if s.type == SpanType.LLM and s.model]
        if llm_spans:
            self.model = max(llm_spans, key=lambda s: s.total_tokens).model

        self.tools_used = {}
        for s in self.spans:
            if s.type == SpanType.TOOL:
                self.tools_used[s.name] = self.tools_used.get(s.name, 0) + 1

    def to_dict(self) -> dict:
        return {
            "trace_id":         self.trace_id,
            "name":             self.name,
            "session_id":       self.session_id,
            "user_id":          self.user_id,
            "project_id":       self.project_id,
            "model":            self.model,
            "total_tokens_in":        self.total_tokens_in,
            "total_tokens_out":       self.total_tokens_out,
            "total_tokens_in_cached": self.total_tokens_in_cached,
            "total_tokens":           self.total_tokens,
            "cost_usd":         self.cost_usd,
            "latency_ms":       self.latency_ms,
            "tools_used":       self.tools_used,
            "spans":            [s.to_dict() for s in self.spans],
            "metadata":         self.metadata,
            "started_at":       self.started_at.isoformat(),
            "finished_at":      self.finished_at.isoformat() if self.finished_at else None,
        }
