# Export Resilience — Specification

> **Status:** Specify complete · Design · Tasks  
> **Escopo:** Large (multi-componente: core export, exporters, dashboard, métricas)  
> **Branch sugerida:** `feature/export-resilience`  
> **Última atualização:** 2026-07-09  
> **Contexto:** VM GCP 2 vCPU / 4 GB; fila/batch/truncate já existem; save full ainda pode falhar (rede, BSON size, timeout, disco).

## Problem Statement

Quando o export do trace **completo** falha (Mongo timeout, documento grande demais, Postgres down, etc.), hoje o TraceCast só loga WARNING e chama `on_export_error` (e só se o item ainda for `Trace`, não `dict`). O operador perde **tudo** daquela request: custo, volume de tokens, projeto e momento.

Em produção self-host isso é pior que “trace sem detalhe”: fica **cego para custo e tráfego**. O mínimo aceitável (inspirado em best-effort de SDKs de observabilidade) é: **se o full save falhar, ainda persistir um resumo** (data, tokens, projeto, tipo/nome do trace).

Além disso, drops de fila e falhas de export não têm **superfície de health** no dashboard — o app “parece ok” enquanto o sink morre.

## Goals

- [ ] WHEN full export falhar THEN o sistema SHALL tentar persistir um **Trace Summary** com campos mínimos (data, tokens, projeto, tipo)
- [ ] WHEN export falhar por erro transitório THEN o sistema SHALL re-tentar com backoff limitado antes do fallback
- [ ] WHEN o operador abrir health/overview THEN o sistema SHALL expor dropped/queue/last_error/summary_fallbacks
- [ ] WHEN listar traces THEN summaries parciais SHALL aparecer marcados (não sumir, não parecer full)
- [ ] Zero perda silenciosa: todo caminho de falha loga + contadores + (quando possível) summary

## Out of Scope

| Item | Reason |
|------|--------|
| Spool durável em disco (JSONL buffer entre process restarts) | Feature seguinte; memória+batch já cobrem pico de processo vivo |
| Rewrite OTEL / multi-sink fanout | Fora do problema de fallback mínimo |
| Aggregates SQL/Mongo nativos completos (GROUP BY tokens/dia) | Desejável; coberto só o necessário para summary + health |
| Sampling inteligente “100% erros” | Spec separada; aqui só sample_rate já existente |
| Auth/RBAC do dashboard | Independente |
| Drivers async nativos (motor/asyncpg) | Não resolve falha de save |

---

## User Stories

### P1: Fallback de resumo quando full save falha ⭐ MVP

**User Story:** Como operador de um agente em prod, quero que, se o save completo do trace falhar, o sistema ainda grave data, tokens gastos, projeto e tipo do trace, para eu não perder visibilidade de custo e volume.

**Why P1:** É o pedido explícito e o maior gap de confiança pós-fila.

**Acceptance Criteria:**

1. WHEN `exporter.export` / `export_docs_batch` levantar exceção após esgotar retries THEN o sistema SHALL construir um documento summary a partir do payload original (dict ou Trace) contendo **no mínimo**:
   - `trace_id`
   - `started_at` (e `finished_at` se existir)
   - `total_tokens`, `total_tokens_in`, `total_tokens_out` (e `total_tokens_in_cached` se existir)
   - `cost_usd` se existir
   - `project_id` e/ou `project_name` se existirem
   - `name` (tipo/nome do trace, ex. rota ou agente)
   - `model` se existir
   - `export_status` = `"summary_only"` (ou equivalente estável)
   - `export_error` = mensagem curta do erro (truncada)
   - `schema_version` compatível com leitores
2. WHEN o summary for gerado THEN o sistema SHALL chamar `exporter.export_summary(summary_doc)` (ou caminho equivalente documentado) em cada exporter que falhou no full save **sem** re-lançar se o summary também falhar (log + contador).
3. WHEN o full save tiver sucesso THEN o sistema SHALL **não** gravar summary redundante.
4. WHEN o summary for persistido no mesmo store de traces THEN o reader/dashboard SHALL conseguir listá-lo e distingui-lo de um full trace (`export_status` / flag `is_summary`).
5. WHEN apenas campos de tokens estiverem zerados (span sem usage) THEN o summary SHALL ainda gravar data + projeto + name + `export_status`.

**Independent Test:** Mock exporter que sempre falha em `export_docs_batch` e implementa `export_summary`; após `trace` + `flush`, summary presente com tokens/projeto/data.

---

### P1: Retry com backoff antes do fallback

**User Story:** Como operador, quero que falhas de rede transitórias sejam re-tentadas antes de cair no summary, para não degradar dados em blips curtos.

**Why P1:** Sem retry, summary vira o caminho comum e perde-se o grafo sem necessidade.

**Acceptance Criteria:**

1. WHEN um export full falhar com exceção THEN o worker/caminho sync SHALL re-tentar até `N` vezes (default **3**, env `TRACECAST_EXPORT_RETRIES`).
2. WHEN re-tentar THEN o sistema SHALL esperar backoff exponencial com jitter (base default **0.2s**, env `TRACECAST_EXPORT_RETRY_BASE`).
3. WHEN todas as tentativas falharem THEN o sistema SHALL executar o fluxo de summary (P1 MVP).
4. WHEN a falha for claramente não-retriável (opcional: validação de schema local) THEN o sistema MAY pular retries e ir direto ao summary — se implementado, documentar; senão, retry em todas e aceitar custo baixo.

**Independent Test:** Exporter falha 2x e passa na 3ª → full doc gravado, zero summary; falha 3x → summary.

---

### P1: Health / contadores de export

**User Story:** Como operador, quero ver no health (e idealmente Overview) quantos exports falharam, quantos foram dropados da fila e quantos caíram em summary, para saber se o sink está saudável.

**Why P1:** Fallback sem visibilidade ainda é semi-cego.

**Acceptance Criteria:**

1. WHEN o Tracer exportar (sync ou worker) THEN contadores em memória SHALL atualizar: `exported_ok`, `export_failed`, `export_retried`, `summary_fallback`, `queue_dropped` (reusar dropped da fila).
2. WHEN `GET /api/health` (ou path documentado sob o prefixo do dashboard) THEN a resposta SHALL incluir bloco `export` com esses contadores + `queue_size` (se background) + `queue_max` + `last_error` (mensagem + timestamp ISO, se houver).
3. WHEN não houver Tracer/worker no processo standalone read-only THEN health SHALL indicar `export: null` ou `mode: "read_only"` sem 500.
4. Contadores NÃO precisam ser multi-process / persistidos (reset no restart é OK e documentado).

**Independent Test:** Forçar 1 fail → `export_failed >= 1` e `summary_fallback >= 1` no health do app com mount.

---

### P1: Leitura e UI mínima de summary

**User Story:** Como dev no dashboard, quero ver traces parciais na lista com badge claro e, no detalhe, mensagem de que o payload completo não foi salvo.

**Why P1:** Summary invisível = feature morta.

**Acceptance Criteria:**

1. WHEN um doc com `export_status == "summary_only"` for listado THEN a API de listagem SHALL devolvê-lo com os campos de resumo e um flag/campo estável para o front.
2. WHEN o usuário abrir o detalhe de um summary THEN o sistema SHALL retornar o summary (não 404) e o front SHALL mostrar aviso “export parcial — spans/payload indisponíveis” + cards de tokens/custo/projeto/data.
3. WHEN o grafo for pedido para um summary THEN o sistema SHALL retornar grafo vazio ou 200 com `nodes: [], edges: []` (não 500).

**Independent Test:** Persist summary via DictExporter; `GET /api/traces` contém item; `GET /api/traces/{id}` retorna summary.

---

### P2: Warn se sink persistente sem `background_export`

**User Story:** Como dev integrando TraceCast, quero um aviso se configurar Mongo/Postgres sem `background_export=True`, para não repetir OOM/bloqueio em prod.

**Why P2:** Previne regressão operacional; não é o core do fallback.

**Acceptance Criteria:**

1. WHEN `Tracer` for criado com exporter Mongo/Postgres/JsonFile e `background_export=False` THEN o sistema SHALL emitir `warnings.warn` uma vez (stacklevel adequado) citando `background_export=True`.
2. WHEN `background_export=True` ou só `DictExporter` THEN **não** warn.

---

### P2: Projeção leve na listagem (sem input/output de spans)

**User Story:** Como usuário do dashboard em VM pequena, quero que a lista de traces não traga payloads de spans, só metadados e totais.

**Why P2:** Reduz RAM/IO do dashboard; complementa resiliência.

**Acceptance Criteria:**

1. WHEN `query` for usado para listagem paginada THEN o exporter (Mongo/Postgres) SHALL poder retornar docs **sem** arrays pesados de `spans[].input/output` (projection ou strip).
2. WHEN o detalhe for pedido THEN o full doc (ou summary) SHALL ser retornado.
3. Compat: exporters sem projection continuam funcionando (strip no reader como fallback).

---

### P3: Overview card “Export health”

**User Story:** Como operador, quero um card no Overview com dropped / failed / summary fallbacks.

**Why P3:** Health API basta no MVP; card é UX.

**Acceptance Criteria:**

1. WHEN Overview carregar e `/api/health` tiver bloco `export` THEN o card SHALL exibir os contadores principais.
2. WHEN `export` ausente THEN o card SHALL ocultar-se ou mostrar “N/A”.

---

## Edge Cases

- WHEN **todos** os exporters falharem no full e no summary THEN o sistema SHALL apenas logar + contadores; app NÃO crasha.
- WHEN houver **múltiplos** exporters e só um falhar THEN o sistema SHALL (a) ainda considerar sucesso parcial dos outros; (b) tentar summary **só** no(s) exporter(s) que falharam no full.
- WHEN o doc enfileirado for dict já serializado (background path) THEN o summary SHALL ser derivado do dict sem re-hidratar Trace completo (salvo se necessário).
- WHEN `sample_rate` descartar o trace THEN o sistema SHALL **não** gerar summary (não houve intenção de export).
- WHEN a fila dropar o item (`queue full`) THEN o sistema SHALL **não** inventar summary (não há payload); só incrementar `queue_dropped`.
- WHEN summary for gravado e um retry posterior de full (não aplicável nesta spec) THEN N/A — full e summary são do mesmo ciclo de export.
- WHEN `trace_id` colidir no upsert do summary após full falho THEN summary upsert por `trace_id` é OK (mesmo id).
- WHEN payload full exceder limite do Mongo (16MB) THEN retry não resolve; summary SHALL ser pequeno o suficiente para caber.

---

## Requirement Traceability

| ID | Requirement | Story | Priority |
|----|-------------|-------|----------|
| FB-01 | Summary mínimo em falha de full export | P1 Fallback | P1 |
| FB-02 | Campos obrigatórios do summary (data, tokens, projeto, name/tipo) | P1 Fallback | P1 |
| FB-03 | `export_status=summary_only` + `export_error` | P1 Fallback | P1 |
| FB-04 | `export_summary` (ou equivalente) nos exporters core | P1 Fallback | P1 |
| FB-05 | Não duplicar summary se full ok | P1 Fallback | P1 |
| FB-06 | Summary não derruba o app se falhar | Edge | P1 |
| FB-07 | Summary só nos exporters que falharam | Edge multi-exporter | P1 |
| RT-01 | Retries configuráveis com backoff | P1 Retry | P1 |
| RT-02 | Após retries → fallback summary | P1 Retry | P1 |
| HL-01 | Contadores in-memory de export | P1 Health | P1 |
| HL-02 | `/api/health` expõe bloco export | P1 Health | P1 |
| UI-01 | Lista marca summary | P1 UI | P1 |
| UI-02 | Detail de summary sem 404/500 | P1 UI | P1 |
| UI-03 | Graph vazio seguro para summary | P1 UI | P1 |
| OP-01 | Warn sem background_export em sink real | P2 Warn | P2 |
| PR-01 | Listagem sem payload de spans | P2 Projection | P2 |
| OV-01 | Card Overview export health | P3 Overview | P3 |

---

## Success Metrics

| Métrica | Alvo |
|---------|------|
| Full export falha + summary ok | ≥ 1 summary no store com tokens/projeto/data |
| App sob exporter sempre-falho | 0 crash; contadores > 0 |
| Suite pytest | gate full verde após feature |
| Tamanho típico do summary doc | << full trace (sem spans I/O) — ordem de KB |

---

## Open Questions (resolvidas nesta spec)

| # | Questão | Decisão |
|---|---------|---------|
| Q1 | Summary na mesma collection/tabela ou store separado? | **Mesma store de traces**, com `export_status` / flag, para listagem e métricas simples reutilizarem `query`. |
| Q2 | Incluir `spans: []` ou omitir? | **`spans: []` e `edges: []`** sempre no summary wire, para hydrate não quebrar. |
| Q3 | Hook `on_export_error` no path dict? | **Sim** — passar summary dict ou pseudo; no mínimo invocar com o erro e um Trace reconstruído leve / dict documentado. Preferência: estender hook para aceitar `Union[Trace, dict]` sem quebrar callables atuais (try Trace first). |
| Q4 | online_eval no fallback? | **Não** rodar online_eval sobre summary-only. |

---

## References

- Código atual: `core/tracer.py`, `core/export_queue.py`, `exporters/*`, `dashboard/router.py` health
- Prior art: Langfuse flush/retry best-effort; LangSmith batch drain + error log sem crash app
- ADR-004 (STATE.md): save best-effort + erros visíveis — esta feature **estende** com fallback de dados mínimos
