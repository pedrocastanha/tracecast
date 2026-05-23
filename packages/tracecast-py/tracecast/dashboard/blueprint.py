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
from .aggregator import compute_metrics, paginate_traces

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

    @bp.route("/")
    def dashboard_index():
        fp = STATIC_DIR / "index.html"
        if fp.exists():
            return send_file(fp, mimetype="text/html")
        return "<h1>TraceCast Dashboard</h1>", 200

    @bp.route("/static/<filename>")
    def static_file(filename: str):
        fp = STATIC_DIR / filename
        if not fp.exists():
            return "Not found", 404
        return send_file(fp, mimetype=_mime(filename))

    return bp
