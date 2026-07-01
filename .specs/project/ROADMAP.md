# Roadmap — TraceCast

**Milestone atual:** M2 — Captura correta (LangGraph nativo)
**Status:** Planning

> Baseado em `.specs/research/langfuse-comparison.md` (2026-06-30). Princípio transversal mantido
> em todo o roadmap: **zero infraestrutura nova**, tudo via contrato de exporter e dashboard já
> existentes (ver AD-1 do SDD `observability-platform`).

---

## M1 — Confiabilidade e schema v2 (COMPLETO)

**Goal:** Tracing de produção correto: hierarquia de spans, save não-silencioso, dashboard com DAG.

### Features

**observability-reliability** — COMPLETE (2026-06-13, T0-T17, 245 testes)

- Schema v2 (`parent_span_id`, `status`/`error`, `edges`)
- Export com erro visível + hook `on_export_error`, `aexport` não-bloqueante
- Dashboard: bug reader Mongo corrigido, endpoint de grafo, DAG react-flow

**golden-dataset-evaluation** — COMPLETE

- `@evaluator`, runner, judge híbrido, scorers determinísticos, aba Evaluators

---

## M2 — Captura correta (LangGraph nativo)

**Goal:** Spans corretos por padrão em LangGraph — só os necessários (nodes reais, LLM, tool),
topologia real (edges + labels de branch condicional) em vez de heurística de tempo.

### Features

**langgraph-native-spans** — PLANNED

- Classificação de span em tempo de captura (`is_node_boundary` via `name == langgraph_node`,
  igual à convenção interna do próprio LangGraph)
- Descarte de spans de canalização (RunnableSequence/ChannelWrite/branch runnables) com
  reparenting correto (LLM/Tool nunca ficam órfãos)
- Topologia real via `compiled_graph.get_graph()` — edges + labels de branch condicional
- Modo `span_capture="all"` para debug/backward-compat
- Ver `.specs/features/langgraph-native-spans/spec.md`

**Por quê agora:** gap não-resolvido identificado na auditoria original (C2 em `CONCERNS.md`) e
confirmado pela comparação com Langfuse — nenhuma das duas ferramentas resolve isso puramente via
captura; TraceCast vai resolver melhor que o estado da arte (Langfuse só esconde via tag, não
descarta; TraceCast descarta com reparenting correto).

---

## M3 — UI de paridade LangFuse/LangSmith (COMPLETO)

**Goal:** Fechar a lacuna de UI do SDD `observability-platform`.

### Features

**observability-platform (UI)** — COMPLETE (commit `d10ffbf`, "observability platform UI —
scores, run compare, prompts"). `STATE.md` estava desatualizado sobre isso (dizia "UI pendente");
corrigido nesta sessão (2026-06-30) após checar `git log -- packages/tracecast-dashboard`.

- Scores no detalhe do trace ✅, comparação A/B de runs ✅, aba Prompts ✅
- Pendência residual pequena: confirmar se T18 (doc README do OnlineEval) foi feito — não
  verificado nesta sessão, baixo risco, checar antes de fechar M3 de vez.

---

## M4 — Interoperabilidade e DX de agente (avaliar, baixo esforço)

**Goal:** Reduzir fricção de quem já usa Langfuse/LangSmith e de agentes de IA (Claude Code e
similares) operando sobre o TraceCast.

### Features

**otel-export-adapter** — PLANNED (P3)

- Exporter opcional que traduz `Span`/`Trace` para OpenTelemetry (não substitui os exporters
  atuais — aditivo). Permite plugar em Grafana Tempo/Jaeger/Datadog sem abandonar o schema
  próprio.

**tracecast-cli** — PLANNED (P3)

- CLI fina para rodar `@evaluator` em CI/CD e consultar runs/scores sem abrir o dashboard.

**agent-tooling (MCP server + SKILL.md)** — PLANNED (P3)

- Servidor MCP read-only sobre `TraceReader`/`EvalReader`/`ScoreReader` (consultar traces, evals,
  scores via linguagem natural) + `SKILL.md` para agentes tipo Claude Code interagirem com o
  TraceCast do próprio projeto. Reaproveita 100% os readers existentes.

---

## M5 — Guardrails dinâmicos e ergonomia de evaluators

**Goal:** Guardrail vira span de primeira classe com decisão estruturada (`allow`/`block`/
`flag`), estático (regex/PII) ou dinâmico (LLM-as-judge reaproveitando `eval/LLMJudge`), sem
adotar framework pesado de terceiros (LLM Guard/NeMo Guardrails ficam como integração opcional,
não dependência obrigatória).

### Features

**dynamic-guardrails** — PLANNED

- `@guardrail` decorator + `GuardrailResult` + span `SpanType.GUARDRAIL`
- `LLMGuardrail` (dinâmico, reusa `eval.judge.LLMJudge`) e `MetricGuardrail` (reusa `METRICS`)
- Presets estáticos (`regex_pii`, `banned_terms`, `pii_advanced` via Presidio opcional)
- Ver `.specs/features/dynamic-guardrails/spec.md`

**Por quê:** pedido explícito do usuário + gap real (C5 do `CONCERNS.md` nunca foi resolvido,
guardrail hoje é convenção informal sem reuso do `eval/` já construído).

---

## M6 — Refresh de UI/UX do dashboard

**Goal:** Acabamento e ergonomia — não falta funcionalidade (M3 já entregou scores/compare/
prompts), falta consistência visual, percentis de latência, busca rápida e uma forma leve de
revisão por não-engenheiros.

### Features

**dashboard-ux-refresh** — PLANNED

- Tokens de design centralizados + estados vazio/loading/erro padronizados (P1)
- P50/P95/P99 de latência/custo (P2), command palette `cmd+k` (P2)
- Anotação lite de trace via `Score` já existente, sem fila multiusuário (P3)
- Ver `.specs/features/dashboard-ux-refresh/spec.md`

---

## M7 — Latência e otimização de recursos do caminho de export

**Goal:** Tirar I/O de exporter do caminho síncrono crítico (`with tracer.trace(...)` não pode
bloquear no I/O do exporter), oferecer batching e sampling **opt-in** (nunca forçado — evitar a
armadilha do LangSmith, onde sampling forçado por custo já causou perda de traces relevantes).

### Features

**performance-optimization** — PLANNED

- `async_export` com worker dedicado (não thread-per-trace)
- Batching opcional (`batch_size`/`batch_interval_ms`)
- `sample_rate` opt-in, com exceção obrigatória para traces com erro
- Ver `.specs/features/performance-optimization/spec.md`

**Nota (custo unificado, item pequeno, não é feature própria):** aceitar `cost_usd` explícito em
spans não-LLM (`trace_span`/`trace_llm_call`) para cobrir custo de tool/API externa paga — resolve
o gap "visão de custo unificada" citado como diferencial do LangSmith 2026, sem abrir feature
nova. Encaixar como task avulsa dentro de M5 ou M7 quando um dos dois entrar em Design.

---

## Future Considerations (fora de escopo deliberado)

- Annotation queue multiusuário — precisa auth real e workflow, é infraestrutura nova (contraria
  princípio "zero infra"). Revisitar só se surgir demanda de time multiusuário.
- Playground de prompts interativo — pesado em UI, baixo retorno para o público-alvo (devs
  integrando via SDK, não PMs editando prompt em UI).
- RBAC / multi-tenant / billing — fora do escopo de lib open-source leve.
- Fila durável de export (buffer em disco + retry + batching) — já listada em `STATE.md` como
  ideia diferida v0.4+, mantém-se diferida.
- Drivers async nativos (asyncpg/motor) — mantém-se diferida.

---

## Notas de execução

- M3 já está completo (verificado via git log nesta sessão) — próximo passo real é escolher entre
  M2, M5, M6, M7 (todos independentes entre si, sem dependência cruzada de código).
- Ordem sugerida por relação esforço/impacto: **M2** (dor mais concretamente relatada, escopo mais
  fechado e já com design+tasks prontos) → **M7** (P1 é pequeno e de alto impacto — 1 flag,
  benchmark claro) → **M5** ou **M6** conforme prioridade de produto (guardrail é diferencial de
  mercado; UX é polish que ajuda adoção/demo).
- M4 fica por último — avaliar esforço real antes de especificar em detalhe; provável modo quick
  para CLI, spec leve para MCP server.
- Todas as specs desta rodada (M2, M5, M6, M7) estão em **Specify**; só M2
  (`langgraph-native-spans`) tem `design.md`/`tasks.md` prontos para execução imediata. As outras
  três precisam de uma passada de Design antes de virar tasks executáveis — intencional, para o
  usuário priorizar antes de aprofundar as três.
