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


class _LazyHandler:
    """Proxy that caches a single TraceCastCallback delegate, resolving tracer lazily on first use.

    LangChain calls methods such as ``on_llm_start`` and ``on_llm_end`` on the
    *same* object stored in a ``CallbackManager``.  ``TraceCastCallback`` is
    stateful — it stores active spans in ``self._span_stack`` — so all callback
    methods **must** share one delegate instance.  Creating a new
    ``TraceCastCallback`` on every ``__getattr__`` call (the previous
    implementation) caused the span stack to be empty on ``on_llm_end``,
    silently dropping every span.

    The tracer reference is kept current without losing span state: if
    ``_default_tracer`` is set after ``patch()`` (e.g. via ``auto_instrument``),
    subsequent attribute accesses update ``delegate.tracer`` in-place.
    """

    def __init__(self) -> None:
        object.__setattr__(self, "_delegate", None)

    def __getattr__(self, name: str):  # type: ignore[override]
        from ..decorators import _default_tracer
        from ..core.tracer import Tracer as _Tracer
        from ..integrations.langchain import TraceCastCallback

        delegate = object.__getattribute__(self, "_delegate")
        if delegate is None:
            tracer = _default_tracer if _default_tracer is not None else _Tracer()
            delegate = TraceCastCallback(tracer)
            object.__setattr__(self, "_delegate", delegate)
        else:
            # Keep tracer reference current without losing span state
            from ..decorators import _default_tracer as _dt
            if _dt is not None:
                delegate.tracer = _dt
        return getattr(delegate, name)


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
        """Register a lazy TraceCastCallback as a global LangChain callback handler."""
        if self._patched:
            return

        # Raises ImportError if langchain_core is not installed — done before
        # any state mutation so the instance stays in an unpatched state.
        _ensure_hook_registered()

        # Use a lazy handler so the tracer is resolved at invocation time, not
        # at patch() time.  This means auto_instrument(tracer) can be called
        # AFTER patch() and the correct tracer will still be used.
        self._handler = _LazyHandler()

        # Set the ContextVar so LangChain includes our handler in every
        # CallbackManager it creates from this point on.
        self._ctx_token = _tracecast_handler_var.set(self._handler)
        self._patched = True

    def unpatch(self) -> None:
        """Remove TraceCastCallback from future LangChain callback managers."""
        if not self._patched or self._handler is None:
            return

        # Use set(None) rather than reset() — reset() is only safe in strict
        # LIFO order within the same Context; any out-of-order call raises
        # ValueError or silently corrupts state.  set(None) is always safe for
        # the single-instance use case.
        _tracecast_handler_var.set(None)
        self._handler = None
        self._ctx_token = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched
