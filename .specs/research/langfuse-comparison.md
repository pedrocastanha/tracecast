# TraceCast vs Langfuse — Comparação Completa (2026-06-30)

> Pesquisa via WebSearch + WebFetch (docs Langfuse) + leitura do código fonte
> `langfuse-python` (`langfuse/langchain/CallbackHandler.py`) + inspeção do código TraceCast.
> Objetivo: fechar gaps reais, sem copiar features que não servem ao princípio "leve, zero infra nova".

## 1. Metodologia

- Fonte primária: docs oficiais Langfuse (langfuse.com/docs) via WebFetch, 2026-06-30.
- Fonte de verdade sobre span granularity: código fonte do `CallbackHandler` do `langfuse-python`
  (GitHub, branch `main`), não documentação de marketing.
- Fonte de verdade sobre TraceCast: leitura direta de `tracecast/integrations/langchain.py`,
  `tracecast/dashboard/aggregator.py`, `tracecast/instrumentors/langchain_inst.py`,
  `.specs/codebase/CONCERNS.md` (auditoria 2026-06-13).

## 2. Achado central — granularidade de spans em LangGraph

**Mito a derrubar:** Langfuse NÃO filtra spans "de canalização" (RunnableSequence, ChannelWrite,
branch runnables) na captura. Inspeção do `on_chain_start` do `CallbackHandler` deles mostra:
toda invocação de Runnable vira uma `observation`, sem exceção. O único mecanismo de filtro é
`tags=["langsmith:hidden"]` → grava a observação com `level=DEBUG` (fica escondida na UI por
padrão, mas ainda ocupa storage).

**TraceCast hoje é pior nesse ponto, não igual:** `integrations/langchain.py:224` marca
`is_node = bool(lg_meta.get("langgraph_node"))` — isso é `True` para QUALQUER chamada aninhada
dentro de um node (não só o node em si), porque o LangGraph propaga `langgraph_node` no metadata
para toda a sub-árvore de Runnables daquele node. Ou seja, o flag `tc_display` hoje super-marca
(inclusive chains internas de um node) e a filtragem só acontece client-side, na leitura do
dashboard (`aggregator.py:179,229`) — o storage (JSONL/Mongo/Postgres) grava tudo, sempre.
Confirmado empiricamente rodando um grafo de 2 nodes com callback de debug local (ver
`.specs/features/langgraph-native-spans/design.md`, seção "Evidência empírica").

**A correção correta (usada internamente pelo próprio LangGraph em
`langgraph/pregel/_messages.py`) é:**

```python
is_node_boundary = (
    metadata.get("langgraph_node") is not None
    and kwargs.get("name") == metadata.get("langgraph_node")
    and "langsmith:hidden" not in (kwargs.get("tags") or [])
)
```

Comparar `name == langgraph_node` (não só presença) é o que distingue "este IS o node" de "isto
está aninhado dentro do node". TraceCast vai adotar essa regra — ver feature
`langgraph-native-spans`.

## 3. Matriz de comparação

| Área | Langfuse | TraceCast (hoje) | Gap | Prioridade |
|---|---|---|---|---|
| Captura LangGraph | Callback handler, tudo capturado, filtro só via tag `langsmith:hidden` (client-side/UI) | Callback handler, tudo capturado, filtro `tc_display` já super-marca (bug) e só filtra na leitura, não na escrita | 🔴 Storage cresce com ruído; UI depende de heurística de tempo (`_build_graph_curated`) em vez de topologia real | **P1** — feature `langgraph-native-spans` |
| Topologia do grafo (edges reais, labels condicionais) | Não documentado explicitamente, mas LangGraph expõe `get_graph()` com edges reais e label da branch condicional | Reconstrói grafo por **heurística de contenção temporal** (`aggregator.py:331-458`) — aproximação, não a topologia real | 🔴 C2 do `CONCERNS.md`: "arestas/roteamento não são eventos de callback" — ainda não resolvido | **P1** — mesma feature, usa `compiled_graph.get_graph()` |
| Persistência de eval (`EvalRun`) | Nativo, servidor | Implementado nesta sessão anterior (fase 0 do SDD `observability-platform`) — backend pronto, UI pendente | 🟡 Só falta UI (T10, T16-UI, T24) | P2 — já especificado, retomar |
| Scores de produção (`score()`) | Nativo (feedback humano, LLM, heurístico) | Implementado (backend) — `tracecast.score()` + `export_score` | 🟡 UI pendente (painel no trace detail) | P2 — já especificado |
| Métricas prontas (faithfulness, hallucination, toxicity...) | Biblioteca extensa, LLM-as-judge configurável | Registry `METRICS` implementado (fase 2 do SDD) | 🟢 Paridade funcional atingida no backend | — |
| Comparação A/B de runs | Sim, UI dedicada | `compare()` implementado, UI pendente | 🟡 UI pendente | P2 |
| Online eval (sampling de produção) | Sim | `OnlineEval` implementado (fase 4) | 🟢 Paridade atingida | — |
| Prompt management versionado | Sim, labels, cache, playground | Versionamento + labels + cache implementado; **sem playground** | 🟡 Playground fora de escopo (decisão AD anterior) | Deferred |
| Annotation queue (revisão humana em fila, multiusuário) | Sim | Não existe | 🟠 Fora de escopo — precisa auth/multiusuário, é infraestrutura nova | Deferred (fora do princípio "zero infra nova") |
| Protocolo de trace | SDK v3 nativo em **OpenTelemetry** — qualquer backend OTel funciona | Schema JSON próprio (v2), exporters custom (Mongo/Postgres/JSONL/Dict) | 🟠 Sem interoperabilidade com Grafana Tempo/Jaeger/Datadog etc. | P3 — avaliar exporter OTel opcional, não substituir o atual |
| CLI para CI/CD | Sim (`langfuse` CLI, 2026) | Não existe | 🟡 Baixo esforço, alto valor para pipelines de eval em CI | P3 |
| MCP Server / SKILL.md para agentes de IA | Sim (lançado 2026) | Não existe | 🟡 Encaixa bem no ecossistema Claude Code/Claude Skills que o próprio usuário já usa | P3 |
| Alertas/monitoramento contínuo | Parcial (via integrações externas) | Não existe (`OnlineEval` grava score, mas não alerta) | 🟢 Baixo valor sem consumidor de alerta definido | Deferred |
| Self-host / infra | Requer Postgres + ClickHouse + Redis + S3 (stack pesada) | JSONL/Dict/Mongo/Postgres, servidor standalone único processo | 🟢 **Vantagem TraceCast** — muito mais leve para hospedar | — |
| Custo de operação | SaaS pago ou self-host pesado | Lib embutida, zero custo de infra além do exporter escolhido | 🟢 **Vantagem TraceCast** | — |

## 4. Conclusão

O gap "estrutural" real (o que o usuário sentiu na prática usando LangGraph) não é falta de
feature de eval/score/prompt — isso já foi resolvido no SDD `observability-platform` (backend
100%, falta só UI). O gap real e **não especificado até hoje** é:

1. **Ruído de spans na captura** (não só na leitura) — nunca foi corrigido, só mascarado no
   dashboard.
2. **Topologia do grafo aproximada por heurística**, não pela estrutura real que o LangGraph já
   expõe via `get_graph()`.

Isso vira a feature `langgraph-native-spans` (ver `.specs/features/langgraph-native-spans/`).

Os gaps de paridade "cosméticos" (CLI, MCP server, exporter OTel) viram itens **P3** no
`ROADMAP.md` — não especificados em detalhe agora (baixo risco, baixa ambiguidade, cabem em modo
quick quando priorizados).

## 5. Addendum — LangSmith (gaps específicos, pesquisa 2026-06-30)

LangSmith não é só "LangFuse com dono" — tem um modelo de negócio que gera fricção estrutural
que o TraceCast pode transformar em vantagem direta, sem esforço extra:

| Gap do LangSmith | Evidência (pesquisa 2026) | Como o TraceCast já resolve / vai resolver |
| --- | --- | --- |
| **Cobrança por trace** (Plus: $39/seat + $2.50/1k traces; retenção estendida dobra o preço) | "trace-heavy workloads" custam 5–10% do gasto de LLM API só em observabilidade | Zero custo por trace — storage é do usuário (Mongo/Postgres/JSONL próprios). Vantagem estrutural, já existe. |
| **Sampling forçado por custo** | "LangSmith lets you filter which runs get traced... once you start sampling, you risk missing the trace that would have helped debug" | Feature `performance-optimization` (P2) faz sampling **opt-in** e nunca aplica a traces com erro — resolve exatamente essa tensão, ao contrário do LangSmith |
| **OTel só parcial, formato proprietário** | "limited OTEL support... tracing format is proprietary" | Já é gap conhecido do TraceCast também (schema próprio) — item `otel-export-adapter` no `ROADMAP.md` (M4) vira ainda mais atrativo por comparação direta |
| **Instrumentação fraca fora do LangChain** | "if your stack uses direct API calls... instrumentation is more manual and you lose automatic tracing" | **Já é ponto forte do TraceCast hoje** — `instrumentors/openai_inst.py`, `anthropic_inst.py`, `gemini_inst.py`, `crewai_inst.py`, `llamaindex_inst.py` existem standalone, não dependem de LangChain. Vale destacar isso em marketing/README, não é trabalho novo. |
| **Visão de custo unificada (LLM + retrieval + tool + API externa)** | Feature nova 2026 do LangSmith, citada como diferencial | TraceCast já agrega custo próprio por node (`own_cost_usd` em `aggregator.py`), mas só para chamadas LLM. Falta permitir custo manual em spans de Tool (chamada de API paga, ex. busca web) — oportunidade pequena e barata: aceitar `cost_usd` explícito em `trace_span`/`trace_llm_call` para qualquer tipo de span, não só LLM. **Candidato a task pequena dentro de `dynamic-guardrails` ou item avulso — não abre feature nova por si só.** |
| **Annotation queues** | Força citada repetidamente como diferencial de LangSmith/Arize | Endereçado de forma leve (sem fila multiusuário) pela story P3 de `dashboard-ux-refresh` (anotação lite via `Score` já existente) |

**Conclusão do addendum:** nenhum gap do LangSmith exige feature nova além do que já está no
roadmap (`langgraph-native-spans`, `performance-optimization`, `dashboard-ux-refresh`,
`otel-export-adapter`). O único item pequeno e novo identificado — custo manual em spans não-LLM
— é baixo esforço o suficiente para ser uma task avulsa, não uma feature. Adicionado como nota em
`ROADMAP.md`.

## Fontes

- [Langfuse LangChain/LangGraph integration](https://langfuse.com/integrations/frameworks/langchain)
- [Langfuse LangGraph cookbook](https://langfuse.com/guides/cookbook/integration_langgraph)
- [Langfuse SDK instrumentation docs](https://langfuse.com/docs/observability/sdk/instrumentation)
- [Langfuse docs overview](https://langfuse.com/docs)
- [Langfuse prompt management](https://langfuse.com/docs/prompt-management/overview)
- `langfuse-python` source: `langfuse/langchain/CallbackHandler.py` (GitHub, branch `main`)
- `langgraph` 1.0.1 source instalado localmente: `langgraph/pregel/_messages.py`,
  `langgraph/constants.py` (`TAG_HIDDEN = "langsmith:hidden"`)
- `langchain_core.runnables.graph`: `Graph(nodes: dict[str, Node], edges: list[Edge])`,
  `Node(id, name, data, metadata)`, `Edge(source, target, data, conditional)` — confirmado por
  introspecção direta (`inspect.signature`) no ambiente local.
- [LLM Guard (Protect AI)](https://appsecsanta.com/llm-guard)
- [NVIDIA NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails)
- [Top AI Guardrails Platforms 2026 — Galileo](https://galileo.ai/blog/best-ai-guardrails-platforms)
- [LLM Guardrails 2026 — MorphLLM](https://www.morphllm.com/llm-guardrails)
- [Langfuse Alternatives 2026 — Laminar](https://laminar.sh/article/langfuse-alternatives-2026)
- [Agent Observability Platforms 2026 — Digital Applied](https://www.digitalapplied.com/blog/agent-observability-platforms-langsmith-langfuse-arize-2026)
- [LangSmith Pricing 2026 — Inference.net](https://inference.net/content/langsmith-pricing/)
- [Langfuse vs LangSmith — TECHSY](https://techsy.io/en/blog/langfuse-vs-langsmith)
