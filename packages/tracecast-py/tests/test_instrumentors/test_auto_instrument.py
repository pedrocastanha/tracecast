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
    from tracecast.instrument import _registry, _reset
    _reset()

    patch_count = 0

    class CountingInstrumentor(BaseInstrumentor):
        def patch(self) -> None:
            nonlocal patch_count
            patch_count += 1
            self._patched = True

        def unpatch(self) -> None:
            self._patched = False

        def is_patched(self) -> bool:
            return getattr(self, "_patched", False)

    _registry["counting"] = CountingInstrumentor()
    auto_instrument()
    auto_instrument()
    assert patch_count == 1  # must be called exactly once
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


def test_instrument_openai_chat_false_does_not_patch_chat_completions():
    """Bots already tracing chat completions through a manual LangChain
    callback should be able to opt into embeddings/audio only."""
    import sys
    import types
    from tracecast.instrument import instrument_openai

    _reset()
    openai = types.ModuleType("openai")
    resources = types.ModuleType("openai.resources")
    embeddings_mod = types.ModuleType("openai.resources.embeddings")

    class Embeddings:
        def create(self, **kwargs):
            return None

    embeddings_mod.Embeddings = Embeddings
    resources.embeddings = embeddings_mod
    openai.resources = resources
    sys.modules["openai"] = openai
    sys.modules["openai.resources"] = resources
    sys.modules["openai.resources.embeddings"] = embeddings_mod

    original_create = Embeddings.create
    instrument_openai(chat=False, embeddings=True, audio=False)

    assert embeddings_mod.Embeddings.create is not original_create
    assert "openai" in _registry
    assert _registry["openai"].is_patched()

    _reset()
    for k in list(sys.modules):
        if k.startswith("openai"):
            del sys.modules[k]


def test_instrument_openai_only_registers_openai():
    """instrument_openai() must not pull in anthropic/gemini/langchain/etc."""
    _reset()
    from tracecast.instrument import instrument_openai
    import sys
    import types

    openai = types.ModuleType("openai")
    resources = types.ModuleType("openai.resources")
    embeddings_mod = types.ModuleType("openai.resources.embeddings")

    class Embeddings:
        def create(self, **kwargs):
            return None

    embeddings_mod.Embeddings = Embeddings
    resources.embeddings = embeddings_mod
    openai.resources = resources
    sys.modules["openai"] = openai
    sys.modules["openai.resources"] = resources
    sys.modules["openai.resources.embeddings"] = embeddings_mod

    instrument_openai(chat=False, embeddings=True, audio=False)
    assert list(_registry.keys()) == ["openai"]

    _reset()
    for k in list(sys.modules):
        if k.startswith("openai"):
            del sys.modules[k]
