import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import CriterionScore
from ..core.cost_calculator import calculate_cost


@dataclass
class JudgeResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class JudgeResult:
    scores: List[CriterionScore] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    candidates = []
    fenced = text.split("```")
    for block in fenced:
        block = block.strip()
        if block.startswith("json"):
            block = block[4:].strip()
        if block.startswith("{"):
            candidates.append(block)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _build_prompt(input_text, output, expected, criteria) -> str:
    lines = [
        "Evaluate the assistant OUTPUT against the EXPECTED reference.",
        "Score each criterion from 0.0 (worst) to 1.0 (best).",
        "",
        f"INPUT:\n{input_text or ''}",
        f"EXPECTED:\n{expected or ''}",
        f"OUTPUT:\n{output or ''}",
        "",
        "CRITERIA:",
    ]
    for c in criteria:
        lines.append(f"- {c['name']}: {c.get('description', '')}")
    lines.append("")
    lines.append(
        'Return ONLY JSON: {"criterion_name": {"score": 0.0, "reasoning": "..."}} '
        "with one entry per criterion."
    )
    return "\n".join(lines)


class LLMJudge:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        call_fn: Optional[Callable[[str, str], JudgeResponse]] = None,
    ):
        self.model = model
        self._call_fn = call_fn

    def _call(self, system: str, user: str) -> JudgeResponse:
        if self._call_fn is not None:
            return self._call_fn(system, user)
        import openai
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        usage = getattr(resp, "usage", None)
        return JudgeResponse(
            text=resp.choices[0].message.content or "",
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
        )

    def score(self, *, input, output, expected, criteria) -> JudgeResult:
        if not criteria:
            return JudgeResult()
        system = "You are a strict, fair evaluator of LLM outputs. Respond with JSON only."
        user = _build_prompt(input, output, expected, criteria)
        try:
            resp = self._call(system, user)
        except Exception as exc:
            return JudgeResult(scores=[
                CriterionScore(name=c["name"], score=0.0, reasoning=f"judge_unavailable: {exc}", kind="llm")
                for c in criteria
            ])
        parsed = _extract_json(resp.text)

        scores: List[CriterionScore] = []
        for c in criteria:
            name = c["name"]
            entry = parsed.get(name) if isinstance(parsed, dict) else None
            if isinstance(entry, dict) and "score" in entry:
                try:
                    value = max(0.0, min(1.0, float(entry["score"])))
                except (TypeError, ValueError):
                    value = 0.0
                scores.append(CriterionScore(name=name, score=value, reasoning=entry.get("reasoning"), kind="llm"))
            else:
                scores.append(CriterionScore(name=name, score=0.0, reasoning="parse_error", kind="llm"))

        cost = calculate_cost(self.model, resp.tokens_in, resp.tokens_out)
        return JudgeResult(scores=scores, tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, cost_usd=cost)
