"""LangChain global callback instrumentor.

Registers TraceCastCallback as a global LangChain callback via
``register_configure_hook`` (langchain-core >= 0.2). Every time LangChain
builds a CallbackManager (i.e. every chain / LLM invocation), the hook
checks whether the ContextVar holds a handler and, if so, attaches it
automatically.

This is the correct extension point for LangChain 0.3.x; the
``_global_callbacks`` attribute used in older prototypes does not exist in
this version.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from .base import BaseInstrumentor

# Module-level ContextVar that LangChain's _configure() will poll.
# Using a module-level var ensures register_configure_hook is called only once,
# regardless of how many LangChainInstrumentor instances are created.
_tracecast_handler_var: ContextVar[Optional[object]] = ContextVar(
    "tracecast_langchain_handler", default=None
)
_hook_registered: bool = False


def _ensure_hook_registered() -> None:
    """Register the ContextVar with LangChain's configure-hook list exactly once."""
    global _hook_registered
    if _hook_registered:
        return
    from langchain_core.tracers.context import register_configure_hook

    # inheritable=True so child callback managers also receive the handler.
    # handler_class=None means LangChain uses direct identity comparison
    # instead of isinstance dedup — required because TraceCastCallback has
    # no unique class identity from LangChain's perspective.
    register_configure_hook(_tracecast_handler_var, inheritable=True)
    _hook_registered = True


class LangChainInstrumentor(BaseInstrumentor):
    """Instruments LangChain by registering TraceCastCallback globally.

    Usage::

        inst = LangChainInstrumentor()
        inst.patch()          # all subsequent LangChain runs are captured
        ...
        inst.unpatch()        # removes the handler from new runs
    """

    def __init__(self) -> None:
        self._handler: Optional[object] = None
        self._patched: bool = False
        self._ctx_token = None  # ContextVar reset token

    def patch(self) -> None:
        """Register TraceCastCallback as a global LangChain callback handler."""
        if self._patched:
            return

        _ensure_hook_registered()

        from ..integrations.langchain import TraceCastCallback
        from ..decorators import _default_tracer
        from ..core.tracer import Tracer

        tracer = _default_tracer or Tracer()
        self._handler = TraceCastCallback(tracer)

        # Set the ContextVar so LangChain includes our handler in every
        # CallbackManager it creates from this point on.
        self._ctx_token = _tracecast_handler_var.set(self._handler)
        self._patched = True

    def unpatch(self) -> None:
        """Remove TraceCastCallback from future LangChain callback managers."""
        if not self._patched or self._handler is None:
            return

        # Restore the ContextVar to its previous value (None by default).
        if self._ctx_token is not None:
            try:
                _tracecast_handler_var.reset(self._ctx_token)
            except ValueError:
                # Token already consumed or from a different context — fall back
                # to explicitly clearing the var.
                _tracecast_handler_var.set(None)
            self._ctx_token = None
        else:
            _tracecast_handler_var.set(None)

        self._handler = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched
