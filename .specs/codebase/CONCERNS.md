# CONCERNS — Auditoria de Verificação (2026-06-13)

Resultado da verificação dos 4 objetivos contra o código real. Cada item tem severidade, local
(`file:line`) e impacto. Severidade: 🔴 crítico (impede objetivo) · 🟠 alto · 🟡 médio.

## G1 — Cobertura de tracing

| # | Sev | Local | Achado |
|---|-----|-------|--------|
| C1 | 🔴 | `models/span.py` (sem campo); `integrations/langchain.py:129` | Span não tem `parent_span_id`. O callback lê `parent_run_id` e **descarta**. Lista de spans é flat → impossível reconstruir árvore/grafo. |
| C2 | 🔴 | `integrations/langchain.py` (on_chain_*) | Nós LangGraph chegam como spans `agent`, mas **arestas/roteamento não** — não são eventos de callback. Topologia do grafo se perde. |
| C3 | 🟠 | `core/tracer.py:11` (`_current_trace` ContextVar) | ContextVar não propaga para threads (`run_in_executor`, ThreadPoolExecutor). `Tracer.current()` → `None` no worker → spans dropados em silêncio. |
| C4 | 🟡 | `decorators.py` + `instrument.py:13` | Decorator na rota só abre o Trace; spans internos dependem de `auto_instrument()` ter rodado OU client estar wrapped. Decorator sozinho ≠ tracing do fluxo. Falta doc/garantia. |
| C5 | 🟡 | `integrations/langchain.py:95-117` | Guardrails implementados como função Python pura (não tool/chain) são invisíveis. Falta `@trace_span` para funções arbitrárias. |

## G2 — Confiabilidade dos dados

| # | Sev | Local | Achado |
|---|-----|-------|--------|
| C6 | 🟠 | `core/token_counter.py` | Streaming: usage costuma vir ausente → `tokens_in/out = 0` → custo 0. Sem acumulação nem `stream_options={"include_usage"}`. |
| C7 | 🟡 | `integrations/langchain.py:167`; `integrations/llm.py:49` | Erro de span vai para `metadata._error`. Não há `status` first-class → dashboard não distingue span ok de span falho. |
| C8 | 🟢 | `models/trace.py:38-40` | `trace.model` = LLM span com mais tokens. Heurística aceitável; documentar. |

## G3 — Save

| # | Sev | Local | Achado |
|---|-----|-------|--------|
| C9 | 🔴 | `core/tracer.py:92-94,100-102` | Exceção de export é engolida com `warnings.warn`. **Perda silenciosa de dados.** Sem retry/buffer/batch/hook. |
| C10 | 🟠 | `exporters/base.py:14-15` | `aexport` default chama `export` síncrono. Postgres/Mongo fazem I/O bloqueante **no event loop** de apps async. |
| C11 | 🟡 | `exporters/mongo.py:34` | `insert_one` sem upsert → re-export duplica. Postgres tem `ON CONFLICT` (ok). |

## G4 — Dashboard

| # | Sev | Local | Achado |
|---|-----|-------|--------|
| C12 | 🔴 | `dashboard/reader.py:102` vs `exporters/mongo.py:26` | Reader lê `exporter._collection`; exporter armazena `self.col`. **Dashboard sempre mostra 0 traces de Mongo.** Bug de atributo. |
| C13 | 🔴 | `dashboard/reader.py` + `aggregator.py` | Filtros (data/projeto/horário) aplicados em memória sobre os **últimos 500** traces (`max_traces=500`, `SELECT *` sem WHERE em `reader.py:117`). Dataset grande: filtros perdem dados antigos, não escala. |
| C14 | 🔴 | `dashboard/components/SpanTimeline.tsx`; `pages/TraceDetail.tsx` | Detalhe do trace renderiza **lista flat** de spans. Sem grafo/aninhamento/arestas → não atende "ver todo o grafo percorrido". |
| C15 | 🟠 | `dashboard/reader.py:111-123` | Reader reusa a **conexão de escrita** do exporter (`_conn`) para ler. Hazard de thread-safety entre writer e dashboard. |
| C16 | 🟡 | `dashboard/standalone.py`; `core/tracer.py:108-170` | Server standalone existe, mas sem config por env nem auth real além de tuple básico. Consumo remoto: ok p/ Postgres (DSN), quebrado p/ Mongo (C12), JsonFile precisa FS compartilhado, Dict não serve remoto. |
| C17 | 🟡 | Duplicação `tracecast-py/dashboard/*` ↔ `tracecast-ts/src/dashboard/*` | Backend do dashboard mantido duas vezes. Risco de divergência. Resolvido por AD-1: **deletar `tracecast-ts`** e manter só o backend Python + frontend React. |

## Verificação positiva (o que JÁ funciona)

- Decorator/middleware abre Trace em ContextVar e propaga para tasks asyncio filhas. ✅
- LangChain callback auto-registrado via `register_configure_hook` (langchain ≥0.2). ✅
- `_finalize()` agrega tokens/custo/latência da soma dos spans corretamente. ✅
- Postgres: schema dinâmico + `ON CONFLICT` upsert + include/exclude fields. ✅
- Cálculo de latência por span e por trace via timestamps UTC. ✅
- Reader tem cache TTL 5s + paginação + agregação por sessão/projeto. ✅
