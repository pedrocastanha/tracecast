from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from .span import Span, SpanType

SCHEMA_VERSION = 2


@dataclass
class Trace:
    trace_id: str
    name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    model: Optional[str] = None
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_tokens_in_cached: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: Optional[int] = None
    tools_used: Dict[str, int] = field(default_factory=dict)
    spans: List[Span] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def _finalize(self) -> None:
        self.total_tokens_in        = sum(s.tokens_in         for s in self.spans)
        self.total_tokens_out       = sum(s.tokens_out        for s in self.spans)
        self.total_tokens_in_cached = sum(s.tokens_in_cached  for s in self.spans)
        self.total_tokens           = self.total_tokens_in + self.total_tokens_out
        self.cost_usd               = sum(s.cost_usd          for s in self.spans)

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

        self.edges = self._build_edges()

    def _build_edges(self) -> List[Dict[str, Any]]:
        known_ids = {s.span_id for s in self.spans}
        siblings: Dict[Optional[str], List[Span]] = {}
        for s in self.spans:
            parent = s.parent_span_id if s.parent_span_id in known_ids else None
            siblings.setdefault(parent, []).append(s)

        edges: List[Dict[str, Any]] = []
        for parent, group in siblings.items():
            ordered = sorted(group, key=lambda s: s.started_at)
            for previous, current in zip(ordered, ordered[1:]):
                edges.append({
                    "from": previous.span_id,
                    "to": current.span_id,
                    "parent_span_id": parent,
                    "conditional": False,
                })
        return edges

    def to_dict(self) -> dict:
        return {
            "schema_version":   SCHEMA_VERSION,
            "trace_id":         self.trace_id,
            "name":             self.name,
            "session_id":       self.session_id,
            "user_id":          self.user_id,
            "project_id":       self.project_id,
            "project_name":     self.project_name,
            "model":            self.model,
            "total_tokens_in":        self.total_tokens_in,
            "total_tokens_out":       self.total_tokens_out,
            "total_tokens_in_cached": self.total_tokens_in_cached,
            "total_tokens":           self.total_tokens,
            "cost_usd":         self.cost_usd,
            "latency_ms":       self.latency_ms,
            "tools_used":       self.tools_used,
            "spans":            [s.to_dict() for s in self.spans],
            "edges":            self.edges,
            "metadata":         self.metadata,
            "started_at":       self.started_at.isoformat(),
            "finished_at":      self.finished_at.isoformat() if self.finished_at else None,
        }
