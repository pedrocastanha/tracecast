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
        self.export(trace)
