from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, AttributeError):
        return None


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


@dataclass
class CriterionScore:
    name: str
    score: float
    reasoning: Optional[str] = None
    kind: str = "llm"

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "reasoning": self.reasoning, "kind": self.kind}

    @classmethod
    def from_dict(cls, d: dict) -> "CriterionScore":
        return cls(
            name=d.get("name", ""),
            score=float(d.get("score", 0.0)),
            reasoning=d.get("reasoning"),
            kind=d.get("kind", "llm"),
        )


@dataclass
class TurnResult:
    index: int
    role: str
    input: Optional[str] = None
    output: Optional[str] = None
    expected: Optional[str] = None
    scores: List[CriterionScore] = field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False

    def compute(self, threshold: float) -> None:
        if self.scores:
            self.overall_score = sum(s.score for s in self.scores) / len(self.scores)
        else:
            self.overall_score = 0.0
        self.passed = self.overall_score >= threshold

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "role": self.role,
            "input": self.input,
            "output": self.output,
            "expected": self.expected,
            "scores": [s.to_dict() for s in self.scores],
            "overall_score": self.overall_score,
            "passed": self.passed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TurnResult":
        return cls(
            index=d.get("index", 0),
            role=d.get("role", "assistant"),
            input=d.get("input"),
            output=d.get("output"),
            expected=d.get("expected"),
            scores=[CriterionScore.from_dict(s) for s in d.get("scores", [])],
            overall_score=float(d.get("overall_score", 0.0)),
            passed=bool(d.get("passed", False)),
        )


@dataclass
class EvalCase:
    case_id: str
    status: str = "pass"
    overall_score: float = 0.0
    passed: bool = False
    turns: List[TurnResult] = field(default_factory=list)
    trace_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute(self, threshold: float) -> None:
        scored = [t for t in self.turns if t.scores]
        if scored:
            self.overall_score = sum(t.overall_score for t in scored) / len(scored)
        else:
            self.overall_score = 0.0
        if self.status == "error":
            self.passed = False
        else:
            self.passed = bool(scored) and all(t.passed for t in scored)
            self.status = "pass" if self.passed else "fail"

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "turns": [t.to_dict() for t in self.turns],
            "trace_id": self.trace_id,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvalCase":
        return cls(
            case_id=d.get("case_id", ""),
            status=d.get("status", "pass"),
            overall_score=float(d.get("overall_score", 0.0)),
            passed=bool(d.get("passed", False)),
            turns=[TurnResult.from_dict(t) for t in d.get("turns", [])],
            trace_id=d.get("trace_id"),
            error=d.get("error"),
            metadata=d.get("metadata", {}),
        )


@dataclass
class EvalRun:
    run_id: str
    name: str
    started_at: datetime
    dataset_name: Optional[str] = None
    dataset_path: Optional[str] = None
    target: Optional[str] = None
    project_id: Optional[str] = None
    judge_model: Optional[str] = None
    criteria: List[str] = field(default_factory=list)
    threshold: float = 0.7
    finished_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    judge_tokens: int = 0
    judge_cost_usd: float = 0.0
    cases: List[EvalCase] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> None:
        self.total_cases = len(self.cases)
        self.passed = sum(1 for c in self.cases if c.passed)
        self.failed = self.total_cases - self.passed
        self.pass_rate = (self.passed / self.total_cases) if self.total_cases else 0.0
        scored = [c for c in self.cases if c.status != "error"]
        self.avg_score = (sum(c.overall_score for c in scored) / len(scored)) if scored else 0.0
        if self.finished_at:
            self.latency_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "name": self.name,
            "dataset_name": self.dataset_name,
            "dataset_path": self.dataset_path,
            "target": self.target,
            "project_id": self.project_id,
            "judge_model": self.judge_model,
            "criteria": self.criteria,
            "threshold": self.threshold,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "latency_ms": self.latency_ms,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "judge_tokens": self.judge_tokens,
            "judge_cost_usd": self.judge_cost_usd,
            "cases": [c.to_dict() for c in self.cases],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvalRun":
        run = cls(
            run_id=d.get("run_id", ""),
            name=d.get("name", ""),
            started_at=_parse_dt(d.get("started_at")) or datetime.now(),
            dataset_name=d.get("dataset_name"),
            dataset_path=d.get("dataset_path"),
            target=d.get("target"),
            project_id=d.get("project_id"),
            judge_model=d.get("judge_model"),
            criteria=d.get("criteria", []),
            threshold=float(d.get("threshold", 0.7)),
            finished_at=_parse_dt(d.get("finished_at")),
            latency_ms=d.get("latency_ms"),
            total_cases=d.get("total_cases", 0),
            passed=d.get("passed", 0),
            failed=d.get("failed", 0),
            pass_rate=float(d.get("pass_rate", 0.0)),
            avg_score=float(d.get("avg_score", 0.0)),
            judge_tokens=d.get("judge_tokens", 0),
            judge_cost_usd=float(d.get("judge_cost_usd", 0.0)),
            cases=[EvalCase.from_dict(c) for c in d.get("cases", [])],
            metadata=d.get("metadata", {}),
        )
        return run
