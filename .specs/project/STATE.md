# STATE — Memória do Projeto TraceCast

> Decisões, blockers, lições. Atualizado a cada sessão.

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
