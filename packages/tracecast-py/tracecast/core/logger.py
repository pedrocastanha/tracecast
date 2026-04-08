import logging
import re
from typing import Optional

_logger = logging.getLogger("tracecast")


def _inline(text: str, max_chars: int = 50) -> str:
    normalized = re.sub(r"[\r\n\t]+", " ", text)
    normalized = re.sub(r" {2,}", " ", normalized).strip()
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars] + "..."
    return normalized


class TraceCastLogger:
    def __init__(self, prefix: Optional[str] = None):
        self._prefix = prefix

    def _fmt(self, prefix: str, msg: str) -> str:
        return f"[{prefix}] {msg}"

    def trace_start(self, trace_name: str) -> None:
        prefix = self._prefix or trace_name
        _logger.info(self._fmt(prefix, "Trace started"))

    def trace_end(
        self,
        trace_name: str,
        *,
        total_tokens: int,
        cost_usd: float,
        latency_ms: Optional[int],
        tools_used: dict,
    ) -> None:
        prefix = self._prefix or trace_name
        latency_str = f"{latency_ms / 1000:.2f}s" if latency_ms is not None else "n/a"
        tools_str = ""
        if tools_used:
            parts = [f"{k}×{v}" for k, v in tools_used.items()]
            tools_str = " | tools: " + ", ".join(parts)
        _logger.info(
            self._fmt(
                prefix,
                f"Trace finished → total: {total_tokens} tokens"
                f" | ${cost_usd:.4f}"
                f" | {latency_str}"
                f"{tools_str}",
            )
        )

    def llm_start(self, trace_name: str, *, model: str) -> None:
        prefix = self._prefix or trace_name
        _logger.info(self._fmt(prefix, f"LLM started → {model}"))

    def llm_end(
        self,
        trace_name: str,
        *,
        model: str,
        tokens_in: int,
        tokens_out: int,
        tokens_in_cached: int = 0,
        cost_usd: float,
        latency_ms: Optional[float],
    ) -> None:
        prefix = self._prefix or trace_name
        latency_str = f"{latency_ms / 1000:.2f}s" if latency_ms is not None else "n/a"
        cached_str = f" ({tokens_in_cached} cached)" if tokens_in_cached > 0 else ""
        _logger.info(
            self._fmt(
                prefix,
                f"LLM end → {model}"
                f" | tokens: {tokens_in} in{cached_str} / {tokens_out} out"
                f" | ${cost_usd:.4f}"
                f" | {latency_str}",
            )
        )

    def llm_error(self, trace_name: str, *, model: str, error: str) -> None:
        prefix = self._prefix or trace_name
        _logger.warning(self._fmt(prefix, f"LLM error → {model} | ⚠ {_inline(error)}"))

    def tool_start(self, trace_name: str, *, name: str, input_str: str) -> None:
        prefix = self._prefix or trace_name
        _logger.info(self._fmt(prefix, f"Tool call → {name} | {_inline(input_str, 80)}"))

    def tool_end(
        self, trace_name: str, *, name: str, latency_ms: Optional[float]
    ) -> None:
        prefix = self._prefix or trace_name
        latency_str = f"{latency_ms / 1000:.2f}s" if latency_ms is not None else "n/a"
        _logger.info(self._fmt(prefix, f"Tool end → {name} | {latency_str}"))

    def tool_error(self, trace_name: str, *, name: str, error: str) -> None:
        prefix = self._prefix or trace_name
        _logger.warning(self._fmt(prefix, f"Tool error → {name} | ⚠ {_inline(error)}"))

    def chain_start(self, trace_name: str, *, name: str) -> None:
        prefix = self._prefix or trace_name
        _logger.info(self._fmt(prefix, f"Chain → {name}"))

    def chain_error(self, trace_name: str, *, name: str, error: str) -> None:
        prefix = self._prefix or trace_name
        _logger.warning(self._fmt(prefix, f"Chain error → {name} | ⚠ {_inline(error)}"))
