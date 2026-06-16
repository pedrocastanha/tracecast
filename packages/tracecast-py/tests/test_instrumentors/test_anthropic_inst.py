import sys
import types
import pytest
from unittest.mock import MagicMock
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_anthropic():
    """Create a fake anthropic module structure matching the Anthropic SDK."""
    anthropic = types.ModuleType("anthropic")
    resources = types.ModuleType("anthropic.resources")
    messages_mod = types.ModuleType("anthropic.resources.messages")

    class Messages:
        def create(self, *args, **kwargs):
            response = MagicMock()
            response.usage.input_tokens = 200
            response.usage.output_tokens = 80
            response.usage.cache_read_input_tokens = 0
            response.content = [MagicMock(type="text", text="Response text")]
            return response

    messages_mod.Messages = Messages
    resources.messages = messages_mod
    anthropic.resources = resources

    sys.modules["anthropic"] = anthropic
    sys.modules["anthropic.resources"] = resources
    sys.modules["anthropic.resources.messages"] = messages_mod
    return anthropic, Messages, messages_mod


def _cleanup_fake_anthropic():
    for k in list(sys.modules):
        if k.startswith("anthropic"):
            del sys.modules[k]


class TestAnthropicInstrumentor:
    def setup_method(self):
        self.anthropic, self.Messages, self.messages_mod = _make_fake_anthropic()

    def teardown_method(self):
        _cleanup_fake_anthropic()

    def test_patch_and_unpatch(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        original = self.Messages.create
        inst = AnthropicInstrumentor()
        inst.patch()
        assert self.Messages.create is not original
        inst.unpatch()
        assert self.Messages.create is original

    def test_is_patched(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        assert not inst.is_patched()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()
        assert not inst.is_patched()

    def test_no_trace_calls_original(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        inst.patch()
        client = self.Messages()
        response = client.create(model="claude-3-5-sonnet-20241022", messages=[])
        # Usage values from our fake Messages.create
        assert response.usage.input_tokens == 200
        assert response.usage.output_tokens == 80
        inst.unpatch()

    def test_trace_active_captures_span(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = self.Messages()

        with tracer.trace("test-trace"):
            client.create(
                model="claude-3-5-sonnet-20241022",
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["type"] == "llm"
        assert span["model"] == "claude-3-5-sonnet-20241022"
        assert span["tokens_in"] == 200
        assert span["tokens_out"] == 80
        inst.unpatch()

    def test_exception_appends_span_with_error(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor

        # Replace create with a raising function BEFORE patching so the
        # instrumentor saves the raising function as _original_create.
        def raising_create(self_c, *args, **kwargs):
            raise RuntimeError("api error")

        self.Messages.create = raising_create

        inst = AnthropicInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = self.Messages()

        with pytest.raises(RuntimeError, match="api error"):
            with tracer.trace("test-trace"):
                client.create(model="claude-3-5-sonnet-20241022", messages=[])

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["status"] == "error"
        assert span["error"] == "api error"
        inst.unpatch()

    def test_async_trace_active_captures_span(self):
        """Verify AsyncMessages.create is also patched and captures spans."""
        import asyncio
        import anthropic.resources.messages as mod

        class AsyncMessages:
            async def create(self, *args, **kwargs):
                response = MagicMock()
                response.usage.input_tokens = 150
                response.usage.output_tokens = 60
                response.usage.cache_read_input_tokens = 0
                response.content = [MagicMock(type="text", text="Async response")]
                return response

        mod.AsyncMessages = AsyncMessages

        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = AsyncMessages()

        async def run():
            async with tracer.atrace("async-anthropic-trace"):
                return await client.create(model="claude-sonnet-4-6", messages=[])

        asyncio.run(run())

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["tokens_in"] == 150
        assert span["tokens_out"] == 60
        inst.unpatch()

    def test_async_exception_appends_span_with_error(self):
        """Verify async error path appends span with _error metadata."""
        import asyncio
        import anthropic.resources.messages as mod

        class AsyncMessages:
            async def create(self, *args, **kwargs):
                raise RuntimeError("async network error")

        mod.AsyncMessages = AsyncMessages

        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = AsyncMessages()

        async def run():
            with tracer.trace("async-error-trace"):
                return await client.create(model="claude-sonnet-4-6", messages=[])

        with pytest.raises(RuntimeError, match="async network error"):
            asyncio.run(run())

        assert len(exporter.traces) == 1
        span = exporter.traces[0]["spans"][0]
        assert span["status"] == "error"
        assert span["error"] == "async network error"
        inst.unpatch()
