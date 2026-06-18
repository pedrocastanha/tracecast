from typing import Any, Dict, List, Optional

from ..models.score import Score
from .logger import _logger


def _resolve_exporters(exporters, tracer) -> List:
    if exporters is not None:
        return exporters
    if tracer is not None:
        return getattr(tracer, "exporters", []) or []
    from ..decorators import _default_tracer
    if _default_tracer is not None:
        return getattr(_default_tracer, "exporters", []) or []
    return []


def score(
    trace_id: str,
    name: str,
    value: float,
    *,
    span_id: Optional[str] = None,
    kind: str = "human",
    data_type: str = "numeric",
    string_value: Optional[str] = None,
    comment: Optional[str] = None,
    source: str = "sdk",
    project_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    exporters: Optional[List] = None,
    tracer=None,
) -> Score:
    """Attach a Score to a production trace (or span) and persist it.

    Validates before persisting; exporter failures are logged, never raised.
    """
    s = Score(
        trace_id=trace_id, name=name, value=value, span_id=span_id, kind=kind,
        data_type=data_type, string_value=string_value, comment=comment,
        source=source, project_id=project_id, metadata=metadata or {},
    )
    s.validate()

    for exporter in _resolve_exporters(exporters, tracer):
        if callable(getattr(exporter, "export_score", None)):
            try:
                exporter.export_score(s)
            except Exception as exc:
                _logger.error(
                    "TraceCast: export_score failed for %s: %s", s.score_id, exc, exc_info=True
                )
    return s
