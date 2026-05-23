from typing import Dict, Optional
from .instrumentors.base import BaseInstrumentor
from .core.tracer import Tracer
from .decorators import set_default_tracer

_registry: Dict[str, BaseInstrumentor] = {}
_instrumented = False


def auto_instrument(tracer: Optional[Tracer] = None) -> None:
    global _instrumented
    if _instrumented:
        return
    if tracer:
        set_default_tracer(tracer)
    for name, inst in _registry.items():
        try:
            inst.patch()
        except ImportError:
            pass
    _instrumented = True


def _reset() -> None:
    global _instrumented
    for inst in _registry.values():
        try:
            if inst.is_patched():
                inst.unpatch()
        except Exception:
            pass
    _registry.clear()
    _instrumented = False
