"""Named, ready-to-use evaluation metrics.

LLM metrics resolve to judge criteria (rubric-scored 0-1). Heuristic metrics
are deterministic functions registered alongside the built-in SCORERS.
RAG metrics (faithfulness, context_*) score the OUTPUT against retrieved
CONTEXT rather than only the EXPECTED reference.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .scorers import SCORERS


@dataclass
class Metric:
    name: str
    kind: str                      # "llm" | "heuristic"
    description: str = ""           # rubric for llm metrics
    needs_context: bool = False     # llm metric scores against retrieval CONTEXT
    fn: Optional[Callable] = None   # heuristic(output, expected) -> float


METRICS: Dict[str, Metric] = {}


def register_metric(metric: Metric) -> None:
    METRICS[metric.name] = metric
    if metric.kind == "heuristic" and metric.fn is not None:
        SCORERS[metric.name] = metric.fn


def get_metric(name: str) -> Optional[Metric]:
    return METRICS.get(name)


def _criterion(m: Metric) -> dict:
    return {"name": m.name, "description": m.description, "needs_context": m.needs_context}


def resolve_metrics(names: List[str]) -> List[dict]:
    """Resolve metric names to LLM judge criteria (heuristic metrics skipped)."""
    out: List[dict] = []
    for n in names:
        m = METRICS.get(n)
        if m is None:
            raise ValueError(f"unknown metric: {n}. Available: {sorted(METRICS)}")
        if m.kind == "llm":
            out.append(_criterion(m))
    return out


def split_metrics(names: List[str]):
    """Split metric names into (llm_criteria, heuristic_names)."""
    llm: List[dict] = []
    heuristic: List[str] = []
    for n in names:
        m = METRICS.get(n)
        if m is None:
            raise ValueError(f"unknown metric: {n}. Available: {sorted(METRICS)}")
        if m.kind == "llm":
            llm.append(_criterion(m))
        else:
            heuristic.append(m.name)
    return llm, heuristic


# --- Heuristic: toxicity --------------------------------------------------

_TOXIC_TERMS = {
    "idiot", "stupid", "dumb", "moron", "hate", "kill", "loser", "trash",
    "worthless", "shut up", "ugly", "racist", "disgusting", "pathetic",
}


def toxicity_score(output: str, expected: str = "") -> float:
    """0.0 (clean) .. 1.0 (toxic). Uses `detoxify` if installed, else a
    lightweight term-list fallback so the library stays dependency-free."""
    text = output or ""
    try:
        from detoxify import Detoxify  # type: ignore
        result = Detoxify("original").predict(text)
        return float(max(0.0, min(1.0, result.get("toxicity", 0.0))))
    except Exception:
        low = text.lower()
        hits = sum(1 for t in _TOXIC_TERMS if t in low)
        return min(1.0, hits / 3.0)


# --- Built-in presets -----------------------------------------------------

_LLM_PRESETS = [
    Metric(
        name="faithfulness", kind="llm", needs_context=True,
        description=("Is every factual claim in the OUTPUT supported by the provided "
                     "CONTEXT? Penalize claims not grounded in the CONTEXT."),
    ),
    Metric(
        name="answer_relevancy", kind="llm", needs_context=False,
        description=("Does the OUTPUT directly and completely address the INPUT "
                     "question, without evasion or off-topic content?"),
    ),
    Metric(
        name="context_precision", kind="llm", needs_context=True,
        description=("Of the retrieved CONTEXT, how much is actually relevant to "
                     "answering the INPUT? Penalize irrelevant or noisy context."),
    ),
    Metric(
        name="context_recall", kind="llm", needs_context=True,
        description=("Does the CONTEXT contain all the information needed to produce "
                     "the EXPECTED answer? Penalize missing information."),
    ),
    Metric(
        name="hallucination", kind="llm", needs_context=True,
        description=("Score 1.0 when the OUTPUT introduces NO fabricated facts beyond "
                     "the CONTEXT/EXPECTED; lower as fabrication increases."),
    ),
    Metric(
        name="conciseness", kind="llm", needs_context=False,
        description=("Is the OUTPUT concise and free of unnecessary verbosity while "
                     "remaining complete and correct?"),
    ),
]

for _m in _LLM_PRESETS:
    register_metric(_m)

register_metric(Metric(name="toxicity", kind="heuristic", fn=toxicity_score,
                       description="Heuristic toxicity level 0.0 (clean) .. 1.0 (toxic)."))
