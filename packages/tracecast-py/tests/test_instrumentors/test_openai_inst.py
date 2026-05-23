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

    sys.modules["openai"] = openai
    sys.modules["openai.resources"] = resources
    sys.modules["openai.resources.chat"] = chat
    sys.modules["openai.resources.chat.completions"] = completions_mod
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
        assert "_error" in span["metadata"]
        assert span["metadata"]["_error"] == "network error"
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
