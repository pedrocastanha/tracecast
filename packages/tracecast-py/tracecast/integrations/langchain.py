import uuid
from datetime import datetime, timezone
from typing import Optional, Union, Tuple
from langchain_core.callbacks.base import BaseCallbackHandler
from ..core.tracer import Tracer, push_span, pop_span
from ..core.token_counter import _from_langchain_response
from ..core.cost_calculator import calculate_cost
from ..core.logger import TraceCastLogger
from ..models.span import Span, SpanType


def _join_prompts(prompts) -> Optional[str]:
    if not prompts:
        return None
    if isinstance(prompts, (list, tuple)):
        return "\n".join(str(p) for p in prompts)
    return str(prompts)


def _stringify(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _extract_generation_text(response) -> Optional[str]:
    try:
        generation = response.generations[0][0]
    except (IndexError, AttributeError):
        return None
    text = getattr(generation, "text", None)
    if text:
        return text
    message = getattr(generation, "message", None)
    content = getattr(message, "content", None) if message else None
    return _stringify(content)


class TraceCastCallback(BaseCallbackHandler):
    def __init__(self, tracer: Tracer):
        self.tracer = tracer
        # Values: (span, ctx_token | None). Tool spans hold a token to restore
        # _current_span after the tool finishes; LLM spans store None.
        self._span_stack: dict[str, Tuple[Span, object]] = {}
        self._logger: Optional[TraceCastLogger] = getattr(tracer, "_tc_logger", None)


    def _trace_name(self) -> str:
        trace = self.tracer.current()
        return trace.name if trace else "tracecast"

    def _elapsed_ms(self, span: Span) -> Optional[float]:
        if span.finished_at and span.started_at:
            delta = span.finished_at - span.started_at
            return delta.total_seconds() * 1000
        return None


    def _parent_id(self, kwargs) -> Optional[str]:
        span = Tracer.current_span()
        return span.span_id if span else None

    def on_llm_start(self, serialized, prompts, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "unknown")
        )
        self._span_stack[run_id] = (Span(
            span_id=run_id,
            parent_span_id=self._parent_id(kwargs),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=self._join_prompts(prompts),
        ), None)
        if self._logger:
            self._logger.llm_start(self._trace_name(), model=model)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "unknown")
        )
        self._span_stack[run_id] = (Span(
            span_id=run_id,
            parent_span_id=self._parent_id(kwargs),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=self._join_messages(messages),
        ), None)
        if self._logger:
            self._logger.llm_start(self._trace_name(), model=model)

    @staticmethod
    def _join_prompts(prompts) -> Optional[str]:
        try:
            if not prompts:
                return None
            return "\n\n".join(str(p) for p in prompts)
        except Exception:
            return None

    @staticmethod
    def _join_messages(messages) -> Optional[str]:
        try:
            parts = []
            for group in messages or []:
                for m in group:
                    role = getattr(m, "type", None) or m.__class__.__name__
                    content = getattr(m, "content", "")
                    parts.append(f"[{role}] {content}")
            return "\n".join(parts) if parts else None
        except Exception:
            return None

    @staticmethod
    def _extract_output(response) -> Optional[str]:
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            if msg is not None and getattr(msg, "content", None):
                return str(msg.content)
            text = getattr(gen, "text", None)
            return str(text) if text else None
        except (IndexError, AttributeError):
            return None

    def on_llm_end(self, response, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        entry = self._span_stack.pop(run_id, None)
        if not entry:
            return
        span, _ = entry
        span.finished_at = datetime.now(timezone.utc)
        span.output = self._extract_output(response)
        usage = _from_langchain_response(response.llm_output or {})
        if usage["input"] == 0 and usage["output"] == 0:
            try:
                meta = response.generations[0][0].message.usage_metadata
                if isinstance(meta, dict):
                    details = meta.get("input_token_details") or {}
                    usage = {
                        "input":  meta.get("input_tokens", 0),
                        "output": meta.get("output_tokens", 0),
                        "cached": details.get("cache_read") or details.get("cached") or 0,
                    }
            except (IndexError, AttributeError):
                pass
        span.tokens_in        = usage["input"]
        span.tokens_out       = usage["output"]
        span.tokens_in_cached = int(usage.get("cached", 0) or 0)
        span.cost_usd         = calculate_cost(
            span.model, span.tokens_in, span.tokens_out,
            tokens_in_cached=span.tokens_in_cached,
        )
        span.output = _extract_generation_text(response)
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)
        if self._logger:
            self._logger.llm_end(
                self._trace_name(),
                model=span.model or "unknown",
                tokens_in=span.tokens_in,
                tokens_out=span.tokens_out,
                tokens_in_cached=span.tokens_in_cached,
                cost_usd=span.cost_usd,
                latency_ms=self._elapsed_ms(span),
            )

    def on_llm_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        entry = self._span_stack.get(run_id)
        if self._logger and entry:
            span, _ = entry
            self._logger.llm_error(self._trace_name(), model=span.model or "unknown", error=str(error))
        self._close_span_with_error(run_id, error)

    def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        name = serialized.get("name", "unknown_tool")
        span = Span(
            span_id=run_id,
            parent_span_id=self._parent_id(kwargs),
            type=SpanType.TOOL,
            name=name,
            started_at=datetime.now(timezone.utc),
            input=_stringify(input_str),
        )
        # Push tool span as current so inner LLM calls nest correctly under it.
        token = push_span(span)
        self._span_stack[run_id] = (span, token)
        if self._logger:
            self._logger.tool_start(self._trace_name(), name=name, input_str=input_str)

    def on_tool_end(self, output, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        entry = self._span_stack.pop(run_id, None)
        if not entry:
            return
        span, token = entry
        if token is not None:
            pop_span(token)
        span.finished_at = datetime.now(timezone.utc)
        span.output = _stringify(output)
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)
        if self._logger:
            self._logger.tool_end(self._trace_name(), name=span.name, latency_ms=self._elapsed_ms(span))

    def on_tool_error(self, error, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        entry = self._span_stack.get(run_id)
        if self._logger and entry:
            span, _ = entry
            self._logger.tool_error(self._trace_name(), name=span.name, error=str(error))
        self._close_span_with_error(run_id, error)


    def on_chain_start(self, serialized, inputs, **kwargs):
        pass  # skip internal LangGraph/LangChain chains — @trace_span handles high-level nodes

    def on_chain_end(self, outputs, **kwargs):
        pass

    def on_chain_error(self, error, **kwargs):
        pass


    def _close_span_with_error(self, run_id: str, error) -> None:
        entry = self._span_stack.pop(run_id, None)
        if not entry:
            return
        span, token = entry
        if token is not None:
            pop_span(token)
        span.finished_at = datetime.now(timezone.utc)
        span.mark_error(error)
        trace = self.tracer.current()
        if trace:
            trace.spans.append(span)
