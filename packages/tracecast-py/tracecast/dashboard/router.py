"""FastAPI APIRouter serving dashboard REST API and static files."""

try:
    from fastapi import APIRouter, Query, HTTPException, Request
    from fastapi.responses import HTMLResponse, Response, JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from .reader import TraceReader
from .aggregator import compute_metrics, paginate_traces, _trace_summary, build_graph, compute_filter_options, _period_delta

STATIC_DIR = Path(__file__).parent / "static"


def _index_html(prefix: str) -> str:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return "<h1>TraceCast Dashboard</h1><p>Static files not found.</p>"
    html = index_path.read_text(encoding="utf-8")
    inject = f'<script>window.__TC_PREFIX__ = "{prefix}";</script>'
    if "__TC_PREFIX__" in html:
        return html
    return html.replace("</head>", f"  {inject}\n</head>", 1)


def _mime(filename: str) -> str:
    if filename.endswith(".html"):
        return "text/html; charset=utf-8"
    if filename.endswith(".css"):
        return "text/css; charset=utf-8"
    if filename.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if filename.endswith(".svg"):
        return "image/svg+xml"
    if filename.endswith(".png"):
        return "image/png"
    return "application/octet-stream"


def _trace_to_api_dict(trace) -> dict:
    doc = trace.to_dict()
    meta = trace.metadata or {}
    export_status = meta.get("_export_status") or "complete"
    is_summary = bool(meta.get("_is_summary") or export_status == "summary_only")
    doc["export_status"] = export_status
    doc["is_summary"] = is_summary
    if meta.get("_export_error") is not None:
        doc["export_error"] = meta.get("_export_error")
    return doc


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _make_router(reader: TraceReader, prefix: str = "") -> "APIRouter":
    if not HAS_FASTAPI:
        raise ImportError("FastAPI is required for dashboard. Install with: pip install fastapi")

    router = APIRouter()

    @router.get("/api/traces")
    def api_traces(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        project_name: Optional[str] = Query(None),
        project_id: Optional[str] = Query(None),
        user_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
        from_dt: Optional[str] = Query(None, alias="from"),
        to_dt: Optional[str] = Query(None, alias="to"),
        sort_by: str = Query("date"),
        order: str = Query("desc"),
    ):
        from_parsed = _parse_iso(from_dt)
        to_parsed = _parse_iso(to_dt)
        pushed = reader.query_page(
            page=page, page_size=page_size,
            project_name=project_name, project_id=project_id, user_id=user_id, session_id=session_id,
            from_dt=from_parsed, to_dt=to_parsed, sort_by=sort_by, order=order,
        )
        if pushed is not None:
            page_items, total = pushed
            return {
                "traces": [_trace_summary(t) for t in page_items],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        return paginate_traces(
            reader.get_traces(),
            page=page,
            page_size=page_size,
            project_name=project_name,
            project_id=project_id,
            user_id=user_id,
            from_dt=from_parsed,
            to_dt=to_parsed,
            sort_by=sort_by,
            order=order,
        )

    @router.get("/api/traces/{trace_id}")
    def api_trace_detail(trace_id: str):
        trace = reader.get_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Trace not found")
        return _trace_to_api_dict(trace)

    @router.get("/api/traces/{trace_id}/graph")
    def api_trace_graph(trace_id: str):
        trace = reader.get_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Trace not found")
        meta = trace.metadata or {}
        if meta.get("_is_summary") or meta.get("_export_status") == "summary_only":
            return {"nodes": [], "edges": []}
        return build_graph(trace)

    @router.get("/api/metrics")
    def api_metrics(
        period: str = Query("24h"),
        from_dt: Optional[str] = Query(None, alias="from"),
        to_dt: Optional[str] = Query(None, alias="to"),
        project_name: Optional[str] = Query(None),
        project_id: Optional[str] = Query(None),
    ):
        from_parsed = _parse_iso(from_dt)
        to_parsed = _parse_iso(to_dt)
        if from_parsed is None:
            to_parsed = datetime.now(timezone.utc)
            from_parsed = to_parsed - _period_delta(period)
        traces = reader.get_traces_for_metrics(
            project_name=project_name, project_id=project_id,
            from_dt=from_parsed, to_dt=to_parsed,
        )
        metrics = compute_metrics(
            traces,
            period=period,
            from_dt=from_parsed,
            to_dt=to_parsed,
            project_name=project_name,
            project_id=project_id,
        )
        totals = reader.get_metrics_totals(
            from_dt=from_parsed, to_dt=to_parsed,
            project_name=project_name, project_id=project_id,
        )
        if totals is not None:
            metrics.update(totals)
        return metrics

    @router.get("/api/health")
    def api_health():
        try:
            from importlib.metadata import version as _pkg_version
            _ver = _pkg_version("tracecast")
        except Exception:
            _ver = "0.3.0"
        body = {
            "status": "ok",
            "version": _ver,
            "exporter": type(reader._exporters[0]).__name__ if reader._exporters else "none",
            "export": None,
            "ingest": None,
            "priorities": ["trace_count", "tokens", "cost"],
        }
        provider = getattr(reader, "export_stats_provider", None)
        if callable(provider):
            try:
                body["export"] = provider()
            except Exception:
                body["export"] = {"error": "stats_unavailable"}
        ingest = getattr(reader, "ingest", None)
        if ingest is not None and hasattr(ingest, "health"):
            try:
                body["ingest"] = ingest.health()
            except Exception:
                body["ingest"] = {"enabled": True, "error": "stats_unavailable"}
        return body

    def _require_ingest_auth(request: Request) -> None:
        from ..core.ingest_auth import check_ingest_authorized

        ok = check_ingest_authorized(
            authorization=request.headers.get("authorization"),
            x_token=request.headers.get("x-tracecast-token"),
        )
        if not ok:
            raise HTTPException(
                status_code=401,
                detail="ingest auth required (X-TraceCast-Token or Bearer)",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def _ingest_response(docs: list):
        ingest = getattr(reader, "ingest", None)
        if ingest is None:
            raise HTTPException(status_code=503, detail="ingest disabled on this server")
        if not docs:
            raise HTTPException(status_code=400, detail="no valid traces in body")
        # Soft body guard: reject absurd batches early.
        if len(docs) > 200:
            raise HTTPException(status_code=413, detail="batch too large (max 200 traces)")
        # Prefer metrics: ensure token fields exist even if spans empty/truncated.
        for d in docs:
            if not isinstance(d, dict):
                continue
            if d.get("total_tokens") is None:
                tin = int(d.get("total_tokens_in") or 0)
                tout = int(d.get("total_tokens_out") or 0)
                d["total_tokens"] = tin + tout
        result = ingest.accept(docs)
        status = 202 if result.get("accepted", 0) > 0 else 503
        return JSONResponse(status_code=status, content=result)

    @router.post("/api/ingest")
    async def api_ingest(request: Request):
        _require_ingest_auth(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        from ..core.ingest import normalize_ingest_body
        return _ingest_response(normalize_ingest_body(body))

    @router.post("/api/ingest/batch")
    async def api_ingest_batch(request: Request):
        _require_ingest_auth(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        from ..core.ingest import normalize_ingest_body
        return _ingest_response(normalize_ingest_body(body))

    @router.get("/", response_class=HTMLResponse)
    def dashboard_index():
        return HTMLResponse(content=_index_html(prefix))

    @router.get("/api/filter-options")
    def api_filter_options():
        return reader.get_filter_options()

    @router.get("/api/sessions")
    def api_sessions(
        project_name: Optional[str] = Query(None),
        project_id: Optional[str] = Query(None),
        user_id: Optional[str] = Query(None),
    ):
        sessions = reader.get_sessions(
            project_name=project_name,
            project_id=project_id,
            user_id=user_id,
        )
        return {"sessions": sessions, "total": len(sessions)}

    @router.get("/api/sessions/{session_id}")
    def api_session_detail(session_id: str):
        traces = reader.get_session(session_id)
        if not traces:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session_id": session_id,
            "traces": [_trace_summary(t) for t in traces],
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "total_tokens": sum(t.total_tokens for t in traces),
        }

    @router.get("/api/projects")
    def api_projects():
        projects = reader.get_projects()
        return {"projects": projects, "total": len(projects)}

    @router.get("/api/projects/{project_name}/sub-projects")
    def api_project_subprojects(project_name: str):
        sub = reader.get_subprojects(project_name)
        return {"project_name": project_name, "sub_projects": sub, "total": len(sub)}

    @router.get("/api/projects/{project_id}")
    def api_project_detail(project_id: str):
        traces = reader.get_project(project_id)
        if not traces:
            raise HTTPException(status_code=404, detail="Project not found")
        return {
            "project_id": project_id,
            "traces": [_trace_summary(t) for t in traces],
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "total_tokens": sum(t.total_tokens for t in traces),
        }

    from .eval_reader import EvalReader
    from .score_reader import ScoreReader
    from .prompt_reader import PromptReader
    eval_reader = EvalReader(reader._exporters)
    score_reader = ScoreReader(reader._exporters)
    prompt_reader = PromptReader(reader._exporters)

    @router.get("/api/prompts")
    def api_prompts():
        prompts = prompt_reader.list_prompts()
        return {"prompts": prompts, "total": len(prompts)}

    @router.get("/api/prompts/{name}")
    def api_prompt_detail(name: str):
        versions = prompt_reader.get_versions(name)
        if versions is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"name": name, "versions": versions}

    @router.get("/api/traces/{trace_id}/scores")
    def api_trace_scores(trace_id: str):
        scores = score_reader.list_for_trace(trace_id)
        return {"scores": scores, "total": len(scores)}

    @router.get("/api/evals")
    def api_evals(
        project_id: Optional[str] = Query(None),
        dataset_name: Optional[str] = Query(None),
        from_dt: Optional[str] = Query(None, alias="from"),
        to_dt: Optional[str] = Query(None, alias="to"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        runs = eval_reader.list_runs(
            project_id=project_id, dataset_name=dataset_name,
            from_dt=_parse_iso(from_dt), to_dt=_parse_iso(to_dt),
            limit=limit, offset=offset,
        )
        summaries = [{k: v for k, v in r.items() if k != "cases"} for r in runs]
        return {"evals": summaries, "total": len(summaries), "limit": limit, "offset": offset}

    @router.get("/api/evals/compare")
    def api_eval_compare(a: str = Query(...), b: str = Query(...)):
        from ..eval.compare import compare
        run_a = eval_reader.get_run(a)
        run_b = eval_reader.get_run(b)
        if not run_a or not run_b:
            missing = a if not run_a else b
            raise HTTPException(status_code=404, detail=f"Eval run not found: {missing}")
        return compare(run_a, run_b)

    @router.get("/api/evals/{run_id}")
    def api_eval_detail(run_id: str):
        run = eval_reader.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Eval run not found")
        return run

    @router.post("/api/evals/run")
    def api_eval_run(body: dict):
        from ..eval.decorator import get_target, list_targets
        from ..eval.runner import run_evaluation
        if not list_targets():
            raise HTTPException(
                status_code=501,
                detail="No evaluation targets registered in this process. "
                       "The standalone server is read-only for evals.",
            )
        target_name = body.get("target")
        if get_target(target_name) is None:
            raise HTTPException(status_code=404, detail=f"Eval target not registered: {target_name}")
        run = run_evaluation(target_name, exporters=reader._exporters, dataset=body.get("dataset"))
        return run.to_dict()

    @router.get("/static/{filename}")
    def static_file(filename: str):
        fp = STATIC_DIR / filename
        if not fp.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return Response(content=fp.read_bytes(), media_type=_mime(filename))

    @router.get("/assets/{path:path}")
    def static_assets(path: str):
        fp = STATIC_DIR / "assets" / path
        if not fp.exists():
            raise HTTPException(status_code=404, detail="Asset not found")
        return Response(content=fp.read_bytes(), media_type=_mime(path))

    @router.get("/{path:path}")
    def spa_fallback(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        if not (STATIC_DIR / "index.html").exists():
            raise HTTPException(status_code=404)
        return HTMLResponse(content=_index_html(prefix))

    return router
