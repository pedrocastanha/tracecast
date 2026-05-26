from fastapi import FastAPI
from tracecast import Tracer, set_default_tracer, trace_cast
from tracecast.exporters import DictExporter

exporter = DictExporter()
tracer = Tracer(exporters=[exporter])


@trace_cast(name="python-smoke-chat", project_id="real-python")
async def run_chat():
    return {"reply": "ok"}


set_default_tracer(tracer)

app = FastAPI()
tracer.mount(app, prefix="/observability")


@app.get("/chat")
async def chat():
    return await run_chat()
