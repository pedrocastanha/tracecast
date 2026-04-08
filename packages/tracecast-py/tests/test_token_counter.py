from unittest.mock import MagicMock
from tracecast.core.token_counter import extract_tokens

def test_extrai_tokens_openai():
    response = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.prompt_tokens_details = None
    result = extract_tokens(response, provider="openai")
    assert result == {"input": 100, "output": 50, "cached": 0}

def test_extrai_tokens_anthropic():
    response = MagicMock()
    response.usage.input_tokens = 200
    response.usage.output_tokens = 80
    response.usage.cache_read_input_tokens = 0
    result = extract_tokens(response, provider="anthropic")
    assert result == {"input": 200, "output": 80, "cached": 0}

def test_extrai_tokens_langchain():
    response = {"token_usage": {"prompt_tokens": 30, "completion_tokens": 15}}
    result = extract_tokens(response, provider="langchain")
    assert result == {"input": 30, "output": 15, "cached": 0}

def test_fallback_retorna_zeros():
    result = extract_tokens({}, provider="provider-desconhecido")
    assert result == {"input": 0, "output": 0, "cached": 0}


# --- cached token extraction ---

def test_extrai_cached_tokens_openai():
    response = MagicMock()
    response.usage.prompt_tokens = 1000
    response.usage.completion_tokens = 200
    response.usage.prompt_tokens_details.cached_tokens = 300
    result = extract_tokens(response, provider="openai")
    assert result["cached"] == 300

def test_extrai_cached_tokens_anthropic():
    response = MagicMock()
    response.usage.input_tokens = 500
    response.usage.output_tokens = 100
    response.usage.cache_read_input_tokens = 250
    result = extract_tokens(response, provider="anthropic")
    assert result["cached"] == 250

def test_cached_zero_quando_ausente_openai():
    response = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.prompt_tokens_details = None
    result = extract_tokens(response, provider="openai")
    assert result["cached"] == 0

def test_cached_langchain_via_prompt_tokens_details():
    response = {
        "token_usage": {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "prompt_tokens_details": {"cached_tokens": 60},
        }
    }
    result = extract_tokens(response, provider="langchain")
    assert result["cached"] == 60
