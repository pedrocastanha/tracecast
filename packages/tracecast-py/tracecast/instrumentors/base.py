from abc import ABC, abstractmethod
from typing import Optional


def active_parent_id() -> Optional[str]:
    from ..core.tracer import Tracer
    return getattr(Tracer.current_span(), "span_id", None)


class BaseInstrumentor(ABC):
    @abstractmethod
    def patch(self) -> None:
        ...

    @abstractmethod
    def unpatch(self) -> None:
        ...

    @abstractmethod
    def is_patched(self) -> bool:
        ...
