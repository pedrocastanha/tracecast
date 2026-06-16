# TraceCast — How to use

Guia prático de ponta a ponta: rodar as demos, ver no dashboard e integrar no seu projeto.

Esta pasta (`demo/`) contém **apenas demonstrações reais e runnable**:

```
demo/
├── HOW-TO-USE.md            # este guia
├── tracing_demo.py          # traceia um agente LangGraph real -> JSONL
├── evaluation_demo.py       # avalia agentes contra golden datasets -> JSONL
├── fastapi_app.py           # API FastAPI instrumentada (tracing + dashboard + eval)
├── test_endpoints.py        # teste in-process real dos endpoints (TestClient)
└── golden_datasets/         # datasets JSON de exemplo (single + multi-turn)
```

> Esta pasta fica fora dos pacotes publicados (não vai para o PyPI nem para o npm do dashboard).

As demos rodam **offline** (LLM e judge simulados). Com `OPENAI_API_KEY` setada, usam LLM real.

---

## 1. Instalação

```bash
pip install "tracecast[all]"
# ou, a partir deste repositório:
pip install -e "packages/tracecast-py[all]"
```

---

## 2. Rodar as demos

```bash
python demo/tracing_demo.py        # gera demo/demo_output/traces.jsonl
python demo/evaluation_demo.py     # gera demo/demo_output/eval_traces.jsonl
```

Saída esperada (tracing): cada request vira um trace com nós do grafo, guardrail, span LLM,
arestas percorridas, tokens e latência. (evaluation): pass_rate por dataset, com um caso de FAIL
proposital para você ver como falhas aparecem.

---

## 2.1 API FastAPI de exemplo

App real instrumentado (`fastapi_app.py`): tracing por request, dashboard embutido em `/tracecast`
e disparo de evaluation por endpoint.

```bash
# subir o servidor:
uvicorn demo.fastapi_app:app --port 8000     # (a partir da raiz do repo)

# em outro terminal, testar de verdade:
curl -s localhost:8000/health
curl -s -X POST localhost:8000/chat -H 'content-type: application/json' \
     -d '{"message":"Qual o horario de atendimento?"}'
curl -s -X POST localhost:8000/tracecast/api/evals/run -H 'content-type: application/json' \
     -d '{"target":"support_bot"}'
# dashboard: http://127.0.0.1:8000/tracecast
```

Sem subir servidor (teste in-process, exercita todos os endpoints):

```bash
python demo/test_endpoints.py
```

---

## 3. Ver no dashboard

Servidor standalone lendo o arquivo gerado:

```bash
TRACECAST_STORE="file://$(pwd)/demo/demo_output/traces.jsonl" tracecast-server
# abra http://127.0.0.1:7777/tracecast
#   - aba Traces  -> abra um trace -> aba Graph (grafo DAG percorrido)
#   - aba Evaluators (use eval_traces.jsonl no TRACECAST_STORE)
```

Para evals:

```bash
TRACECAST_STORE="file://$(pwd)/demo/demo_output/eval_traces.jsonl" tracecast-server
```

---

## 4. Integrar no seu projeto

### 4.1 Tracing automático (LangChain / LangGraph)

```python
from tracecast import Tracer, auto_instrument, trace_cast
from tracecast.exporters.mongo import MongoExporter

tracer = Tracer(exporters=[MongoExporter("mongodb://localhost:27017", db="myapp")], logging=True)
auto_instrument(tracer)                 # registra o callback global do LangChain + patch de SDKs

@trace_cast(project_id="suporte", user_id="u1")   # na rota/handler de entrada
def handle(message: str):
    return app.invoke({"messages": [message]})     # seu StateGraph compilado
```

Cada nó vira um span (`AGENT`), tools viram `TOOL`, chamadas LLM viram `LLM`; a hierarquia pai→filho e
as arestas percorridas são derivadas automaticamente.

### 4.2 Traçar funções avulsas (guardrails, validações)

```python
from tracecast import trace_span
from tracecast.models.span import SpanType

@trace_span(name="guardrail_pii", type=SpanType.TOOL)
def guardrail(text: str) -> str:
    return remove_pii(text)
```

### 4.3 Threads / executors

ContextVars não cruzam threads. Capture o contexto antes de offloadar:

```python
from tracecast import bind_context
pool.submit(bind_context(node_fn, state))
await loop.run_in_executor(None, bind_context(node_fn, state))
```

### 4.4 Onde salvar (exporters)

```python
from tracecast.exporters import JsonFileExporter, DictExporter
from tracecast.exporters.mongo import MongoExporter
from tracecast.exporters.postgres import PostgresExporter

MongoExporter("mongodb://localhost:27017", db="myapp", collection="traces")
PostgresExporter("postgresql://user:pass@host:5432/db", table="traces")
JsonFileExporter("./traces.jsonl")
```

Falhas de export são logadas (ERROR) e expostas via `Tracer(on_export_error=...)`, nunca silenciosas.

### 4.5 Dashboard: embutido ou standalone

Embutido no app:

```python
from fastapi import FastAPI
app = FastAPI()
tracer.mount(app, prefix="/tracecast")
```

Standalone numa VM separada (só lê o storage remoto — não importa seu app):

```bash
export TRACECAST_STORE="mongodb://prod-host:27017"
export TRACECAST_DB="myapp"
export TRACECAST_AUTH="admin:senha"     # basic auth opcional
tracecast-server
```

---

## 5. Evaluation por golden dataset

### 5.1 Formato do dataset (JSON)

Single-turn e multi-turn convivem no mesmo arquivo:

```json
{
  "name": "support-bot-v1",
  "criteria": [{"name": "faithfulness", "description": "Fiel ao expected?"}],
  "threshold": 0.7,
  "cases": [
    {"id": "c1", "input": "Horário?", "expected": "8h às 18h"},
    {"id": "c2", "turns": [
      {"role": "user", "content": "Cancelar pedido"},
      {"role": "assistant", "expected": "Informe o número do pedido."}
    ]}
  ]
}
```

### 5.2 Decorar o agente e rodar

```python
from tracecast import evaluator, run_evaluation
from tracecast.exporters.mongo import MongoExporter

@evaluator(dataset="demo/golden_datasets/support_bot.json", name="support_bot",
           scorers=["similarity"], threshold=0.7, project_id="suporte")
def support_bot(question: str) -> str:
    return meu_agente(question)

run = run_evaluation("support_bot", exporters=[MongoExporter("mongodb://localhost:27017", db="myapp")])
print(run.pass_rate, run.avg_score)
```

Scorers determinísticos disponíveis: `exact_match`, `contains`, `regex`, `similarity`.
O LLM-as-judge usa os `criteria` do dataset (rubrica). Injete um judge custom em `run_evaluation(judge=...)`
ou use o `LLMJudge` (default) com uma `OPENAI_API_KEY`.

### 5.3 Via CLI (CI)

```bash
tracecast-eval --target seu_modulo:support_bot --store mongodb://localhost:27017 --db myapp
# exit code != 0 quando pass_rate < threshold
```

Cada caso é traceado: no dashboard, a aba Evaluators mostra cada turn, a resposta da LLM, o score por
critério do judge e um link para o grafo daquela execução.

---

## 6. Troubleshooting

| Sintoma | Causa / solução |
|---------|-----------------|
| Spans não aparecem | Faltou `auto_instrument(tracer)` ou o callback não foi propagado (`config={"callbacks":[cb]}`). |
| Tokens 0 em streaming | Use os wrappers/`auto_instrument` (injetam `stream_options={"include_usage": True}` no OpenAI). |
| Spans perdidos em threads | Use `bind_context(fn, ...)` ao submeter para executors. |
| Dashboard Mongo vazio | Atualize para a versão com o fix do reader; confira `TRACECAST_DB`/`TRACECAST_STORE`. |
| Trigger de eval por endpoint dá 501 | O endpoint só funciona com o dashboard embutido no app (precisa da função registrada). |
