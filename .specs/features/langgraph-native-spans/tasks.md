# LangGraph Native Spans — Tasks

**Design**: `.specs/features/langgraph-native-spans/design.md`
**Status**: Draft

---

## Execution Plan

### Phase 0: Verification spike (Sequential)

```
T1
```

### Phase 1: Capture-time classification (Sequential — same file)

```
T1 → T2 → T3 → T4
```

### Phase 2: Graph topology (Parallel with Phase 1 after T1)

```
T1 ──→ T5 → T6
```

### Phase 3: Dashboard integration (Sequential, needs Phase 1 + Phase 2)

```
(T4, T6) → T7 → T8
```

### Phase 4: Docs + changelog (Sequential, last)

```
T8 → T9
```

---

## Task Breakdown

### T1: Spike — confirmar `get_graph()` e classificação em versão pinada do projeto

**What**: Script descartável (`scratch/verify_langgraph.py`, não commitado) que roda um grafo de
teste com branch condicional contra a versão de `langgraph` do `pyproject.toml` do projeto e
imprime: (a) `kwargs` de `on_chain_start` para root/node/plumbing, (b) `get_graph().nodes`/`.edges`
shape. Confirma ou corrige as suposições do `design.md` (evidência empírica já coletada contra
`langgraph==1.0.1` local — este task garante que a versão *pinada no projeto* bate).
**Where**: script temporário, não faz parte do pacote
**Depends on**: None
**Reuses**: nenhum código do projeto — é só verificação
**Requirement**: N/A (gate de qualidade, não requisito funcional)

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] Output confirma `name == metadata["langgraph_node"]` como critério de boundary
- [ ] Output confirma `Graph.nodes`/`Graph.edges` com os atributos `id/name/data/metadata` e
      `source/target/data/conditional` respectivamente
- [ ] Divergências (se houver) documentadas como atualização no `design.md` antes de prosseguir

**Tests**: none (é um spike de verificação, não código de produção)
**Gate**: quick (rodar o script manualmente, sem gate automatizado)

---

### T2: Implementar `_classify_chain_span` + `span_capture`/`keep_tags` em `TraceCastCallback`

**What**: Adicionar a função `_classify_chain_span` (módulo-nível) e os parâmetros
`span_capture: Literal["curated","all"] = "curated"` e
`keep_tags: frozenset[str] = frozenset({"tracecast:keep"})` no `__init__` de `TraceCastCallback`.
**Where**: `packages/tracecast-py/tracecast/integrations/langchain.py`
**Depends on**: T1
**Reuses**: nenhuma mudança em outras funções ainda (isolado, sem side-effect visível até T3)
**Requirement**: LGSPAN-01, LGSPAN-05, LGSPAN-12

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] `_classify_chain_span(name, metadata, tags, has_parent, keep_tags) -> bool` implementada
      exatamente conforme `design.md` (raiz sempre True, tag opt-in sempre True, node boundary via
      `name == langgraph_node` e não hidden, senão False)
- [ ] Unit tests cobrindo os 4 casos (raiz / node boundary / plumbing aninhado / tag opt-in)
- [ ] Gate check passa: `python -m pytest tests/test_instrumentors/test_langchain_inst.py -v`
- [ ] Test count: baseline + pelo menos 4 novos testes, nenhuma remoção silenciosa

**Tests**: unit
**Gate**: quick

---

### T3: Reescrever `_span_stack`/`_parent_id` para reparenting + descarte condicional [depende de T2]

**What**: `_span_stack` passa a guardar `(Span, kept: bool)`; `_parent_id` reparenta através de
ancestrais `plumbing`; `on_chain_start` usa `_classify_chain_span` para decidir `kept` de cada
chain; `on_chain_end`/`on_chain_error` só fazem `trace.spans.append(...)` quando
`span_capture == "all" or kept`.
**Where**: `packages/tracecast-py/tracecast/integrations/langchain.py` (métodos `on_chain_start`,
`on_chain_end`, `on_chain_error`, `_parent_id`, `_close_span_with_error`)
**Depends on**: T2
**Reuses**: `_classify_chain_span` (T2), `Tracer.current_span()` (existente)
**Requirement**: LGSPAN-02, LGSPAN-03, LGSPAN-04, LGSPAN-06, LGSPAN-07

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] `on_llm_start`/`on_tool_start` continuam sempre "kept" (sem mudança de comportamento)
- [ ] Span `plumbing` fechado NÃO aparece em `trace.spans`, mas seus filhos (LLM/Tool/node
      seguinte) resolvem `parent_span_id` corretamente para o ancestral mantido
- [ ] `test_e2e_langgraph.py::test_e2e_captures_full_flow` continua passando (spans AGENT/LLM/TOOL
      presentes, node com `parent_span_id` não-nulo)
- [ ] Novo teste: nenhum span em `trace.spans` tem nome batendo com
      `RunnableSequence|RunnableParallel|RunnableBinding|RunnableLambda|ChannelWrite` após rodar o
      grafo de `test_e2e_langgraph.py`
- [ ] Novo teste: todo `parent_span_id` não-nulo em `trace.spans` corresponde a um `span_id`
      presente em `trace.spans` (nenhum órfão)
- [ ] Gate check passa: `python -m pytest tests/test_e2e_langgraph.py tests/test_langchain_callback.py tests/test_instrumentors/test_langchain_inst.py -v`
- [ ] Test count: baseline + pelo menos 3 novos testes

**Tests**: integration
**Gate**: full

**Commit**: `feat(langchain): capture only meaningful spans in LangGraph runs by default`

---

### T4: `span_capture="all"` modo legado + regressão completa [P]

**What**: Garantir que `TraceCastCallback(tracer, span_capture="all")` reproduz o comportamento
pré-feature byte-a-byte (todo chain vira span, `tc_display` igual a hoje) — teste de paridade
explícito.
**Where**: `packages/tracecast-py/tests/test_langchain_callback.py` (novo teste)
**Depends on**: T3
**Reuses**: fixtures existentes de `test_langchain_callback.py`
**Requirement**: LGSPAN-05

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] Teste roda o mesmo grafo com `span_capture="all"` e `span_capture="curated"` e compara: o
      `"all"` tem `len(trace.spans) >= ` o `"curated"` (nunca menos), e todo span do `"curated"`
      também existe (por `name`+tipo) no `"all"`
- [ ] Gate check passa: `python -m pytest tests/test_langchain_callback.py -v`
- [ ] Test count: baseline + 1

**Tests**: unit
**Gate**: quick

---

### T5: `capture_graph_topology` em novo módulo `integrations/langgraph.py` [P]

**What**: Implementar `capture_graph_topology(compiled_graph) -> Optional[dict]` conforme
`design.md` componente 3 — extrai nodes/edges de `get_graph()`, degrada graciosamente em erro.
**Where**: `packages/tracecast-py/tracecast/integrations/langgraph.py` (novo arquivo)
**Depends on**: T1
**Reuses**: nenhum código existente — módulo novo e isolado
**Requirement**: LGSPAN-08

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] Retorna `{"nodes": [...], "edges": [...]}` com os campos exatos do `design.md` para um grafo
      real (`langgraph.graph.StateGraph`)
- [ ] Edge condicional inclui `"conditional": True` e `"label"` com o valor de `.data`
- [ ] `compiled_graph` sem `get_graph()` (objeto qualquer) retorna `None` sem exceção
- [ ] `get_graph()` que lança exceção é capturado, loga `warnings.warn`, retorna `None`
- [ ] Gate check passa: `python -m pytest tests/test_instrumentors/ -k langgraph -v` (novo arquivo
      de teste `tests/test_integrations/test_langgraph_topology.py`)
- [ ] Test count: 4 novos testes (grafo real, sem branch, com branch condicional, erro simulado)

**Tests**: unit
**Gate**: quick

---

### T6: `Trace.graph_definition` + `Tracer.trace(graph=...)` [depende de T5]

**What**: Adicionar campo opcional `graph_definition` em `models/trace.py` (`to_dict`/`from_dict`
incluem o campo, default `None`); adicionar parâmetro `graph=` em `Tracer.trace()` que chama
`capture_graph_topology` (import local) e popula o campo no início do `with`.
**Where**: `packages/tracecast-py/tracecast/models/trace.py`,
`packages/tracecast-py/tracecast/core/tracer.py`
**Depends on**: T5
**Reuses**: `Trace.__init__`/`to_dict`/`from_dict` existentes (só ganham um campo)
**Requirement**: LGSPAN-08

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] `tracer.trace("x", graph=app)` popula `trace.graph_definition` com o resultado de
      `capture_graph_topology(app)`
- [ ] `tracer.trace("x")` (sem `graph=`) mantém `graph_definition=None`, sem mudança de
      comportamento para chamadores existentes
- [ ] `to_dict()`/`from_dict()` roundtrip preserva `graph_definition`
- [ ] Gate check passa: `python -m pytest tests/ -k "trace or tracer" -v`
- [ ] Test count: baseline + 3

**Tests**: unit
**Gate**: quick

---

### T7: `_build_graph_from_definition` no dashboard [depende de T3, T6]

**What**: Nova função em `aggregator.py` que monta nodes/edges a partir de
`trace.graph_definition`, casando node definido ↔ span executado por `name`, marcando
`executed=false` para nodes sem span correspondente; `build_graph()` chama essa função primeiro
quando `trace.graph_definition` existe.
**Where**: `packages/tracecast-py/tracecast/dashboard/aggregator.py`
**Depends on**: T3, T6
**Reuses**: `_node_from_calls`, `_llm_call`, `_parse_tool_params` (existentes, sem mudança)
**Requirement**: LGSPAN-09, LGSPAN-10, LGSPAN-11

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] Trace com `graph_definition` + branch `a` tomada: edge `classify→answer_a` presente com
      `conditional=true`/label `"a"`; node `answer_b` presente com `executed=false`, sem
      `own_tokens_in`/`own_cost_usd` sintéticos (zerados/ausentes, não inventados)
- [ ] Trace sem `graph_definition`: comportamento idêntico ao atual (`_build_graph_curated` ou
      fallback flat), zero regressão
- [ ] Gate check passa: `python -m pytest tests/test_e2e_langgraph.py -v` (inclui o teste
      `test_e2e_dashboard_graph_and_filters` já existente + novo teste de branch)
- [ ] Test count: baseline + 2

**Tests**: integration
**Gate**: full

**Commit**: `feat(dashboard): render real LangGraph topology from get_graph() when available`

---

### T8: Passar `graph=` nos exemplos reais (`real_examples/langgraph_graph.py`) [depende de T7]

**What**: Atualizar `real_examples/langgraph_graph.py` para passar `graph=app` em
`tracer.trace(...)`, validando a feature ponta-a-ponta com um exemplo real do repo (não só teste).
**Where**: `packages/tracecast-py/real_examples/langgraph_graph.py`
**Depends on**: T7
**Reuses**: script existente, só adiciona o parâmetro
**Requirement**: N/A (validação manual, não requisito novo)

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] `python real_examples/langgraph_graph.py` roda sem erro e o JSONL gerado
      (`traces/langgraph_traces.jsonl`) contém `graph_definition` não-nulo
- [ ] Rodar `tracecast-server` local sobre esse JSONL e abrir `/api/traces/{id}/graph` retorna
      grafo com as 3 edges reais do exemplo (`input_node→processor_node→output_node`)

**Tests**: none (script de demonstração, já coberto por T7 nos testes automatizados)
**Gate**: quick (verificação manual)

---

### T9: Atualizar CHANGELOG + `STATE.md` [depende de T8]

**What**: Documentar a mudança de comportamento (`span_capture` default `"curated"`) no
`CHANGELOG.md` como breaking change de comportamento (não de API pública), e registrar ADR em
`.specs/project/STATE.md`.
**Where**: `CHANGELOG.md`, `.specs/project/STATE.md`
**Depends on**: T8
**Reuses**: formato existente do `CHANGELOG.md` e `STATE.md`
**Requirement**: N/A

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [ ] `CHANGELOG.md` tem entrada explicando: default mudou, como reverter (`span_capture="all"`),
      por que (menos ruído, storage menor, topologia real)
- [ ] `STATE.md` tem ADR novo referenciando esta feature como implementada

**Tests**: none
**Gate**: none (docs)

---

## Parallel Execution Map

```
Phase 0 (Sequential):
  T1

Phase 1+2 (Parallel após T1):
  T1 ──┬──→ T2 ──→ T3 ──→ T4 [P]
       └──→ T5 [P] ──→ T6

Phase 3 (Sequential, precisa de T4 e T6):
  (T4, T6) ──→ T7 ──→ T8

Phase 4 (Sequential):
  T8 ──→ T9
```

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: Spike de verificação | 1 script descartável | ✅ Granular |
| T2: `_classify_chain_span` + params | 1 função + 1 construtor | ✅ Granular |
| T3: Reparenting + descarte condicional | 1 arquivo, métodos coesos do mesmo componente | ✅ Granular (2-3 métodos relacionados, cohesive) |
| T4: Modo `"all"` + regressão | 1 teste de paridade | ✅ Granular |
| T5: `capture_graph_topology` | 1 função, 1 arquivo novo | ✅ Granular |
| T6: `graph_definition` + `trace(graph=)` | 2 arquivos, 1 campo + 1 parâmetro relacionados | ✅ Granular (cohesive) |
| T7: `_build_graph_from_definition` | 1 função, 1 arquivo | ✅ Granular |
| T8: Exemplo real | 1 arquivo, 1 linha | ✅ Granular |
| T9: Docs | 2 arquivos de doc | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ----------------------- | -------------- | ------ |
| T1 | None | None | ✅ Match |
| T2 | T1 | T1→T2 | ✅ Match |
| T3 | T2 | T2→T3 | ✅ Match |
| T4 | T3 | T3→T4 | ✅ Match |
| T5 | T1 | T1→T5 | ✅ Match |
| T6 | T5 | T5→T6 | ✅ Match |
| T7 | T3, T6 | (T4,T6)→T7 — **nota**: T7 depende de T3 (código) não de T4 (teste); T4 é validação de T3, roda em paralelo com T5/T6, não bloqueia T7. Diagrama ajustado para `(T3, T6)→T7` | ✅ Match após correção |
| T8 | T7 | T7→T8 | ✅ Match |
| T9 | T8 | T8→T9 | ✅ Match |

**Correção aplicada:** T7 depende de **T3** (implementação) e **T6**, não de T4 (que é só o teste
de paridade do modo `"all"`, independente do caminho crítico). T4 pode terminar depois de T7 sem
bloquear nada — mantido como `[P]` solto após T3.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | ---------------------------- | ---------------- | ---------- | ------ |
| T2 | `integrations/langchain.py` (função pura nova) | unit (sem `TESTING.md` formal — inferido do padrão existente do repo: toda lógica de callback tem teste em `tests/test_instrumentors/`) | unit | ✅ OK |
| T3 | `integrations/langchain.py` (callback, E2E com LangGraph real) | integration (padrão do repo: `test_e2e_langgraph.py` já testa o fluxo completo) | integration | ✅ OK |
| T4 | teste de paridade | unit | unit | ✅ OK |
| T5 | `integrations/langgraph.py` (função pura nova) | unit | unit | ✅ OK |
| T6 | `models/trace.py` + `core/tracer.py` | unit (roundtrip serialização) | unit | ✅ OK |
| T7 | `dashboard/aggregator.py` + endpoint HTTP | integration (endpoint via `TestClient`, padrão de `test_e2e_langgraph.py::test_e2e_dashboard_graph_and_filters`) | integration | ✅ OK |
| T8 | script de exemplo | none (script manual) | none | ✅ OK |
| T9 | docs | none | none | ✅ OK |

**Nota:** projeto não tem `TESTING.md` formal em `.specs/codebase/`. Padrão inferido diretamente
da suíte existente (`tests/test_instrumentors/*` = unit; `tests/test_e2e_*.py` = integration via
`TestClient`/grafo real). Gate commands: `python -m pytest tests/ -v` (full),
`python -m pytest <arquivo específico> -v` (quick).

---

## Tools/Skills por task

Todas as tasks são Python puro dentro do pacote `tracecast-py`, sem necessidade de MCP externo ou
skill adicional além do já ativo (`tlc-spec-driven` para o processo de Execute). `codenavi` (se
instalado) pode acelerar T2/T3 na localização de todos os call-sites de `_span_stack` antes de
editar — recomendado, não obrigatório.
