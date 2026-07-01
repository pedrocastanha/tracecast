# LangGraph Native Spans — Specification

> **Status:** Specify → Design (ver `design.md`)
> **Escopo:** Large (novo comportamento de captura no callback + novo módulo de topologia +
> mudança de default; sem novo modelo de storage)
> **Branch sugerida:** `feature/langgraph-native-spans`
> **Depende de:** `observability-reliability` (schema v2, `parent_span_id`, `Tracer`, callback
> LangChain existentes)
> **Relacionado:** `.specs/research/langfuse-comparison.md` (pesquisa que originou esta feature),
> `.specs/codebase/CONCERNS.md` item **C2**
> **Última atualização:** 2026-06-30

## Problem Statement

O callback LangChain do TraceCast (`integrations/langchain.py`) cria um span `AGENT` para **toda**
invocação de `Runnable` que o LangGraph dispara internamente — não só os nodes definidos pelo
usuário, mas também `RunnableSequence`, `ChannelWrite` e runnables de branch condicional que o
Pregel executor usa como cola interna. Hoje isso é mascarado só na leitura do dashboard
(`_is_curated`/`tc_display` em `aggregator.py`), e mesmo essa marcação tem um bug: `langgraph_node`
aparece no metadata de qualquer chamada aninhada *dentro* de um node, não só do node em si, então
`tc_display=True` pode super-marcar. O storage (JSONL/Mongo/Postgres) grava tudo sempre — cresce
sem necessidade e não reflete o grafo real.

Além disso, a reconstrução do grafo no dashboard hoje é uma **heurística de contenção temporal**
(`_build_graph_curated`), não a topologia real que o `compiled_graph.get_graph()` do LangGraph já
expõe (nodes + edges reais + label de branch condicional).

## Goals

- [ ] Captura por padrão grava só os spans necessários para reconstruir a execução real: nodes de
      grafo, chamadas LLM, chamadas de tool e o span raiz da invocação — não a canalização interna
      do LangGraph/LangChain.
- [ ] Spans LLM/Tool nunca ficam órfãos mesmo quando o ancestral imediato é descartado
      (reparenting correto para o ancestral mantido mais próximo).
- [ ] Topologia do grafo no dashboard usa edges reais (`compiled_graph.get_graph()`), incluindo
      labels de branch condicional, quando disponível — cai para a heurística atual só quando não
      há grafo LangGraph (fluxo LangChain puro).
- [ ] Comportamento é configurável e não quebra quem depende do modo atual (debug/paridade).

## Out of Scope

| Item | Razão |
| ---- | ----- |
| Suporte a subgrafos aninhados (`langgraph_checkpoint_ns` com múltiplos níveis) | Adiciona complexidade de namespacing; grafo de 1 nível já resolve a dor relatada. Detectar e não quebrar é suficiente (ver Edge Cases); expandir depois. |
| Streaming de eventos do grafo (`astream_events`) como fonte alternativa de captura | Fora do padrão de captura via callback já estabelecido no projeto; mudaria a superfície de integração inteira. |
| Migração de schema de armazenamento (`models/span.py`) | Feature não precisa de novo campo persistido — classificação é decidida e resolvida inteiramente dentro do callback, antes de qualquer span virar `Span` persistido. |
| Exporter OpenTelemetry | Item separado no `ROADMAP.md` (M4), não bloqueia nem é bloqueado por esta feature. |

---

## User Stories

### P1: Captura curada por padrão em LangGraph ⭐ MVP

**User Story**: Como dev usando TraceCast com LangGraph, quero que só os spans que representam
nodes reais, chamadas LLM e chamadas de tool sejam persistidos, para que o trace reflita a
execução do meu grafo sem ruído de implementação do LangChain/LangGraph.

**Why P1**: É a dor relatada diretamente — "correct spans in langgraph, not all spans, only the
necessary ones".

**Acceptance Criteria**:

1. WHEN um `on_chain_start` dispara com `metadata.langgraph_node` presente E
   `kwargs["name"] == metadata["langgraph_node"]` E a tag `langsmith:hidden` NÃO está presente
   THEN o sistema SHALL classificar o span como `node boundary` (mantido).
2. WHEN um `on_chain_start` dispara sem essas condições (chain aninhada dentro de um node, ou
   canalização interna do Pregel/LCEL) THEN o sistema SHALL classificar o span como `plumbing`
   (descartado por padrão).
3. WHEN um `on_chain_start` dispara sem `parent_run_id` E sem span ativo no `ContextVar`
   (`Tracer.current_span()`) THEN o sistema SHALL classificar o span como raiz (mantido) —
   independente de nome — pois é o ponto de entrada da invocação.
4. WHEN um span é do tipo `LLM` ou `TOOL` THEN o sistema SHALL sempre mantê-lo, independente da
   classificação do ancestral.
5. WHEN `Tracer` (ou `TraceCastCallback`) é criado com `span_capture="all"` THEN o sistema SHALL
   manter o comportamento atual (grava tudo) — modo debug/paridade.
6. WHEN nenhum `span_capture` é especificado THEN o default SHALL ser `"curated"`.

**Independent Test**: rodar o grafo de `test_e2e_langgraph.py` (`classify → answer_a/answer_b`)
com `span_capture="curated"` (default) e verificar que `trace.spans` não contém nenhum span cujo
nome bata com `RunnableSequence`/`RunnableParallel`/`ChannelWrite`/`RunnableBinding`, mas contém
`classify`, `answer_a` (ou `answer_b`), a chamada LLM e a chamada de tool (`guardrail_pii`).

---

### P1: Reparenting correto de spans mantidos ⭐ MVP

**User Story**: Como dev inspecionando um trace, quero que `parent_span_id` de um span LLM/Tool
sempre aponte para um span que realmente existe no trace, para poder reconstruir a árvore sem
nós órfãos.

**Why P1**: Sem isso, descartar spans de canalização quebraria a árvore (LLM span apontando para
um `parent_span_id` que nunca foi persistido).

**Acceptance Criteria**:

1. WHEN um span é aberto com `parent_run_id` apontando para um span classificado como `plumbing`
   THEN o sistema SHALL resolver `parent_span_id` para o ancestral mantido mais próximo (o
   `parent_span_id` já resolvido do span descartado), não para o span descartado em si.
2. WHEN a cadeia de ancestrais até a raiz é toda `plumbing` THEN o sistema SHALL resolver
   `parent_span_id` para o span raiz mantido (regra da story anterior, critério 3) ou `None` se
   não houver nenhum.
3. WHEN um span `plumbing` é fechado (`on_chain_end`) THEN o sistema SHALL remover sua entrada de
   rastreio interno sem gravá-lo em `trace.spans`.

**Independent Test**: no mesmo teste E2E, todo span do tipo `LLM`/`TOOL` tem `parent_span_id` que
corresponde ao `span_id` de outro span presente em `trace.spans` (nunca `None` quando dentro de um
node, nunca um ID que não existe na lista).

---

### P2: Topologia real do grafo no dashboard

**User Story**: Como dev revisando um trace no dashboard, quero ver o grafo real que o LangGraph
executou — incluindo qual branch condicional foi tomada — em vez de uma reconstrução aproximada
por tempo.

**Why P2**: Fecha o C2 do `CONCERNS.md` ("arestas/roteamento não são eventos de callback"). Não é
MVP porque a P1 já entrega valor standalone (menos ruído); isso é a camada de visualização.

**Acceptance Criteria**:

1. WHEN `tracer.trace(...)` é chamado com o parâmetro `graph=<compiled_graph>` THEN o sistema
   SHALL capturar `compiled_graph.get_graph()` uma vez e anexar a topologia estática
   (`nodes`, `edges` com `conditional`/`data`) ao trace como `trace.graph_definition`.
2. WHEN o dashboard monta o grafo de um trace que tem `graph_definition` THEN o sistema SHALL
   usar as edges reais (incluindo o label da branch condicional tomada, cruzando com os nodes
   efetivamente executados) em vez da heurística de contenção temporal.
3. WHEN o trace não tem `graph_definition` (fluxo LangChain puro, sem LangGraph, ou usuário não
   passou `graph=`) THEN o sistema SHALL cair para o comportamento atual (`_build_graph_curated`
   ou fallback flat) sem erro.
4. WHEN um node do `get_graph()` nunca foi executado nesta invocação específica (branch não
   tomada) THEN o sistema SHALL incluí-lo no grafo estático marcado como `executed=false`, não
   removê-lo — para o usuário ver o grafo completo autor vs. o caminho realmente percorrido.

**Independent Test**: rodar o grafo de branch condicional (`classify → answer_a | answer_b`) duas
vezes (uma para cada branch), passar `graph=app` no `tracer.trace(...)`, e verificar que o
endpoint `/api/traces/{id}/graph` retorna a edge `classify → answer_a` com `conditional=true` e
`data="a"` numa execução, e `classify → answer_b` com `data="b"` na outra — com o node não
executado presente e marcado `executed=false`.

---

### P3: Opt-in de span específico fora de um node

**User Story**: Como dev com uma chain LCEL nomeada relevante rodando fora de um LangGraph node
(ex.: dentro de uma tool, ou numa chain solta), quero poder marcar essa chain para ser mantida
mesmo sem ser um node boundary.

**Why P3**: Escape hatch para os casos em que a heurística automática descarta algo que o usuário
considera relevante. Não é P1/P2 porque a maioria dos casos já é coberta por LLM/Tool/node
boundary automaticamente.

**Acceptance Criteria**:

1. WHEN uma chain é invocada com `config={"tags": ["tracecast:keep"]}` (ou a tag configurável via
   `Tracer(keep_tags=...)`) THEN o sistema SHALL manter o span mesmo que não seja node boundary
   nem raiz.

**Independent Test**: invocar uma sub-chain com `tags=["tracecast:keep"]` dentro de um node e
verificar que ela aparece em `trace.spans` com `parent_span_id` apontando para o node.

---

## Edge Cases

- WHEN o LangGraph usa subgrafos (`langgraph_checkpoint_ns` com mais de um segmento) THEN o
  sistema SHALL tratar o node do subgrafo como `plumbing` por padrão (mesma regra: só é boundary
  se `name == langgraph_node` no nível mais externo) — não quebrar, não tentar resolver
  hierarquia de subgrafo nesta feature (Out of Scope).
- WHEN `span_capture="curated"` e um span `plumbing` lança exceção (`on_chain_error`) THEN o
  sistema SHALL propagar o erro para o span mantido mais próximo? — **Decisão (AD-4 no design):
  NÃO propaga campo de erro entre spans; o span LLM/Tool que efetivamente falhou já registra seu
  próprio erro via `on_llm_error`/`on_tool_error`.** Um erro em canalização pura (raro) é perdido
  silenciosamente da mesma forma que hoje um erro de `RunnableSequence` non-terminal já não altera
  o resultado do node pai se o node captura a exceção.
- WHEN `compiled_graph.get_graph()` lança exceção (grafo malformado, versão incompatível de
  langgraph) THEN o sistema SHALL capturar a exceção, logar warning, e seguir sem
  `graph_definition` (degradação graciosa, mesmo padrão de exporters).
- WHEN dois `on_chain_start` competem pelo mesmo `run_id` (não deveria acontecer, mas
  defensivamente) THEN o sistema SHALL manter o comportamento atual de sobrescrever
  (`self._span_stack[run_id] = Span(...)`).
- WHEN o usuário usa `LangChainInstrumentor.patch()` (global) em vez de `TraceCastCallback`
  explícito THEN a classificação curada SHALL se aplicar igualmente (mesma implementação
  subjacente via `_LazyHandler`).

## Requirement Traceability

| Requirement ID | Story | Fase | Status |
| -------------- | ----- | ---- | ------ |
| LGSPAN-01 | P1 Classificação node boundary | Design | Pending |
| LGSPAN-02 | P1 Descarte de plumbing por padrão | Design | Pending |
| LGSPAN-03 | P1 Span raiz sempre mantido | Design | Pending |
| LGSPAN-04 | P1 LLM/Tool sempre mantidos | Design | Pending |
| LGSPAN-05 | P1 Config `span_capture="all"` | Design | Pending |
| LGSPAN-06 | P1 Reparenting para ancestral mantido | Design | Pending |
| LGSPAN-07 | P1 Plumbing fechado não grava | Design | Pending |
| LGSPAN-08 | P2 Captura de `graph_definition` via `get_graph()` | Design | Pending |
| LGSPAN-09 | P2 Dashboard usa edges reais + label condicional | Design | Pending |
| LGSPAN-10 | P2 Fallback sem `graph_definition` | Design | Pending |
| LGSPAN-11 | P2 Node não executado marcado `executed=false` | Design | Pending |
| LGSPAN-12 | P3 Tag opt-in `tracecast:keep` | Design | Pending |

**Status values:** Pending → In Design → In Tasks → Implementing → Verified
**Coverage:** 12 requisitos. Mapeamento → tasks em `tasks.md`.

## Success Criteria

- [ ] Rodando `test_e2e_langgraph.py` com o novo default, nenhum span de canalização
      (`RunnableSequence`/`RunnableParallel`/`ChannelWrite`/`RunnableBinding`) aparece em
      `trace.spans`.
- [ ] Nenhum span `LLM`/`TOOL` tem `parent_span_id` órfão (aponta para ID inexistente em
      `trace.spans`).
- [ ] `/api/traces/{id}/graph` reflete a branch condicional real tomada quando `graph=` é passado.
- [ ] Suite Python verde, sem regressão dos testes atuais (baseline: suite completa do projeto —
      confirmar contagem exata rodando `python -m pytest tests/ -v` antes de começar, ver
      `tasks.md` T1).
- [ ] Tamanho médio do payload de trace (`len(json.dumps(trace.to_dict()))`) para o grafo de teste
      de branch condicional **reduz** em relação ao baseline atual (evidência de que menos spans
      de ruído estão sendo persistidos).
