from typing import Optional, Dict

PRICE_TABLE: Dict[str, Dict[str, float]] = {
    "gpt-5":             {"input": 0.00125,  "output": 0.01000,  "cached": 0.000125},
    "gpt-5.4":           {"input": 0.00250,  "output": 0.01500,  "cached": 0.000250},
    "gpt-4o":            {"input": 0.00250,  "output": 0.01000,  "cached": 0.001250},
    "gpt-4o-mini":       {"input": 0.00015,  "output": 0.00060,  "cached": 0.000075},
    "gpt-4-turbo":       {"input": 0.01000,  "output": 0.03000},
    "gpt-4.1":           {"input": 0.00200,  "output": 0.00800,  "cached": 0.000500},
    "gpt-4.1-mini":      {"input": 0.00040,  "output": 0.00160,  "cached": 0.000100},
    "gpt-4.1-nano":      {"input": 0.00010,  "output": 0.00040,  "cached": 0.000025},
    "o3":                {"input": 0.00200,  "output": 0.00800,  "cached": 0.000500},
    "o4-mini":           {"input": 0.00110,  "output": 0.00440,  "cached": 0.000275},

    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
    "text-embedding-ada-002": {"input": 0.00010, "output": 0.0},

    "claude-opus-4-6":   {"input": 0.00500,  "output": 0.02500,  "cached": 0.000500},
    "claude-sonnet-4-6": {"input": 0.00300,  "output": 0.01500,  "cached": 0.000300},
    "claude-haiku-4-5":  {"input": 0.00100,  "output": 0.00500,  "cached": 0.000100},
    "claude-opus-4-5":   {"input": 0.00500,  "output": 0.02500,  "cached": 0.000500},
    "claude-sonnet-4-5": {"input": 0.00300,  "output": 0.01500,  "cached": 0.000300},
    "claude-opus-4":     {"input": 0.01500,  "output": 0.07500,  "cached": 0.001500},
    "claude-sonnet-4":   {"input": 0.00300,  "output": 0.01500,  "cached": 0.000300},
    "claude-haiku-3-5":  {"input": 0.00080,  "output": 0.00400,  "cached": 0.000080},

    "gemini-3.1-pro":    {"input": 0.00200,  "output": 0.01200},
    "gemini-3-flash":    {"input": 0.00050,  "output": 0.00300},
    "gemini-2.5-flash":  {"input": 0.00030,  "output": 0.00250},
    "gemini-2.5-pro":    {"input": 0.00125,  "output": 0.01000},
    "gemini-2.0-flash":  {"input": 0.00010,  "output": 0.00040},

    "llama-3.3-70b-versatile":                       {"input": 0.00059, "output": 0.00079},
    "meta-llama/llama-4-scout-17b-16e-instruct":     {"input": 0.00011, "output": 0.00034},
    "meta-llama/llama-4-maverick-17b-128e-instruct": {"input": 0.00020, "output": 0.00060},
    "llama-3.3-70b":     {"input": 0.00059, "output": 0.00079},
    "llama-4-scout":     {"input": 0.00011, "output": 0.00034},
    "llama-4-maverick":  {"input": 0.00020, "output": 0.00060},

    "ollama/*":          {"input": 0.0,     "output": 0.0},
}


def calculate_cost(
    model: str,
    tokens_in: int,
    tokens_out: int,
    custom_prices: Optional[Dict] = None,
    tokens_in_cached: int = 0,
) -> float:
    prices = {**PRICE_TABLE, **custom_prices} if custom_prices else PRICE_TABLE
    table = prices.get(model) or _prefix_match(model, prices)
    if not table:
        return 0.0
    cached_price = table.get("cached")
    if cached_price is not None and tokens_in_cached > 0:
        uncached = tokens_in - tokens_in_cached
        return (
            (uncached / 1000 * table["input"])
            + (tokens_in_cached / 1000 * cached_price)
            + (tokens_out / 1000 * table["output"])
        )
    return (tokens_in / 1000 * table["input"]) + (tokens_out / 1000 * table["output"])


def _prefix_match(model: str, prices: Dict) -> Optional[Dict]:
    provider = model.split("/")[0] + "/*"
    return prices.get(provider)


# Audio isn't token-billed: transcription is per-minute of input audio, TTS is
# per-character of input text. gpt-4o-mini-tts's rate is an approximation
# (not published on OpenAI's current pricing page as of 2026-07) — verify
# against an actual invoice before trusting it for reconciliation.
AUDIO_PRICE_TABLE: Dict[str, Dict[str, float]] = {
    "whisper-1":       {"unit": "minute", "price": 0.006},
    "gpt-4o-mini-tts": {"unit": "char",   "price": 0.000015},
    "tts-1":           {"unit": "char",   "price": 0.000015},
    "tts-1-hd":        {"unit": "char",   "price": 0.00003},
}


def calculate_audio_cost(model: str, *, minutes: float = 0.0, chars: int = 0) -> float:
    entry = AUDIO_PRICE_TABLE.get(model)
    if not entry:
        return 0.0
    if entry["unit"] == "minute":
        return minutes * entry["price"]
    return chars * entry["price"]
