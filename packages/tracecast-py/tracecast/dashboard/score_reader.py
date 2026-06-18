from typing import List, Optional


class ScoreReader:
    def __init__(self, exporters: list):
        self._exporters = exporters

    def _readable(self):
        for exporter in self._exporters:
            if callable(getattr(exporter, "query_scores", None)):
                return exporter
        return None

    def list_for_trace(self, trace_id: str, *, limit: int = 100, offset: int = 0) -> List[dict]:
        exporter = self._readable()
        if exporter is None:
            return []
        return exporter.query_scores(trace_id=trace_id, limit=limit, offset=offset)

    def list_scores(self, *, trace_id: Optional[str] = None, name: Optional[str] = None,
                    from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> List[dict]:
        exporter = self._readable()
        if exporter is None:
            return []
        return exporter.query_scores(
            trace_id=trace_id, name=name, from_dt=from_dt, to_dt=to_dt,
            limit=limit, offset=offset,
        )
