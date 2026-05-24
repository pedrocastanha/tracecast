"""Flask Blueprint serving dashboard REST API and static files."""

try:
    from flask import Blueprint, jsonify, request, send_file
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

from pathlib import Path
from datetime import datetime
from typing import Optional
from .reader import TraceReader
from .aggregator import compute_metrics, paginate_traces, _trace_summary

STATIC_DIR = Path(__file__).parent / "static"


def _mime(filename: str) -> str:
    if filename.endswith(".html"): return "text/html; charset=utf-8"
    if filename.endswith(".css"): return "text/css; charset=utf-8"
    if filename.endswith(".js"): return "application/javascript; charset=utf-8"
    if filename.endswith(".svg"): return "image/svg+xml"
    return "application/octet-stream"


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _make_blueprint(reader: TraceReader, prefix: str = "/tracecast") -> "Blueprint":
    if not HAS_FLASK:
        raise ImportError("Flask is required for dashboard. Install with: pip install flask")

    bp = Blueprint("tracecast_dashboard", __name__, url_prefix=prefix)

    @bp.route("/api/traces")
    def api_traces():
        traces = reader.get_traces()
        return jsonify(paginate_traces(
            traces,
            page=request.args.get("page", 1, type=int),
            page_size=request.args.get("page_size", 50, type=int),
            project_id=request.args.get("project_id"),
            user_id=request.args.get("user_id"),
            from_dt=_parse_iso(request.args.get("from")),
            to_dt=_parse_iso(request.args.get("to")),
            sort_by=request.args.get("sort_by", "date"),
            order=request.args.get("order", "desc"),
        ))

    @bp.route("/api/traces/<trace_id>")
    def api_trace_detail(trace_id: str):
        trace = reader.get_trace(trace_id)
        if not trace:
            return jsonify({"error": "Trace not found"}), 404
        return jsonify(trace.to_dict())

    @bp.route("/api/metrics")
    def api_metrics():
        traces = reader.get_traces()
        return jsonify(compute_metrics(
            traces,
            period=request.args.get("period", "7d"),
            from_dt=_parse_iso(request.args.get("from")),
            to_dt=_parse_iso(request.args.get("to")),
            project_id=request.args.get("project_id"),
        ))

    @bp.route("/api/health")
    def api_health():
        return jsonify({
            "status": "ok",
            "version": "0.3.0",
            "exporter": type(reader._exporters[0]).__name__ if reader._exporters else "none",
        })

    @bp.route("/api/sessions")
    def api_sessions():
        sessions = reader.get_sessions()
        return jsonify({"sessions": sessions, "total": len(sessions)})

    @bp.route("/api/sessions/<session_id>")
    def api_session_detail(session_id: str):
        traces = reader.get_session(session_id)
        if not traces:
            return jsonify({"error": "Session not found"}), 404
        return jsonify({
            "session_id": session_id,
            "traces": [_trace_summary(t) for t in traces],
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "total_tokens": sum(t.total_tokens for t in traces),
        })

    @bp.route("/api/projects")
    def api_projects():
        projects = reader.get_projects()
        return jsonify({"projects": projects, "total": len(projects)})

    @bp.route("/api/projects/<project_id>")
    def api_project_detail(project_id: str):
        traces = reader.get_project(project_id)
        if not traces:
            return jsonify({"error": "Project not found"}), 404
        return jsonify({
            "project_id": project_id,
            "traces": [_trace_summary(t) for t in traces],
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "total_tokens": sum(t.total_tokens for t in traces),
        })

    @bp.route("/static/<filename>")
    def static_file(filename: str):
        fp = STATIC_DIR / filename
        if not fp.exists():
            return "Not found", 404
        return send_file(fp, mimetype=_mime(filename))

    @bp.route("/assets/<path:path>")
    def static_assets(path: str):
        fp = STATIC_DIR / "assets" / path
        if not fp.exists():
            return "Not found", 404
        return send_file(fp, mimetype=_mime(path))

    @bp.route("/", defaults={"path": ""})
    @bp.route("/<path:path>")
    def spa_fallback(path: str):
        if path.startswith("api/"):
            return "Not found", 404
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return send_file(index_path, mimetype="text/html")
        return "<h1>TraceCast Dashboard</h1>", 200

    return bp
