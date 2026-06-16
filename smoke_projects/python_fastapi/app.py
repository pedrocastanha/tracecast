from types import SimpleNamespace

from fastapi import FastAPI
from tracecast import Tracer, set_default_tracer, trace_cast, wrap_openai
from tracecast.exporters import DictExporter

exporter = DictExporter()
tracer = Tracer(exporters=[exporter])


class FakeCompletions:
    def create(self, **kwargs):
        usage = SimpleNamespace(
            prompt_tokens=90,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=20),
        )
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(usage=usage, choices=[choice], model=kwargs["model"])


class FakeOpenAI:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


client = wrap_openai(FakeOpenAI())


@trace_cast(name="python-smoke-chat", project_id="real-python")
async def run_chat():
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )
    return {"reply": response.choices[0].message.content}


set_default_tracer(tracer)

app = FastAPI()
tracer.mount(app, prefix="/observability")


@app.get("/chat")
async def chat():
    return await run_chat()
