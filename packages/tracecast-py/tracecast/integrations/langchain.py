import uuid
from datetime import datetime, timezone
from typing import Optional
from langchain_core.callbacks.base import BaseCallbackHandler
from ..core.tracer import Tracer
from ..core.token_counter import _from_langchain_response
from ..core.cost_calculator import calculate_cost
from ..core.logger import TraceCastLogger
from ..models.span import Span, SpanType


class TraceCastCallback(BaseCallbackHandler):
    def __init__(self, tracer: Tracer):
        self.tracer = tracer
        self._span_stack: dict[str, Span] = {}
        self._logger: Optional[TraceCastLogger] = getattr(tracer, "_tc_logger", None)


    def _trace_name(self) -> str:
        trace = self.tracer.current()
        return trace.name if trace else "tracecast"

    def _elapsed_ms(self, span: Span) -> Optional[float]:
        if span.finished_at and span.started_at:
            delta = span.finished_at - span.started_at
            return delta.total_seconds() * 1000
        return None


    def on_llm_start(self, serialized, prompts, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "unknown")
        )
        self._span_stack[run_id] = Span(
            span_id=run_id,
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
        )
        if self._logger:
            self._logger.llm_start(self._trace_name(), model=model)

    def on_llm_end(self, response, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._span_stack.pop(run_id, None)
        if not span:
            return
        span.finished_at = datetime.now(timezone.utc)
        usage = _from_langchain_response(response.llm_output or {})
        if usage["input"] == 0 and usage["output"] == 0:
            try:
                meta = response.generations[0][0].message.usage_metadata
                usage = {
                    "input": meta.get("input_tokens", 0),
                    "output": meta.get("output_tokens", 0),
                }
            except (IndexError, AttributeError):
                pass
        span.tokens_in  = usage["input"]
        span.tokens_out = usage["output"]
        span.cost_usd   = calculate_cost(span.model, span.tokens_in, span.tokens_out)
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)
        if self._logger:
            self._logger.llm_end(
                self._trace_name(),
                model=span.model or "unknown",
                tokens_in=span.tokens_in,
                tokens_out=span.tokens_out,
                cost_usd=span.cost_usd,
                latency_ms=self._elapsed_ms(span),
            )

    def on_llm_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._span_stack.get(run_id)
        if self._logger and span:
            self._logger.llm_error(self._trace_name(), model=span.model or "unknown", error=str(error))
        self._close_span_with_error(run_id, error)


    def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        name = serialized.get("name", "unknown_tool")
        self._span_stack[run_id] = Span(
            span_id=run_id,
            type=SpanType.TOOL,
            name=name,
            started_at=datetime.now(timezone.utc),
        )
        if self._logger:
            self._logger.tool_start(self._trace_name(), name=name, input_str=input_str)

    def on_tool_end(self, output, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._span_stack.pop(run_id, None)
        if not span:
            return
        span.finished_at = datetime.now(timezone.utc)
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)
        if self._logger:
            self._logger.tool_end(self._trace_name(), name=span.name, latency_ms=self._elapsed_ms(span))

    def on_tool_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._span_stack.get(run_id)
        if self._logger and span:
            self._logger.tool_error(self._trace_name(), name=span.name, error=str(error))
        self._close_span_with_error(run_id, error)


    def on_chain_start(self, serialized, inputs, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        parent_run_id = kwargs.get("parent_run_id")
        if serialized:
            ids = serialized.get("id") or []
            name = (ids[-1] if ids else None) or serialized.get("name", "chain")
        else:
            name = kwargs.get("name", "chain")
        self._span_stack[run_id] = Span(
            span_id=run_id,
            type=SpanType.AGENT,
            name=f"chain:{name}",
            started_at=datetime.now(timezone.utc),
        )
        if self._logger and parent_run_id is None:
            self._logger.chain_start(self._trace_name(), name=name)

    def on_chain_end(self, outputs, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._span_stack.pop(run_id, None)
        if not span:
            return
        span.finished_at = datetime.now(timezone.utc)
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)

    def on_chain_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._span_stack.get(run_id)
        if self._logger and span:
            self._logger.chain_error(self._trace_name(), name=span.name, error=str(error))
        self._close_span_with_error(run_id, error)


    def _close_span_with_error(self, run_id: str, error) -> None:
        span = self._span_stack.pop(run_id, None)
        if not span:
            return
        span.finished_at = datetime.now(timezone.utc)
        span.metadata = {**(span.metadata or {}), "_error": str(error)}
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)
