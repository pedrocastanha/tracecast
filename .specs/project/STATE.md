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

## Correção de STATE stale (2026-06-30)
A entrada acima ("PENDENTE (UI)") estava desatualizada: `git log -- packages/tracecast-dashboard`
mostra commit `d10ffbf` ("observability platform UI — scores, run compare, prompts (#3)") já
entregue depois de 2026-06-17. **M3 do `ROADMAP.md` está completo**, não pendente. Lição: sempre
checar `git log` do diretório antes de confiar em status registrado em `STATE.md` — memória pode
ficar stale entre sessões.

## SDD/roadmap criado (2026-06-30) — pesquisa Langfuse/LangSmith + 4 novas features
`.specs/research/langfuse-comparison.md` (pesquisa completa via WebSearch/WebFetch + leitura do
código fonte do `langfuse-python` CallbackHandler + introspecção local de `langgraph`/
`langchain_core`), `.specs/project/ROADMAP.md` (novo, M1-M7), 4 feature dirs em
`.specs/features/`. Decisões-chave:

- **Achado central:** granularidade de span em LangGraph não é resolvida nem pelo Langfuse (só
  esconde via tag `langsmith:hidden`, ainda grava tudo) nem pelo TraceCast hoje (bug: `tc_display`
  usa `bool(langgraph_node)` em vez de `name == langgraph_node`, super-marca chains aninhadas
  dentro de um node). Confirmado empiricamente rodando `langgraph==1.0.1` local com callback de
  debug — ver `.specs/features/langgraph-native-spans/design.md` seção "Evidência empírica".
- **`langgraph-native-spans`** (spec+design+tasks completos, pronto para Execute): classifica
  span em tempo de captura (não só leitura), descarta canalização (`RunnableSequence`/
  `ChannelWrite`/branch runnables) com reparenting correto, usa `compiled_graph.get_graph()` para
  topologia real (edges + label de branch condicional) em vez de heurística de tempo. Resolve C2
  do `CONCERNS.md`. Default `span_capture="curated"` é breaking change de comportamento
  (documentar no CHANGELOG), modo `"all"` preserva paridade para quem depender.
- **`dynamic-guardrails`** (spec only): guardrail vira span de primeira classe
  (`allow`/`block`/`flag`), estático (regex/PII) ou dinâmico (reusa `eval.judge.LLMJudge` — zero
  motor de judge novo). Fail-open default em erro de judge. Sem dependência obrigatória nova
  (LLM Guard/Presidio/NeMo Guardrails ficam opcionais).
- **`dashboard-ux-refresh`** (spec only): tokens de design + estados padronizados (P1), P50/P95/
  P99 de latência (gap confirmado vs LangSmith) + `cmd+k` (P2), anotação lite via `Score` já
  existente sem fila multiusuário (P3).
- **`performance-optimization`** (spec only): C10 do `CONCERNS.md` confirmado ainda parcialmente
  aberto — `tracer.py:101` chama `_export()` síncrono dentro do `finally` do `with tracer.trace()`,
  bloqueando o caminho de retorno na I/O do exporter. P1 = `async_export` com worker dedicado
  (não thread-per-trace como `atrace()` faz hoje). P2 = batching opcional + `sample_rate` opt-in
  que **nunca** dropa trace com erro (aprendizado direto do ponto de dor do LangSmith: sampling
  forçado por custo já causou perda de trace relevante para usuários deles).
- Addendum LangSmith: gaps deles (cobrança por trace, sampling forçado, OTel só parcial,
  instrumentação fraca fora do LangChain) já são coberto pelo roadmap existente ou já são pontos
  fortes do TraceCast (instrumentors standalone para OpenAI/Anthropic/Gemini/CrewAI/LlamaIndex já
  existem, sem depender de LangChain — vale destacar em marketing, não é trabalho novo).
- Todas as 4 features estão em `.specs/features/`; só `langgraph-native-spans` tem design+tasks
  prontos. As outras 3 aguardam o usuário priorizar antes de aprofundar em Design.
