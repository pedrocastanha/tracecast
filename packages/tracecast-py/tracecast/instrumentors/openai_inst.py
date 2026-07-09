import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor, active_parent_id


# Only LangChain's own LLM-wrapper packages directly invoke the underlying
# provider client on their own behalf, triggering LangChain's callback system
# (which TraceCastCallback hooks into via LangChainInstrumentor). Orchestration
# packages (langchain_core.tools, langchain.agents, langgraph.*) run *above*
# a raw client call made by application code (e.g. a @tool function) — that
# call is invisible to LangChain's callbacks, so it must NOT be deferred here,
# or it silently disappears from tracing entirely.
_LANGCHAIN_LLM_WRAPPER_PREFIXES = (
    "langchain_openai.",
    "langchain_community.chat_models",
    "langchain_community.llms",
    "langchain.chat_models",
    "langchain.llms",
)


def _handled_by_langchain() -> bool:
    from ..instrument import _registry

    inst = _registry.get("langchain")
    if inst is None or not inst.is_patched():
        return False
    frame = sys._getframe(2)
    depth = 0
    while frame is not None and depth < 60:
        module = frame.f_globals.get("__name__", "")
        if module.startswith(_LANGCHAIN_LLM_WRAPPER_PREFIXES):
            return True
        frame = frame.f_back
        depth += 1
    return False


class OpenAIInstrumentor(BaseInstrumentor):

    def __init__(self) -> None:
        self._original_create: Optional[Any] = None
        self._original_acreate: Optional[Any] = None
        self._original_embeddings_create: Optional[Any] = None
        self._original_async_embeddings_create: Optional[Any] = None
        self._original_transcriptions_create: Optional[Any] = None
        self._original_async_transcriptions_create: Optional[Any] = None
        self._original_speech_create: Optional[Any] = None
        self._original_async_speech_create: Optional[Any] = None
        self._patched: bool = False

    def patch(self, *, chat: bool = True, embeddings: bool = True, audio: bool = True) -> None:
        """Patch the requested OpenAI API surfaces.

        `chat=False` lets callers add embeddings/audio coverage without
        re-patching chat.completions — needed when chat completions are
        already traced through another mechanism (e.g. a manually-wired
        LangChain callback), where re-patching would double-count spans.
        """
        if self._patched:
            return

        if chat:
            import openai.resources.chat.completions as mod

            # Sync
            self._original_create = mod.Completions.create
            self_ref = self
            _orig_create = self._original_create

            def patched_create(client_self, *args, **kwargs):
                return self_ref._intercept(client_self, args, kwargs, _orig_create)

            mod.Completions.create = patched_create

            # Async
            if hasattr(mod, "AsyncCompletions"):
                self._original_acreate = mod.AsyncCompletions.create
                _orig_acreate = self._original_acreate

                async def patched_acreate(client_self, *args, **kwargs):
                    return await self_ref._async_intercept(client_self, args, kwargs, _orig_acreate)

                mod.AsyncCompletions.create = patched_acreate

        if embeddings:
            self._patch_embeddings()
        if audio:
            self._patch_audio()

        self._patched = True

    def _patch_embeddings(self) -> None:
        try:
            import openai.resources.embeddings as emb_mod
        except ImportError:
            return
        self._original_embeddings_create = emb_mod.Embeddings.create
        self_ref = self
        _orig = self._original_embeddings_create

        def patched(client_self, *args, **kwargs):
            return self_ref._intercept_embeddings(client_self, args, kwargs, _orig)

        emb_mod.Embeddings.create = patched

        if hasattr(emb_mod, "AsyncEmbeddings"):
            self._original_async_embeddings_create = emb_mod.AsyncEmbeddings.create
            _orig_async = self._original_async_embeddings_create

            async def patched_async(client_self, *args, **kwargs):
                return await self_ref._async_intercept_embeddings(client_self, args, kwargs, _orig_async)

            emb_mod.AsyncEmbeddings.create = patched_async

    def _patch_audio(self) -> None:
        try:
            import openai.resources.audio.transcriptions as tr_mod
        except ImportError:
            tr_mod = None
        if tr_mod is not None:
            self._original_transcriptions_create = tr_mod.Transcriptions.create
            self_ref = self
            _orig = self._original_transcriptions_create

            def patched_tr(client_self, *args, **kwargs):
                return self_ref._intercept_transcription(client_self, args, kwargs, _orig)

            tr_mod.Transcriptions.create = patched_tr

            if hasattr(tr_mod, "AsyncTranscriptions"):
                self._original_async_transcriptions_create = tr_mod.AsyncTranscriptions.create
                _orig_async_tr = self._original_async_transcriptions_create

                async def patched_async_tr(client_self, *args, **kwargs):
                    return await self_ref._async_intercept_transcription(client_self, args, kwargs, _orig_async_tr)

                tr_mod.AsyncTranscriptions.create = patched_async_tr

        try:
            import openai.resources.audio.speech as sp_mod
        except ImportError:
            sp_mod = None
        if sp_mod is not None:
            self._original_speech_create = sp_mod.Speech.create
            self_ref = self
            _orig_sp = self._original_speech_create

            def patched_sp(client_self, *args, **kwargs):
                return self_ref._intercept_speech(client_self, args, kwargs, _orig_sp)

            sp_mod.Speech.create = patched_sp

            if hasattr(sp_mod, "AsyncSpeech"):
                self._original_async_speech_create = sp_mod.AsyncSpeech.create
                _orig_async_sp = self._original_async_speech_create

                async def patched_async_sp(client_self, *args, **kwargs):
                    return await self_ref._async_intercept_speech(client_self, args, kwargs, _orig_async_sp)

                sp_mod.AsyncSpeech.create = patched_async_sp

    def unpatch(self) -> None:
        if not self._patched:
            return
        if self._original_create is not None:
            import openai.resources.chat.completions as mod
            mod.Completions.create = self._original_create
            if self._original_acreate is not None:
                mod.AsyncCompletions.create = self._original_acreate
            self._original_create = None
            self._original_acreate = None

        if self._original_embeddings_create is not None:
            import openai.resources.embeddings as emb_mod
            emb_mod.Embeddings.create = self._original_embeddings_create
            self._original_embeddings_create = None
            if self._original_async_embeddings_create is not None:
                emb_mod.AsyncEmbeddings.create = self._original_async_embeddings_create
                self._original_async_embeddings_create = None

        if self._original_transcriptions_create is not None:
            import openai.resources.audio.transcriptions as tr_mod
            tr_mod.Transcriptions.create = self._original_transcriptions_create
            self._original_transcriptions_create = None
            if self._original_async_transcriptions_create is not None:
                tr_mod.AsyncTranscriptions.create = self._original_async_transcriptions_create
                self._original_async_transcriptions_create = None

        if self._original_speech_create is not None:
            import openai.resources.audio.speech as sp_mod
            sp_mod.Speech.create = self._original_speech_create
            self._original_speech_create = None
            if self._original_async_speech_create is not None:
                sp_mod.AsyncSpeech.create = self._original_async_speech_create
                self._original_async_speech_create = None

        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None or _handled_by_langchain():
            return original_fn(client_self, *args, **kwargs)
        return self._capture(client_self, args, kwargs, original_fn, trace)

    def _capture(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any, trace: Any) -> Any:
        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content, extract_input_text
        from ..core.cost_calculator import calculate_cost

        from ..core.payload import truncate_payload

        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, "openai")

        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=truncate_payload(input_text),
        )

        if kwargs.get("stream"):
            from ._streaming import stream_openai
            kwargs.setdefault("stream_options", {"include_usage": True})
            raw = original_fn(client_self, *args, **kwargs)
            return stream_openai(raw, span, trace, model)

        try:
            response = original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "openai")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(
            model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached
        )
        span.output = truncate_payload(extract_content(response, "openai"))
        trace.spans.append(span)

        return response

    async def _async_intercept(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None or _handled_by_langchain():
            return await original_fn(client_self, *args, **kwargs)
        return await self._async_capture(client_self, args, kwargs, original_fn, trace)

    async def _async_capture(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any, trace: Any) -> Any:
        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content, extract_input_text
        from ..core.cost_calculator import calculate_cost
        from ..core.payload import truncate_payload

        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, "openai")

        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=truncate_payload(input_text),
        )

        if kwargs.get("stream"):
            from ._streaming import astream_openai
            kwargs.setdefault("stream_options", {"include_usage": True})
            raw = await original_fn(client_self, *args, **kwargs)
            return astream_openai(raw, span, trace, model)

        try:
            response = await original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "openai")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(
            model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached
        )
        span.output = truncate_payload(extract_content(response, "openai"))
        trace.spans.append(span)
        return response

    def _intercept_embeddings(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None or _handled_by_langchain():
            return original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_cost

        model = kwargs.get("model", "unknown")
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.EMBEDDING,
            name=f"embedding:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
        )
        try:
            response = original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        usage = getattr(response, "usage", None)
        span.tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        span.cost_usd = calculate_cost(model, span.tokens_in, 0)
        trace.spans.append(span)
        return response

    def _intercept_transcription(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_audio_cost

        model = kwargs.get("model", "unknown")
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.AUDIO,
            name=f"audio:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
        )
        try:
            response = original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        duration = getattr(response, "duration", None)
        if duration is not None:
            span.metadata["duration_seconds"] = duration
            span.cost_usd = calculate_audio_cost(model, minutes=duration / 60)
        trace.spans.append(span)
        return response

    def _intercept_speech(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_audio_cost

        model = kwargs.get("model", "unknown")
        char_count = len(kwargs.get("input", "") or "")
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.AUDIO,
            name=f"audio:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            metadata={"char_count": char_count},
        )
        try:
            response = original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        span.cost_usd = calculate_audio_cost(model, chars=char_count)
        trace.spans.append(span)
        return response

    async def _async_intercept_embeddings(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None or _handled_by_langchain():
            return await original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_cost

        model = kwargs.get("model", "unknown")
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.EMBEDDING,
            name=f"embedding:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
        )
        try:
            response = await original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        usage = getattr(response, "usage", None)
        span.tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        span.cost_usd = calculate_cost(model, span.tokens_in, 0)
        trace.spans.append(span)
        return response

    async def _async_intercept_transcription(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return await original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_audio_cost

        model = kwargs.get("model", "unknown")
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.AUDIO,
            name=f"audio:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
        )
        try:
            response = await original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        duration = getattr(response, "duration", None)
        if duration is not None:
            span.metadata["duration_seconds"] = duration
            span.cost_usd = calculate_audio_cost(model, minutes=duration / 60)
        trace.spans.append(span)
        return response

    async def _async_intercept_speech(self, client_self: Any, args: tuple, kwargs: dict, original_fn: Any) -> Any:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return await original_fn(client_self, *args, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_audio_cost

        model = kwargs.get("model", "unknown")
        char_count = len(kwargs.get("input", "") or "")
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=active_parent_id(),
            type=SpanType.AUDIO,
            name=f"audio:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            metadata={"char_count": char_count},
        )
        try:
            response = await original_fn(client_self, *args, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.mark_error(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        span.cost_usd = calculate_audio_cost(model, chars=char_count)
        trace.spans.append(span)
        return response
