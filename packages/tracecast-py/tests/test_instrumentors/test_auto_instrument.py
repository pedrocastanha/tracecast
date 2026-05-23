import pytest
from tracecast.instrumentors.base import BaseInstrumentor
from tracecast.instrument import auto_instrument, _registry, _reset


class FakeInstrumentor(BaseInstrumentor):
    def __init__(self):
        self.patched = False
        self.unpatched = False

    def patch(self) -> None:
        self.patched = True

    def unpatch(self) -> None:
        self.unpatched = True
        self.patched = False

    def is_patched(self) -> bool:
        return self.patched


def test_base_instrumentor_is_abstract():
    with pytest.raises(TypeError):
        BaseInstrumentor()


def test_auto_instrument_calls_patch_on_registered():
    _reset()
    fake = FakeInstrumentor()
    _registry["fake"] = fake
    auto_instrument()
    assert fake.is_patched()
    _reset()


def test_auto_instrument_idempotent():
    _reset()
    fake = FakeInstrumentor()
    _registry["fake"] = fake
    auto_instrument()
    auto_instrument()  # second call should be no-op
    assert fake.is_patched()
    _reset()


def test_auto_instrument_sets_default_tracer():
    _reset()
    from tracecast import Tracer
    from tracecast.decorators import _default_tracer

    tracer = Tracer()
    auto_instrument(tracer)

    from tracecast.decorators import _default_tracer as dt
    assert dt is tracer
    _reset()


def test_auto_instrument_skip_import_error():
    _reset()

    class BadInstrumentor(BaseInstrumentor):
        def patch(self):
            raise ImportError("no such module")
        def unpatch(self):
            pass
        def is_patched(self):
            return False

    _registry["bad"] = BadInstrumentor()
    auto_instrument()  # should not raise
    _reset()
