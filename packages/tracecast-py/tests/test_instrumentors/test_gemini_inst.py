import sys
import types
import pytest
from unittest.mock import MagicMock
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_gemini():
    """Create a fake google.generativeai module structure matching the Gemini SDK."""
    google = types.ModuleType("google")
    genai = types.ModuleType("google.generativeai")

    class GenerativeModel:
        def __init__(self, model_name="gemini-2.5-flash"):
            self.model_name = model_name

        def generate_content(self, contents, **kwargs):
            response = MagicMock()
            response.usage_metadata.prompt_token_count = 150
            response.usage_metadata.candidates_token_count = 60
            response.usage_metadata.cached_content_token_count = 0
            response.candidates = [MagicMock()]
            response.candidates[0].content.parts = [MagicMock(text="Gemini response")]
            return response

    genai.GenerativeModel = GenerativeModel
    google.generativeai = genai

    sys.modules["google"] = google
    sys.modules["google.generativeai"] = genai
    return genai, GenerativeModel


def _cleanup_fake_gemini():
    for k in list(sys.modules):
        if k.startswith("google"):
            del sys.modules[k]


class TestGeminiInstrumentor:
    def setup_method(self):
        self.genai, self.GenerativeModel = _make_fake_gemini()

    def teardown_method(self):
        _cleanup_fake_gemini()

    def test_patch_and_unpatch(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor
        original = self.GenerativeModel.generate_content
        inst = GeminiInstrumentor()
        inst.patch()
        assert self.GenerativeModel.generate_content is not original
        inst.unpatch()
        assert self.GenerativeModel.generate_content is original

    def test_is_patched(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor
        inst = GeminiInstrumentor()
        assert not inst.is_patched()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()
        assert not inst.is_patched()

    def test_no_trace_calls_original(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor
        inst = GeminiInstrumentor()
        inst.patch()
        model = self.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content("Hello, world!")
        # Values come from our fake GenerativeModel.generate_content
        assert response.usage_metadata.prompt_token_count == 150
        assert response.usage_metadata.candidates_token_count == 60
        inst.unpatch()

    def test_trace_active_captures_span(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor
        inst = GeminiInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        model = self.GenerativeModel("gemini-2.5-flash")

        with tracer.trace("test-gemini-trace"):
            model.generate_content("Tell me a joke")

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["type"] == "llm"
        assert span["model"] == "gemini-2.5-flash"
        assert span["tokens_in"] == 150
        assert span["tokens_out"] == 60
        inst.unpatch()

    def test_exception_appends_span_with_error(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor

        # Replace generate_content with a raising function BEFORE patching so
        # the instrumentor saves the raising function as _original_generate.
        def raising_generate(model_self, contents, **kwargs):
            raise RuntimeError("gemini api error")

        self.GenerativeModel.generate_content = raising_generate

        inst = GeminiInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        model = self.GenerativeModel("gemini-2.5-flash")

        with pytest.raises(RuntimeError, match="gemini api error"):
            with tracer.trace("test-gemini-error-trace"):
                model.generate_content("Hello!")

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["status"] == "error"
        assert span["error"] == "gemini api error"
        inst.unpatch()
