import threading
import warnings
from typing import Dict, Optional
from .instrumentors.base import BaseInstrumentor
from .core.tracer import Tracer
from .decorators import set_default_tracer

_registry: Dict[str, BaseInstrumentor] = {}
_instrumented = False
_lock = threading.Lock()


def auto_instrument(tracer: Optional[Tracer] = None) -> None:
    global _instrumented
    with _lock:
        if _instrumented:
            return
        if tracer:
            set_default_tracer(tracer)
        # Register all built-in instrumentors (lazy to avoid circular imports at
        # package load time; _register_all() is defined in instrumentors/__init__.py).
        try:
            from .instrumentors import _register_all
            _register_all()
        except Exception as exc:
            warnings.warn(f"TraceCast: failed to register instrumentors: {exc}")
        for name, inst in _registry.items():
            try:
                inst.patch()
            except ImportError:
                pass
            except Exception as exc:
                warnings.warn(f"TraceCast: instrumentor '{name}' failed to patch: {exc}")
        _instrumented = True


def _reset() -> None:
    global _instrumented
    with _lock:
        for inst in _registry.values():
            try:
                if inst.is_patched():
                    inst.unpatch()
            except Exception:
                pass
        _registry.clear()
        _instrumented = False
