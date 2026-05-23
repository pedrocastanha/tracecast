from typing import Any, Optional


def extract_tokens(response: Any, provider: str) -> dict:
    extractors = {
        "openai":    _from_openai,
        "anthropic": _from_anthropic,
        "langchain": _from_langchain_response,
    }
    fn = extractors.get(provider, _fallback)
    return fn(response)


def extract_content(response: Any, provider: str) -> Optional[str]:
    if provider == "openai":
        try:
            choices = getattr(response, "choices", []) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    return getattr(msg, "content", None) or getattr(msg, "reasoning_content", None) or ""
        except Exception:
            pass
        return None
    if provider == "anthropic":
        try:
            content = getattr(response, "content", []) or []
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        texts.append(f"[thinking] {block.get('thinking', '')}")
                else:
                    t = getattr(block, "type", None)
                    if t == "text":
                        texts.append(getattr(block, "text", ""))
                    elif t == "thinking":
                        texts.append(f"[thinking] {getattr(block, 'thinking', '')}")
            return "".join(texts) if texts else None
        except Exception:
            pass
        return None
    return None


def extract_input_text(response_or_kwargs: Any, provider: str) -> Optional[str]:
    """Tries to extract the input prompt from the call. Gets kwargs from proxy."""
    if isinstance(response_or_kwargs, dict):
        messages = response_or_kwargs.get("messages", [])
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                return last.get("content", "")
    return None


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
