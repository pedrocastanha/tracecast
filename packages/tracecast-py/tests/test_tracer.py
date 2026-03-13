import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from tracecast.core.tracer import Tracer
from tracecast.models.span import Span, SpanType
from datetime import datetime, timezone

def test_trace_contextmanager_chama_export():
    exporter = MagicMock()
    tracer = Tracer(exporters=[exporter])
    with tracer.trace("meu-agente", user_id="u1") as t:
        assert t.trace_id is not None
        assert t.name == "meu-agente"
        assert t.user_id == "u1"
    exporter.export.assert_called_once()
    trace_exportado = exporter.export.call_args[0][0]
    assert trace_exportado.finished_at is not None
    assert trace_exportado.latency_ms >= 0


def test_current_retorna_trace_dentro_do_bloco():
    tracer = Tracer()
    with tracer.trace("ctx-test") as t:
        assert Tracer.current() is t
    assert Tracer.current() is None


def test_contextvars_isolam_traces_aninhados():
    tracer = Tracer()
    with tracer.trace("outer") as outer:
        assert Tracer.current() is outer
        with tracer.trace("inner") as inner:
            assert Tracer.current() is inner
        assert Tracer.current() is outer


def test_atrace_async():
    exporter = MagicMock()
    exporter.aexport = AsyncMock()
    tracer = Tracer(exporters=[exporter])

    async def run():
        async with tracer.atrace("async-agent") as t:
            assert Tracer.current() is t
        return t

    t = asyncio.run(run())
    exporter.aexport.assert_called_once()
    assert t.finished_at is not None

def test_trace_exporta_mesmo_com_excecao():
    exported = []
    exporter = MagicMock()
    exporter.export.side_effect = lambda t: exported.append(t)
    tracer = Tracer(exporters=[exporter])

    with pytest.raises(ValueError, match="boom"):
        with tracer.trace("failing-agent"):
            raise ValueError("boom")

    assert len(exported) == 1
    assert exported[0].finished_at is not None
    assert exported[0].latency_ms >= 0


def test_trace_preserva_erro_original():
    tracer = Tracer()
    original = RuntimeError("original error")
    with pytest.raises(RuntimeError) as exc_info:
        with tracer.trace("err-trace"):
            raise original
    assert exc_info.value is original


def test_trace_limpa_contextvars_apos_excecao():
    tracer = Tracer()
    with pytest.raises(Exception):
        with tracer.trace("err"):
            raise Exception("x")
    assert Tracer.current() is None


def test_atrace_exporta_mesmo_com_excecao():
    exported = []
    exporter = MagicMock()
    exporter.aexport = AsyncMock(side_effect=lambda t: exported.append(t))
    tracer = Tracer(exporters=[exporter])

    async def run():
        with pytest.raises(ValueError):
            async with tracer.atrace("async-fail"):
                raise ValueError("async boom")

    asyncio.run(run())
    assert len(exported) == 1
    assert exported[0].finished_at is not None

def test_exporter_falho_nao_propaga_excecao():
    bad_exporter = MagicMock()
    bad_exporter.export.side_effect = IOError("disk full")
    good_exported = []
    good_exporter = MagicMock()
    good_exporter.export.side_effect = lambda t: good_exported.append(t)

    tracer = Tracer(exporters=[bad_exporter, good_exporter])

    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with tracer.trace("safe") as t:
            pass
    assert len(good_exported) == 1
    assert any("disk full" in str(warn.message) or "MagicMock" in str(warn.message) for warn in w)

def test_trace_agrega_tokens_e_custo_dos_spans():
    exported = []
    exporter = MagicMock()
    exporter.export.side_effect = lambda t: exported.append(t)
    tracer = Tracer(exporters=[exporter])

    with tracer.trace("span-test") as t:
        t.spans.append(Span(
            span_id="s1", type=SpanType.LLM, name="llm:gpt-4o",
            model="gpt-4o", started_at=datetime.now(timezone.utc),
            tokens_in=100, tokens_out=50, cost_usd=0.00075,
        ))

    tr = exported[0]
    assert tr.total_tokens_in  == 100
    assert tr.total_tokens_out == 50
    assert tr.total_tokens     == 150
    assert abs(tr.cost_usd - 0.00075) < 1e-9
