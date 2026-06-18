"""Compare two EvalRuns (A/B regression diff). Operates on run dicts as
returned by exporter.get_eval / EvalReader.get_run."""
from typing import Dict, List


def compare(run_a: dict, run_b: dict) -> dict:
    a_cases: Dict[str, dict] = {c["case_id"]: c for c in run_a.get("cases", [])}
    b_cases: Dict[str, dict] = {c["case_id"]: c for c in run_b.get("cases", [])}

    ordered_ids: List[str] = list(a_cases)
    for cid in b_cases:
        if cid not in a_cases:
            ordered_ids.append(cid)

    cases: List[dict] = []
    for cid in ordered_ids:
        ca = a_cases.get(cid)
        cb = b_cases.get(cid)
        if ca is not None and cb is not None:
            sa = ca.get("overall_score", 0.0)
            sb = cb.get("overall_score", 0.0)
            delta = sb - sa
            cases.append({
                "case_id": cid, "score_a": sa, "score_b": sb,
                "delta": delta, "status": "changed" if delta != 0 else "same",
            })
        elif cb is not None:
            cases.append({"case_id": cid, "score_a": None,
                          "score_b": cb.get("overall_score", 0.0),
                          "delta": None, "status": "added"})
        else:
            cases.append({"case_id": cid, "score_a": ca.get("overall_score", 0.0),
                          "score_b": None, "delta": None, "status": "removed"})

    return {
        "run_a": run_a.get("run_id"),
        "run_b": run_b.get("run_id"),
        "dataset_mismatch": run_a.get("dataset_name") != run_b.get("dataset_name"),
        "avg_score_delta": run_b.get("avg_score", 0.0) - run_a.get("avg_score", 0.0),
        "pass_rate_delta": run_b.get("pass_rate", 0.0) - run_a.get("pass_rate", 0.0),
        "cases": cases,
    }
