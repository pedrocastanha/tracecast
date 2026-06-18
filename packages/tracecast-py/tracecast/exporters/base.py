import asyncio
from abc import ABC, abstractmethod
from ..models.trace import Trace


class BaseExporter(ABC):
    @abstractmethod
    def export(self, trace: Trace) -> None:
        ...

    def export_batch(self, traces: list) -> None:
        for trace in traces:
            self.export(trace)

    async def aexport(self, trace: Trace) -> None:
        await asyncio.to_thread(self.export, trace)

    # --- Optional domain persistence (default no-op / empty) ---------------
    # Exporters that back the dashboard's eval views override these. Exporters
    # that don't implement them degrade gracefully: writes are no-ops, reads
    # return empty.

    def export_eval(self, run) -> None:
        return None

    def query_evals(self, *, project_id=None, dataset_name=None,
                    from_dt=None, to_dt=None, limit: int = 50, offset: int = 0) -> list:
        return []

    def get_eval(self, run_id: str):
        return None

    def export_score(self, score) -> None:
        return None

    def query_scores(self, *, trace_id=None, name=None,
                     from_dt=None, to_dt=None, limit: int = 100, offset: int = 0) -> list:
        return []
