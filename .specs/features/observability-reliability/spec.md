# SDD — Observabilidade Confiável de Agentes (TraceCast v0.2 → v0.3)

> **Status:** Specify
> **Escopo:** Large/Complex (multi-componente, novo domínio de hierarquia + grafo)
> **Branch:** `feature/v0.2.0`
> **Última atualização:** 2026-06-13

## 1. Problema

TraceCast é um SDK de observabilidade self-hosted (inspirado em LangSmith/Langfuse) que captura
interações com LLMs e exporta para Mongo/Postgres/JSONL. O usuário precisa garantir que, em sistemas
reais (LangGraph com muitos nós, arestas, guardrails), o produto:

1. Rastreia **todo** o fluxo de uma request, não só a chamada LLM final.
2. Gera dados **confiáveis** (latência, tokens, quem passou pela request).
3. **Salva** de forma confiável e re-consumível.
4. Tem um **dashboard** que filtra (data/projeto/horário), mostra o **grafo percorrido**, e detalha
   cada etapa — deployável standalone numa VM apontando para o storage remoto.

A auditoria de código (ver `.specs/codebase/CONCERNS.md`) confirmou que a mecânica base existe, mas há
**lacunas estruturais** que impedem cada um desses 4 objetivos de serem cumpridos com confiança.

## 2. Decisões de Arquitetura (ver ADR-001/ADR-002 em STATE.md)

- **AD-1** **Python-only.** A SDK TypeScript (`packages/tracecast-ts`) é **descontinuada e removida** —
  sem usuários e a maioria do público usa Python. Toda captura, export, server e backend de dashboard
  passam a viver exclusivamente em `tracecast-py`. (Removida a hipótese "lib só em TS": tracing é
  in-process, um tracer Node não traceia um processo Python.)
- **AD-2** O backend do dashboard fica **consolidado em `tracecast-py`** (FastAPI router + server
  standalone, que já existem). O React SPA `packages/tracecast-dashboard` é apenas o **frontend** —
  compila para estático e é servido pelo backend Python. Não há mais backend Node duplicado.
- **AD-3** Existe **um schema de wire único (v2)**, fonte de verdade no `tracecast-py`. Inclui
  `parent_span_id`, `status`, e topologia de grafo (`edges`).
- **AD-4** Confiabilidade do save é **best-effort + erros visíveis** nesta fase: parar de engolir
  exceções, expor falhas via logger/hook, export assíncrono não-bloqueante. Fila durável fica para v0.4.

## 3. Requisitos

### G1 — Cobertura completa de tracing

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-1.1 | Cada span carrega `parent_span_id`; o trace reconstrói a árvore de execução. | Dado um fluxo aninhado (chain → tool → llm), o trace salvo permite reconstruir pai→filho sem ambiguidade. |
| FR-1.2 | Nós LangGraph são capturados como spans com pai correto. | Um grafo de N nós produz ≥ N spans `agent`/`tool`/`llm` ligados ao span da request. |
| FR-1.3 | A topologia do grafo (arestas/roteamento) é capturada. | O trace contém a lista de arestas percorridas (`from_node → to_node`), incluindo condicionais. |
| FR-1.4 | Contexto do trace propaga através de threads e executors. | Um nó rodando em `run_in_executor`/ThreadPool ainda anexa spans ao trace ativo (0 spans perdidos). |
| FR-1.5 | Funções arbitrárias (guardrails, validações) são traceáveis via decorator de span. | `@trace_span` em uma função guardrail produz um span filho com input/output/latência. |
| FR-1.6 | A request agregada reporta latência total e tokens totais corretos. | `trace.latency_ms` == wall-clock da request; `total_tokens` == soma dos spans. |

### G2 — Confiabilidade dos dados

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-2.1 | Span tem `status` first-class (`ok`/`error`) + mensagem de erro. | Span com exceção tem `status="error"` e `error` legível, não enterrado em `metadata._error`. |
| FR-2.2 | Tokens são capturados em respostas streaming. | Chamada streaming (OpenAI/Anthropic) registra `tokens_in/out > 0` e custo > 0. |
| NFR-2.1 | Exatidão verificável de tokens/custo/latência. | Suite de testes compara valores capturados com fixtures de resposta conhecidas (tolerância 0 para tokens). |
| NFR-2.2 | Concorrência: requests paralelas não cruzam spans. | Sob 50 requests concorrentes, nenhum span aparece no trace errado. |

### G3 — Save confiável

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-3.1 | Falha de exporter não é silenciosa. | Exceção de export é logada em nível ERROR e dispara hook `on_export_error`; nunca só `warnings.warn`. |
| FR-3.2 | Export assíncrono não bloqueia o event loop. | Em app async, `aexport` de Postgres/Mongo roda fora do loop (driver async ou offload em thread). |
| FR-3.3 | Save é idempotente por `trace_id`. | Re-exportar o mesmo trace faz upsert (Postgres já tem; Mongo precisa) — sem duplicatas. |
| NFR-3.1 | Round-trip íntegro. | Para cada exporter, `read(export(trace)) == trace` (campos de schema v2 preservados, incluindo spans/parent/edges). |

### G4 — Dashboard

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-4.1 | Reader Mongo funciona. | **BUG ATUAL:** reader lê `exporter._collection`, exporter expõe `self.col` → dashboard mostra 0 traces. Corrigir + teste. |
| FR-4.2 | Filtros (data, projeto, sessão, horário) são server-side no storage. | Filtros aplicados via query no DB (WHERE/find), não em memória sobre os últimos 500. Dataset grande funciona. |
| FR-4.3 | Visualização DAG do fluxo percorrido. | `TraceDetail` renderiza grafo nós+arestas (react-flow), refletindo a ordem/topologia real de execução. |
| FR-4.4 | Server standalone Python deployável, config por env. | `tracecast.serve()` (ou container) sobe numa VM lendo `TRACECAST_STORE` remoto; sem SDK embarcado no app de produção. |
| FR-4.5 | Detalhe por etapa preservado. | Clicar num nó do DAG mostra input/output/tokens/custo/latência/status daquela etapa. |
| NFR-4.1 | Leitura remota sem acoplamento de escrita. | Reader não compartilha a conexão de escrita do exporter; usa pool próprio read-only. |

## 4. Fora de escopo (desta fase)

- Fila durável com persistência em disco + retry com backoff (v0.4 — ver FR diferido em STATE.md).
- Sampling / rate limiting de traces.
- Multi-tenancy / RBAC no dashboard (só auth básica).
- Manter ou evoluir a SDK TS — está descontinuada e será removida (AD-1).

## 5. Rastreabilidade

Mapa requisito → tarefa em `tasks.md`. Cada tarefa referencia o(s) ID(s) que satisfaz.
