"""LlamaIndex instrumentor using the dispatcher-based event system."""

from __future__ import annotations

from typing import Optional, Any

from .base import BaseInstrumentor


class LlamaIndexInstrumentor(BaseInstrumentor):
    """Instruments LlamaIndex by registering a TraceCastSpanHandler with the global dispatcher.

    Usage::

        inst = LlamaIndexInstrumentor()
        inst.patch()          # all subsequent LlamaIndex spans are captured
        ...
        inst.unpatch()        # removes the handler
    """

    def __init__(self) -> None:
        self._patched: bool = False
        self._handler: Optional[Any] = None

    def patch(self) -> None:
        if self._patched:
            return

        from llama_index.core.instrumentation import get_dispatcher
        from ._llamaindex_handler import _build_handler_class

        TraceCastSpanHandler = _build_handler_class()
        dispatcher = get_dispatcher()
        self._handler = TraceCastSpanHandler()
        dispatcher.add_span_handler(self._handler)
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return

        from llama_index.core.instrumentation import get_dispatcher

        dispatcher = get_dispatcher()
        if self._handler in dispatcher.span_handlers:
            dispatcher.span_handlers.remove(self._handler)

        self._handler = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched
