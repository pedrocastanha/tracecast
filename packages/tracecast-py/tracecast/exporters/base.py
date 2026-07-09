import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from ..models.trace import Trace


class BaseExporter(ABC):
    @abstractmethod
    def export(self, trace: Trace) -> None:
        ...

    def export_doc(self, doc: Dict[str, Any]) -> None:
        self.export_docs_batch([doc])

    def export_batch(self, traces: list) -> None:
        docs = []
        live = []
        for item in traces:
            if isinstance(item, dict):
                docs.append(item)
            else:
                live.append(item)
        if docs:
            self.export_docs_batch(docs)
        for trace in live:
            self.export(trace)

    def export_docs_batch(self, docs: List[Dict[str, Any]]) -> None:
        for doc in docs:
            self.export(_trace_from_doc(doc))

    def export_summary(self, summary: Dict[str, Any]) -> None:
        self.export_doc(summary)

    async def aexport(self, trace: Trace) -> None:
        await asyncio.to_thread(self.export, trace)

    def export_eval(self, run) -> None:
        return None

    def query_evals(self, *, project_id=None, dataset_name=None,
                    from_dt=None, to_dt=None, limit: int = 50, offset: int = 0) -> list:
        return []

    def get_eval(self, run_id: str):
        return None

    def export_score(self, score) -> None:
        return None

    def query_scores(self, *, trace_id=None, name=None,
                     from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> list:
        return []

    def export_prompt(self, prompt) -> None:
        return None

    def query_prompts(self, *, name=None) -> list:
        return []


def _trace_from_doc(d: dict) -> Trace:
    from datetime import datetime
    from ..models.span import Span, SpanType, SpanStatus

    def _parse_dt(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None

    spans = []
    for s in d.get("spans") or []:
        spans.append(Span(
            span_id=s.get("span_id", s.get("spanId", "")),
            parent_span_id=s.get("parent_span_id", s.get("parentSpanId")),
            type=SpanType(s.get("type", "llm")),
            name=s.get("name", ""),
            status=SpanStatus(s.get("status", "ok")),
            error=s.get("error"),
            started_at=_parse_dt(s.get("started_at")) or datetime.now(),
            finished_at=_parse_dt(s.get("finished_at")),
            model=s.get("model"),
            tokens_in=s.get("tokens_in", s.get("tokensIn", 0)),
            tokens_out=s.get("tokens_out", s.get("tokensOut", 0)),
            tokens_in_cached=s.get("tokens_in_cached", s.get("tokensInCached", 0)),
            cost_usd=s.get("cost_usd", s.get("costUsd", 0.0)),
            input=s.get("input"),
            output=s.get("output"),
            metadata=s.get("metadata", {}),
        ))

    return Trace(
        trace_id=d.get("trace_id", d.get("traceId", "")),
        name=d.get("name", "unknown"),
        started_at=_parse_dt(d.get("started_at")) or datetime.now(),
        finished_at=_parse_dt(d.get("finished_at")),
        session_id=d.get("session_id", d.get("sessionId")),
        user_id=d.get("user_id", d.get("userId")),
        project_id=d.get("project_id", d.get("projectId")),
        project_name=d.get("project_name", d.get("projectName")),
        model=d.get("model"),
        total_tokens_in=d.get("total_tokens_in", d.get("totalTokensIn", 0)),
        total_tokens_out=d.get("total_tokens_out", d.get("totalTokensOut", 0)),
        total_tokens_in_cached=d.get("total_tokens_in_cached", d.get("totalTokensInCached", 0)),
        total_tokens=d.get("total_tokens", d.get("totalTokens", 0)),
        cost_usd=d.get("cost_usd", d.get("costUsd", 0.0)),
        latency_ms=d.get("latency_ms", d.get("latencyMs")),
        tools_used=d.get("tools_used", d.get("toolsUsed", {})),
        spans=spans,
        edges=d.get("edges", []),
        metadata=d.get("metadata", {}),
    )
