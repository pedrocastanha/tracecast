# TraceCast — Documentação Completa

> SDK de observabilidade para LLMs — Python · TypeScript · Framework-Agnostic

---

## 1. O Que a Lib Faz

TraceCast é um SDK que **rastreia interações com LLMs** — tokens consumidos, custo em USD, latência, chamadas de ferramentas — e **exporta esses dados** para o destino que você escolher. Zero vendor lock-in.

### Capacidades Principais

| Feature | Descrição |
|---------|-----------|
| **Token tracking** | Contabiliza `tokens_in` / `tokens_out` por span e agrega no trace |
| **Cálculo de custo** | Tabela de preços built-in para 20+ modelos (OpenAI, Anthropic, Google, Groq, Ollama) |
| **Latência** | Mede `latency_ms` por span e por trace automaticamente |
| **Tool tracking** | Registra quais ferramentas foram usadas e quantas vezes (`tools_used`) |
| **Tagging** | Suporta `user_id`, `session_id`, `project_id` e `metadata` livre |
| **Exporters plugáveis** | MongoDB, PostgreSQL, JSON file, DictExporter (callback/lista), ou custom |
| **Seleção de campos** | Cada exporter aceita `include_fields` / `exclude_fields` para filtrar o que é salvo |
| **Logging integrado** | `logging=True` no `Tracer` emite linhas estruturadas de LLM/Tool/Chain sem nenhum código extra |
| **Isolamento** | Traces são isolados via `ContextVar` (Python) / `AsyncLocalStorage` (TS) — safe para async/multi-tenant |

---

## 2. Arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│  Seu código (SDK direto, LangChain, LangGraph, CrewAI, etc) │
└──────────────────┬──────────────────┬────────────────────────┘
                   │                  │
           ┌───────▼───────┐   ┌──────▼──────────┐
           │    Tracer      │   │ TraceCastCallback│  (integração LangChain)
           │ (context mgr)  │   │ (callback handler)│
           └───────┬────────┘   └──────┬──────────┘
                   │                   │
                   │ spans acumulados  │
                   ▼                   ▼
           ┌───────────────────────────────┐
           │         Trace (modelo)        │
           │  trace_id, name, spans[],     │
           │  total_tokens, cost_usd, ...  │
           └───────────────┬───────────────┘
                           │ _finalize()
                           ▼
           ┌───────────────────────────────┐
           │     Exporters (plugáveis)     │
           │  MongoDB │ Postgres │ JSON    │
           └───────────────────────────────┘
```

### Modelos de Dados

**Span** — uma operação individual (chamada LLM, tool call, chain/agent node):
- `span_id`, `type` (LLM | TOOL | AGENT), `name`, `model`
- `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`
- `started_at`, `finished_at`, `metadata`

**Trace** — agrupa múltiplos spans numa execução:
- `trace_id`, `name`, `user_id`, `session_id`, `project_id`
- `total_tokens_in`, `total_tokens_out`, `total_tokens`, `cost_usd`
- `latency_ms`, `model` (modelo dominante por volume de tokens)
- `tools_used` (mapa nome → contagem), `spans[]`, `metadata`

---

## 3. Comportamento por Framework

### 3.1 SDK Direto (OpenAI, Anthropic, qualquer SDK)

**Modo**: Spans manuais — você cria o `Span` e adiciona ao `trace.spans`.

#### Python
```python
from tracecast import Tracer, Span, SpanType, calculate_cost
from datetime import datetime, timezone
import uuid

tracer = Tracer(exporters=[...])

with tracer.trace("meu-agente", user_id="usr_1") as trace:
    started = datetime.now(timezone.utc)
    # response = client.chat.completions.create(model="gpt-4o", ...)
    finished = datetime.now(timezone.utc)

    span = Span(
        span_id=str(uuid.uuid4()),
        type=SpanType.LLM,
        name="llm:gpt-4o",
        model="gpt-4o",
        started_at=started,
        finished_at=finished,
        tokens_in=response.usage.prompt_tokens,
        tokens_out=response.usage.completion_tokens,
    )
    span.cost_usd = calculate_cost("gpt-4o", span.tokens_in, span.tokens_out)
    trace.spans.append(span)

# Ao sair do `with`, o trace é finalizado e exportado automaticamente
```

#### TypeScript
```typescript
import { Tracer, calculateCost, SpanType, Span } from "tracecast";
import { randomUUID } from "crypto";

const tracer = new Tracer({ exporters: [...] });

const result = await tracer.trace("meu-agente", async (trace) => {
  const span: Span = {
    spanId: randomUUID(),
    type: SpanType.LLM,
    name: "llm:gpt-4o",
    model: "gpt-4o",
    startedAt: new Date(),
    finishedAt: new Date(),
    tokensIn: response.usage.prompt_tokens,
    tokensOut: response.usage.completion_tokens,
    costUsd: calculateCost("gpt-4o", tokensIn, tokensOut),
  };
  trace.spans.push(span);
  return response;
}, { userId: "usr_1" });
```

**Comportamento**: Funciona com **qualquer SDK** (OpenAI, Anthropic, Google AI, Groq, etc). Você é responsável por extrair tokens da resposta e criar os Spans. O `_finalize()` agrega tudo ao fechar o trace.

---

### 3.2 LangChain / LangChain.js

**Modo**: Automático via `TraceCastCallback` — intercepta eventos `on_llm_start`, `on_llm_end`, `on_tool_start/end`, `on_chain_start/end`.

#### Python
```python
from tracecast import Tracer
from tracecast.integrations.langchain import TraceCastCallback

tracer = Tracer(exporters=[...])
callback = TraceCastCallback(tracer=tracer)

with tracer.trace("meu-agente", user_id="u1") as trace:
    result = chain.invoke({"input": "Olá"}, config={"callbacks": [callback]})
```

#### TypeScript
```typescript
import { Tracer } from "tracecast";
import { TraceCastCallback } from "tracecast/integrations/langchain";

const tracer = new Tracer({ exporters: [...] });
const cb = new TraceCastCallback(tracer);

await tracer.trace("meu-agente", async () => {
  await chain.invoke({ input: "Olá" }, { callbacks: [cb] });
}, { userId: "u1" });
```

**O que é capturado automaticamente**:
- **Spans LLM**: modelo, tokens_in/out, cost_usd (via tabela de preços built-in)
- **Spans TOOL**: nome da ferramenta, duração
- **Spans AGENT/CHAIN**: nós do grafo, duração

**Comportamento em erro**: Se o LLM ou tool lançar erro, o span é fechado com `metadata._error` e adicionado ao trace. O trace é **sempre exportado** (via `finally`).

> **⚠️ Atenção — LangChain moderno usa streaming por padrão em `AgentExecutor`**
> A partir do LangChain 0.3+, o `AgentExecutor` transmite as respostas internamente, e os chunks de streaming não carregam informação de token usage. Para garantir que tokens sejam rastreados corretamente, configure o LLM com `stream_usage=True` (OpenAI) ou equivalente do seu provider:
>
> ```python
> # Python — necessário para rastrear tokens em AgentExecutor
> llm = ChatOpenAI(model="gpt-4o-mini", stream_usage=True)
> ```
> ```typescript
> // TypeScript — mesmo comportamento
> const llm = new ChatOpenAI({ model: "gpt-4o-mini", streamUsage: true });
> ```
> Para chains simples (sem `AgentExecutor`), o streaming não é usado e os tokens são capturados normalmente.

---

### 3.3 LangGraph / LangGraph.js

**Modo**: Mesmo `TraceCastCallback` — LangGraph dispara `on_chain_start/end` para cada nó do `StateGraph`.

```python
# Python — funciona igual
with tracer.trace("meu-grafo"):
    graph.invoke({"messages": []}, config={"callbacks": [callback]})
```

**Comportamento**: Cada nó do grafo gera um span `AGENT` (`chain:NomeDo Nó`). Se um nó contiver chamada LLM, gera spans `AGENT` + `LLM` aninhados. Spans são isolados por `ContextVar`/`AsyncLocalStorage`.

---

### 3.4 CrewAI (Python)

**Modo**: Spans manuais — CrewAI 1.x usa seu próprio layer de LLM, não propaga LangChain callbacks.

```python
with tracer.trace("crew-run", project_id="proj-crew") as trace:
    crew = Crew(agents=[agent], tasks=[task])

    started = datetime.now(timezone.utc)
    result = crew.kickoff()
    finished = datetime.now(timezone.utc)

    # CrewAI 1.x expõe token_usage no objeto de resultado.
    # Extraímos se disponível; caso contrário os tokens ficam zerados (sem custo falso).
    usage = getattr(result, "token_usage", None)
    tokens_in  = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0

    span = Span(
        span_id=str(uuid.uuid4()),
        type=SpanType.AGENT,
        name="crewai_sequential",
        model="gpt-4o-mini",
        started_at=started,
        finished_at=finished,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    span.cost_usd = calculate_cost("gpt-4o-mini", tokens_in, tokens_out)
    trace.spans.append(span)
```

---

### 3.5 LlamaIndex (Python)

**Modo**: Spans manuais via `LlamaDebugHandler` para interceptar eventos `CBEventType.LLM` e `CBEventType.RETRIEVE`.

```python
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler, CBEventType

dbh = LlamaDebugHandler()
# Passe o callback_manager ao criar o índice/LLM
index = VectorStoreIndex.from_documents(docs, callback_manager=CallbackManager([dbh]))

with tracer.trace("rag-query") as trace:
    index.as_query_engine().query("Minha pergunta")

    for event in dbh.get_events():
        if event.event_type == CBEventType.LLM:
            p = event.payload or {}
            model = p.get("model", "unknown")
            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llm:{model}",
                model=model,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                tokens_in=p.get("formatted_prompt_tokens_count", 0),
                tokens_out=p.get("completion_tokens_count", 0),
            )
            span.cost_usd = calculate_cost(model, span.tokens_in, span.tokens_out)
            trace.spans.append(span)
        elif event.event_type == CBEventType.RETRIEVE:
            trace.spans.append(Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.TOOL,
                name="vector_retrieval",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ))
```

> **⚠️ Limitação**: O `LlamaDebugHandler` na versão atual do LlamaIndex não expõe token usage via `CBEventType.LLM` — os campos `formatted_prompt_tokens_count` e `completion_tokens_count` retornam 0. O rastreamento de **latência, estrutura do trace e retrieval** funciona normalmente. Para token tracking granular com LlamaIndex, considere usar o `OpenInferenceCallbackHandler` (OpenTelemetry) diretamente.

---

### 3.6 Ollama (modelos locais)

**Comportamento**: Modelos `ollama/*` têm custo $0.00 na tabela de preços. O prefix matching `ollama/*` captura qualquer modelo (`ollama/llama3`, `ollama/mistral`, etc).

---

## 4. Exporters — Comportamento para Salvar no Banco

### 4.1 JsonFileExporter

| Aspecto | Comportamento |
|---------|---------------|
| **Formato** | JSONL (1 JSON por linha) — append-only |
| **Diretório** | Cria diretórios pai automaticamente (`mkdir -p`) |
| **Async (Python)** | `aexport()` usa `asyncio.to_thread()` — non-blocking |
| **Async (TypeScript)** | `export()` já é `async` via `fs/promises` |
| **Concorrência** | Seguro para uso sequencial; para escrita paralela intensiva, considere MongoDB |
| **Seleção de campos** | `include_fields` / `exclude_fields` — filtra quais campos são gravados por linha |

```python
# Python — com seleção de campos
from tracecast.exporters.json_file import JsonFileExporter
exporter = JsonFileExporter(
    path="./logs/traces.jsonl",
    exclude_fields={"spans"},          # omite spans (verboso)
)
```

```typescript
// TypeScript — com seleção de campos
import { JsonFileExporter } from "tracecast/exporters/jsonFile";
const exporter = new JsonFileExporter("./traces.jsonl", {
  excludeFields: ["spans"],
});
```

### 4.2 MongoExporter

| Aspecto | Comportamento |
|---------|---------------|
| **Operação** | `insert_one()` / `insertOne()` — cada trace é um documento |
| **Campo extra** | Adiciona `exported_at` (datetime UTC) |
| **Conexão (Python)** | `pymongo.MongoClient` — criada no construtor |
| **Conexão (TypeScript)** | Lazy — conecta na primeira exportação via `import("mongodb")` dinâmico |
| **Dependência** | Python: `pip install pymongo` / TS: `npm install mongodb` |
| **Schema** | Sem schema fixo — documento segue o schema do `to_dict()` / object spread |
| **Seleção de campos** | `include_fields` / `exclude_fields` — filtra quais campos vão para o documento |

```python
# Python — inclui apenas campos essenciais
from tracecast.exporters.mongo import MongoExporter
exporter = MongoExporter(
    uri="mongodb://localhost:27017",
    db="myapp",
    collection="traces",
    include_fields={"trace_id", "cost_usd", "total_tokens", "model", "latency_ms"},
)
```

```typescript
// TypeScript — exclui spans (economiza espaço)
import { MongoExporter } from "tracecast/exporters/mongo";
const exporter = new MongoExporter("mongodb://localhost:27017", "myapp", "traces", {
  excludeFields: ["spans"],
});
// Lembre de chamar await exporter.close() ao encerrar
```

### 4.3 PostgresExporter

| Aspecto | Comportamento |
|---------|---------------|
| **Tabela** | Criada automaticamente via `CREATE TABLE IF NOT EXISTS` |
| **Operação** | `UPSERT` — `INSERT ... ON CONFLICT (trace_id) DO UPDATE` |
| **Campos estruturados** | `tools_used`, `spans`, `metadata` como `JSONB` |
| **Campo extra** | `exported_at` (TIMESTAMPTZ) |
| **Idempotência** | Re-exportar o mesmo `trace_id` atualiza os dados |
| **Conexão (Python)** | `psycopg2` com autocommit |
| **Conexão (TypeScript)** | `pg.Pool` com lazy init via `import("pg")` dinâmico |
| **Seleção de campos** | `include_fields` / `exclude_fields` — o schema da tabela é gerado dinamicamente com as colunas escolhidas |

> **Nota**: `trace_id`, `started_at` e `exported_at` são sempre incluídos, independente do filtro (necessários para o UPSERT funcionar).

```python
# Python — tabela com apenas colunas de custo e tokens
from tracecast.exporters.postgres import PostgresExporter
with PostgresExporter(
    dsn="postgresql://user:pass@host:5432/db",
    table="traces",
    include_fields=["trace_id", "name", "model", "cost_usd", "total_tokens", "latency_ms"]
) as exporter:
    tracer = Tracer(exporters=[exporter])
```

```typescript
// TypeScript — excluindo spans e metadata
import { PostgresExporter } from "tracecast/exporters/postgres";
const exporter = new PostgresExporter("postgresql://user:pass@host:5432/db", "traces", {
  excludeFields: ["spans", "metadata"],
});
// Lembre de chamar await exporter.close() ao encerrar
```

### 4.4 DictExporter

Captura traces como dicts Python / objetos JS — sem arquivo, sem banco. Útil para testes, pipelines customizados, filas de mensagem, etc.

```python
# Python — coleta em lista (default)
from tracecast.exporters import DictExporter

exporter = DictExporter()
tracer = Tracer(exporters=[exporter])
with tracer.trace("run"):
    ...
print(exporter.traces)  # lista de dicts

# Python — com callback
exporter = DictExporter(
    on_trace=lambda d: my_queue.put(d),
    include_fields={"trace_id", "cost_usd", "total_tokens"},
)
```

```typescript
// TypeScript — coleta em array (default)
import { DictExporter } from "tracecast";

const exporter = new DictExporter();
const tracer = new Tracer({ exporters: [exporter] });
await tracer.trace("run", async () => { ... });
console.log(exporter.traces);  // Record<string, unknown>[]

// TypeScript — com callback
const exporter = new DictExporter({
  onTrace: (d) => myQueue.push(d),
  includeFields: ["traceId", "costUsd", "totalTokens"],
});
```

### 4.5 Custom Exporter

```python
# Python — implemente BaseExporter
from tracecast.exporters.base import BaseExporter

class WebhookExporter(BaseExporter):
    def __init__(self, url: str):
        self.url = url
    def export(self, trace) -> None:
        httpx.post(self.url, json=trace.to_dict())
```

```typescript
// TypeScript — implemente BaseExporter interface
import { BaseExporter } from "tracecast/exporters/base";
import { Trace } from "tracecast";

class WebhookExporter implements BaseExporter {
  constructor(private url: string) {}
  async export(trace: Trace): Promise<void> {
    await fetch(this.url, { method: "POST", body: JSON.stringify(trace) });
  }
}
```

---

## 5. Tabela de Preços Built-in

| Modelo | Input ($/1K tokens) | Output ($/1K tokens) |
|--------|---------------------|----------------------|
| `gpt-5` | 0.00125 | 0.01000 |
| `gpt-5.4` | 0.00250 | 0.01500 |
| `gpt-4o` | 0.00250 | 0.01000 |
| `gpt-4o-mini` | 0.00015 | 0.00060 |
| `gpt-4-turbo` | 0.01000 | 0.03000 |
| `gpt-4.1` | 0.00200 | 0.00800 |
| `gpt-4.1-mini` | 0.00040 | 0.00160 |
| `o3` | 0.00200 | 0.00800 |
| `o4-mini` | 0.00110 | 0.00440 |
| `claude-opus-4-6` | 0.00500 | 0.02500 |
| `claude-sonnet-4-6` | 0.00300 | 0.01500 |
| `claude-haiku-4-5` | 0.00100 | 0.00500 |
| `claude-opus-4` (legacy) | 0.01500 | 0.07500 |
| `claude-sonnet-4` | 0.00300 | 0.01500 |
| `claude-haiku-3-5` | 0.00080 | 0.00400 |
| `gemini-3.1-pro` | 0.00200 | 0.01200 |
| `gemini-3-flash` | 0.00050 | 0.00300 |
| `gemini-2.5-flash` | 0.00030 | 0.00250 |
| `gemini-2.5-pro` | 0.00125 | 0.01000 |
| `gemini-2.0-flash` | 0.00010 | 0.00040 |
| `llama-3.3-70b` | 0.00059 | 0.00079 |
| `llama-4-scout` | 0.00011 | 0.00034 |
| `llama-4-maverick` | 0.00020 | 0.00060 |
| `ollama/*` | 0.00000 | 0.00000 |

**Custom prices**: Use `custom_prices` (Python) / `customPrices` (TypeScript) para adicionar ou sobrescrever modelos. O merge é feito via spread — modelos built-in continuam funcionando.

---

## 6. Comportamentos Importantes

### Isolamento de Traces (Thread/Async Safety)

- **Python**: Usa `ContextVar` — cada thread/coroutine tem seu próprio trace ativo
- **TypeScript**: Usa `AsyncLocalStorage` — cada contexto async tem isolamento completo
- **Traces aninhados** (Python): Suportados — `ContextVar` mantém stack automático
- **Multi-tenant**: Seguro para múltiplos usuários simultâneos

### Resiliência a Erros

1. **Exceção no código do usuário**: O trace é **sempre finalizado e exportado** (via `finally`)
2. **Exceção no exporter**: É engolida com `warning` (Python) / `console.warn` (TS) — **nunca interrompe** o código do usuário
3. **`failOnExportError: true`** (TS only): Opção para propagar erros de exporter
4. **Span com erro**: Erros em LLM/Tool/Chain fecham o span com `metadata._error` e adiciona ao trace

### Finalize (`_finalize()`)

Chamada automaticamente ao fechar o trace. Agrega:
- `total_tokens_in` / `total_tokens_out` / `total_tokens` (soma de todos os spans)
- `cost_usd` (soma de todos os spans)
- `latency_ms` (diferença entre `started_at` e `finished_at` do trace)
- `model` (modelo do span LLM com maior volume total de tokens)
- `tools_used` (mapa de ferramentas → contagem)

---

## 6. Logging Integrado

Habilite com um único flag no `Tracer` — zero código extra. Cada evento LLM/Tool/Chain gera uma linha de log formatada e colapsada numa única linha.

### Configuração

```python
# Python
tracer = Tracer(
    exporters=[...],
    logging=True,            # habilita
    log_prefix="meu_agente" # opcional — default: usa o name de cada trace
)
```

```typescript
// TypeScript
const tracer = new Tracer({
  exporters: [...],
  logging: true,
  logPrefix: "meu_agente",  // opcional — default: usa o name de cada trace
  // logFn / warnFn: funções customizadas em vez de console.log / console.warn
});
```

### Saída esperada

```
[meu_agente] Trace started
[meu_agente] LLM started → gpt-4o
[meu_agente] Tool call → search_web | quem é o presidente...
[meu_agente] Tool end → search_web | 0.82s
[meu_agente] LLM end → gpt-4o | tokens: 310 in / 95 out | $0.0019 | 2.10s
[meu_agente] Trace finished → total: 405 tokens | $0.0019 | 3.40s | tools: search_web×1
```

### Comportamentos

| Aspecto | Detalhe |
|---------|---------|
| **Python logger** | `logging.getLogger("tracecast")` — nível `INFO`. Configure com `logging.basicConfig` ou qualquer handler existente. |
| **TypeScript logger** | `console.log` por padrão. Passe `logFn` / `warnFn` para redirecionar para seu logger favorito. |
| **Formato** | `[prefix] mensagem` — sempre uma única linha (newlines colapsados em espaços). |
| **Chain logging** | Apenas o nó raiz do grafo é logado (sem spam de sub-nós internos). |
| **Logging desabilitado** | `logging=False` (default) — zero overhead, nenhum código de log executado. |
| **Erros** | Emitidos via `logging.warning` (Python) / `warnFn` (TS) com prefixo `⚠`. |

---

## 8. Performance

### Python (128 testes, 6.34s)

- **Zero dependências core** — `dependencies = []` no `pyproject.toml`
- Exporters são opcionais: `pymongo`, `psycopg2`, `langchain-core`
- Usa `dataclass` (não Pydantic) — overhead mínimo de serialização
- `ContextVar` é nativo CPython — zero overhead de thread-safety
- `asyncio.to_thread()` para I/O non-blocking no `JsonFileExporter.aexport()`
- Cálculo de custo é O(1) lookup em dict + O(n) prefix match como fallback
- Logger é instanciado **somente se** `logging=True` — zero overhead quando desabilitado

### TypeScript (113 testes, 5.9s)

- `AsyncLocalStorage` (Node.js built-in) — zero dependência externa para isolamento
- Dynamic `import()` para MongoDB e PostgreSQL — **zero custo** se não usar esses exporters
- Interfaces (não classes abstratas) para exporters — sem overhead de herança
- `Map<string, Span>` para span stack no callback — O(1) lookup/insert/delete
- Todas as operações de I/O são `async/await` — compatível com event loop
- `logFn` / `warnFn` injetáveis — testabilidade sem mocking de `console`

### Características Comuns

- **Price table**: Objeto estático em memória — consulta O(1)
- **Prefix matching**: Fallback apenas para modelos não encontrados diretamente (ex: `ollama/llama3` → `ollama/*`)
- **Serialização**: `to_dict()` (Python) / object spread (TS) — nenhuma reflexão em runtime
- **Exporters independentes**: Falha em um exporter não afeta os outros (loop com try/catch individual)

---

## 9. Status dos Testes

| Suite | Testes | Tempo | Status |
|-------|--------|-------|--------|
| Python (pytest) | **128 passed** | 6.34s | ✅ Todos passam |
| TypeScript (Jest) | **113 passed** | 5.90s | ✅ Todos passam |

### Cobertura de Testes

#### Python (13 arquivos de teste)
- `test_tracer.py` — context manager sync/async, erros, isolamento, exporter resilience
- `test_cost_calculator.py` — 19 modelos parametrizados, custom prices, aliases, prefix match
- `test_span.py` — latency_ms, total_tokens, to_dict
- `test_trace.py` — finalize aggregation, tools_used, serialization
- `test_json_exporter.py` — JSONL escrita, criação de diretórios, async
- `test_mongo_exporter.py` — insert_one mockado
- `test_exporters_db.py` — MongoDB + PostgreSQL com mocks completos (UPSERT, ON CONFLICT, context manager)
- `test_token_counter.py` — extração de tokens OpenAI, Anthropic, LangChain, fallback
- `test_langchain_callback.py` — LLM/Tool/Chain spans, error handling, memory leak check
- `test_integration_langchain.py` — FakeListLLM, FakeChatModel, RunnableSequence, JSONL export
- `test_integration_frameworks.py` — OpenAI, Anthropic, LangChain, LangGraph, CrewAI, LlamaIndex
- `test_logging.py` — TraceCastLogger helper, Tracer logging options, TraceCastCallback integration

#### TypeScript (8 arquivos de teste)
- `tracer.test.ts` — trace callback, erros, finalize, addSpan, failOnExportError
- `costCalculator.test.ts` — mesmos 19 modelos, custom prices, aliases, getPriceTable
- `jsonFileExporter.test.ts` — escrita, diretórios, append, JSON válido
- `langchainCallback.test.ts` — handleLLM/Tool/Chain Start/End/Error, memory leak
- `exporters.test.ts` — MongoExporter + PostgresExporter com mocks, UPSERT, close
- `integration.test.ts` — FakeChatModel real, JsonFile, AsyncLocalStorage isolation
- `integration_frameworks.test.ts` — OpenAI, Anthropic, Groq, Gemini, LangGraph, multi-provider
- `logging.test.ts` — TraceCastLogger helper, Tracer logging options, TraceCastCallback integration

---

## 10. Guia de Publicação

### 10.1 Estrutura recomendada do repositório GitHub

```
lib-tracecast/                  ← raiz do monorepo
├── README.md                   ← README principal (visível no GitHub)
├── packages/
│   ├── tracecast-py/           ← pacote Python
│   │   ├── tracecast/          ← código-fonte
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── tracecast-ts/           ← pacote TypeScript/Node.js
│       ├── src/
│       ├── tests/
│       └── package.json
└── docs/
    └── explanation.md
```

**Pontos importantes do `.gitignore`** (já deve ter, mas confirme):
```
# Python
__pycache__/
*.egg-info/
dist/
.venv/

# TypeScript
node_modules/
dist/

# Geral
.env
*.jsonl
```

---

### 10.2 Publicar o pacote Python no PyPI

#### Pré-requisitos
```bash
pip install build twine
```

#### Passo a passo

```bash
# 1. Entre na pasta do pacote Python
cd packages/tracecast-py

# 2. Rode os testes
python -m pytest tests/ -q

# 3. Gere o build
python -m build
# Cria: dist/tracecast-0.1.0-py3-none-any.whl
#        dist/tracecast-0.1.0.tar.gz

# 4. Publique no TestPyPI primeiro (recomendado)
twine upload --repository testpypi dist/*
# Instale e teste:
pip install --index-url https://test.pypi.org/simple/ tracecast

# 5. Quando validado, publique no PyPI oficial
twine upload dist/*
```

#### Credenciais
Crie uma conta em [pypi.org](https://pypi.org) e use um **API token** (não username/senha):
- Vá em Account Settings → API tokens → Add API token
- Use `twine upload dist/* --username __token__ --password pypi-XXXX...`

> **Dica**: crie um `~/.pypirc` para não precisar digitar a cada vez:
> ```ini
> [pypi]
> username = __token__
> password = pypi-XXXXXXXXXXXXXXXX
> ```

#### Atualizar versão

Edite `pyproject.toml`:
```toml
[project]
version = "0.2.0"
```
Depois rode `python -m build && twine upload dist/*`.

#### Resultado

Após publicar, qualquer pessoa instala com:
```bash
pip install tracecast
pip install "tracecast[mongo]"
pip install "tracecast[all]"
```

---

### 10.3 Publicar o pacote TypeScript no npm

#### Pré-requisitos
Conta no [npmjs.com](https://www.npmjs.com) e login:
```bash
npm login
```

#### Passo a passo

```bash
# 1. Entre na pasta do pacote TypeScript
cd packages/tracecast-ts

# 2. Rode os testes
npx jest --forceExit

# 3. Build (compila TypeScript → JavaScript + .d.ts)
npm run build
# Cria: dist/index.js, dist/index.d.ts, dist/exporters/*, dist/integrations/*

# 4. Valide o que será publicado
npm pack --dry-run
# Mostra todos os arquivos incluídos (dist/, README.md, LICENSE)

# 5. Publique
npm publish
```

#### Escopo (scope) — opcional mas recomendado

Se quiser publicar como pacote com escopo (ex: `@minha-org/tracecast`):
```json
// package.json
{
  "name": "@minha-org/tracecast",
  ...
}
```
```bash
npm publish --access public
```

#### Atualizar versão

```bash
npm version patch   # 0.1.0 → 0.1.1
npm version minor   # 0.1.0 → 0.2.0
npm version major   # 0.1.0 → 1.0.0
npm publish
```

O `package.json` já tem `"prepublishOnly": "npm run build && npm test"` — o build e os testes rodam automaticamente antes de cada `npm publish`.

#### Resultado

Após publicar, qualquer pessoa instala com:
```bash
npm install tracecast
# ou
npm install @minha-org/tracecast
```

---

### 10.4 Automatizando com GitHub Actions (CI/CD)

Exemplo de workflow que roda testes em todo PR e publica automaticamente quando uma tag é criada:

```yaml
# .github/workflows/publish.yml
name: Test & Publish

on:
  push:
    tags: ["v*"]       # publica ao criar tag v0.2.0, v1.0.0, etc.
  pull_request:
    branches: [main]   # testa em todo PR

jobs:
  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e "packages/tracecast-py[all]"
      - run: cd packages/tracecast-py && python -m pytest -q

  test-typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: cd packages/tracecast-ts && npm ci
      - run: cd packages/tracecast-ts && npx jest --forceExit

  publish-pypi:
    needs: [test-python, test-typescript]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install build twine
      - run: cd packages/tracecast-py && python -m build
      - run: twine upload packages/tracecast-py/dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}

  publish-npm:
    needs: [test-python, test-typescript]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"
      - run: cd packages/tracecast-ts && npm ci && npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

**Secrets necessários no GitHub** (Settings → Secrets and variables → Actions):
- `PYPI_TOKEN` — API token do PyPI
- `NPM_TOKEN` — token de automação do npm (`npm token create`)

**Fluxo de release:**
```bash
git tag v0.2.0
git push origin v0.2.0
# → GitHub Actions roda testes → publica no PyPI e npm automaticamente
```

---

### 10.5 Checklist antes de publicar

- [ ] Versão atualizada em `pyproject.toml` e `package.json`
- [ ] `CHANGELOG` ou release notes documentados
- [ ] `README.md` atualizado com novos exemplos
- [ ] Testes passando: `128 Python + 113 TypeScript`
- [ ] Build TypeScript limpo: `npx tsc --noEmit`
- [ ] `.gitignore` inclui `dist/`, `*.egg-info/`, `node_modules/`
- [ ] Secrets do GitHub configurados (`PYPI_TOKEN`, `NPM_TOKEN`)
