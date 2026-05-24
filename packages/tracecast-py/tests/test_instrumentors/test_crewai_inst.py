"""Tests for CrewAIInstrumentor using a fake crewai module."""

import sys
import types
import pytest
from unittest.mock import MagicMock

from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_crewai():
    """Inject a fake crewai module with a Crew class."""
    crewai = types.ModuleType("crewai")

    class Crew:
        def kickoff(self, inputs=None):
            result = MagicMock()
            result.token_usage = MagicMock()
            result.token_usage.total_tokens = 500
            result.token_usage.prompt_tokens = 300
            result.token_usage.completion_tokens = 200
            result.raw = "Crew finished"
            return result

    crewai.Crew = Crew
    sys.modules["crewai"] = crewai
    return crewai, Crew


def _cleanup_fake_crewai():
    for k in list(sys.modules):
        if k.startswith("crewai") or k.startswith("tracecast.instrumentors.crewai"):
            del sys.modules[k]


class TestCrewAIInstrumentor:
    def setup_method(self):
        _cleanup_fake_crewai()
        self.crewai, self.Crew = _make_fake_crewai()

    def teardown_method(self):
        _cleanup_fake_crewai()

    def test_patch_replaces_kickoff(self):
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        original = self.Crew.kickoff
        inst = CrewAIInstrumentor()
        inst.patch()
        assert self.Crew.kickoff is not original
        inst.unpatch()

    def test_unpatch_restores_kickoff(self):
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        original = self.Crew.kickoff
        inst = CrewAIInstrumentor()
        inst.patch()
        inst.unpatch()
        assert self.Crew.kickoff is original

    def test_is_patched_lifecycle(self):
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        inst = CrewAIInstrumentor()
        assert not inst.is_patched()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()
        assert not inst.is_patched()

    def test_patch_idempotent(self):
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        inst = CrewAIInstrumentor()
        inst.patch()
        first_patched = self.Crew.kickoff
        inst.patch()  # second call should be no-op
        assert self.Crew.kickoff is first_patched
        inst.unpatch()

    def test_no_trace_passthrough(self):
        """When no trace is active, kickoff returns result normally."""
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        inst = CrewAIInstrumentor()
        inst.patch()
        crew = self.Crew()
        result = crew.kickoff(inputs={"topic": "AI"})
        assert result.raw == "Crew finished"
        inst.unpatch()

    def test_trace_active_captures_span(self):
        """When trace is active, kickoff creates an AGENT span with token counts."""
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        inst = CrewAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        crew = self.Crew()

        with tracer.trace("crewai-test"):
            result = crew.kickoff(inputs={"topic": "AI"})

        assert result.raw == "Crew finished"
        assert len(exporter.traces) == 1
        spans = exporter.traces[0]["spans"]
        assert len(spans) == 1
        span = spans[0]
        assert span["type"] == "agent"
        assert span["name"] == "crewai:kickoff"
        assert span["tokens_in"] == 300
        assert span["tokens_out"] == 200
        inst.unpatch()

    def test_error_path_appends_span_with_error(self):
        """If kickoff raises, span is recorded with _error metadata."""
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor

        class FailingCrew:
            def kickoff(self, inputs=None):
                raise RuntimeError("crew failed")

        import crewai
        crewai.Crew = FailingCrew

        inst = CrewAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        crew = FailingCrew()

        with pytest.raises(RuntimeError, match="crew failed"):
            with tracer.trace("crewai-error-test"):
                crew.kickoff()

        assert len(exporter.traces) == 1
        spans = exporter.traces[0]["spans"]
        assert len(spans) == 1
        assert "_error" in spans[0]["metadata"]
        assert spans[0]["metadata"]["_error"] == "crew failed"
        inst.unpatch()

    def test_unpatch_when_not_patched_is_safe(self):
        from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
        inst = CrewAIInstrumentor()
        inst.unpatch()  # should not raise
