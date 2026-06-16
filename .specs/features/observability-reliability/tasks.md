# Tasks — Observabilidade Confiável (Python-only)

Tarefas atômicas, commit por tarefa. `[P]` = paralelizável. Cada uma referencia requisito(s) de `spec.md`
e concern(s) de CONCERNS.md. Ordem por dependência.

Legenda Done-when = critério verificável. Gate = comando que precisa passar.

---

## Fase 0 — Limpeza de escopo

### T0 `[P]` Remover SDK TypeScript (AD-1, C17)
- **O quê:** deletar `packages/tracecast-ts/`; remover jobs TS do CI; limpar README (seção/badges TS);
  remover/marcar `smoke_projects/node_http`.
- **Reusa:** —
- **Done-when:** `rg -l "tracecast-ts" --hidden` só acha histórico; `ci.yml` sem step TS; README sem
  instalação npm.
- **Gate:** CI verde sem jobs TS.

---

## Fase 1 — Schema v2 + Hierarquia (G1, G2)

### T1 Schema v2 no modelo (FR-1.1, FR-2.1, C1, C7)
- **O quê:** `Span` ganha `parent_span_id`, `status="ok"`, `error`; `Trace` ganha `edges`,
  `schema_version=2`. Atualizar `to_dict()` dos dois e `_hydrate_trace` (defaults retrocompat).
- **Reusa:** `models/span.py`, `models/trace.py`, `dashboard/reader.py:_hydrate_trace`.
- **Depends:** —
- **Done-when:** trace serializa/desserializa com os campos novos; trace v1 antigo ainda hidrata.
- **Gate:** `pytest tests/test_span.py tests/test_trace.py`.

### T2 Capturar parent no callback LangChain (FR-1.1, FR-1.2, C1)
- **O quê:** em todos `on_*_start`, setar `span.parent_span_id = str(parent_run_id) if parent_run_id`.
  Setar `status/error` em `_close_span_with_error` e nos `on_*_error`.
- **Reusa:** `integrations/langchain.py`.
- **Depends:** T1.
- **Done-when:** fixture LangGraph 4 nós → todos spans têm parent coerente; nó raiz `parent_span_id=None`.
- **Gate:** `pytest tests/test_integration_langchain.py`.

### T3 Span ativo em ContextVar + aninhamento manual (FR-1.1)
- **O quê:** novo ContextVar `_current_span`; `Tracer.current_span()`. `trace_llm_call` e instrumentors
  setam `parent_span_id = current_span` quando houver.
- **Reusa:** `core/tracer.py`, `integrations/llm.py`, `instrumentors/*`.
- **Depends:** T1.
- **Done-when:** span LLM dentro de um `@trace_span` recebe o span do decorator como pai.
- **Gate:** `pytest tests/test_llm_wrappers.py`.

### T4 Decorator `@trace_span` p/ funções/guardrails (FR-1.5, C5)
- **O quê:** decorator sync+async em `decorators.py` que cria span filho (input/output/latência/status).
- **Reusa:** `decorators.py`, T3.
- **Depends:** T3.
- **Done-when:** guardrail decorado aparece como span filho com input/output/latência.
- **Gate:** novo `tests/test_decorators.py::test_trace_span`.

### T5 Derivar `edges` em `_finalize` (FR-1.3, C2)
- **O quê:** em `Trace._finalize`, agrupar spans por `parent_span_id`, ordenar irmãos por `started_at`,
  emitir arestas consecutivas em `self.edges`.
- **Reusa:** `models/trace.py`.
- **Depends:** T1, T2.
- **Done-when:** fixture de grafo conhecido produz a lista de arestas esperada (caminho percorrido).
- **Gate:** `pytest tests/test_trace.py::test_edges`.

### T6 Propagação de contexto em threads (FR-1.4, C3)
- **O quê:** helper `tracecast.run_in_context`; doc do padrão LangGraph; tracer robusto a thread sem
  trace ativo (não cria spans órfãos perdidos).
- **Reusa:** `core/tracer.py`, `__init__.py`.
- **Depends:** T1.
- **Done-when:** nó rodando em `run_in_executor` anexa spans ao trace (0 perdidos no teste).
- **Gate:** novo `tests/test_tracer.py::test_threadpool_propagation`.

### T7 Tokens em streaming (FR-2.2, C6)
- **O quê:** wrappers LLM forçam/colhem usage em streaming (`stream_options={"include_usage": True}` p/
  OpenAI; acumular `message_delta.usage` p/ Anthropic). Extrair tokens do chunk final.
- **Reusa:** `integrations/llm.py`, `core/token_counter.py`.
- **Depends:** T1.
- **Done-when:** fixture de stream → `tokens_out>0`, custo>0.
- **Gate:** `pytest tests/test_token_counter.py::test_streaming`.

---

## Fase 2 — Save confiável (G3)

### T8 `[P]` Não engolir erros de export (FR-3.1, C9)
- **O quê:** `Tracer(on_export_error=...)`; `_export`/`_aexport` logam ERROR + chamam hook. Trocar
  `warnings.warn` por `logger.error(exc_info=True)`.
- **Reusa:** `core/tracer.py`, `core/logger.py`.
- **Depends:** —
- **Done-when:** exporter que levanta → hook chamado 1x + log ERROR; outros exporters seguem rodando.
- **Gate:** `pytest tests/test_tracer.py::test_export_error_surfaced`.

### T9 `[P]` aexport não-bloqueante (FR-3.2, C10)
- **O quê:** `BaseExporter.aexport` default = `await asyncio.to_thread(self.export, trace)`.
- **Reusa:** `exporters/base.py`.
- **Depends:** —
- **Done-when:** sob carga async, event loop não trava em I/O de export (teste de latência do loop).
- **Gate:** `pytest tests/test_exporters_db.py::test_async_offload`.

### T10 `[P]` Upsert Mongo (FR-3.3, C11)
- **O quê:** `MongoExporter.export` → `replace_one({trace_id}, doc, upsert=True)`; criar índice único
  `trace_id` no `__init__`.
- **Reusa:** `exporters/mongo.py`.
- **Depends:** —
- **Done-when:** export duplo do mesmo trace → 1 doc.
- **Gate:** `pytest tests/test_mongo_exporter.py::test_upsert`.

### T11 Round-trip por exporter (NFR-3.1)
- **O quê:** teste paramétrico export→read por exporter (Dict/JsonFile/Postgres/Mongo) compara trace v2
  íntegro (spans/parent/edges/status).
- **Reusa:** `tests/test_exporters_db.py`.
- **Depends:** T1, T10, T12.
- **Done-when:** round-trip igual em todos.
- **Gate:** `pytest tests/test_exporters_db.py`.

---

## Fase 3 — Dashboard (G4)

### T12 Corrigir reader Mongo (FR-4.1, C12)
- **O quê:** `_from_mongo` lê `getattr(exporter,"_collection",None) or getattr(exporter,"col",None)`.
- **Reusa:** `dashboard/reader.py`.
- **Depends:** —
- **Done-when:** dashboard lista traces vindos de Mongo.
- **Gate:** `pytest tests/test_dashboard_sessions.py` + novo teste Mongo read.

### T13 Interface `query()` + filtros server-side (FR-4.2, NFR-4.1, C13, C15)
- **O quê:** `query/get/count` em Postgres (WHERE param + pool read-only próprio) e Mongo (find+sort+
  skip/limit). `TraceReader` delega quando disponível; fallback in-memory p/ Json/Dict. Router passa
  filtros adiante.
- **Reusa:** `exporters/postgres.py`, `exporters/mongo.py`, `dashboard/reader.py`, `dashboard/router.py`.
- **Depends:** T12.
- **Done-when:** filtro por projeto+data bate `count` do DB; não reusa conexão de escrita; >500 traces ok.
- **Gate:** `pytest tests/test_exporters_db.py::test_query_pushdown`.

### T14 Endpoint `/api/traces/{id}/graph` (FR-4.3)
- **O quê:** retorna `{nodes, edges}` derivados dos spans+`trace.edges`.
- **Reusa:** `dashboard/router.py`, `dashboard/aggregator.py`.
- **Depends:** T5.
- **Done-when:** trace de grafo conhecido → JSON de nós/arestas esperado.
- **Gate:** `pytest tests/test_dashboard_*` (novo `test_graph_endpoint`).

### T15 Frontend `TraceGraph` (react-flow) (FR-4.3, FR-4.5, C14)
- **O quê:** add `reactflow`; componente DAG layout dagre; cor por type, borda vermelha em error; clique
  no nó → painel input/output/tokens/custo/latência/status. Aba "lista" reusa `SpanTimeline`.
- **Reusa:** `tracecast-dashboard/src/pages/TraceDetail.tsx`, `components/SpanTimeline.tsx`.
- **Depends:** T14.
- **Done-when:** `npm run build` ok; TraceDetail mostra grafo navegável; estático copiado p/ backend.
- **Gate:** `npm --prefix packages/tracecast-dashboard run build`.

### T16 Server standalone + env config (FR-4.4, C16)
- **O quê:** `tracecast/serve.py` CLI + `build_exporter_from_dsn`; env `TRACECAST_STORE/PORT/HOST/PREFIX/
  AUTH`; basic-auth opcional; CORS. Console_script `tracecast-server` no `pyproject.toml`.
- **Reusa:** `dashboard/standalone.py`, `core/tracer.py:serve`, `dashboard/router.py`.
- **Depends:** T13, T15.
- **Done-when:** `TRACECAST_STORE=postgresql://... tracecast-server` sobe e lista traces remotos sem
  importar o app do usuário.
- **Gate:** `pytest tests/test_dashboard_mount.py` + smoke manual standalone.

---

## Fase 4 — Validação E2E

### T17 Smoke E2E LangGraph → DB → dashboard (todos os FR)
- **O quê:** app FastAPI com `@trace_cast` + LangGraph (nós, tool, guardrail, condicional) → exporta
  Postgres → server standalone lê e mostra grafo. Assert cobertura de spans, parent, edges, tokens,
  latência, status, filtros.
- **Reusa:** `smoke_projects/python_fastapi`, `examples/`.
- **Depends:** T1–T16.
- **Done-when:** checklist UAT de `spec.md` §3 (G1–G4) todo verde.
- **Gate:** script smoke E2E exit 0.

---

## Matriz de rastreabilidade

| Requisito | Tarefas |
|-----------|---------|
| FR-1.1 | T1, T2, T3 |
| FR-1.2 | T2 |
| FR-1.3 | T5 |
| FR-1.4 | T6 |
| FR-1.5 | T4 |
| FR-1.6 | (existe; validado em T17) |
| FR-2.1 | T1, T2 |
| FR-2.2 | T7 |
| NFR-2.1/2.2 | T11, T17 |
| FR-3.1 | T8 |
| FR-3.2 | T9 |
| FR-3.3 | T10 |
| NFR-3.1 | T11 |
| FR-4.1 | T12 |
| FR-4.2 | T13 |
| FR-4.3 | T14, T15 |
| FR-4.4 | T16 |
| FR-4.5 | T15 |
| NFR-4.1 | T13 |
| AD-1 | T0 |

## Ordem sugerida de execução
T0 ∥ T1 → T2 ∥ T3 → T4, T5, T6, T7 ∥ T8 ∥ T9 ∥ T10 → T11 ; T12 → T13 → T14 → T15 → T16 → T17.
