# SDD — Plataforma de Observabilidade (paridade LangFuse/LangSmith)

> **Status:** Specify
> **Escopo:** Large/Complex (6 fases; novos modelos de dados, nova API SDK, novas abas no dashboard)
> **Branch sugerida:** `feature/observability-platform`
> **Depende de:** features `observability-reliability` (schema v2, exporters, dashboard, tracer) e
> `golden-dataset-evaluation` (módulo `eval/`, judge, runner, dashboard eval)
> **Última atualização:** 2026-06-17

## 1. Problema

O TraceCast já observa produção (tracing) e já avalia offline contra golden datasets (judge +
scorers). Mas, comparado a LangFuse/LangSmith, faltam peças centrais para ser uma plataforma de
observabilidade "de verdade", **mantendo simplicidade, leveza e zero infraestrutura nova** (sem
ClickHouse; reusa os exporters Mongo/Postgres/JSONL e o dashboard já existentes).

Gaps confirmados por inspeção do código (2026-06-17):

1. **G1 — Persistência de eval não implementada (crítico).** `runner.run_evaluation` chama
   `exporter.export_eval(run)` e `EvalReader` chama `exporter.query_evals(...)` / `exporter.get_eval(...)`,
   mas **nenhum exporter implementa esses métodos**. Resultados de avaliação não são persistidos nem
   lidos pelo dashboard. Tudo a jusante depende disso.
2. **G2 — Sem scores de produção.** Não existe `Score` de primeira classe ligado a um `Trace` de
   produção. Não há API para feedback do usuário (👍/👎), nota humana ou métrica custom sobre um trace
   ao vivo. Hoje scores só existem dentro de um `EvalRun` offline.
3. **G3 — Métricas prontas ausentes.** Só há 4 scorers de string + judge genérico. Faltam métricas
   nomeadas (faithfulness, answer_relevancy, context_precision/recall, hallucination, toxicity,
   conciseness).
4. **G4 — Sem prompt management.** Não há prompts versionados, fetch por label, nem ligação
   versão-de-prompt → trace.
5. **G5 — Sem experimentos/comparação.** Existe `EvalRun` isolado, mas não há comparação A/B
   (regressão) entre runs.
6. **G6 — Sem online/continuous eval.** Só batch offline; não há amostragem de tráfego de produção
   disparando judge/métricas automaticamente.
7. **G7 — Datasets só à mão.** Não dá para promover um trace de produção a caso de golden dataset.

## 2. Objetivos

- [ ] Persistir e ler `EvalRun` pelos exporters existentes (desbloqueia o que já foi construído).
- [ ] `Score` de primeira classe ligado a traces de produção, com API SDK (`tracecast.score(...)`).
- [ ] Biblioteca de métricas nomeadas reusando `LLMJudge` + heurísticas.
- [ ] Comparação A/B de runs no dashboard (delta por caso, regressões em vermelho).
- [ ] Online eval por amostragem (N% do tráfego → métricas → `Score`).
- [ ] Promover trace de produção a caso de dataset (SDK + dashboard).
- [ ] Prompt management versionado com cache cliente e auto-link no trace.

**Princípio transversal:** nenhuma fase adiciona backend novo. Tudo passa pelos contratos de exporter
e pelo dashboard já existentes. Cada fase é um vertical slice demonstrável.

## 3. Decisões (AD)

- **AD-1 — Contrato único de persistência por domínio.** Cada novo domínio (eval, score, prompt) ganha
  um par de métodos opcionais no exporter: `export_<x>` (escrita) e `query_<x>`/`get_<x>` (leitura),
  espelhando o padrão já assumido por `runner`/`EvalReader`. Exporter que não implementa = no-op de
  escrita / lista vazia na leitura (degradação graciosa, como hoje).
- **AD-2 — Coleções/tabelas separadas.** `tracecast_evals`, `tracecast_scores`, `tracecast_prompts`.
  Postgres idempotente via `ON CONFLICT ... DO UPDATE` (mesmo padrão do `PostgresExporter` atual).
- **AD-3 — `Score` é genérico e poliforma.** Um `Score` referencia `trace_id` (obrigatório) e
  opcionalmente `span_id`. Campo `kind ∈ {human, llm, heuristic}` e `data_type ∈ {numeric, boolean, categorical}`.
  Vale para feedback do usuário, anotação humana e output de métrica automática — mesma tabela.
- **AD-4 — Métricas reusam `LLMJudge` e `SCORERS`.** Uma "métrica" é um preset: nome + tipo
  (llm|heuristic) + (para llm) rubrica/critério e prompt; (para heuristic) função. Registradas num
  `METRICS` registry análogo a `SCORERS`. Métricas RAG recebem `context` via campo dedicado.
- **AD-5 — Experimento = comparação de `EvalRun` existentes.** Não há novo modelo pesado; compare
  consome dois (ou N) `run_id` já persistidos e calcula deltas. Reusa `EvalReader`.
- **AD-6 — Online eval é assíncrono e best-effort.** Um sampler intercepta a exportação de trace,
  sorteia N%, e em background roda métricas selecionadas, gravando `Score` com `kind=llm|heuristic`.
  Falha de métrica nunca afeta o trace nem o app (mesma política try/except dos exporters).
- **AD-7 — `add_to_dataset` anexa caso a um golden JSON** (single ou multi-turn), derivando
  `input`/`expected` do trace. Mantém o formato de dataset atual (AD-2 da feature golden-dataset).
- **AD-8 — Prompt management com cache cliente.** `get_prompt(name, label="production")` resolve a
  versão ativa, faz cache em memória com TTL, e injeta `prompt_name`/`prompt_version` no `metadata` do
  trace corrente (link versão→trace). Prompts são persistidos via exporter (AD-1).
- **AD-9 — Standalone server é read-only para tudo.** Igual à feature golden-dataset: escrita/disparo
  (run, score, online eval, criação de prompt) só no dashboard **embutido** no processo; standalone
  apenas consome.
- **AD-10 — Paridade TypeScript fica fora deste SDD.** O pacote `tracecast-ts` hoje só tem `dashboard/`;
  reescrever o SDK TS é épico separado. Ver Out of Scope.

## 4. Out of Scope

| Item | Razão |
| ---- | ----- |
| Paridade do SDK TypeScript (tracer + eval em TS) | `tracecast-ts/src` só tem `dashboard/`; é reescrita grande, épico próprio (AD-10) |
| Annotation queue com workflow multiusuário | Precisa UI rica + auth; G6 humano fica em fase futura |
| Playground de prompts interativo | LangFuse-like; pesado em UI, não essencial p/ paridade core |
| Novo backend analítico (ClickHouse/OLAP) | Princípio: zero infra nova; exporters atuais bastam |
| RBAC / multi-tenant / billing | Fora do escopo de uma lib open-source leve |
| Disparo de run/score a partir do server standalone | AD-9: standalone é read-only |

## 5. User Stories

### Fase 0 — Persistência de eval

#### P1: Persistir e ler EvalRun ⭐ MVP

**User Story**: Como dev, quero que `run_evaluation` salve o `EvalRun` e que o dashboard liste/abra
runs, para que a avaliação já construída pare de se perder.

**Why P1**: Bloqueia tudo. Funcionalidade já existe mas é inerte sem persistência.

**Acceptance Criteria**:
1. WHEN `run_evaluation(...)` termina com um exporter Mongo/Postgres/JSONL THEN o sistema SHALL gravar
   o `EvalRun.to_dict()` na coleção/tabela `tracecast_evals`.
2. WHEN o dashboard chama `EvalReader.list_runs(...)` THEN o exporter SHALL retornar runs ordenados por
   `started_at desc`, filtráveis por `project_id`/`dataset_name`/intervalo de datas, com `limit`/`offset`.
3. WHEN `EvalReader.get_run(run_id)` é chamado THEN o exporter SHALL retornar o run completo (cases +
   turns + scores) ou `None`.
4. WHEN o exporter não implementa `export_eval` THEN o sistema SHALL seguir sem erro (no-op atual).

**Independent Test**: rodar uma eval com `file://out.jsonl`, depois `EvalReader` lista e abre o run.

### Fase 1 — Scores de produção

#### P1: Score ligado a trace ⭐ MVP

**User Story**: Como dev, quero anexar um score (feedback, nota, métrica) a um trace de produção via
SDK, para capturar qualidade sobre tráfego real.

**Why P1**: É o recurso que LangFuse mais vende; pequeno e alto valor.

**Acceptance Criteria**:
1. WHEN chamo `tracecast.score(trace_id, name="user_feedback", value=1, comment="útil")` THEN o sistema
   SHALL construir um `Score` e persistir via `export_score`.
2. WHEN um `Score` é gravado sem `span_id` THEN ele SHALL ligar-se ao trace inteiro; com `span_id`, ao span.
3. WHEN o dashboard abre o detalhe de um trace THEN SHALL exibir todos os `Score` daquele `trace_id`.
4. WHEN `value` viola o `data_type` declarado (ex.: boolean fora de {0,1}) THEN o sistema SHALL rejeitar
   com erro claro antes de persistir.

**Independent Test**: criar trace, chamar `tracecast.score(...)`, ver o score no detalhe do trace.

### Fase 2 — Métricas prontas

#### P1: Registry de métricas nomeadas ⭐ MVP

**User Story**: Como dev, quero métricas prontas (faithfulness, answer_relevancy, context_precision,
context_recall, hallucination, toxicity, conciseness) usáveis no judge/runner sem escrever prompt.

**Acceptance Criteria**:
1. WHEN referencio `criteria=["faithfulness", "answer_relevancy"]` no `@evaluator`/runner THEN o sistema
   SHALL resolver presets do registry `METRICS` e aplicá-los como critérios do judge.
2. WHEN uma métrica RAG é usada THEN o caso SHALL fornecer `context`, e a métrica SHALL pontuar a
   resposta contra o `context` (não só contra `expected`).
3. WHEN uma métrica heurística (ex.: `toxicity` via lista/Detoxify opcional) roda THEN SHALL produzir
   score 0–1 determinístico sem chamar LLM.
4. WHEN uma métrica desconhecida é referenciada THEN o sistema SHALL erro com a lista de métricas válidas.

**Independent Test**: rodar eval com `criteria=["faithfulness"]` e ver score por critério no run.

### Fase 3 — Experimentos / comparação

#### P2: Comparar dois runs

**User Story**: Como dev, quero comparar dois `EvalRun` lado a lado para detectar regressão entre
mudanças de prompt/modelo/código.

**Acceptance Criteria**:
1. WHEN chamo `compare(run_a_id, run_b_id)` THEN o sistema SHALL alinhar casos por `case_id` e retornar
   delta de `overall_score` por caso e agregados (`pass_rate`, `avg_score`).
2. WHEN um caso existe em A mas não em B (ou vice-versa) THEN o resultado SHALL marcá-lo como
   `added`/`removed`.
3. WHEN o dashboard abre a comparação THEN regressões (delta < 0) SHALL aparecer destacadas.

**Independent Test**: rodar a mesma eval 2x mudando o alvo, comparar e ver os deltas.

### Fase 4 — Online eval + dataset a partir de trace

#### P2: Online eval por amostragem

**User Story**: Como dev, quero amostrar N% do tráfego de produção e rodar métricas automaticamente,
gravando scores, para monitorar qualidade contínua sem dataset.

**Acceptance Criteria**:
1. WHEN configuro `OnlineEval(sample_rate=0.1, metrics=["toxicity"])` e um trace é exportado THEN o
   sistema SHALL, com prob. 0.1, rodar as métricas em background e gravar `Score(kind=llm|heuristic)`.
2. WHEN uma métrica online falha THEN o trace e o app SHALL seguir intactos (best-effort, AD-6).
3. WHEN `sample_rate=0` THEN nenhuma avaliação online SHALL ocorrer.

**Independent Test**: configurar `sample_rate=1.0` + `toxicity`, gerar trace, ver `Score` anexado.

#### P3: Promover trace a caso de dataset

**User Story**: Como dev, quero anexar um trace de produção como caso de um golden dataset.

**Acceptance Criteria**:
1. WHEN chamo `add_to_dataset(trace_id, "datasets/x.json", expected=...)` THEN o sistema SHALL derivar
   `input` do trace e anexar um caso ao JSON, preservando o formato existente.
2. WHEN o trace é multi-turn THEN o caso gerado SHALL usar o formato `turns`.

**Independent Test**: promover um trace, abrir o JSON e ver o caso novo; rodar eval com ele.

### Fase 5 — Prompt management

#### P2: Prompts versionados com fetch por label

**User Story**: Como dev, quero gerenciar prompts versionados e buscá-los por label em runtime, com
cache, ligando a versão usada ao trace.

**Acceptance Criteria**:
1. WHEN crio/atualizo um prompt THEN o sistema SHALL gravar uma nova `version` (inteiro incremental) via
   `export_prompt`, sem mutar versões antigas.
2. WHEN chamo `get_prompt("greeting", label="production")` THEN SHALL retornar a versão com aquele label,
   servida de cache em memória dentro do TTL (sem latência extra após o 1º fetch).
3. WHEN um prompt é resolvido dentro de um trace ativo THEN `prompt_name`/`prompt_version` SHALL ser
   injetados no `metadata` do trace.
4. WHEN o label não existe THEN o sistema SHALL erro claro com os labels disponíveis.

**Independent Test**: criar v1/v2, apontar label `production` p/ v2, `get_prompt` retorna v2 e o trace
registra `prompt_version=2`.

## 6. Edge Cases

- WHEN dois exporters legíveis coexistem THEN reader SHALL usar o primeiro que implementa `query_*` (padrão `_readable` atual).
- WHEN `score(value=...)` com `data_type=categorical` recebe valor fora do conjunto permitido THEN SHALL rejeitar.
- WHEN `compare` recebe runs de datasets diferentes THEN SHALL avisar (`dataset_mismatch=true`) mas ainda alinhar por `case_id`.
- WHEN online eval e o trace não tem output de LLM THEN as métricas que exigem output SHALL ser puladas (score n/a), não falhar.
- WHEN `get_prompt` é chamado sem exporter de prompt configurado THEN SHALL erro explicativo (não silencioso).
- WHEN `add_to_dataset` aponta para JSON inexistente THEN SHALL criar o arquivo com `cases: []` + o caso novo.

## 7. Requirement Traceability

| Requirement ID | Story | Fase | Status |
| -------------- | ----- | ---- | ------ |
| STORE-01 | P1 Persistir EvalRun (write) | 0 | Pending |
| STORE-02 | P1 query_evals (list) | 0 | Pending |
| STORE-03 | P1 get_eval (detail) | 0 | Pending |
| STORE-04 | P1 degradação graciosa | 0 | Pending |
| SCORE-01 | P1 modelo Score + validação | 1 | Pending |
| SCORE-02 | P1 API `tracecast.score()` + export_score | 1 | Pending |
| SCORE-03 | P1 query_scores + detalhe no dashboard | 1 | Pending |
| METRIC-01 | P1 registry METRICS + presets LLM | 2 | Pending |
| METRIC-02 | P1 métricas RAG com context | 2 | Pending |
| METRIC-03 | P1 métricas heurísticas (toxicity) | 2 | Pending |
| EXP-01 | P2 `compare()` core (deltas) | 3 | Pending |
| EXP-02 | P2 view de comparação no dashboard | 3 | Pending |
| ONLINE-01 | P2 sampler + execução background | 4 | Pending |
| ONLINE-02 | P2 best-effort / sample_rate | 4 | Pending |
| DSGEN-01 | P3 `add_to_dataset()` | 4 | Pending |
| PROMPT-01 | P2 modelo Prompt + versionamento + export_prompt | 5 | Pending |
| PROMPT-02 | P2 `get_prompt()` + cache + labels | 5 | Pending |
| PROMPT-03 | P2 auto-link versão→trace | 5 | Pending |

**Status values:** Pending → In Design → In Tasks → Implementing → Verified
**Coverage:** 18 requisitos. Mapeamento → tasks em `tasks.md`.

## 8. Success Criteria

- [ ] Uma eval rodada via CLI aparece no dashboard (lista + detalhe) — fecha G1.
- [ ] `tracecast.score()` anexa feedback a um trace de produção visível no dashboard — fecha G2.
- [ ] `criteria=["faithfulness","answer_relevancy"]` funcionam sem escrever prompt — fecha G3.
- [ ] Comparar dois runs mostra regressões — fecha G5.
- [ ] `sample_rate=1.0 + toxicity` anexa score a traces de produção — fecha G6.
- [ ] `add_to_dataset` promove trace a caso e a eval roda com ele — fecha G7.
- [ ] `get_prompt(label=...)` resolve versão e o trace registra a versão — fecha G4.
- [ ] Suite de testes Python verde (gate: `python -m pytest tests/ -v`), sem regressão das 109 atuais.
