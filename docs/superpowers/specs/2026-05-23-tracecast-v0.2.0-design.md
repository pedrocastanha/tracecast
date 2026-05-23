# TraceCast v0.2.0 Design Spec

**Status:** Approved  
**Date:** 2026-05-23  
**Target version:** v0.2.0  

---

## Goals

1. **`@trace_cast` decorator** with global auto-instrumentation of LLM SDKs and frameworks
2. **React dashboard** bundled with the package, mounted at `/tracecast`
3. **Persistent + in-memory storage** with clear warnings

---

## 1. Auto-Instrument Engine

### User API

```python
from tracecast import Tracer, auto_instrument, trace_cast
from tracecast.exporters.json_file import JsonFileExporter

tracer = Tracer(exporters=[JsonFileExporter("./traces.jsonl")])
auto_instrument(tracer)  # global patch of all detected SDKs/frameworks

@trace_cast
async def chat(prompt: str):
    response = openai.chat.completions.create(model="gpt-4o", messages=[...])
    return response
```

```typescript
import { Tracer, autoInstrument, traceCast } from 'tracecast'

const tracer = new Tracer({ exporters: [new JsonFileExporter('./traces.jsonl')] })
autoInstrument(tracer)

app.post('/chat', traceCast(async (req, res) => {
    const response = await openai.chat.completions.create({...})
    res.json({ reply: response.choices[0].message.content })
}))
```

### Instrumented Targets

| SDK/Framework | Python Patch Target | TS Patch Target | Detection |
|---|---|---|---|
| OpenAI | `openai.resources.chat.completions.Completions.create` | `OpenAI.chat.completions.create` (Proxy) | `import openai` |
| Anthropic | `anthropic.resources.messages.Messages.create` | `Anthropic.messages.create` (Proxy) | `import anthropic` |
| Google Gemini | `google.generativeai.GenerativeModel.generate_content` | `@google/generative-ai` (Proxy) | `import google.generativeai` |
| LangChain | Global callback handler registration | Global callback handler registration | `import langchain_core` |
| LlamaIndex | Event dispatcher handler registration | N/A (Python only) | `import llama_index` |
| CrewAI | Patch `Crew.kickoff()` for token usage capture | N/A (Python only) | `import crewai` |

### Architecture

```
tracecast/
  instrument.py              # auto_instrument() entry point
  instrumentors/
    __init__.py
    base.py                  # BaseInstrumentor interface
    openai_inst.py
    anthropic_inst.py
    gemini_inst.py
    langchain_inst.py
    llamaindex_inst.py
    crewai_inst.py
```

Each instrumentor:
- Lazy-imports the SDK (skip if not installed)
- Saves original function reference
- Patches with wrapper that checks `Tracer.current()` for active trace
- If no active trace, calls original directly (zero overhead)
- If active trace, creates Span, captures tokens/cost, appends to trace
- Has `unpatch()` for cleanup/testing

```python
class BaseInstrumentor:
    def patch(self) -> None: ...
    def unpatch(self) -> None: ...
    def is_patched(self) -> bool: ...
```

### Key Behavior

- `auto_instrument()` is idempotent (safe to call multiple times)
- Patches are global (module-level), but only capture when `Tracer.current()` returns active trace
- Outside `@trace_cast` context, all LLM calls behave normally with zero overhead
- `auto_instrument(tracer)` calls `set_default_tracer(tracer)` internally

---

## 2. Dashboard (React + Vite)

### Package Structure

```
packages/tracecast-dashboard/
  package.json              # vite + react + recharts + typescript
  vite.config.ts
  tsconfig.json
  src/
    main.tsx
    App.tsx
    pages/
      Overview.tsx          # stat cards + charts
      Traces.tsx            # trace list + filters + pagination
      TraceDetail.tsx       # spans waterfall, input/output
      Models.tsx            # cost/tokens per model
      Sessions.tsx          # traces grouped by session_id
      Projects.tsx          # traces grouped by project_id
    components/
      Layout.tsx            # sidebar nav + header + dark theme
      StatCard.tsx
      CostChart.tsx
      TokenChart.tsx
      SpanTimeline.tsx      # waterfall view of spans
      TraceTable.tsx
      Pagination.tsx
      Filters.tsx
      SessionCard.tsx
      ProjectCard.tsx
    hooks/
      useApi.ts             # fetch wrapper, relative base URL
      useMetrics.ts
      useTraces.ts
    styles/
      globals.css           # dark theme (current color scheme)
  dist/                     # vite build output
```

### Pages

**Overview** (5 pages total):
1. **Overview** — 6 stat cards (total traces, total cost, avg latency, cache hit rate, tokens in, tokens out) + 3 charts (cost over time line, cost by model donut, cost by project bar)
2. **Traces** — Sortable table with filters (project_id, user_id, date range). Click row opens TraceDetail modal/page with span waterfall view showing input/output per span
3. **Models** — Table (model, trace count, total tokens, total cost, avg latency) + bar chart of cost per model
4. **Sessions** — Groups traces by `session_id`. Shows session timeline, total cost, total tokens. Useful for "how much did conversation X cost"
5. **Projects** — Groups by `project_id`. Total cost, traces, tokens per project. Cost trend over time per project

### Build Pipeline

```bash
cd packages/tracecast-dashboard
npm run build                  # vite build → dist/

# Copy script:
npm run copy:py                # cp dist/* → packages/tracecast-py/tracecast/dashboard/static/
npm run copy:ts                # cp dist/* → packages/tracecast-ts/src/dashboard/static/
```

Build output committed to repo. No build step for end users.

### Theme

Dark theme matching current design:
- `--bg: #0f1117`
- `--surface: #1a1d27`
- `--border: #2a2d37`
- `--text: #e1e4ed`
- `--accent: #6366f1`

---

## 3. Backend API

### Existing Endpoints (unchanged)

```
GET /api/traces                     # paginated trace list
GET /api/traces/{trace_id}          # full trace with spans
GET /api/metrics                    # aggregated metrics
GET /api/health                     # status check
```

### New Endpoints

```
GET /api/sessions                   # list sessions with aggregates
    Response: { sessions: [{ session_id, trace_count, total_cost, total_tokens, first_trace_at, last_trace_at }], total }
    Query params: page, page_size, sort_by, order

GET /api/sessions/{session_id}      # traces in a session
    Response: { session_id, traces: [...], total_cost, total_tokens }

GET /api/projects                   # list projects with aggregates
    Response: { projects: [{ project_id, trace_count, total_cost, total_tokens, first_trace_at, last_trace_at }], total }
    Query params: page, page_size, sort_by, order

GET /api/projects/{project_id}      # project detail + traces
    Response: { project_id, traces: [...], total_cost, total_tokens, cost_trend: [...] }
```

### Implementation

Added to:
- `packages/tracecast-py/tracecast/dashboard/router.py` (FastAPI)
- `packages/tracecast-py/tracecast/dashboard/blueprint.py` (Flask)
- `packages/tracecast-ts/src/dashboard/router.ts` (Express)

Aggregation logic in `aggregator.py` / `aggregator.ts`:
- `compute_sessions(traces)` — groups by session_id, returns summaries
- `compute_projects(traces)` — groups by project_id, returns summaries

### TraceReader — Enhanced

```python
class TraceReader:
    def get_traces(self) -> list[Trace]
    def get_trace(self, trace_id: str) -> Trace | None
    def get_sessions(self) -> list[SessionSummary]         # NEW
    def get_session(self, session_id: str) -> list[Trace]  # NEW
    def get_projects(self) -> list[ProjectSummary]         # NEW
    def get_project(self, project_id: str) -> list[Trace]  # NEW
```

For Mongo/Postgres: native aggregation queries.
For JsonFile/Dict: load all, group in Python/JS.

---

## 4. Storage & Persistence

### DictExporter (new, in-memory)

```python
class DictExporter(BaseExporter):
    """In-memory exporter. Data lost on restart."""
    def __init__(self, max_traces: int = 1000): ...
    def export(self, trace: Trace) -> None: ...
```

### Auto-fallback on mount()

```python
def mount(self, app, ...):
    if not self.exporters:
        self.exporters = [DictExporter()]
        warnings.warn(
            "TraceCast: No exporter configured. Using in-memory storage. "
            "Data will be lost on restart. Configure a persistent exporter "
            "(JsonFileExporter, MongoExporter, PostgresExporter) for production."
        )
    ...
```

### Exporter Hierarchy

| Exporter | Persistent | Query Capability | Best For |
|---|---|---|---|
| MongoExporter | Yes | Full (aggregation pipeline) | Production |
| PostgresExporter | Yes | Full (SQL queries) | Production |
| JsonFileExporter | Yes | In-memory scan | Dev / small scale |
| DictExporter | No | In-memory scan | Dev / testing |

---

## 5. Static File Serving

Vite build generates hashed assets (`assets/index-abc123.js`). Router must serve:

```
GET /tracecast/                     # index.html
GET /tracecast/assets/{path}        # JS/CSS bundles
```

Python (FastAPI):
```python
@router.get("/assets/{path:path}")
async def static_assets(path: str):
    fp = STATIC_DIR / "assets" / path
    if not fp.exists():
        raise HTTPException(404)
    return Response(content=fp.read_bytes(), media_type=_mime(path))
```

Fallback: all non-API routes serve `index.html` (SPA client-side routing).

---

## 6. Package Changes

### Python pyproject.toml

```toml
[project.optional-dependencies]
dashboard = ["fastapi>=0.100.0", "uvicorn>=0.20"]
all = ["fastapi>=0.100.0", "uvicorn>=0.20", "pymongo>=4.0", "psycopg2-binary>=2.9"]
```

### TypeScript package.json

```json
{
  "peerDependencies": {
    "express": ">=4.0.0"
  },
  "peerDependenciesMeta": {
    "express": { "optional": true }
  }
}
```

### Exports

Python `__init__.py` adds:
```python
from .instrument import auto_instrument
from .exporters.dict_exporter import DictExporter
```

TypeScript `index.ts` adds:
```typescript
export { autoInstrument } from './instrument'
export { DictExporter } from './exporters/dictExporter'
```

---

## 7. Implementation Sequence

1. **DictExporter** — simple in-memory exporter
2. **Instrumentors** — base + openai + anthropic + gemini + langchain + llamaindex + crewai
3. **`auto_instrument()`** — entry point, registers all instrumentors
4. **Backend API** — new sessions/projects endpoints in aggregator + router
5. **React dashboard** — scaffold Vite + React, implement 5 pages
6. **Build pipeline** — vite build + copy script
7. **Static serving** — update routers to serve Vite output
8. **Mount auto-fallback** — DictExporter warning
9. **TypeScript port** — instrumentors + dashboard
10. **Tests** — instrumentors (mock SDKs), dashboard API, React components

---

## 8. Non-Goals (v0.2.0)

- No distributed tracing / cross-service propagation
- No real-time WebSocket updates (poll every 30s)
- No user accounts / multi-tenant auth
- No trace deletion via UI
- No alerts / budget thresholds
- No streaming support (token-by-token)

---

## 9. Testing Plan

```
tests/
  test_instrumentors/
    test_openai_inst.py           # mock openai, verify spans captured
    test_anthropic_inst.py
    test_gemini_inst.py
    test_langchain_inst.py
    test_llamaindex_inst.py
    test_crewai_inst.py
    test_auto_instrument.py       # integration: all instrumentors together
  test_dict_exporter.py
  test_dashboard_sessions.py      # new API endpoints
  test_dashboard_projects.py
```

TypeScript:
```
tests/
  instrumentors/
    openai.test.ts
    anthropic.test.ts
    gemini.test.ts
    langchain.test.ts
  dictExporter.test.ts
  dashboard/
    sessions.test.ts
    projects.test.ts
```
