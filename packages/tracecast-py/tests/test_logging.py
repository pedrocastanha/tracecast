
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest

from tracecast.core.tracer import Tracer
from tracecast.core.logger import TraceCastLogger, _inline
from tracecast.integrations.langchain import TraceCastCallback

def test_inline_colapsa_newlines():
    text = "linha 1\nlinha 2\nlinha 3"
    result = _inline(text)
    assert "\n" not in result
    assert "linha 1" in result
    assert "linha 2" in result


def test_inline_trunca_texto_longo():
    text = "a" * 200
    result = _inline(text, max_chars=50)
    assert result.endswith("...")
    assert len(result) == 53


def test_inline_texto_curto_nao_trunca():
    text = "curto"
    assert _inline(text) == "curto"

def test_logger_usa_prefix_configurado(caplog):
    logger = TraceCastLogger(prefix="meu_agente")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.trace_start("qualquer_nome")
    assert "[meu_agente]" in caplog.text
    assert "Trace started" in caplog.text


def test_logger_usa_trace_name_sem_prefix(caplog):
    logger = TraceCastLogger()
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.trace_start("meu_trace")
    assert "[meu_trace]" in caplog.text


def test_logger_trace_end_contem_tokens_e_custo(caplog):
    logger = TraceCastLogger(prefix="agent")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.trace_end(
            "agent",
            total_tokens=500,
            cost_usd=0.0025,
            latency_ms=1200,
            tools_used={"search": 2},
        )
    assert "500 tokens" in caplog.text
    assert "$0.0025" in caplog.text
    assert "1.20s" in caplog.text
    assert "search×2" in caplog.text


def test_logger_llm_start(caplog):
    logger = TraceCastLogger(prefix="a")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.llm_start("a", model="gpt-4o")
    assert "LLM started" in caplog.text
    assert "gpt-4o" in caplog.text


def test_logger_llm_end_unico_linha(caplog):
    logger = TraceCastLogger(prefix="a")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.llm_end("a", model="gpt-4o", tokens_in=100, tokens_out=50, cost_usd=0.001, latency_ms=800)
    lines = [l for l in caplog.text.split("\n") if "LLM end" in l]
    assert len(lines) == 1
    assert "100 in" in lines[0]
    assert "50 out" in lines[0]


def test_logger_tool_start_e_end(caplog):
    logger = TraceCastLogger(prefix="a")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.tool_start("a", name="search_web", input_str="quem é o presidente")
        logger.tool_end("a", name="search_web", latency_ms=450)
    assert "Tool call → search_web" in caplog.text
    assert "Tool end → search_web" in caplog.text
    assert "0.45s" in caplog.text


def test_logger_tool_start_colapsa_input_multiline(caplog):
    logger = TraceCastLogger(prefix="a")
    multiline_input = "linha1\nlinha2\nlinha3"
    with caplog.at_level(logging.INFO, logger="tracecast"):
        logger.tool_start("a", name="tool", input_str=multiline_input)
    lines = [l for l in caplog.text.split("\n") if "Tool call" in l]
    assert len(lines) == 1
    assert "\n" not in lines[0]


def test_logger_error_emite_warning(caplog):
    logger = TraceCastLogger(prefix="a")
    with caplog.at_level(logging.WARNING, logger="tracecast"):
        logger.llm_error("a", model="gpt-4o", error="timeout")
    assert "⚠" in caplog.text
    assert "timeout" in caplog.text

def test_tracer_logging_false_nao_loga(caplog):
    tracer = Tracer(logging=False)
    assert tracer._tc_logger is None
    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("meu_trace"):
            pass
    assert "[meu_trace]" not in caplog.text


def test_tracer_logging_true_loga_trace_start_e_end(caplog):
    tracer = Tracer(logging=True)
    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("meu_trace"):
            pass
    assert "[meu_trace] Trace started" in caplog.text
    assert "Trace finished" in caplog.text


def test_tracer_logging_com_prefix_usa_prefix(caplog):
    tracer = Tracer(logging=True, log_prefix="agente_x")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("qualquer"):
            pass
    assert "[agente_x]" in caplog.text
    assert "[qualquer]" not in caplog.text


def test_tracer_logging_trace_end_contem_summary(caplog):
    tracer = Tracer(logging=True, log_prefix="agent")
    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("qualquer"):
            pass
    assert "Trace finished" in caplog.text
    assert "tokens" in caplog.text
    assert "$" in caplog.text

def test_callback_loga_llm_start_e_end(caplog):
    tracer = Tracer(logging=True, log_prefix="cb_agent")
    cb = TraceCastCallback(tracer=tracer)
    run_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.llm_output = {"token_usage": {"prompt_tokens": 100, "completion_tokens": 50}}

    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("run"):
            cb.on_llm_start({"kwargs": {"model_name": "gpt-4o"}}, [], run_id=run_id)
            cb.on_llm_end(mock_result, run_id=run_id)

    assert "LLM started → gpt-4o" in caplog.text
    assert "LLM end → gpt-4o" in caplog.text
    assert "100 in" in caplog.text


def test_callback_loga_tool_start_e_end(caplog):
    tracer = Tracer(logging=True, log_prefix="cb_agent")
    cb = TraceCastCallback(tracer=tracer)
    run_id = uuid.uuid4()

    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("run"):
            cb.on_tool_start({"name": "pesquisa"}, "minha query", run_id=run_id)
            cb.on_tool_end("resultado", run_id=run_id)

    assert "Tool call → pesquisa" in caplog.text
    assert "minha query" in caplog.text
    assert "Tool end → pesquisa" in caplog.text


def test_callback_sem_logging_nao_loga(caplog):
    tracer = Tracer(logging=False)
    cb = TraceCastCallback(tracer=tracer)
    run_id = uuid.uuid4()

    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("run"):
            cb.on_llm_start({"kwargs": {"model_name": "gpt-4o"}}, [], run_id=run_id)
            mock_result = MagicMock()
            mock_result.llm_output = {}
            cb.on_llm_end(mock_result, run_id=run_id)
    assert "LLM started" not in caplog.text
    assert "LLM end" not in caplog.text


def test_callback_loga_chain_apenas_raiz(caplog):
    tracer = Tracer(logging=True, log_prefix="cb_agent")
    cb = TraceCastCallback(tracer=tracer)
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()

    with caplog.at_level(logging.INFO, logger="tracecast"):
        with tracer.trace("run"):
            cb.on_chain_start({"name": "RootChain"}, {}, run_id=root_id, parent_run_id=None)
            cb.on_chain_start({"name": "SubChain"}, {}, run_id=child_id, parent_run_id=root_id)
            cb.on_chain_end({}, run_id=child_id)
            cb.on_chain_end({}, run_id=root_id)

    chain_logs = [l for l in caplog.text.split("\n") if "Chain →" in l]
    assert len(chain_logs) == 1
    assert "RootChain" in chain_logs[0]
