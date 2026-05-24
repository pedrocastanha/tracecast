"""
TraceCast v0.2.0 — Fake Demo App
=================================
Demonstrates auto-instrumentation + dashboard with a mock LLM backend.

Run from the repo root:
    python3 examples/fake_app.py

Then open:  http://localhost:7777/tracecast/
API health: http://localhost:7777/tracecast/api/health
Chat:       POST http://localhost:7777/chat  {"message": "hi", "model": "gpt-4o"}
"""

import sys
import os
import types
import random
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Inject a fake openai module BEFORE importing tracecast so the instrumentor
# can patch it. In a real app the real `openai` package would be installed.
# ---------------------------------------------------------------------------
def _make_fake_openai():
    openai = types.ModuleType("openai")
    resources = types.ModuleType("openai.resources")
    chat = types.ModuleType("openai.resources.chat")
    completions_mod = types.ModuleType("openai.resources.chat.completions")

    class Completions:
        # The real OpenAI SDK exposes Completions.create as an instance method.
        # Our instrumentor patches Completions.create at class level.
        def create(self, *args, **kwargs):
            # Base (un-patched) implementation — returns a fake response.
            model = kwargs.get("model", "gpt-4o-mini")
            messages = kwargs.get("messages", [])
            prompt = messages[-1].get("content", "") if messages else ""
            return _build_response(model, prompt)

    completions_mod.Completions = Completions
    chat.completions = completions_mod
    resources.chat = chat
    openai.resources = resources

    sys.modules["openai"] = openai
    sys.modules["openai.resources"] = resources
    sys.modules["openai.resources.chat"] = chat
    sys.modules["openai.resources.chat.completions"] = completions_mod
    return completions_mod

_completions_mod = _make_fake_openai()

# ---------------------------------------------------------------------------
# Now import tracecast — auto_instrument will patch our fake Completions
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "tracecast-py"))

from tracecast import Tracer, auto_instrument, trace_cast, DictExporter
from tracecast.models.span import Span, SpanType
from tracecast.models.trace import Trace
from tracecast.core.cost_calculator import calculate_cost

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("Install:  pip install fastapi uvicorn")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Fake response builder
# ---------------------------------------------------------------------------
FAKE_ANSWERS = [
    "Sure! Use `sorted(lst)` in Python to sort a list in ascending order.",
    "The capital of France is Paris — city of lights and baguettes.",
    "Machine learning models learn patterns from training data without explicit rules.",
    "To fix a merge conflict: edit the conflicting file, then `git add` + `git commit`.",
    "Docker containers package your app and its dependencies for reproducible runs.",
    "REST APIs use GET (read), POST (create), PUT (update), DELETE (remove).",
    "Use `async/await` with `asyncio` for concurrent I/O-bound tasks in Python.",
    "SQL `JOIN` combines rows from two tables based on a matching column.",
    "A webhook fires an HTTP POST to your URL when an event occurs externally.",
    "LLM context windows determine how much text the model can 'see' at once.",
]

MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini", "gpt-3.5-turbo"]
PROJECTS = ["chatbot-prod", "code-assistant", "data-pipeline", "support-bot"]
SESSIONS = [f"sess-{i:04d}" for i in range(1, 9)]
USERS = ["alice", "bob", "carol", "dave", "eve"]


def _build_response(model: str, prompt: str) -> MagicMock:
    tokens_in = len(prompt.split()) * 4 + random.randint(20, 80)
    tokens_out = random.randint(40, 180)
    cached = random.randint(0, tokens_in // 5)
    content = random.choice(FAKE_ANSWERS)

    resp = MagicMock()
    resp.usage.prompt_tokens = tokens_in
    resp.usage.completion_tokens = tokens_out
    resp.usage.prompt_tokens_details.cached_tokens = cached
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.reasoning_content = None
    return resp


# ---------------------------------------------------------------------------
# TraceCast setup
# ---------------------------------------------------------------------------
exporter = DictExporter()
tracer = Tracer(exporters=[exporter])
auto_instrument(tracer)   # patches our fake Completions.create


# ---------------------------------------------------------------------------
# Seed historical traces directly (bypass HTTP)
# ---------------------------------------------------------------------------
def _seed_traces() -> None:
    now = datetime.now(timezone.utc)
    for i in range(35):
        project = random.choice(PROJECTS)
        session = random.choice(SESSIONS)
        user = random.choice(USERS)
        model = random.choice(MODELS)
        age_h = random.uniform(0.5, 168)
        started = now - timedelta(hours=age_h)
        latency = random.randint(250, 3500)
        finished = started + timedelta(milliseconds=latency)

        tok_in = random.randint(80, 700)
        tok_out = random.randint(30, 250)
        tok_cached = random.randint(0, tok_in // 5)
        cost = calculate_cost(model, tok_in, tok_out, tokens_in_cached=tok_cached)

        span = Span(
            span_id=f"span-seed-{i:04d}",
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=started,
            finished_at=finished,
            tokens_in=tok_in,
            tokens_out=tok_out,
            tokens_in_cached=tok_cached,
            cost_usd=cost,
            input=f"Seed query #{i}: explain something interesting about AI.",
            output=random.choice(FAKE_ANSWERS),
        )
        trace = Trace(
            trace_id=f"trace-seed-{i:04d}",
            name=f"chat/{project}",
            started_at=started,
            finished_at=finished,
            project_id=project,
            session_id=session,
            user_id=user,
            model=model,
            total_tokens_in=tok_in,
            total_tokens_out=tok_out,
            total_tokens_in_cached=tok_cached,
            total_tokens=tok_in + tok_out,
            cost_usd=cost,
            latency_ms=latency,
            spans=[span],
        )
        exporter.export(trace)
    print(f"[tracecast] Seeded {len(exporter.traces)} historical traces")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="TraceCast Fake Demo")


@app.get("/")
async def root():
    return JSONResponse({
        "app": "TraceCast Fake Demo v0.2.0",
        "dashboard": "http://localhost:7777/tracecast/",
        "endpoints": {
            "chat": "POST /chat  body: {message, model?, session_id?, project_id?}",
            "health": "GET /tracecast/api/health",
            "traces": "GET /tracecast/api/traces",
            "metrics": "GET /tracecast/api/metrics",
        },
        "total_traces": len(exporter.traces),
    })


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "Hello! What can you do?")
    model = body.get("model", "gpt-4o-mini")
    session_id = body.get("session_id", random.choice(SESSIONS))
    project_id = body.get("project_id", "chatbot-prod")
    user_id = body.get("user_id", random.choice(USERS))

    async with tracer.atrace(
        "chat/completions",
        session_id=session_id,
        project_id=project_id,
        user_id=user_id,
    ):
        # Call through the patched Completions.create —
        # the OpenAI instrumentor intercepts this and creates a span.
        instance = _completions_mod.Completions()
        result = _completions_mod.Completions.create(
            instance,
            model=model,
            messages=[{"role": "user", "content": message}],
        )

    return JSONResponse({
        "reply": result.choices[0].message.content,
        "model": model,
        "session_id": session_id,
        "project_id": project_id,
        "total_traces": len(exporter.traces),
    })


# ---------------------------------------------------------------------------
# Generate a burst of live traces 1 second after startup
# ---------------------------------------------------------------------------
async def _live_burst() -> None:
    await asyncio.sleep(1.2)
    print("[tracecast] Generating 8 live traces via @trace_cast ...")
    for i in range(8):
        model = random.choice(MODELS)
        project = random.choice(PROJECTS)
        session = random.choice(SESSIONS)
        prompt = f"Live query #{i+1}: what is {random.choice(['asyncio', 'docker', 'LangChain', 'vector databases', 'RAG', 'RLHF'])}?"

        async with tracer.atrace(
            f"live-burst-{i+1}",
            project_id=project,
            session_id=session,
            user_id=random.choice(USERS),
        ):
            instance = _completions_mod.Completions()
            _completions_mod.Completions.create(
                instance,
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
        await asyncio.sleep(0.05)
    print(f"[tracecast] Done. Total traces in exporter: {len(exporter.traces)}")


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_live_burst())


# ---------------------------------------------------------------------------
# Mount dashboard
# ---------------------------------------------------------------------------
tracer.mount(app, prefix="/tracecast", max_traces=500)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _seed_traces()

    print()
    print("=" * 60)
    print("  TraceCast v0.2.0 — Fake Demo App")
    print("=" * 60)
    print("  Dashboard  →  http://localhost:7777/tracecast/")
    print("  API root   →  http://localhost:7777/")
    print()
    print("  Try a chat request:")
    print('  curl -s -X POST http://localhost:7777/chat \\')
    print('    -H "Content-Type: application/json" \\')
    print("    -d '{\"message\": \"What is Docker?\", \"model\": \"gpt-4o\"}' | python3 -m json.tool")
    print("=" * 60)
    print()

    uvicorn.run(app, host="0.0.0.0", port=7777, log_level="warning")
