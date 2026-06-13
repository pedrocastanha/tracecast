# TraceCast

> **SDK de observabilidade para LLMs** — rastreie tokens, custo, latência, tool calls e o **grafo completo** de agentes em qualquer framework de IA. Self-hosted, framework-agnostic, Python.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://pypi.org/project/tracecast/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-242%20passing-brightgreen)](#testes)

---

## O que é

TraceCast captura **automaticamente** cada interação dentro de uma request de IA — nós, arestas,
guardrails, chamadas LLM e tools — e exporta para onde você quiser: MongoDB, PostgreSQL, arquivo JSONL,
ou qualquer destino customizado. Um dashboard self-hosted permite visualizar o **grafo percorrido**,
filtrar traces e inspecionar cada etapa.

- **Captura o fluxo inteiro** — hierarquia pai→filho de spans e arestas (`from → to`) reconstroem o grafo.
- **Zero configuração** para LangChain/LangGraph — um callback (ou `auto_instrument()`) resolve tudo.
- **Dados confiáveis** — tokens (incl. streaming e cache), custo, latência e status por etapa.
- **Save resiliente** — falhas de export são logadas e expostas por hook, nunca silenciosas.
- **Dashboard separável** — rode embutido no app ou standalone numa VM lendo o storage remoto.
- **Zero dependências core** — instale só o que for usar.

---

## Instalação

```bash
# Core (sem dependências)
pip install tracecast

# Extras
pip install "tracecast[mongo]"      # MongoExporter
pip install "tracecast[postgres]"   # PostgresExporter
pip install "tracecast[langchain]"  # LangChain / LangGraph
pip install "tracecast[dashboard]"  # FastAPI + uvicorn (dashboard/servidor)
pip install "tracecast[all]"        # tudo
```

---

## Início rápido

### LangGraph / LangChain (captura automática)

```python
from tracecast import Tracer, auto_instrument
from tracecast.exporters.mongo import MongoExporter

tracer = Tracer(exporters=[MongoExporter("mongodb://localhost:27017", db="myapp")], logging=True)
auto_instrument(tracer)  # registra o callback global do LangChain

# decore a função/rota que inicia a request
from tracecast import trace_cast

@trace_cast(project_id="suporte", user_id="u1")
def handle(message: str):
    return app.invoke({"messages": [message]})  # seu StateGraph compilado
```

Cada nó do grafo vira um span com pai correto; arestas percorridas são derivadas automaticamente.
Tokens, custo, latência e status são preenchidos por chamada e agregados no trace.

### Span manual

```python
from tracecast import Tracer, Span, SpanType, calculate_cost
from tracecast.exporters import JsonFileExporter
from datetime import datetime, timezone
import uuid

tracer = Tracer(exporters=[JsonFileExporter("./traces.jsonl")])

with tracer.trace("minha_run", user_id="usr_1") as trace:
    span = Span(
        span_id=str(uuid.uuid4()),
        type=SpanType.LLM,
        name="llm:gpt-4o",
        model="gpt-4o",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        tokens_in=120,
        tokens_out=80,
    )
    span.cost_usd = calculate_cost("gpt-4o", span.tokens_in, span.tokens_out)
    trace.spans.append(span)
```

---

## Decorators

| Decorator | Uso |
|-----------|-----|
| `@trace_cast(...)` | Abre um **trace** (request inteira). Coloque na rota/handler de entrada. Sync e async. |
| `@trace_span(name=..., type=...)` | Cria um **span filho** para qualquer função (guardrails, validações, etapas). Captura input/output/latência/status. Aninha sob o span ativo. |

```python
from tracecast import trace_cast, trace_span
from tracecast.models.span import SpanType

@trace_span(name="guardrail_pii", type=SpanType.TOOL)
def check_pii(text: str) -> str:
    ...
    return cleaned

@trace_cast(project_id="suporte")
async def handle(req):
    safe = check_pii(req.text)     # vira span filho com input/output
    return await agent.ainvoke(safe)
```

---

## Frameworks

### OpenAI / Anthropic (auto-instrument, inclui streaming)

```python
import openai
from tracecast import Tracer, auto_instrument

tracer = Tracer(exporters=[...])
auto_instrument(tracer)            # faz patch em openai/anthropic/gemini

client = openai.OpenAI()
with tracer.trace("openai-run"):
    # não-streaming e streaming são capturados (tokens via include_usage)
    stream = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": "Olá!"}], stream=True,
    )
    for chunk in stream:
        ...
```

Alternativa explícita sem patch global: `wrap_openai(client)` / `wrap_anthropic(client)`.

### CrewAI / LlamaIndex

`auto_instrument()` registra os instrumentors disponíveis. Veja `real_examples/` para setups completos.

---

## Propagação de contexto em threads

ContextVars propagam para tasks asyncio filhas, mas **não** para threads (`run_in_executor`/ThreadPool).
Use `bind_context` para capturar o trace ativo e rodar a função no worker:

```python
from tracecast import bind_context

# ThreadPoolExecutor
pool.submit(bind_context(node_fn, state))

# asyncio executor
await loop.run_in_executor(None, bind_context(node_fn, state))
```

---

## Exporters

Todos aceitam `include_fields` / `exclude_fields`. Mongo e Postgres expõem `query/get/count` usados pelo
dashboard para **filtrar no banco** (data, projeto, usuário, sessão) — sem carregar tudo em memória.

```python
from tracecast.exporters import JsonFileExporter, DictExporter
from tracecast.exporters.mongo import MongoExporter
from tracecast.exporters.postgres import PostgresExporter

JsonFileExporter("./traces.jsonl", exclude_fields={"spans"})
MongoExporter("mongodb://localhost:27017", db="myapp", collection="traces")   # upsert por trace_id
PostgresExporter("postgresql://user:pass@host:5432/db", table="traces")        # ON CONFLICT upsert
DictExporter(on_trace=lambda d: fila.put(d))
```

Custom:

```python
from tracecast.exporters.base import BaseExporter

class WebhookExporter(BaseExporter):
    def __init__(self, url): self.url = url
    def export(self, trace) -> None:
        import httpx; httpx.post(self.url, json=trace.to_dict())
```

---

## Dashboard

O dashboard (SPA React) é servido pelo backend Python. Duas formas de uso:

### 1. Embutido no app

```python
from fastapi import FastAPI
app = FastAPI()
tracer.mount(app, prefix="/tracecast")   # dashboard em /tracecast, API em /tracecast/api
```

### 2. Standalone numa VM (lê o storage remoto)

O servidor não importa o app de produção — só aponta para o mesmo banco.

```bash
pip install "tracecast[dashboard,mongo]"

export TRACECAST_STORE="mongodb://prod-host:27017"   # postgresql:// ou file:// também
export TRACECAST_DB="myapp"
export TRACECAST_PORT=7777
export TRACECAST_AUTH="admin:senha"                  # basic auth opcional
export TRACECAST_CORS="https://meu-front.com"        # opcional

tracecast-server
```

Variáveis: `TRACECAST_STORE` (obrigatória), `TRACECAST_HOST`, `TRACECAST_PORT`, `TRACECAST_PREFIX`,
`TRACECAST_DB`, `TRACECAST_COLLECTION`, `TRACECAST_TABLE`, `TRACECAST_AUTH`, `TRACECAST_CORS`,
`TRACECAST_MAX_TRACES`.

**Recursos:** filtros por data/projeto/usuário/sessão (server-side), lista paginada, e visualização do
**grafo DAG** percorrido (nós + arestas) com detalhe de input/output/tokens/custo/latência/status ao
clicar em cada etapa.

**API REST** (`{prefix}/api`): `/traces`, `/traces/{id}`, `/traces/{id}/graph`, `/metrics`,
`/sessions`, `/projects`, `/health`.

---

## Logging integrado

```python
tracer = Tracer(exporters=[...], logging=True, log_prefix="meu_agente")
```

```
[meu_agente] Trace started
[meu_agente] LLM end → gpt-4o | tokens: 310 in / 95 out | $0.0019 | 2.10s
[meu_agente] Trace finished → total: 405 tokens | $0.0019 | 3.40s | tools: search_web×1
```

Usa `logging.getLogger("tracecast")`. Configure com `logging.basicConfig` ou qualquer handler.

---

## Modelo de dados

`to_dict()` inclui `schema_version: 2`. Leitura é retrocompatível com v1.

### Trace
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `trace_id` | `str` | UUID da execução. |
| `name`, `user_id`, `session_id`, `project_id` | `str?` | Identificadores. |
| `model` | `str?` | Modelo que mais consumiu tokens. |
| `total_tokens_in/out/_in_cached/total_tokens` | `int` | Agregados dos spans. |
| `cost_usd` | `float` | Custo total. |
| `latency_ms` | `int?` | Wall-clock da request. |
| `tools_used` | `dict` | `{tool: count}`. |
| `spans` | `list[Span]` | Spans da request. |
| `edges` | `list` | Arestas percorridas: `{from, to, parent_span_id, conditional}`. |
| `metadata`, `started_at`, `finished_at` | | |

### Span
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `span_id` | `str` | UUID. |
| `parent_span_id` | `str?` | Pai na árvore (None = raiz). |
| `type` | `Enum` | `LLM` / `TOOL` / `AGENT`. |
| `name` | `str` | Nome descritivo. |
| `status` | `Enum` | `ok` / `error`. |
| `error` | `str?` | Mensagem quando `status == error`. |
| `model`, `tokens_in/out/_in_cached`, `cost_usd`, `latency_ms` | | Métricas. |
| `input`, `output`, `metadata` | | Conteúdo da etapa. |
| `started_at`, `finished_at` | `ISO8601` | |

---

## Resiliência

1. **Exceção no código do usuário** → trace sempre finalizado e exportado via `finally`.
2. **Exceção no exporter** → logada em nível `ERROR` e exposta via hook `on_export_error`; **nunca**
   silenciosa e nunca interrompe o app. Outros exporters continuam.
   ```python
   Tracer(exporters=[...], on_export_error=lambda exc, trace, exp: alertar(exc))
   ```
3. **Export assíncrono não-bloqueante** — `aexport` roda fora do event loop (offload em thread).
4. **Spans com erro** marcados com `status="error"` + `error` (first-class, não enterrado em metadata).
5. **Multi-tenant / concorrência** — cada coroutine/thread isola seu próprio trace via `ContextVar`.

---

## Testes

```bash
cd packages/tracecast-py
pip install -e ".[all]" pytest
python -m pytest tests/ -q
# → 242 passed
```

---

## Licença

MIT © Pedro Castanheira Costa
