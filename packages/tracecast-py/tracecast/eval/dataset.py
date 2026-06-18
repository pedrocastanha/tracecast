import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GoldenTurn:
    role: str
    content: Optional[str] = None
    expected: Optional[str] = None
    context: Optional[str] = None


@dataclass
class GoldenCase:
    case_id: str
    turns: List[GoldenTurn] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Optional[str] = None


@dataclass
class GoldenDataset:
    name: str
    cases: List[GoldenCase]
    criteria: List[Dict[str, str]] = field(default_factory=list)
    threshold: Optional[float] = None
    path: Optional[str] = None


def _normalize_case(raw: dict, index: int) -> GoldenCase:
    case_id = str(raw.get("id", f"case_{index}"))
    metadata = raw.get("metadata", {})

    case_context = raw.get("context")

    if "turns" in raw:
        turns_raw = raw["turns"]
        if not isinstance(turns_raw, list) or not turns_raw:
            raise ValueError(f"case '{case_id}': 'turns' must be a non-empty list")
        turns = []
        for t in turns_raw:
            if not isinstance(t, dict) or "role" not in t:
                raise ValueError(f"case '{case_id}': each turn needs a 'role'")
            turns.append(GoldenTurn(role=t["role"], content=t.get("content"),
                                    expected=t.get("expected"), context=t.get("context")))
        return GoldenCase(case_id=case_id, turns=turns, metadata=metadata, context=case_context)

    if "input" in raw:
        return GoldenCase(
            case_id=case_id,
            turns=[
                GoldenTurn(role="user", content=str(raw["input"])),
                GoldenTurn(role="assistant", expected=raw.get("expected"), context=case_context),
            ],
            metadata=metadata,
            context=case_context,
        )

    raise ValueError(f"case '{case_id}': must have 'input' (single-turn) or 'turns' (multi-turn)")


def parse_dataset(data: dict, *, path: Optional[str] = None) -> GoldenDataset:
    cases_raw = data.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("dataset must contain a non-empty 'cases' list")
    cases = [_normalize_case(c, i) for i, c in enumerate(cases_raw)]
    return GoldenDataset(
        name=data.get("name", Path(path).stem if path else "dataset"),
        cases=cases,
        criteria=data.get("criteria", []),
        threshold=data.get("threshold"),
        path=path,
    )


def load_dataset(path: str) -> GoldenDataset:
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(f"golden dataset not found: {path}")
    with fp.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_dataset(data, path=str(fp))


def _resolve_trace(trace, exporters) -> Optional[dict]:
    if isinstance(trace, dict):
        return trace
    if hasattr(trace, "to_dict"):
        return trace.to_dict()
    for exporter in exporters or []:
        getter = getattr(exporter, "get", None)
        if callable(getter):
            doc = getter(trace)
            if doc:
                return doc
        for doc in getattr(exporter, "traces", []):
            if doc.get("trace_id") == trace:
                return doc
    return None


def _derive_input(doc: dict) -> Optional[str]:
    for span in doc.get("spans", []):
        if span.get("input"):
            return span["input"]
    return None


def add_to_dataset(trace, path: str, *, expected: Optional[str] = None,
                   input: Optional[str] = None, context: Optional[str] = None,
                   exporters: Optional[list] = None) -> None:
    """Promote a production trace (dict, Trace, or trace_id) to a golden case,
    appending it to the dataset JSON at `path` (created if missing)."""
    doc = _resolve_trace(trace, exporters)
    if doc is None:
        raise ValueError(f"trace not found: {trace}")

    case: Dict[str, Any] = {
        "id": doc.get("trace_id"),
        "input": input if input is not None else (_derive_input(doc) or ""),
        "expected": expected,
    }
    if context is not None:
        case["context"] = context

    fp = Path(path)
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
    else:
        if fp.parent != Path("."):
            fp.parent.mkdir(parents=True, exist_ok=True)
        data = {"name": fp.stem, "cases": []}
    data.setdefault("cases", []).append(case)
    fp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
