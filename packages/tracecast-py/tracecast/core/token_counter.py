from typing import Any


def extract_tokens(response: Any, provider: str) -> dict:
    extractors = {
        "openai":    _from_openai,
        "anthropic": _from_anthropic,
        "langchain": _from_langchain_response,
    }
    fn = extractors.get(provider, _fallback)
    return fn(response)


def _from_openai(r) -> dict:
    usage = getattr(r, "usage", None) or {}
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    return {
        "input":  getattr(usage, "prompt_tokens", 0),
        "output": getattr(usage, "completion_tokens", 0),
        "cached": cached,
    }


def _from_anthropic(r) -> dict:
    usage = getattr(r, "usage", None) or {}
    return {
        "input":  getattr(usage, "input_tokens", 0),
        "output": getattr(usage, "output_tokens", 0),
        "cached": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


def _from_langchain_response(r) -> dict:
    usage = r.get("token_usage") or r.get("usage", {})
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens", 0) or 0
    return {
        "input":  usage.get("prompt_tokens") or usage.get("input_tokens", 0),
        "output": usage.get("completion_tokens") or usage.get("output_tokens", 0),
        "cached": cached,
    }


def _fallback(r) -> dict:
    return {"input": 0, "output": 0, "cached": 0}
