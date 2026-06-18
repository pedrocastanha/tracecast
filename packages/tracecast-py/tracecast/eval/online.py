"""Online (continuous) evaluation: sample production traces and run metrics,
writing the results back as Scores. Best-effort — never affects the trace
or the application (see AD-6)."""
import random
import threading
from typing import List, Optional

from ..core.scoring import score
from ..core.logger import _logger
from .dataset import _derive_input
from .metrics import split_metrics
from .scorers import SCORERS


def _derive_output(doc: dict) -> Optional[str]:
    out = None
    for span in doc.get("spans", []):
        if span.get("output"):
            out = span["output"]
    return out


class OnlineEval:
    def __init__(self, sample_rate: float, metrics: List[str], *,
                 exporters: Optional[list] = None, judge=None,
                 background: bool = True, seed: Optional[int] = None):
        self.sample_rate = sample_rate
        self.metrics = metrics
        self.exporters = exporters
        self.judge = judge
        self.background = background
        self._rng = random.Random(seed)

    def maybe_evaluate(self, trace, *, default_exporters: Optional[list] = None) -> None:
        if self.sample_rate <= 0:
            return
        if self._rng.random() >= self.sample_rate:
            return
        exporters = self.exporters if self.exporters is not None else (default_exporters or [])
        if self.background:
            threading.Thread(
                target=self._evaluate, args=(trace, exporters), daemon=True
            ).start()
        else:
            self._evaluate(trace, exporters)

    def _evaluate(self, trace, exporters) -> None:
        try:
            doc = trace if isinstance(trace, dict) else trace.to_dict()
            trace_id = doc.get("trace_id")
            output = _derive_output(doc)
            input_text = _derive_input(doc)

            llm_criteria, heuristics = split_metrics(self.metrics)

            for name in heuristics:
                fn = SCORERS.get(name)
                if fn is None:
                    continue
                value = float(fn(output or "", ""))
                score(trace_id, name=name, value=value, kind="heuristic",
                      source="online_eval", exporters=exporters)

            if llm_criteria and self.judge is not None and output is not None:
                jr = self.judge.score(input=input_text, output=output,
                                      expected=None, criteria=llm_criteria)
                for cs in jr.scores:
                    score(trace_id, name=cs.name, value=cs.score, kind="llm",
                          source="online_eval", comment=cs.reasoning, exporters=exporters)
        except Exception:
            _logger.error("TraceCast: online eval failed for trace", exc_info=True)
