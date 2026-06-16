from types import SimpleNamespace

from tracecast import Tracer, wrap_openai
from tracecast.exporters.dict_exporter import DictExporter


class FakeCompletions:
    def create(self, **kwargs):
        usage = SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=40,
            prompt_tokens_details=SimpleNamespace(cached_tokens=30),
        )
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(usage=usage, choices=[choice], model=kwargs["model"])


class FakeOpenAI:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


def test_wrap_openai_saves_tokens_and_cached_tokens():
    exporter = DictExporter()
    tracer = Tracer(exporters=[exporter])
    client = wrap_openai(FakeOpenAI())

    with tracer.trace("wrapped-openai"):
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
        )

    trace = exporter.traces[0]
    span = trace["spans"][0]

    assert trace["total_tokens_in"] == 120
    assert trace["total_tokens_out"] == 40
    assert trace["total_tokens_in_cached"] == 30
    assert trace["total_tokens"] == 160
    assert trace["model"] == "gpt-4o"
    assert span["tokens_in"] == 120
    assert span["tokens_out"] == 40
    assert span["tokens_in_cached"] == 30
    assert span["cost_usd"] > 0
