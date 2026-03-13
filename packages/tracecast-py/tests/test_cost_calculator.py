import pytest
from tracecast.core.cost_calculator import calculate_cost, PRICE_TABLE

@pytest.mark.parametrize("model", [
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
    "gpt-4.1", "gpt-4.1-mini", "o3", "o4-mini",
    "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
    "claude-opus-4", "claude-sonnet-4", "claude-haiku-3-5",
    "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash",
    "llama-3.3-70b", "llama-4-scout", "llama-4-maverick",
])
def test_calcula_custo_positivo(model):
    cost = calculate_cost(model, tokens_in=1000, tokens_out=500)
    assert cost > 0, f"Esperado custo > 0 para {model}"


def test_calcula_custo_gpt4o():
    cost = calculate_cost("gpt-4o", tokens_in=1000, tokens_out=500)
    assert abs(cost - (0.0025 + 0.005)) < 1e-9


def test_calcula_custo_claude_sonnet():
    cost = calculate_cost("claude-sonnet-4", tokens_in=2000, tokens_out=1000)
    assert abs(cost - (0.006 + 0.015)) < 1e-9


def test_calcula_custo_claude_opus_4_6():
    cost = calculate_cost("claude-opus-4-6", tokens_in=1000, tokens_out=1000)
    assert abs(cost - (0.005 + 0.025)) < 1e-9


def test_calcula_custo_claude_haiku_4_5():
    cost = calculate_cost("claude-haiku-4-5", tokens_in=1000, tokens_out=1000)
    assert abs(cost - (0.001 + 0.005)) < 1e-9


def test_calcula_custo_gpt4_1():
    cost = calculate_cost("gpt-4.1", tokens_in=1000, tokens_out=1000)
    assert abs(cost - (0.002 + 0.008)) < 1e-9


def test_calcula_custo_o4_mini():
    cost = calculate_cost("o4-mini", tokens_in=1000, tokens_out=1000)
    assert abs(cost - (0.0011 + 0.0044)) < 1e-9


def test_calcula_custo_gemini_2_5_flash():
    cost = calculate_cost("gemini-2.5-flash", tokens_in=1000, tokens_out=1000)
    assert abs(cost - (0.00030 + 0.0025)) < 1e-9


def test_calcula_custo_llama_4_scout():
    cost = calculate_cost("llama-4-scout", tokens_in=1000, tokens_out=1000)
    assert abs(cost - (0.00011 + 0.00034)) < 1e-9


def test_modelo_desconhecido_retorna_zero():
    assert calculate_cost("modelo-inexistente", 1000, 1000) == 0.0


def test_prefix_match_ollama():
    assert calculate_cost("ollama/llama3", 9999, 9999) == 0.0
    assert calculate_cost("ollama/mistral", 5000, 5000) == 0.0


def test_custom_prices_sobrescrevem_tabela():
    custom = {"meu-modelo": {"input": 1.0, "output": 2.0}}
    cost = calculate_cost("meu-modelo", 1000, 1000, custom_prices=custom)
    assert cost == 3.0


def test_custom_prices_nao_quebram_modelos_builtin():
    custom = {"meu-modelo": {"input": 1.0, "output": 2.0}}
    cost = calculate_cost("gpt-4o", tokens_in=1000, tokens_out=0, custom_prices=custom)
    assert abs(cost - 0.0025) < 1e-9
    cost2 = calculate_cost("meu-modelo", 1000, 0, custom_prices=custom)
    assert abs(cost2 - 1.0) < 1e-9


def test_claude_opus_legado_e_mais_caro_que_atual():
    legacy = calculate_cost("claude-opus-4",   1000, 1000)
    current = calculate_cost("claude-opus-4-6", 1000, 1000)
    assert legacy > current


def test_claude_sonnet_alias_tem_mesmo_preco():
    c1 = calculate_cost("claude-sonnet-4",   1000, 1000)
    c2 = calculate_cost("claude-sonnet-4-6", 1000, 1000)
    assert abs(c1 - c2) < 1e-9


def test_price_table_tem_provedores_principais():
    assert "gpt-4o" in PRICE_TABLE
    assert "claude-sonnet-4-6" in PRICE_TABLE
    assert "gemini-2.5-flash" in PRICE_TABLE
    assert "llama-4-scout" in PRICE_TABLE
    assert "o4-mini" in PRICE_TABLE
