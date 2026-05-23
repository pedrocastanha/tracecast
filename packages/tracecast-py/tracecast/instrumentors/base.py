from abc import ABC, abstractmethod


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
