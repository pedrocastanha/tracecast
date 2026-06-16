import re
import difflib
from typing import Callable, Dict, Optional

from .models import CriterionScore


def exact_match(output: str, expected: str) -> float:
    return 1.0 if output.strip() == expected.strip() else 0.0


def contains(output: str, expected: str) -> float:
    return 1.0 if expected.strip().lower() in output.lower() else 0.0


def regex(output: str, expected: str) -> float:
    try:
        return 1.0 if re.search(expected, output) else 0.0
    except re.error:
        return 0.0


def similarity(output: str, expected: str) -> float:
    return difflib.SequenceMatcher(None, output.strip(), expected.strip()).ratio()


SCORERS: Dict[str, Callable[[str, str], float]] = {
    "exact_match": exact_match,
    "contains": contains,
    "regex": regex,
    "similarity": similarity,
}


def run_scorer(name: str, output: Optional[str], expected: Optional[str]) -> CriterionScore:
    fn = SCORERS.get(name)
    if fn is None:
        raise ValueError(f"unknown scorer: {name}. Available: {sorted(SCORERS)}")
    if expected is None:
        return CriterionScore(name=name, score=0.0, reasoning="no expected", kind="deterministic")
    score = float(fn(output or "", expected))
    return CriterionScore(name=name, score=score, reasoning=None, kind="deterministic")
