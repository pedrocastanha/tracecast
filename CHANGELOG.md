# Changelog

## v0.2.0 — Observabilidade confiável + Evaluation (o que mudou vs a base auditada)

Comparação com o estado inicial do projeto (auditoria em `.specs/codebase/CONCERNS.md`).

### Resumo quantitativo

| Área | Antes | Agora |
|------|-------|-------|
| Testes (Python) | 204 | **295** (+91) |
| Dashboard lendo de Mongo | **quebrado** — 0 traces (bug de atributo `_collection`/`col`) | funciona |
| Hierarquia de spans | flat, sem pai | `parent_span_id` + árvore/grafo |
| Visualização de fluxo | lista flat | **grafo DAG** (react-flow, nós + arestas) |
| Filtros do dashboard | em memória, últimos 500 traces | server-side (Postgres `WHERE` / Mongo `find`), escala |
| Falha de export | engolida com `warning` (perda silenciosa) | log `ERROR` + hook `on_export_error` |
| Export em app async | `aexport` chamava `export` síncrono (bloqueava o event loop) | offload (`to_thread`) ou background |
| Latência de save no caminho da request | +1–10ms (round-trip do DB, sync) | ~0 com `background_export=True` |
| Comportamento sob overload | n/a / fila ilimitada (risco de OOM) | fila limitada + drop (best-effort, não cai) |
| Erro de span | escondido em `metadata["_error"]` | `status`/`error` first-class |
| Tokens em streaming | passthrough → 0 tokens/custo | capturados (OpenAI/Anthropic) |
| Spans em threads (`run_in_executor`) | perdidos | `bind_context` propaga o contexto |
| Idempotência Mongo | `insert_one` (duplicava em re-export) | upsert por `trace_id` + índices |
| Evaluation por golden dataset | inexistente | subsistema completo |
| SDK TypeScript | duplicada, sem usuários | removida (Python-only) |
| Exemplos | `examples/fake_app.py` | `demo/` runnable + `HOW-TO-USE.md` + API FastAPI + `ARCHITECTURE.md` |

Benchmark do caminho da request (CPU, sem rede): trace + 5 spans com JSONL síncrono **~128µs** →
**~55µs** com `background_export=True` (2.3x). A captura em si (~17–60µs) é desprezível frente a uma
chamada LLM (200ms–3s, <0.05%). Com Mongo/Postgres, o background remove o round-trip de rede
(~1–10ms) do caminho da request.

### Adicionado
- **Schema v2**: `Span.parent_span_id`, `Span.status`/`error` (first-class), `Trace.edges`, `schema_version=2`.
- **Captura de fluxo completo**: hierarquia pai→filho via callback LangChain; `@trace_span` para
  guardrails/funções; `bind_context` para threads; aninhamento via ContextVar de span ativo.
- **Streaming**: captura de tokens em respostas streaming (OpenAI/Anthropic, sync + async).
- **Save assíncrono e seguro para produção**: `Tracer(background_export=True)` com fila limitada +
  worker daemon + drop sob overload + `flush()`/`atexit` (env `TRACECAST_EXPORT_QUEUE`).
- **Dashboard**: visualização DAG do grafo percorrido; filtros server-side; endpoint
  `/api/traces/{id}/graph`; servidor standalone (`tracecast-server`) configurável por env + basic-auth + CORS.
- **Evaluation por golden dataset**: `@evaluator`, golden datasets JSON (single + multi-turn),
  scorers determinísticos + LLM-as-judge (rubrica), runner, CLI `tracecast-eval`, aba **Evaluators**,
  endpoint de disparo (embutido).
- **Docs/exemplos**: `demo/` (tracing, evaluation, API FastAPI, testes in-process), `demo/HOW-TO-USE.md`,
  `ARCHITECTURE.md`.

### Corrigido
- Reader do Mongo lia `_collection` enquanto o exporter expunha `col` → dashboard mostrava 0 traces.
- Perda silenciosa de dados quando um exporter falhava.
- `aexport` bloqueando o event loop em apps async.
- Filtros do dashboard limitados aos últimos 500 traces, em memória.

### Removido
- SDK TypeScript (`packages/tracecast-ts`) — sem usuários; foco em Python.
