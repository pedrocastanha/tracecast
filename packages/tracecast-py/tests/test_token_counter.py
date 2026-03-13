from unittest.mock import MagicMock
from tracecast.core.token_counter import extract_tokens

def test_extrai_tokens_openai():
    response = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    result = extract_tokens(response, provider="openai")
    assert result == {"input": 100, "output": 50}

def test_extrai_tokens_anthropic():
    response = MagicMock()
    response.usage.input_tokens = 200
    response.usage.output_tokens = 80
    result = extract_tokens(response, provider="anthropic")
    assert result == {"input": 200, "output": 80}

def test_extrai_tokens_langchain():
    response = {"token_usage": {"prompt_tokens": 30, "completion_tokens": 15}}
    result = extract_tokens(response, provider="langchain")
    assert result == {"input": 30, "output": 15}

def test_fallback_retorna_zeros():
    result = extract_tokens({}, provider="provider-desconhecido")
    assert result == {"input": 0, "output": 0}
