● Feito. O que foi feito:           

  1. pyproject.toml corrigido:                                                                                                                                                                  
  postgres  = ["psycopg2>=2.9"]
  all       = ["tracecast[mongo,postgres,langchain]"]                                                                                                                                           
                                                                  
  2. .github/workflows/ci.yml criado — roda em todo push/PR para main:                                                                                                                          
  - Python 3.11 e 3.12 em paralelo                                                                                                                                                              
  - TypeScript com build + testes                                                                                                                                                               
                                                                                                                                                                                                
  ---                                                                                                                                                                                           
  Próximos passos para publicar:                                  
                                                                                                                                                                                                
  # Confirmar tudo ok                                             
  cd packages/tracecast-py && python -m pytest tests/ -q                                                                                                                                        
  
  # Build Python                                                                                                                                                                                
  pip install build twine                                         
  python -m build                                                                                                                                                                               
                                                                  
  # Publicar PyPI (precisa de conta + API token)                                                                                                                                                
  twine upload dist/*
                                                                                                                                                                                                
  # Build + publicar npm (precisa de npm login)                                                                                                                                                 
  cd ../tracecast-ts
  npx tsc                                                                                                                                                                                       
  npm publish --access public                                     
                                                                                                                                                                                                
  Você já tem conta no PyPI e npm configurada?                                                                                                                                                  
  
❯ Não tenho, como faço?                                                                                                                                                                         
                                                                  
● PyPI (Python)                                                                                                                                                                                 
                                               
  1. Criar conta                                                                                                                                                                                
  - Acesse pypi.org → "Register"                                                                                                                                                                
  - Confirme o e-mail                                                                                                                                                                           
                                                                  
  2. Ativar 2FA (obrigatório desde 2024)                                                                                                                                                        
  - Vá em Account Settings → Two-factor authentication                                                                                                                                          
  - Use um app como Google Authenticator              
                                                                                                                                                                                                
  3. Gerar API Token                                                                                                                                                                            
  - Account Settings → API tokens → "Add API token"
  - Scope: "Entire account" (para o primeiro upload)                                                                                                                                            
  - Copie o token — ele só aparece uma vez                        
                                                                                                                                                                                                
  4. Configurar localmente                                        
  # Cria o arquivo de credenciais                                                                                                                                                               
  cat > ~/.pypirc << 'EOF'                                        
  [pypi]                                                                                                                                                                                        
    username = __token__                                          
    password = pypi-SeuTokenAqui                                                                                                                                                                
  EOF                                                             
  chmod 600 ~/.pypirc                                                                                                                                                                           
                     
  5. Publicar                                                                                                                                                                                   
  cd /home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py                                                                                                            
  pip install build twine
  python -m build                                                                                                                                                                               
  twine upload dist/*                                             
                                                                                                                                                                                                
  ---                                                             
  npm (TypeScript)

  1. Criar conta
  - Acesse npmjs.com → "Sign Up"
  - Confirme o e-mail                                                                                                                                                                           
                     
  2. Login no terminal                                                                                                                                                                          
  npm login                                                                                                                                                                                     
  # vai pedir: username, password, e-mail, OTP (se tiver 2FA)
                                                                                                                                                                                                
  3. Publicar                                                                                                                                                                                   
  cd /home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-ts                                                                                                            
  npm publish --access public                                                                                                                                                                   
  # --access public é necessário porque o pacote não tem escopo (@org/pkg)                                                                                                                      
                                                                  
  ---                                                                                                                                                                                           
  Verificar disponibilidade do nome
                                                                                                                                                                                                
  Antes de criar as contas, vale checar se o nome tracecast está livre:
                                                                                                                                                                                                
  # PyPI                                                          
  curl -s https://pypi.org/pypi/tracecast/json | python3 -c "import sys,json; d=json.load(sys.stdin); print('JA EXISTE:', d['info']['version'])" 2>/dev/null || echo "Nome livre no PyPI"       
                                                                                                                                                                                                
  # npm
  npm view tracecast version 2>/dev/null || echo "Nome livre no npm"                                                                                                                            
                                                                  
  Se o nome já estiver ocupado, você precisaria usar algo como tracecast-sdk ou py-tracecast. Quer que eu verifique isso agora?      

# TraceCast

> **SDK de observabilidade para LLMs** — rastreie tokens, custo, latência e tool calls em qualquer framework de IA. Python · TypeScript · Framework-Agnostic.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://pypi.org/project/tracecast/)
[![npm](https://img.shields.io/badge/npm-tracecast-red)](https://www.npmjs.com/package/tracecast)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 128 Python + 113 TypeScript](https://img.shields.io/badge/tests-128%20%2B%20113-brightgreen)](#)

---

## O que é

TraceCast é um SDK leve que **captura automaticamente** cada interação com LLMs e as exporta para onde você precisar — MongoDB, PostgreSQL, arquivo JSONL, ou qualquer destino customizado.

- **Zero vendor lock-in** — funciona com OpenAI, Anthropic, Google, Groq, Ollama, e qualquer SDK compatível.
- **Zero configuração** para LangChain/LangGraph — um callback resolve tudo.
- **Zero dependências core** — instale só o que for usar.
- **Exemplos Reais** — Veja a pasta `real_examples/` em cada pacote para implementações completas.

---

## Instalação

### Python

```bash
#Core (sem dependências)
pip install tracecast

# Com suporte a MongoDB
pip install "tracecast[mongo]"

# Com suporte a LangChain / LangGraph
pip install "tracecast[langchain]"

# Tudo junto
pip install "tracecast[all]"
```

### TypeScript / Node.js

```bash
npm install tracecast

# Opcionais — instale apenas o que for usar
npm install mongodb   # para MongoExporter
npm install pg        # para PostgresExporter
```

---

## Inicio Rápido

### Python

```python
from tracecast import Tracer, Span, SpanType, calculate_cost
from tracecast.exporters import JsonFileExporter
from datetime import datetime, timezone
import uuid

tracer = Tracer(
    exporters=[JsonFileExporter("./traces.jsonl")],
    logging=True,
    log_prefix="meu_agente",
)

with tracer.trace("minha_run", user_id="usr_1") as trace:
    # sua chamada LLM aqui
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
# → trace exportado automaticamente ao sair do `with`
```

### TypeScript

```typescript
import { Tracer, JsonFileExporter, SpanType, calculateCost } from "tracecast";
import { randomUUID } from "crypto";

const tracer = new Tracer({
  exporters: [new JsonFileExporter("./traces.jsonl")],
  logging: true,
  logPrefix: "meu_agente",
});

await tracer.trace("minha_run", async (trace) => {
  const span = {
    spanId: randomUUID(),
    type: SpanType.LLM,
    name: "llm:gpt-4o",
    model: "gpt-4o",
    startedAt: new Date(),
    finishedAt: new Date(),
    tokensIn: 120,
    tokensOut: 80,
    costUsd: calculateCost("gpt-4o", 120, 80),
  };
  trace.spans.push(span);
}, { userId: "usr_1" });
```

---

## Frameworks Suportados

### SDK Puro (OpenAI, Anthropic, Google, Groq...)

Crie spans manualmente com os dados de uso retornados pelo SDK.

**Python**
```python
import openai
from tracecast import Tracer, Span, SpanType, calculate_cost
from tracecast.exporters import JsonFileExporter
from datetime import datetime, timezone
import uuid

client = openai.OpenAI()
tracer = Tracer(exporters=[JsonFileExporter("./traces.jsonl")], logging=True)

with tracer.trace("openai-run", user_id="u1") as trace:
    started = datetime.now(timezone.utc)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Olá!"}]
    )
    finished = datetime.now(timezone.utc)

    span = Span(
        span_id=str(uuid.uuid4()),
        type=SpanType.LLM,
        name="llm:gpt-4o",
        model="gpt-4o",
        started_at=started,
        finished_at=finished,
        tokens_in=resp.usage.prompt_tokens,
        tokens_out=resp.usage.completion_tokens,
    )
    span.cost_usd = calculate_cost("gpt-4o", span.tokens_in, span.tokens_out)
    trace.spans.append(span)
```

**TypeScript**
```typescript
import OpenAI from "openai";
import { Tracer, JsonFileExporter, SpanType, calculateCost } from "tracecast";
import { randomUUID } from "crypto";

const client = new OpenAI();
const tracer = new Tracer({ exporters: [new JsonFileExporter("./traces.jsonl")], logging: true });

await tracer.trace("openai-run", async (trace) => {
  const start = new Date();
  const resp = await client.chat.completions.create({
    model: "gpt-4o",
    messages: [{ role: "user", content: "Olá!" }],
  });
  trace.spans.push({
    spanId: randomUUID(),
    type: SpanType.LLM,
    name: "llm:gpt-4o",
    model: "gpt-4o",
    startedAt: start,
    finishedAt: new Date(),
    tokensIn: resp.usage!.prompt_tokens,
    tokensOut: resp.usage!.completion_tokens,
    costUsd: calculateCost("gpt-4o", resp.usage!.prompt_tokens, resp.usage!.completion_tokens),
  });
}, { userId: "u1" });
```

---

### LangChain

O `TraceCastCallback` intercepta automaticamente todos os eventos LLM, Tool e Chain — nenhum código extra necessário.

**Python**
```python
from tracecast import Tracer
from tracecast.exporters import JsonFileExporter
from tracecast.integrations.langchain import TraceCastCallback
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

tracer = Tracer(
    exporters=[JsonFileExporter("./traces.jsonl")],
    logging=True,
    log_prefix="langchain_agent",
)
callback = TraceCastCallback(tracer=tracer)

# stream_usage=True garante token tracking quando usar AgentExecutor
llm = ChatOpenAI(model="gpt-4o-mini", stream_usage=True)
prompt = ChatPromptTemplate.from_messages([("user", "{input}")])
chain = prompt | llm

with tracer.trace("langchain-run", user_id="u1"):
    result = chain.invoke({"input": "Olá!"}, config={"callbacks": [callback]})
```

**TypeScript**
```typescript
import { Tracer, JsonFileExporter } from "tracecast";
import { TraceCastCallback } from "tracecast/integrations/langchain";
import { ChatOpenAI } from "@langchain/openai";
import { ChatPromptTemplate } from "@langchain/core/prompts";

const tracer = new Tracer({
  exporters: [new JsonFileExporter("./traces.jsonl")],
  logging: true,
  logPrefix: "langchain_agent",
});
const cb = new TraceCastCallback(tracer);

// streamUsage: true garante token tracking quando usar AgentExecutor
const llm = new ChatOpenAI({ model: "gpt-4o-mini", streamUsage: true });
const prompt = ChatPromptTemplate.fromMessages([["user", "{input}"]]);
const chain = prompt.pipe(llm as any);

await tracer.trace("langchain-run", async () => {
  await chain.invoke({ input: "Olá!" }, { callbacks: [cb] });
}, { userId: "u1" });
```

**O que é capturado automaticamente:**
- `LLM started → modelo` ao chamar o LLM
- `LLM end → modelo | tokens: X in / Y out | $custo | latência` ao concluir
- `Tool call → nome | input` ao invocar uma tool
- `Tool end → nome | latência` ao retornar
- `Chain → nome` para o nó raiz (LangGraph/Chains)

---

### LangGraph

LangGraph usa o mesmo `TraceCastCallback` — cada nó do `StateGraph` gera um span `AGENT` automaticamente.

**Python**
```python
from tracecast import Tracer
from tracecast.integrations.langchain import TraceCastCallback
from langgraph.graph import StateGraph, END
from typing import TypedDict

tracer = Tracer(logging=True, log_prefix="meu_grafo")
callback = TraceCastCallback(tracer=tracer)

class State(TypedDict):
    messages: list

def node_a(state): return {"messages": state["messages"] + ["A"]}
def node_b(state): return {"messages": state["messages"] + ["B"]}

graph = StateGraph(State)
graph.add_node("A", node_a)
graph.add_node("B", node_b)
graph.add_edge("A", "B")
graph.add_edge("B", END)
graph.set_entry_point("A")
app = graph.compile()

with tracer.trace("grafo-run"):
    app.invoke({"messages": []}, config={"callbacks": [callback]})
```

> Cada nó gera um span do tipo `AGENT` com `name: "chain:NomeDoNó"` e latência medida automaticamente.

---

### CrewAI

CrewAI usa seu próprio layer de LLM e não propaga callbacks LangChain. Use spans manuais para capturar tokens após o `kickoff()`.

```python
from tracecast import Tracer, Span, SpanType, calculate_cost
from tracecast.exporters import JsonFileExporter
from crewai import Agent, Task, Crew
from datetime import datetime, timezone
import uuid

tracer = Tracer(exporters=[JsonFileExporter("traces.jsonl")], logging=True)

with tracer.trace("crew-run", project_id="proj-crew") as trace:
    agent = Agent(role="Pesquisador", goal="Pesquisar IA", backstory="...", llm="gpt-4o-mini")
    task = Task(description="Explique LLMs em 2 frases", expected_output="Texto", agent=agent)
    crew = Crew(agents=[agent], tasks=[task])

    started = datetime.now(timezone.utc)
    result = crew.kickoff()
    finished = datetime.now(timezone.utc)

    # Capture usage do LLM internamente (CrewAI > 1.x expõe usage no result)
    span = Span(
        span_id=str(uuid.uuid4()),
        type=SpanType.LLM,
        name="llm:gpt-4o-mini",
        model="gpt-4o-mini",
        started_at=started,
        finished_at=finished,
        tokens_in=120,   # extraia de result.token_usage se disponível
        tokens_out=45,
    )
    span.cost_usd = calculate_cost("gpt-4o-mini", span.tokens_in, span.tokens_out)
    trace.spans.append(span)
```

> **Nota**: O log automático de eventos LLM/Tool não está disponível para CrewAI (o framework não expõe hooks). O TraceCast loga automaticamente o início e fim do **trace** completo.

---

### LlamaIndex

Use o `LlamaDebugHandler` para capturar eventos LLM e criar spans manualmente.

```python
from tracecast import Tracer, Span, SpanType, calculate_cost
from tracecast.exporters import JsonFileExporter
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler, CBEventType
from llama_index.core.llms import MockLLM
from datetime import datetime, timezone
import uuid

tracer = Tracer(exporters=[JsonFileExporter("traces.jsonl")], logging=True)
dbh = LlamaDebugHandler()
llm = MockLLM(callback_manager=CallbackManager([dbh]))

with tracer.trace("rag-query") as trace:
    llm.complete("Minha pergunta sobre o documento")

    for event in dbh.get_events():
        if event.event_type == CBEventType.LLM:
            span = Span(
                span_id=str(uuid.uuid4()),
                type=SpanType.LLM,
                name=f"llm:{event.payload.get('model', 'unknown')}",
                model=event.payload.get("model", "unknown"),
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                tokens_in=event.payload.get("formatted_prompt_tokens_count", 0),
                tokens_out=event.payload.get("completion_tokens_count", 0),
            )
            span.cost_usd = calculate_cost(span.model, span.tokens_in, span.tokens_out)
            trace.spans.append(span)
```

---

## 🚀 Exemplos Completos (Módulo real_examples)

Para facilitar a sua implementação, criamos exemplos completos e comentados que simulam cenários reais (como agentes de pesquisa, suporte técnico e análise financeira) em ambas as linguagens.

### Python (`packages/tracecast-py/real_examples/`)
- [openai_sdk.py](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py/real_examples/openai_sdk.py) — Funcionamento manual com tools.
- [anthropic_sdk.py](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py/real_examples/anthropic_sdk.py) — Claude com tool use extraído.
- [langchain_agent.py](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py/real_examples/langchain_agent.py) — Agente financeiro automático.
- [langgraph_graph.py](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py/real_examples/langgraph_graph.py) — Orquestração de grafos.
- [crewai_crew.py](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py/real_examples/crewai_crew.py) — Multi-agent setup.
- [llamaindex_index.py](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-py/real_examples/llamaindex_index.py) — RAG com interceptação de eventos.

### TypeScript (`packages/tracecast-ts/real_examples/`)
- [openaiSdk.ts](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-ts/real_examples/openaiSdk.ts) — Análise de código com MongoDB.
- [langchainAgent.ts](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-ts/real_examples/langchainAgent.ts) — Tradução automática.
- [langgraphAgent.ts](file:///home/pedrocastanha/Desktop/python-projects/lib-tracecast/packages/tracecast-ts/real_examples/langgraphAgent.ts) — Ciclo de decisão com LangGraph.

---

## Exporters e Campos Disponíveis

Cada exporter permite filtrar quais campos serão salvos usando `include_fields` ou `exclude_fields`. Isso é útil para reduzir o tamanho dos logs ou ocultar dados sensíveis.


### JsonFileExporter — JSONL (sem dependências)

```python
from tracecast.exporters import JsonFileExporter

# Salva tudo
exporter = JsonFileExporter("./traces.jsonl")

# Apenas campos essenciais
exporter = JsonFileExporter("./traces.jsonl", include_fields={"trace_id", "cost_usd", "total_tokens", "model"})

# Sem spans (mais leve)
exporter = JsonFileExporter("./traces.jsonl", exclude_fields={"spans"})
```

```typescript
import { JsonFileExporter } from "tracecast";

const exporter = new JsonFileExporter("./traces.jsonl", { excludeFields: ["spans"] });
```

### MongoExporter

```bash
pip install "tracecast[mongo]"   # Python
npm install mongodb               # TypeScript
```

```python
from tracecast.exporters.mongo import MongoExporter

exporter = MongoExporter(
    uri="mongodb://localhost:27017",
    db="myapp",
    collection="traces",
    include_fields={"trace_id", "cost_usd", "total_tokens", "model", "latency_ms"},
)
```

```typescript
import { MongoExporter } from "tracecast/exporters/mongo";

const exporter = new MongoExporter("mongodb://localhost:27017", "myapp", "traces", {
  excludeFields: ["spans"],       // economiza espaço
});
await exporter.close();           // ao encerrar a aplicação
```

### PostgresExporter

```bash
pip install psycopg2-binary   # Python
npm install pg                 # TypeScript
```

```python
from tracecast.exporters.postgres import PostgresExporter

# Tabela criada automaticamente; schema adapta-se a include/exclude
with PostgresExporter(
    dsn="postgresql://user:pass@host:5432/db",
    table="traces",
    include_fields=["trace_id", "name", "model", "cost_usd", "total_tokens", "latency_ms"],
) as exporter:
    tracer = Tracer(exporters=[exporter])
```

```typescript
import { PostgresExporter } from "tracecast/exporters/postgres";

const exporter = new PostgresExporter("postgresql://user:pass@host:5432/db", "traces", {
  excludeFields: ["spans", "metadata"],
});
await exporter.close();
```

### DictExporter — sem arquivo, sem banco

Ideal para testes, pipelines customizados ou integração com filas.

```python
from tracecast.exporters import DictExporter

# Coleta em lista (default)
exporter = DictExporter()
tracer = Tracer(exporters=[exporter])
with tracer.trace("run"):
    ...
print(exporter.traces)  # [{"trace_id": ..., "cost_usd": ..., ...}]

# Ou via callback
exporter = DictExporter(
    on_trace=lambda d: minha_fila.put(d),
    include_fields={"trace_id", "cost_usd", "total_tokens"},
)
```

```typescript
import { DictExporter } from "tracecast";

const exporter = new DictExporter({
  onTrace: (d) => myQueue.push(d),
  includeFields: ["traceId", "costUsd", "totalTokens"],
});
```

### Custom Exporter

```python
from tracecast.exporters.base import BaseExporter

class WebhookExporter(BaseExporter):
    def __init__(self, url: str):
        self.url = url
    def export(self, trace) -> None:
        import httpx
        httpx.post(self.url, json=trace.to_dict())
```

```typescript
import { BaseExporter } from "tracecast/exporters/base";
import type { Trace } from "tracecast";

class WebhookExporter implements BaseExporter {
  constructor(private url: string) {}
  async export(trace: Trace): Promise<void> {
    await fetch(this.url, { method: "POST", body: JSON.stringify(trace) });
  }
}
```

---

## Logging Integrado

Habilite com um único flag — logs estruturados de todos os eventos LLM/Tool/Chain, sem código extra.

```python
tracer = Tracer(
    exporters=[...],
    logging=True,
    log_prefix="meu_agente",   # opcional
)
```

```typescript
const tracer = new Tracer({
  exporters: [...],
  logging: true,
  logPrefix: "meu_agente",
  // logFn: (msg) => myLogger.info(msg)   // customizável
});
```

**Saída:**
```
[meu_agente] Trace started
[meu_agente] LLM started → gpt-4o
[meu_agente] Tool call → search_web | quem é Pedro Castanheira...
[meu_agente] Tool end → search_web | 0.82s
[meu_agente] LLM end → gpt-4o | tokens: 310 in / 95 out | $0.0019 | 2.10s
[meu_agente] Trace finished → total: 405 tokens | $0.0019 | 3.40s | tools: search_web×1
```

- **Python**: usa `logging.getLogger("tracecast")` — configure com `logging.basicConfig` ou qualquer handler.
- **TypeScript**: usa `console.log` por padrão — injete `logFn`/`warnFn` para redirecionar.
- Cada linha é garantidamente uma **única linha** (newlines colapsados).
- Chain logging mostra apenas o **nó raiz** (sem spam de sub-nós internos do LangGraph).

---

## Tabela de Preços Built-in

| Modelo | Input ($/1K tokens) | Output ($/1K tokens) |
|--------|---------------------|----------------------|
| `gpt-5` | 0.00125 | 0.01000 |
| `gpt-5.4` | 0.00250 | 0.01500 |
| `gpt-4o` | 0.00250 | 0.01000 |
| `gpt-4o-mini` | 0.00015 | 0.00060 |
| `gpt-4.1` | 0.00200 | 0.00800 |
| `gpt-4.1-mini` | 0.00040 | 0.00160 |
| `o3` | 0.00200 | 0.00800 |
| `o4-mini` | 0.00110 | 0.00440 |
| `claude-opus-4-6` | 0.00500 | 0.02500 |
| `claude-sonnet-4-6` | 0.00300 | 0.01500 |
| `claude-haiku-4-5` | 0.00100 | 0.00500 |
| `claude-sonnet-4` | 0.00300 | 0.01500 |
| `claude-haiku-3-5` | 0.00080 | 0.00400 |
| `gemini-3.1-pro` | 0.00200 | 0.01200 |
| `gemini-3-flash` | 0.00050 | 0.00300 |
| `gemini-2.5-flash` | 0.00030 | 0.00250 |
| `gemini-2.5-pro` | 0.00125 | 0.01000 |
| `gemini-2.0-flash` | 0.00010 | 0.00040 |
| `llama-4-scout` | 0.00011 | 0.00034 |
| `llama-4-maverick` | 0.00020 | 0.00060 |
| `llama-3.3-70b` | 0.00059 | 0.00079 |
| `ollama/*` | 0.00000 | 0.00000 |

**Preços customizados:**

```python
tracer = Tracer(exporters=[...])
from tracecast.core.cost_calculator import calculate_cost

# Use custom_prices no calculate_cost
cost = calculate_cost("meu-modelo", tokens_in=100, tokens_out=50,
                      custom_prices={"meu-modelo": (0.001, 0.002)})
```

---

## Modelo de Dados

### Trace (Nível Superior)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `trace_id` | `str` | UUID único gerado para cada execução. |
| `name` | `str` | Nome lógico da tarefa (ex: "pesquisa_web"). |
| `user_id` | `str?` | ID do usuário final (útil para auditoria). |
| `session_id` | `str?` | Identificador da conversa ou sessão. |
| `project_id` | `str?` | Identificador do projeto no qual a IA está inserida. |
| `model` | `str?` | O modelo que mais consumiu tokens neste trace. |
| `total_tokens_in` | `int` | Soma de `tokens_in` de todos os spans LLM. |
| `total_tokens_out` | `int` | Soma de `tokens_out` de todos os spans LLM. |
| `total_tokens` | `int` | Soma total de tokens (in + out). |
| `cost_usd` | `float` | Custo total estimado baseado na tabela built-in. |
| `latency_ms` | `int?` | Tempo total decorrido (finished_at - started_at). |
| `tools_used` | `dict` | Mapa `{"tool_name": count}` de todas as tools chamadas. |
| `spans` | `list` | Lista de objetos Span. |
| `metadata` | `dict` | Objeto livre para tags personalizadas. |
| `started_at` | `ISO8601` | Timestamp de início (UTC). |
| `finished_at` | `ISO8601` | Timestamp de conclusão (UTC). |

### Span (Eventos Individuais)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `span_id` | `str` | UUID único do span. |
| `type` | `Enum` | `LLM` (IA), `TOOL` (ferramenta), `AGENT` (passo intermediário). |
| `name` | `str` | Nome descritivo (ex: "gpt-4o:summarize"). |
| `model` | `str?` | Modelo específico usado neste span. |
| `tokens_in` | `int?` | Tokens enviados ao modelo. |
| `tokens_out` | `int?` | Tokens gerados pelo modelo. |
| `cost_usd` | `float?` | Custo específico deste span. |
| `latency_ms` | `int?` | Tempo de resposta deste span individual. |
| `started_at` | `ISO8601` | Início do evento. |
| `finished_at`| `ISO8601` | Fim do evento. |
| `metadata` | `dict?` | Dados extras (ex: inputs da tool ou erros via `_error`). |

---

## Resiliência

1. **Exceção no código do usuário** → trace sempre finalizado e exportado via `finally`.
2. **Exceção no exporter** → engolida com `warning` — **nunca interrompe** o código principal.
3. **`failOnExportError: true`** (TypeScript) → propaga erros do exporter se quiser controle explícito.
4. **Traces aninhados** (Python) → suportados via stack de `ContextVar`.
5. **Multi-tenant** → seguro — cada coroutine/thread tem seu próprio contexto isolado.

---

## Testes

```bash
# Python
cd packages/tracecast-py
pip install -e ".[all]"
python -m pytest tests/ -q
# → 128 passed

# TypeScript
cd packages/tracecast-ts
npm install
npx jest --forceExit
# → 113 passed
```

---

## Licença

MIT © Pedro Castanheira Costa
