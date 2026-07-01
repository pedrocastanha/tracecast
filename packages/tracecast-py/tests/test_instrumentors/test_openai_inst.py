import sys
import types
import pytest
from unittest.mock import MagicMock
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_openai():
    """Create a fake openai module structure matching openai SDK."""
    openai = types.ModuleType("openai")
    resources = types.ModuleType("openai.resources")
    chat = types.ModuleType("openai.resources.chat")
    completions_mod = types.ModuleType("openai.resources.chat.completions")

    class Completions:
        def create(self, **kwargs):
            response = MagicMock()
            response.usage.prompt_tokens = 100
            response.usage.completion_tokens = 50
            response.usage.prompt_tokens_details.cached_tokens = 0
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Hello!"
            return response

    completions_mod.Completions = Completions
    chat.completions = completions_mod
    resources.chat = chat
    openai.resources = resources

    embeddings_mod = types.ModuleType("openai.resources.embeddings")

    class Embeddings:
        def create(self, **kwargs):
            response = MagicMock()
            response.usage.prompt_tokens = 30
            response.usage.total_tokens = 30
            return response

    embeddings_mod.Embeddings = Embeddings
    resources.embeddings = embeddings_mod

    class AsyncEmbeddings:
        async def create(self, **kwargs):
            response = MagicMock()
            response.usage.prompt_tokens = 30
            response.usage.total_tokens = 30
            return response

    embeddings_mod.AsyncEmbeddings = AsyncEmbeddings

    audio = types.ModuleType("openai.resources.audio")
    transcriptions_mod = types.ModuleType("openai.resources.audio.transcriptions")

    class Transcriptions:
        def create(self, **kwargs):
            response = MagicMock()
            response.text = "transcribed text"
            response.duration = 42.0
            return response

    transcriptions_mod.Transcriptions = Transcriptions
    audio.transcriptions = transcriptions_mod

    class AsyncTranscriptions:
        async def create(self, **kwargs):
            response = MagicMock()
            response.text = "transcribed text"
            response.duration = 42.0
            return response

    transcriptions_mod.AsyncTranscriptions = AsyncTranscriptions

    speech_mod = types.ModuleType("openai.resources.audio.speech")

    class Speech:
        def create(self, **kwargs):
            return MagicMock()

    speech_mod.Speech = Speech
    audio.speech = speech_mod
    resources.audio = audio

    class AsyncSpeech:
        async def create(self, **kwargs):
            return MagicMock()

    speech_mod.AsyncSpeech = AsyncSpeech

    sys.modules["openai"] = openai
    sys.modules["openai.resources"] = resources
    sys.modules["openai.resources.chat"] = chat
    sys.modules["openai.resources.chat.completions"] = completions_mod
    sys.modules["openai.resources.embeddings"] = embeddings_mod
    sys.modules["openai.resources.audio"] = audio
    sys.modules["openai.resources.audio.transcriptions"] = transcriptions_mod
    sys.modules["openai.resources.audio.speech"] = speech_mod
    return openai, Completions


def _cleanup_fake_openai():
    for k in list(sys.modules):
        if k.startswith("openai"):
            del sys.modules[k]


class TestOpenAIInstrumentor:
    def setup_method(self):
        self.openai, self.Completions = _make_fake_openai()

    def teardown_method(self):
        _cleanup_fake_openai()

    def test_patch_replaces_create(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        original = self.Completions.create
        inst = OpenAIInstrumentor()
        inst.patch()
        assert self.Completions.create is not original
        inst.unpatch()
        assert self.Completions.create is original

    def test_is_patched(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        assert not inst.is_patched()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()
        assert not inst.is_patched()

    def test_no_trace_active_calls_original(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        inst.patch()
        client = self.Completions()
        response = client.create(model="gpt-4o", messages=[])
        assert response.choices[0].message.content == "Hello!"
        inst.unpatch()

    def test_trace_active_captures_span(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = self.Completions()

        with tracer.trace("test-trace"):
            response = client.create(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["type"] == "llm"
        assert span["model"] == "gpt-4o"
        assert span["tokens_in"] == 100
        assert span["tokens_out"] == 50
        assert span["cost_usd"] > 0
        inst.unpatch()

    def test_exception_appends_span_with_error(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor

        # Replace create with a raising function BEFORE patching so the
        # instrumentor saves the raising function as _original_create.
        def raising_create(self_c, *args, **kwargs):
            raise RuntimeError("network error")
        self.Completions.create = raising_create

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = self.Completions()

        with pytest.raises(RuntimeError, match="network error"):
            with tracer.trace("test-trace"):
                client.create(model="gpt-4o", messages=[])

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["status"] == "error"
        assert span["error"] == "network error"
        inst.unpatch()

    def test_async_trace_active_captures_span(self):
        """Verify AsyncCompletions.create is also patched."""
        import asyncio
        import openai.resources.chat.completions as mod

        class AsyncCompletions:
            async def create(self, *args, **kwargs):
                response = MagicMock()
                response.usage.prompt_tokens = 80
                response.usage.completion_tokens = 40
                response.usage.prompt_tokens_details.cached_tokens = 0
                response.choices = [MagicMock()]
                response.choices[0].message.content = "Async Hello!"
                return response

        mod.AsyncCompletions = AsyncCompletions

        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = AsyncCompletions()

        async def run():
            with tracer.trace("async-test-trace"):
                return await client.create(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

        asyncio.run(run())

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["tokens_in"] == 80
        assert span["tokens_out"] == 40
        inst.unpatch()

    def test_embeddings_captures_span(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.embeddings as emb_mod

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = emb_mod.Embeddings()

        with tracer.trace("test-trace"):
            client.create(model="text-embedding-3-small", input="hello world")

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["type"] == "embedding"
        assert span["model"] == "text-embedding-3-small"
        assert span["tokens_in"] == 30
        assert span["tokens_out"] == 0
        assert span["cost_usd"] > 0
        inst.unpatch()

    def test_embeddings_no_trace_active_calls_original(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.embeddings as emb_mod

        inst = OpenAIInstrumentor()
        inst.patch()
        client = emb_mod.Embeddings()
        response = client.create(model="text-embedding-3-small", input="hi")
        assert response.usage.prompt_tokens == 30
        inst.unpatch()

    def test_audio_transcription_captures_span_with_duration(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.audio.transcriptions as tr_mod

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = tr_mod.Transcriptions()

        with tracer.trace("test-trace"):
            client.create(model="whisper-1", file=b"fake-audio")

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["type"] == "audio"
        assert span["model"] == "whisper-1"
        assert span["metadata"]["duration_seconds"] == 42.0
        assert abs(span["cost_usd"] - (42.0 / 60 * 0.006)) < 1e-9
        inst.unpatch()

    def test_audio_speech_captures_span_with_char_count(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.audio.speech as sp_mod

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = sp_mod.Speech()

        with tracer.trace("test-trace"):
            client.create(model="gpt-4o-mini-tts", input="hello world", voice="alloy")

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["type"] == "audio"
        assert span["model"] == "gpt-4o-mini-tts"
        assert span["metadata"]["char_count"] == len("hello world")
        assert span["cost_usd"] > 0
        inst.unpatch()

    def test_async_embeddings_captures_span(self):
        """Bots almost universally use AsyncOpenAI — embeddings must be captured
        for the async client, not just the sync one."""
        import asyncio
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.embeddings as emb_mod

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = emb_mod.AsyncEmbeddings()

        async def run():
            with tracer.trace("test-trace"):
                await client.create(model="text-embedding-3-small", input="hello world")

        asyncio.run(run())

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["type"] == "embedding"
        assert span["tokens_in"] == 30
        assert span["cost_usd"] > 0
        inst.unpatch()

    def test_async_transcription_captures_span(self):
        import asyncio
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.audio.transcriptions as tr_mod

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = tr_mod.AsyncTranscriptions()

        async def run():
            with tracer.trace("test-trace"):
                await client.create(model="whisper-1", file=b"fake-audio")

        asyncio.run(run())

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["type"] == "audio"
        assert span["metadata"]["duration_seconds"] == 42.0
        assert span["cost_usd"] > 0
        inst.unpatch()

    def test_async_speech_captures_span(self):
        import asyncio
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.audio.speech as sp_mod

        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = sp_mod.AsyncSpeech()

        async def run():
            with tracer.trace("test-trace"):
                await client.create(model="gpt-4o-mini-tts", input="hello world", voice="alloy")

        asyncio.run(run())

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["type"] == "audio"
        assert span["metadata"]["char_count"] == len("hello world")
        inst.unpatch()

    def test_patch_chat_false_leaves_chat_completions_untouched(self):
        """Bots that already trace chat completions via a manual LangChain
        callback must be able to add embeddings/audio coverage without also
        re-patching chat.completions.create (which would double-count)."""
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.chat.completions as chat_mod
        import openai.resources.embeddings as emb_mod

        original_create = chat_mod.Completions.create
        inst = OpenAIInstrumentor()
        inst.patch(chat=False, embeddings=True, audio=False)

        assert chat_mod.Completions.create is original_create
        assert emb_mod.Embeddings.create is not None
        inst.unpatch()
        assert chat_mod.Completions.create is original_create

    def test_patch_embeddings_only_still_captures_span(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.embeddings as emb_mod

        inst = OpenAIInstrumentor()
        inst.patch(chat=False, embeddings=True, audio=False)

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = emb_mod.Embeddings()

        with tracer.trace("test-trace"):
            client.create(model="text-embedding-3-small", input="hi")

        assert len(exporter.traces) == 1
        assert exporter.traces[0]["spans"][0]["type"] == "embedding"
        inst.unpatch()

    def test_patch_defaults_to_all_surfaces(self):
        """Backward compat: patch() with no args still patches everything (bot-captacao's
        existing auto_instrument() flow must keep working unchanged)."""
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        import openai.resources.chat.completions as chat_mod

        original_create = chat_mod.Completions.create
        inst = OpenAIInstrumentor()
        inst.patch()
        assert chat_mod.Completions.create is not original_create
        inst.unpatch()


class TestHandledByLangchain:
    """_handled_by_langchain() decides whether the raw-client patch should skip a
    call because LangChain's own callback mechanism will independently capture it.
    It must distinguish "LangChain's ChatOpenAI is the direct caller" (defer) from
    "some LangChain orchestration exists upstream but app code is the direct caller"
    (capture) — a raw openai call made inside a @tool function or a langgraph node
    is NOT seen by LangChain's callback system and must not be silently dropped."""

    def setup_method(self):
        from tracecast.instrument import _registry, _reset
        _reset()

        class FakePatchedLangchainInstrumentor:
            def is_patched(self):
                return True

        _registry["langchain"] = FakePatchedLangchainInstrumentor()

    def teardown_method(self):
        from tracecast.instrument import _reset
        _reset()

    @staticmethod
    def _mid1():
        """Stands in for the `_intercept` frame (the direct caller of _handled_by_langchain)."""
        from tracecast.instrumentors.openai_inst import _handled_by_langchain
        return _handled_by_langchain()

    @staticmethod
    def _mid2():
        """Stands in for the `patched_create` frame: _handled_by_langchain's
        `sys._getframe(2)` lands here, so `.f_back` must reach the real caller."""
        return TestHandledByLangchain._mid1()

    @staticmethod
    def _call_from_module(module_name, fn):
        import types
        mod = types.ModuleType(module_name)
        mod.__dict__["_target"] = fn
        exec("def _caller():\n    return _target()\n", mod.__dict__)
        return mod.__dict__["_caller"]()

    def test_true_when_direct_caller_is_langchain_openai_wrapper(self):
        result = self._call_from_module("langchain_openai.chat_models.base", self._mid2)
        assert result is True

    def test_false_when_caller_is_langchain_orchestration_not_llm_wrapper(self):
        """The bug: a raw openai call inside a @tool function (stack has a
        langchain_core.tools frame above it, but the DIRECT caller is app code)
        must be captured, not silently dropped."""
        result = self._call_from_module("langchain_core.tools", self._mid2)
        assert result is False

    def test_false_when_caller_is_langgraph_node(self):
        result = self._call_from_module("langgraph.utils.runnable", self._mid2)
        assert result is False

    def test_false_when_langchain_instrumentor_not_patched(self):
        from tracecast.instrument import _registry
        _registry.clear()
        result = self._call_from_module("langchain_openai.chat_models.base", self._mid2)
        assert result is False
