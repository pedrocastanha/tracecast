"""Tests for LlamaIndexInstrumentor using a fake llama_index module."""

import sys
import types
import pytest
from unittest.mock import MagicMock

from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_llama_index():
    """Inject a fake llama_index module structure into sys.modules."""
    llama = types.ModuleType("llama_index")
    core = types.ModuleType("llama_index.core")
    instrumentation = types.ModuleType("llama_index.core.instrumentation")

    dispatcher = MagicMock()
    dispatcher.span_handlers = []
    instrumentation.get_dispatcher = MagicMock(return_value=dispatcher)

    core.instrumentation = instrumentation
    llama.core = core

    sys.modules["llama_index"] = llama
    sys.modules["llama_index.core"] = core
    sys.modules["llama_index.core.instrumentation"] = instrumentation

    return llama, core, instrumentation, dispatcher


def _cleanup_fake_llama_index():
    for k in list(sys.modules):
        if k.startswith("llama_index") or k.startswith("tracecast.instrumentors.llamaindex"):
            del sys.modules[k]


class TestLlamaIndexInstrumentor:
    def setup_method(self):
        _cleanup_fake_llama_index()
        self.llama, self.core, self.instrumentation, self.dispatcher = _make_fake_llama_index()

    def teardown_method(self):
        _cleanup_fake_llama_index()

    def test_patch_calls_add_span_handler(self):
        from tracecast.instrumentors.llamaindex_inst import LlamaIndexInstrumentor
        inst = LlamaIndexInstrumentor()
        inst.patch()
        self.dispatcher.add_span_handler.assert_called_once()
        inst.unpatch()

    def test_is_patched_lifecycle(self):
        from tracecast.instrumentors.llamaindex_inst import LlamaIndexInstrumentor
        inst = LlamaIndexInstrumentor()
        assert not inst.is_patched()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()
        assert not inst.is_patched()

    def test_patch_idempotent(self):
        from tracecast.instrumentors.llamaindex_inst import LlamaIndexInstrumentor
        inst = LlamaIndexInstrumentor()
        inst.patch()
        inst.patch()  # second call should be no-op
        self.dispatcher.add_span_handler.assert_called_once()
        inst.unpatch()

    def test_unpatch_removes_handler(self):
        from tracecast.instrumentors.llamaindex_inst import LlamaIndexInstrumentor
        inst = LlamaIndexInstrumentor()
        inst.patch()

        handler = inst._handler
        # Manually add handler to span_handlers list so unpatch can remove it
        self.dispatcher.span_handlers = [handler]

        inst.unpatch()
        assert handler not in self.dispatcher.span_handlers
        assert inst._handler is None

    def test_unpatch_when_not_patched_is_safe(self):
        from tracecast.instrumentors.llamaindex_inst import LlamaIndexInstrumentor
        inst = LlamaIndexInstrumentor()
        inst.unpatch()  # should not raise


class TestTraceCastSpanHandler:
    def setup_method(self):
        _cleanup_fake_llama_index()
        self.llama, self.core, self.instrumentation, self.dispatcher = _make_fake_llama_index()

    def teardown_method(self):
        _cleanup_fake_llama_index()

    def test_new_span_no_active_trace(self):
        """new_span does nothing when there's no active trace."""
        from tracecast.instrumentors._llamaindex_handler import TraceCastSpanHandler
        handler = TraceCastSpanHandler()
        handler.new_span(id_="span-1", bound_args=MagicMock(), instance=None,
                         parent_span_id=None, tags={}, kwargs={})
        assert "span-1" not in handler._open_spans

    def test_new_span_with_active_trace(self):
        """new_span stores a span in _open_spans when a trace is active."""
        from tracecast.instrumentors._llamaindex_handler import TraceCastSpanHandler

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])

        handler = TraceCastSpanHandler()

        with tracer.trace("li-test"):
            handler.new_span(id_="span-42", bound_args=MagicMock(), instance=None,
                             parent_span_id=None, tags={}, kwargs={})
            assert "span-42" in handler._open_spans

    def test_prepare_to_exit_span_finalizes(self):
        """prepare_to_exit_span appends the span to the active trace."""
        from tracecast.instrumentors._llamaindex_handler import TraceCastSpanHandler

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        handler = TraceCastSpanHandler()

        with tracer.trace("li-exit-test"):
            handler.new_span(id_="s1", bound_args=MagicMock(), instance=None,
                             parent_span_id=None, tags={}, kwargs={})
            result = MagicMock()
            result.raw = None
            handler.prepare_to_exit_span(id_="s1", bound_args=MagicMock(),
                                         instance=None, result=result, kwargs={})

        assert len(exporter.traces) == 1
        spans = exporter.traces[0]["spans"]
        assert len(spans) == 1
        assert spans[0]["name"] == "llamaindex:span"

    def test_prepare_to_exit_span_extracts_tokens_from_raw(self):
        """Token counts are extracted from result.raw when present."""
        from tracecast.instrumentors._llamaindex_handler import TraceCastSpanHandler

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        handler = TraceCastSpanHandler()

        with tracer.trace("li-tokens-test"):
            handler.new_span(id_="s2", bound_args=MagicMock(), instance=None,
                             parent_span_id=None, tags={}, kwargs={})

            raw = MagicMock()
            raw.usage = MagicMock()
            raw.usage.prompt_tokens = 100
            raw.usage.completion_tokens = 50

            result = MagicMock()
            result.raw = raw
            handler.prepare_to_exit_span(id_="s2", bound_args=MagicMock(),
                                         instance=None, result=result, kwargs={})

        spans = exporter.traces[0]["spans"]
        assert spans[0]["tokens_in"] == 100
        assert spans[0]["tokens_out"] == 50

    def test_prepare_to_drop_span_records_error(self):
        """prepare_to_drop_span finalizes span with error metadata."""
        from tracecast.instrumentors._llamaindex_handler import TraceCastSpanHandler

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        handler = TraceCastSpanHandler()

        with tracer.trace("li-error-test"):
            handler.new_span(id_="s3", bound_args=MagicMock(), instance=None,
                             parent_span_id=None, tags={}, kwargs={})
            handler.prepare_to_drop_span(id_="s3", bound_args=MagicMock(),
                                         instance=None, err=ValueError("oops"), kwargs={})

        spans = exporter.traces[0]["spans"]
        assert len(spans) == 1
        assert spans[0]["status"] == "error"
        assert spans[0]["error"] == "oops"
