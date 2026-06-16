from typing import List, Optional


class EvalReader:
    def __init__(self, exporters: list):
        self._exporters = exporters

    def _readable(self):
        for exporter in self._exporters:
            if callable(getattr(exporter, "query_evals", None)):
                return exporter
        return None

    def list_runs(self, *, project_id=None, dataset_name=None, from_dt=None, to_dt=None,
                  limit: int = 50, offset: int = 0) -> List[dict]:
        exporter = self._readable()
        if exporter is None:
            return []
        return exporter.query_evals(
            project_id=project_id, dataset_name=dataset_name,
            from_dt=from_dt, to_dt=to_dt, limit=limit, offset=offset,
        )

    def get_run(self, run_id: str) -> Optional[dict]:
        exporter = self._readable()
        if exporter is None:
            return None
        return exporter.get_eval(run_id)
