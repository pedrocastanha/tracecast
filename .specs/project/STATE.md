# STATE — Memória do Projeto TraceCast

> Decisões, blockers, lições. Atualizado a cada sessão.

## Sessão 2026-07-14 — light-http-ingest + queue/spool

### Problema
VM 2vCPU/4GB (vm-aitracing-dev) sufoca com N bots → Mongo direto; request path bloqueava.

### Arquitetura nova (v0.3.0)
```
Bot request → finalize + span_filter(llm_tool)
  → put_nowait fila local (background_export)  [O(1), não bloqueia]
  → worker thread: serialize + batch POST HttpExporter
  → VM POST /api/ingest → fila server (1000) + spool JSONL
  → worker: bulk_write Mongo
  → dashboard lê Mongo
```

### Entregue
- `HttpExporter` (stdlib urllib, timeout 2s)
- `IngestService` + `POST /api/ingest` + `/api/ingest/batch` + health.ingest
- Client `ExportWorker` spool opcional (`TRACECAST_EXPORT_SPOOL`)
- Serialize no worker thread (não no request/event loop)
- Deploy VM `/home/pcastanheira/ai-tracing` wheel 0.3.0
- Consumers atualizados (sem commit): captacao, clara, atendimento, transferencia setup
- Load test: 300 concurrent POSTs → 300/300 202, 0 drop, exported_ok=301, list total 304

### Env prod bot
- `TRACECAST_HTTP_URL=http://136.115.42.200:8010/tracecast`
- `TRACECAST_SPAN_FILTER=llm_tool`
- `background_export=True` (no setup)

## Sessão 2026-07-09

### Implementado (sem SDD formal prévio)
- `background_export` real: fila limitada + worker + batch (flush_at / interval / max_batch_bytes)
- Serialize cedo (`to_dict` no enqueue)
- Truncate global de payload (`TRACECAST_MAX_PAYLOAD_CHARS`)
- Sample rate (`TRACECAST_SAMPLE_RATE`)
- Cap métricas hydrate (`TRACECAST_METRICS_MAX_TRACES`)
- Suite ~416 passed

### SDD criado — feature `export-resilience`
Path: `.specs/features/export-resilience/{spec,design,tasks}.md`  
PROJECT.md + ROADMAP.md criados em `.specs/project/`.

**MVP pedido pelo user:** se full save falhar → ainda persistir **data, tokens, projeto, tipo/nome** (`export_status=summary_only`).  
Também no SDD: retry+backoff, ExportStats + `/api/health`, UI badge/banner, P2 warn/projection, P3 overview card.

**Status:** Specify + Design + Tasks prontos; **Execute T1–T16 implementados** (código + testes + e2e bot-captacao).

### Execute progress — export-resilience
| Task | Status |
|------|--------|
| T1–T16 | ✅ implementados (suite 434 passed) |
| E2E bot-captacao | ✅ uvicorn + chat + dashboard (sem commit no bot) |

### E2E notes (bot-captacao 2026-07-09)
- Mongo remoto timeout → health mostra `export_retried` + `last_error`; dual JsonFile salvou full (33 spans).
- `/tracecast/api/health` com bloco `export` + `background_export: true`.
- Lista traces + detail + graph 200; SPA index/js/css 200.
- Alterações locais no bot (não commitadas): `background_export=True`, dual JsonL, `TRACECAST_JSONL_PATH`.

### span_filter=flow (2026-07-09)
- `Tracer(span_filter=...)` / `TRACECAST_SPAN_FILTER` modes: all|flow|llm_tool
- Captacao: 21→15 spans; flow `guard→router→service→final_guardrail→final_response` + LLMs c/ input/output
- Atendimento: 22→20; nodes reais + LLMs; noise Runnable/Prompt/agent/tools removido
- Bots: captacao + atendimento com flow default, logs de kept/dropped, dashboard montado
- Mongo GCP ainda timeout da rede local; JSONL local + health OK

### ADR-006 — Fallback summary no mesmo store (2026-07-09) [SPEC]
**Decisão:** summary de export parcial vive na **mesma** collection/tabela/JSONL de traces, com `export_status=summary_only` e `spans=[]`, não store separado.  
**Por quê:** listagem e contagem reusam `query`/`get`; operador vê o “buraco” com métricas mínimas.  
**Consequência:** reader/UI precisam distinguir full vs summary; Postgres pode embutir flags em `metadata` se schema rígido.

## Decisões (ADR)

### ADR-001 — Python-only (2026-06-13)
**Decisão:** descontinuar e remover a SDK TypeScript (`packages/tracecast-ts`). Foco total em Python.
**Por quê:** sem usuários TS; a maioria do público-alvo usa Python; manter duas SDKs + dois backends de
dashboard dobra custo e gera divergência. Tracing é in-process — uma lib Node não traceia processos
Python, então "TS único cobrindo os dois" é inviável para captura.
**Consequência:** captura, export, server e backend de dashboard vivem só em `tracecast-py`. O React SPA
(`packages/tracecast-dashboard`) permanece como frontend, servido estático pelo backend Python.

### ADR-002 — Backend de dashboard consolidado em Python (2026-06-13)
**Decisão:** o backend do dashboard fica em `tracecast-py` (FastAPI router + standalone server, que já
existem). Sem backend Node.
**Por quê:** elimina a duplicação `tracecast-py/dashboard/*` ↔ `tracecast-ts/src/dashboard/*` (C17).
**Consequência:** server standalone Python deployável numa VM, config por env (`TRACECAST_STORE`).

### ADR-003 — Schema de wire v2 (2026-06-13)
**Decisão:** schema único v2 com `parent_span_id`, `status`/`error` no span e `edges` no trace.
**Por quê:** sem hierarquia não há como reconstruir o grafo percorrido (G1/G4). Leitura retrocompatível
com v1.

### ADR-005 — Evaluation por golden dataset (2026-06-13) [SPEC]
**Decisão:** nova feature `golden-dataset-evaluation` (SDD em `.specs/features/golden-dataset-evaluation/`).
Decorator `@evaluator` (distinto de `@trace_cast`) marca o SUT + path(s) JSON; runner roda o agente sobre
cada caso (traceado, linkado por `trace_id`), judge híbrido (LLM-as-judge rubrica multi-critério 0–1 +
scorers determinísticos) pontua vs `expected`; resultados persistidos pelos mesmos exporters em store
separado (`tracecast_evals`); aba **Evaluators** no dashboard.
**Por quê:** observabilidade de produção não cobre qualidade contra referência; eval offline fecha o loop.
**Consequência:** disparo por CLI/script/endpoint; endpoint de trigger só com dashboard embutido (precisa
da fn em memória); server standalone é read-only para evals. Status: especificado, **não implementado**.

### ADR-004 — Save best-effort + erros visíveis (2026-06-13)
**Decisão:** nesta fase, parar de engolir exceções (log ERROR + hook `on_export_error`) e tornar
`aexport` não-bloqueante. Sem fila durável ainda.
**Por quê:** corrige a perda silenciosa (C9) e o bloqueio do event loop (C10) com baixo risco; fila
durável é escopo maior.

## Blockers / Bugs confirmados
- ✅ **C12** RESOLVIDO (T12): MongoExporter expõe `_collection` (+ alias `col`); reader lê `_collection or col`.
- ✅ **C9** RESOLVIDO (T8): export loga ERROR + hook `on_export_error`; nunca silencioso.

## Implementado (2026-06-13) — feature observability-reliability
Todas as tarefas T0–T17 entregues. Suite: **245 passed**. Resumo:
- Schema v2: `parent_span_id`, `status`/`error` (first-class), `edges` derivadas, `schema_version=2`.
- Captura: parent no callback LangChain; `@trace_span` p/ guardrails; `bind_context` p/ threads;
  aninhamento via ContextVar de span ativo; streaming OpenAI/Anthropic (sync+async).
- Save: erros não-silenciosos + hook; `aexport` não-bloqueante (offload thread); upsert Mongo + índices.
- Dashboard: bug Mongo reader corrigido; `query/get/count` pushdown (Postgres WHERE + conn read dedicada,
  Mongo find); endpoint `/api/traces/{id}/graph`; frontend DAG react-flow; prefix injetado no index.
- Server standalone Python: `tracecast-server` / `python -m tracecast.serve`, config por env
  (`TRACECAST_STORE` etc.), basic-auth + CORS. SDK TS removida.

## Ideias diferidas (v0.4+)
- Fila durável de export (buffer em disco + retry com backoff + flush no shutdown + batching).
- Instrumentor LangGraph nativo (rótulos de aresta verdadeiros via `compiled_graph.get_graph()`).
- Drivers async nativos (asyncpg/motor) em vez de offload em thread.
- Sampling / rate limiting de traces; multi-tenancy + RBAC no dashboard.

## Lições
- Tracing é in-process: a linguagem da SDK é determinada pela linguagem do app traceado, não por
  preferência de performance. O overhead de span é μs; o gargalo real é I/O do exporter.

## Preferências
- Usuário comunica em PT-BR. Modo caveman (full) ativo nas respostas.
- Tarefas leves (validação, state update, handoff) rodam bem em modelos mais rápidos/baratos.

## SDD criado (2026-06-17) — feature observability-platform (paridade LangFuse/LangSmith)
`.specs/features/observability-platform/{spec,design,tasks}.md`. 6 fases, 24 tasks (T1–T24), 18 reqs.
Pesquisa web feita (LangFuse/LangSmith/DeepEval/RAGAS). Decisões-chave:
- **Gap crítico G1:** `eval/` já existe (datasets, judge, scorers, runner, CLI) mas **nenhum exporter
  implementa `export_eval/query_evals/get_eval`** — resultados de eval não persistem. Fase 0 desbloqueia.
- Fases: 0 persistência eval · 1 `tracecast.score()` (Score ligado a trace de produção) · 2 métricas
  nomeadas (faithfulness/answer_relevancy/context_*/toxicity, reusa LLMJudge+SCORERS) · 3 compare A/B
  de runs · 4 online eval por amostragem + `add_to_dataset` · 5 prompt management versionado.
- Princípio: zero infra nova; tudo via contrato de exporter (AD-1) e dashboard existentes.
- AD-10: paridade TS fora de escopo (tracecast-ts/src só tem dashboard/, SDK TS foi removida — C17).
- Decisões do usuário (2026-06-17): (1) entregar em ordem 0→5; (2) `detoxify` opcional aceito;
  (3) backend+endpoints primeiro, UI depois.

### EXECUTADO (2026-06-17) — backend completo das 6 fases, TDD, branch `feature/observability-platform`
Suite: **351 passed** (era 300 no baseline desta sessão). Commits atômicos por fatia. Status:
- **Fase 0 (G1)** ✅ `export_eval/query_evals/get_eval` nos 4 exporters + endpoints `/api/evals`,
  `/api/evals/{id}`, `POST /api/evals/run`. Eval agora persiste e aparece no dashboard.
- **Fase 1 (G2)** ✅ `models/score.py` (Score validado) + `tracecast.score()` + `export_score`/
  `query_scores` + `ScoreReader` + `GET /api/traces/{id}/scores`.
- **Fase 2 (G3)** ✅ `eval/metrics.py` registry: presets LLM (faithfulness, answer_relevancy,
  context_precision/recall, hallucination, conciseness) + heurística `toxicity` (detoxify lazy,
  fallback termos). Judge/dataset/runner ganham `context` (RAG). Runner resolve nomes de métrica.
- **Fase 3 (G5)** ✅ `eval/compare.py` + `GET /api/evals/compare` (registrado ANTES de `/{run_id}`).
- **Fase 4 (G6,G7)** ✅ `eval/online.py` OnlineEval (amostragem, background, best-effort) + hook no
  Tracer (`online_eval=`, chamado após export em `_export`/`_aexport`). `add_to_dataset()` promove
  trace a caso golden.
- **Fase 5 (G4)** ✅ `prompts/` (PromptVersion + client com cache TTL, label resolution, auto-link
  versão→trace) + persistência nos 4 exporters + `PromptReader` + `/api/prompts`.
- **PENDENTE (UI)**: T10 (painel Scores no trace detail), T16-UI (view compare), T24 (aba Prompts),
  T18 doc README do OnlineEval. Frontend em `dashboard/static/` (build React). Backend/endpoints prontos.
- Novos métodos de exporter são opcionais no BaseExporter (default no-op/[]) → degradação graciosa.
  Idempotência: Mongo upsert, Postgres ON CONFLICT, file/dict dedup por chave lógica.
