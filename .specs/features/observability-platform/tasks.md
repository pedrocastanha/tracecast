# Plataforma de Observabilidade — Tasks

**Design**: `.specs/features/observability-platform/design.md`
**Status**: Draft

> **TESTING.md ausente** (`.specs/codebase/` só tem CONCERNS.md). Convenção do projeto (memória +
> README): testes co-localizados em `packages/tracecast-py/tests/`, `pytest`.
> **Gate único**: `cd packages/tracecast-py && python -m pytest tests/ -v` (baseline: 109 verdes).
> Cada task que cria código Python inclui testes unitários na MESMA task (regra de co-localização).
> Toda task fecha com um **commit atômico**.

---

## Execution Plan

### Fase 0 — Persistência de eval (desbloqueia tudo) — Sequential

```
T1 → (T2, T3, T4) → T5
```

### Fase 1 — Scores de produção

```
T6 → T7 → (T8, T9) → T10
```

### Fase 2 — Métricas prontas

```
T11 → (T12, T13) → T14
```

### Fase 3 — Experimentos / comparação

```
T15 → T16
```

### Fase 4 — Online eval + dataset-from-trace

```
(T6,T7) ─┐
T11 ─────┼→ T17 → T18
T1 ──────┘
T19 (independe, só precisa de reader de trace)
```

### Fase 5 — Prompt management

```
T20 → T21 → (T22, T23) → T24
```

**Ordem recomendada de entrega:** Fase 0 → 1 → 2 → 3 → 4 → 5 (valor/esforço). Fases são
independentes entre si após a 0; 4 depende de 1 (Score) e 2 (métricas); 3 e 5 são autônomas.

---

## Task Breakdown

### Fase 0 — Persistência de eval

#### T1: Adicionar métodos opcionais de domínio ao `BaseExporter`
**What**: Declarar `export_eval/query_evals/get_eval`, `export_score/query_scores`, `export_prompt/query_prompts/get_prompt_row` como métodos não-abstratos com default no-op/`[]`/`None`.
**Where**: `packages/tracecast-py/tracecast/exporters/base.py`
**Depends on**: None
**Reuses**: estrutura atual de `BaseExporter`
**Requirement**: STORE-01, STORE-04
**Done when**:
- [ ] 8 métodos presentes com defaults seguros (no-op escrita / `[]` ou `None` leitura)
- [ ] Exporter existente sem override continua funcionando (degradação graciosa)
- [ ] Teste: subclasse mínima não quebra; `query_evals` default → `[]`
- [ ] Gate passa: `python -m pytest tests/ -v` (≥109)
**Tests**: unit · **Gate**: full
**Commit**: `feat(exporters): optional domain methods on BaseExporter`

#### T2: Implementar persistência de eval no `JsonFileExporter` [P]
**What**: `export_eval` (append JSONL irmão `*.evals.jsonl`), `query_evals` (scan+filtro+sort), `get_eval`.
**Where**: `exporters/json_file.py`
**Depends on**: T1
**Reuses**: append/scan atuais; `EvalRun.from_dict`
**Requirement**: STORE-01/02/03
**Done when**:
- [ ] Run gravado e relido; filtros `project_id/dataset_name/datas` e `limit/offset` corretos
- [ ] `get_eval(run_id)` retorna completo ou `None`
- [ ] Teste unit cobre write→list→get + arquivo inexistente
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(exporters): eval persistence in JsonFileExporter`

#### T3: Implementar persistência de eval no `MongoExporter` [P]
**What**: Coleção `tracecast_evals`; `export_eval` via `update_one(upsert=True)` por `run_id`; `query_evals`/`get_eval`.
**Where**: `exporters/mongo.py`
**Depends on**: T1
**Reuses**: padrão `__init__`/`query`/`count`; idempotência (C11)
**Requirement**: STORE-01/02/03
**Done when**:
- [ ] Upsert idempotente (re-export não duplica)
- [ ] Filtros traduzidos para query Mongo; sort `started_at desc`
- [ ] Teste com `mongomock`/patch cobre write→list→get
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(exporters): eval persistence in MongoExporter`

#### T4: Implementar persistência de eval no `PostgresExporter` [P]
**What**: Tabela `tracecast_evals` (PK `run_id`); `export_eval` com `ON CONFLICT (run_id) DO UPDATE`; `query_evals`/`get_eval`.
**Where**: `exporters/postgres.py`
**Depends on**: T1
**Reuses**: schema dinâmico + `ON CONFLICT` atual
**Requirement**: STORE-01/02/03
**Done when**:
- [ ] WHERE real no SQL p/ filtros (não em memória)
- [ ] Upsert idempotente
- [ ] Teste com patch de cursor cobre write→list→get
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(exporters): eval persistence in PostgresExporter`

#### T5: Endpoint dashboard de eval ligado às impls reais
**What**: Confirmar/expor `GET /api/evals` e `GET /api/evals/{run_id}` no router usando `EvalReader`; verificar `_readable` acha o exporter.
**Where**: `dashboard/router.py` (+ ajuste mínimo em `dashboard/eval_reader.py` se preciso)
**Depends on**: T2, T3, T4
**Reuses**: `_make_router`, `EvalReader`, `_parse_iso`
**Requirement**: STORE-02/03
**Done when**:
- [ ] `GET /api/evals` lista runs; `GET /api/evals/{id}` abre detalhe
- [ ] Teste de integração via `TestClient` com `JsonFileExporter`
- [ ] Gate passa
**Tests**: integration · **Gate**: full
**Commit**: `feat(dashboard): wire eval list/detail endpoints`

### Fase 1 — Scores de produção

#### T6: Modelo `Score` + validação
**What**: `dataclass Score` com `to_dict/from_dict` e `validate()` (numeric/boolean/categorical).
**Where**: `models/score.py`
**Depends on**: None
**Reuses**: estilo de `models/span.py` (`to_dict/from_dict`)
**Requirement**: SCORE-01
**Done when**:
- [ ] `validate()` rejeita boolean∉{0,1} e categorical sem `string_value`
- [ ] Round-trip `to_dict→from_dict` estável
- [ ] Teste unit cobre cada `data_type` + casos inválidos
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(models): Score model with data_type validation`

#### T7: API `tracecast.score()` + `export_score` nos 3 exporters
**What**: Função `score(...)` em `core/scoring.py` (constrói, valida, persiste); implementar `export_score`/`query_scores` em json_file/mongo/postgres (`tracecast_scores`, idempotente por `score_id`). Export em `__init__.py`.
**Where**: `core/scoring.py`, `exporters/{json_file,mongo,postgres}.py`, `__init__.py`
**Depends on**: T6
**Reuses**: T1 contrato; padrão de persistência da Fase 0; política try/except
**Requirement**: SCORE-02
**Done when**:
- [ ] `tracecast.score(trace_id, name, value, ...)` grava via exporter
- [ ] `value` inválido → erro antes de persistir
- [ ] Falha de exporter não propaga (logger.error)
- [ ] Teste unit cobre os 3 exporters (patch) + degradação graciosa
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(core): tracecast.score() API + export_score`

#### T8: `query_scores` filtrável + `ScoreReader` [P]
**What**: `query_scores(trace_id=..., name=..., datas, limit, offset)` nos exporters; `dashboard/score_reader.py` no padrão `_readable`.
**Where**: `exporters/*` (refino), `dashboard/score_reader.py`
**Depends on**: T7
**Reuses**: `EvalReader._readable`
**Requirement**: SCORE-03
**Done when**:
- [ ] `ScoreReader.list_for_trace(trace_id)` retorna scores ordenados por `created_at`
- [ ] Teste unit do reader com `JsonFileExporter`
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(dashboard): ScoreReader`

#### T9: Endpoint `GET /api/traces/{id}/scores` [P]
**What**: Rota que devolve scores do trace via `ScoreReader`.
**Where**: `dashboard/router.py`
**Depends on**: T7
**Reuses**: `_make_router`
**Requirement**: SCORE-03
**Done when**:
- [ ] Rota responde lista de scores; trace sem score → `[]`
- [ ] Teste `TestClient`
- [ ] Gate passa
**Tests**: integration · **Gate**: full
**Commit**: `feat(dashboard): trace scores endpoint`

#### T10: Aba Scores no detalhe do trace (frontend)
**What**: Renderizar scores (nome, valor, kind, comment) no painel de detalhe do trace.
**Where**: `dashboard/static/` (build do frontend)
**Depends on**: T8, T9
**Reuses**: componentes de detalhe existentes
**Requirement**: SCORE-03
**Done when**:
- [ ] Scores aparecem no detalhe; estado vazio tratado
- [ ] Verificação manual via `/run` ou screenshot (sem teste unit de UI — convenção atual)
- [ ] Gate passa (sem regressão backend)
**Tests**: none · **Gate**: build
**Commit**: `feat(dashboard): scores panel in trace detail`

### Fase 2 — Métricas prontas

#### T11: Registry `METRICS` + presets LLM (faithfulness, answer_relevancy, hallucination, conciseness)
**What**: `eval/metrics.py` com `register_metric`, `resolve_metrics(names)` → `criteria` p/ `LLMJudge`; presets LLM.
**Where**: `eval/metrics.py`, export em `eval/__init__.py`
**Depends on**: None
**Reuses**: `LLMJudge.score(criteria=...)`, formato de critério `{name, description}`
**Requirement**: METRIC-01
**Done when**:
- [ ] `resolve_metrics(["faithfulness"])` → critério válido; nome inválido → erro com lista
- [ ] Teste unit com `LLMJudge(call_fn=fake)` valida pontuação por critério
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(eval): metrics registry + LLM presets`

#### T12: Métricas RAG com `context` (context_precision, context_recall, answer_relevancy) [P]
**What**: Suporte a `context` no caso/turn e nos presets RAG; runner passa `context` ao judge.
**Where**: `eval/metrics.py`, `eval/dataset.py` (campo `context`), `eval/runner.py`, `eval/judge.py` (prompt c/ context)
**Depends on**: T11
**Reuses**: parser de dataset; `_build_prompt`
**Requirement**: METRIC-02
**Done when**:
- [ ] Caso com `context` pontua resposta contra context; sem context → métrica RAG n/a (não falha)
- [ ] Teste unit com judge fake
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(eval): RAG metrics with retrieval context`

#### T13: Métricas heurísticas (`toxicity`) sem LLM [P]
**What**: Heurística determinística (detoxify lazy; fallback lista de termos) registrada no `METRICS`/`SCORERS`.
**Where**: `eval/metrics.py` (ou `eval/scorers.py`)
**Depends on**: T11
**Reuses**: assinatura de `SCORERS`/`run_scorer`
**Requirement**: METRIC-03
**Done when**:
- [ ] `toxicity` retorna 0–1 sem chamar LLM; sem `detoxify` usa fallback
- [ ] Teste unit (texto tóxico vs neutro)
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(eval): heuristic toxicity metric`

#### T14: Integrar métricas no `runner`/`@evaluator`
**What**: `criteria`/`scorers` aceitam nomes de `METRICS`; runner resolve presets transparentemente.
**Where**: `eval/runner.py`, `eval/decorator.py`
**Depends on**: T12, T13
**Reuses**: fluxo atual de `run_evaluation`
**Requirement**: METRIC-01/02/03
**Done when**:
- [ ] Eval com `criteria=["faithfulness","toxicity"]` roda fim-a-fim
- [ ] Teste integração (judge fake) verifica scores no `EvalRun`
- [ ] Gate passa
**Tests**: integration · **Gate**: full
**Commit**: `feat(eval): resolve named metrics in runner`

### Fase 3 — Experimentos / comparação

#### T15: `compare()` core
**What**: `eval/compare.py` — alinha 2 runs por `case_id`, calcula deltas + `dataset_mismatch`, marca added/removed.
**Where**: `eval/compare.py`
**Depends on**: T1 (persistência p/ obter runs) — usa `EvalRun.from_dict`
**Reuses**: `eval/models.py`, `EvalReader.get_run`
**Requirement**: EXP-01
**Done when**:
- [ ] Deltas por caso e agregados corretos; added/removed corretos; mismatch sinalizado
- [ ] Teste unit com 2 runs sintéticos
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(eval): compare two EvalRuns`

#### T16: Endpoint + view de comparação
**What**: `GET /api/evals/compare?a=&b=` + tela lado a lado com regressões destacadas.
**Where**: `dashboard/router.py`, `dashboard/static/`
**Depends on**: T15, T5
**Reuses**: `EvalReader`, `_make_router`
**Requirement**: EXP-02
**Done when**:
- [ ] Endpoint devolve `CompareResult`; UI destaca delta<0
- [ ] Teste `TestClient` do endpoint
- [ ] Gate passa
**Tests**: integration · **Gate**: full
**Commit**: `feat(dashboard): eval comparison view`

### Fase 4 — Online eval + dataset-from-trace

#### T17: `OnlineEval` sampler (hook pós-export, best-effort)
**What**: `eval/online.py` — `OnlineEval(sample_rate, metrics, exporters)`; `maybe_evaluate(trace)` sorteia e roda métricas em background → `export_score(kind=llm|heuristic)`.
**Where**: `eval/online.py`, ponto de engate no `core/tracer.py` (hook análogo a `on_export_error`)
**Depends on**: T7 (export_score), T11 (METRICS), T1
**Reuses**: hook `on_export_error` pattern (`core/tracer.py:42`); `asyncio.to_thread`
**Requirement**: ONLINE-01/02
**Done when**:
- [ ] `sample_rate=1.0` grava score; `=0` não grava nada
- [ ] Falha de métrica não afeta trace; **latência/contagem de spans inalteradas** (teste de não-regressão, C9/C10)
- [ ] Teste unit cobre amostragem (seed fixa) + best-effort
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(eval): online evaluation sampler`

#### T18: Config de OnlineEval no Tracer + doc
**What**: Permitir registrar `OnlineEval` no `Tracer`/`auto_instrument`; documentar no README.
**Where**: `core/tracer.py`, `instrument.py`, `README.md`
**Depends on**: T17
**Reuses**: construção atual do `Tracer`
**Requirement**: ONLINE-01
**Done when**:
- [ ] `Tracer(..., online_eval=OnlineEval(...))` funciona; doc com exemplo
- [ ] Teste integração: trace exportado → score anexado
- [ ] Gate passa
**Tests**: integration · **Gate**: full
**Commit**: `feat(core): register OnlineEval on Tracer`

#### T19: `add_to_dataset(trace_id, path, expected=...)`
**What**: Buscar trace via reader, derivar `input` (single/multi-turn), anexar caso ao JSON (cria se ausente).
**Where**: `eval/dataset.py`
**Depends on**: None (usa reader de trace existente)
**Reuses**: `TraceReader`, formato de `_normalize_case` (inverso)
**Requirement**: DSGEN-01
**Done when**:
- [ ] Caso anexado em formato válido (single e multi-turn); JSON inexistente é criado
- [ ] Eval roda com o dataset resultante
- [ ] Teste unit cobre criação + append + multi-turn
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(eval): promote trace to dataset case`

### Fase 5 — Prompt management

#### T20: Modelo `PromptVersion` + `export_prompt`/`query_prompts`/`get_prompt_row`
**What**: `prompts/models.py` + impl de persistência nos 3 exporters (`tracecast_prompts`, versão imutável, label move).
**Where**: `prompts/models.py`, `exporters/{json_file,mongo,postgres}.py`
**Depends on**: T1
**Reuses**: contrato T1; idempotência por (`name`,`version`)
**Requirement**: PROMPT-01
**Done when**:
- [ ] Nova versão = max+1; versões antigas imutáveis; `set_label` move label
- [ ] Teste unit dos 3 exporters (patch)
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(prompts): PromptVersion model + persistence`

#### T21: Cliente `get_prompt`/`create_prompt`/`set_label` com cache TTL
**What**: `prompts/client.py` — resolve por label/versão, cache em memória com TTL; export em `__init__.py`.
**Where**: `prompts/client.py`, `__init__.py`
**Depends on**: T20
**Reuses**: contrato de exporter; relógio simples p/ TTL
**Requirement**: PROMPT-02
**Done when**:
- [ ] `get_prompt(name, label=)` retorna versão certa; 2º fetch vem do cache (sem I/O)
- [ ] Label inexistente → erro com labels disponíveis; sem exporter → erro explicativo
- [ ] Teste unit cobre cache hit/miss + erros
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(prompts): client with label resolution + TTL cache`

#### T22: Auto-link versão→trace [P]
**What**: Ao resolver prompt dentro de trace ativo, injetar `prompt_name`/`prompt_version` no `metadata` do trace.
**Where**: `prompts/client.py`
**Depends on**: T21
**Reuses**: `bind_context`/`Tracer.current`, `Trace.metadata`
**Requirement**: PROMPT-03
**Done when**:
- [ ] Trace ativo recebe `prompt_*` no metadata; sem trace ativo não falha
- [ ] Teste unit verifica metadata injetada
- [ ] Gate passa
**Tests**: unit · **Gate**: full
**Commit**: `feat(prompts): link resolved prompt version to active trace`

#### T23: Endpoints de prompt + `PromptReader` [P]
**What**: `GET /api/prompts`, `GET /api/prompts/{name}` via `PromptReader` (padrão `_readable`).
**Where**: `dashboard/prompt_reader.py`, `dashboard/router.py`
**Depends on**: T20
**Reuses**: `EvalReader._readable`, `_make_router`
**Requirement**: PROMPT-01
**Done when**:
- [ ] Endpoints listam prompts e versões; teste `TestClient`
- [ ] Gate passa
**Tests**: integration · **Gate**: full
**Commit**: `feat(dashboard): prompt endpoints + PromptReader`

#### T24: Aba Prompts (frontend)
**What**: Tela listando prompts, versões e labels.
**Where**: `dashboard/static/`
**Depends on**: T22, T23
**Reuses**: componentes de tabela existentes
**Requirement**: PROMPT-01
**Done when**:
- [ ] Aba mostra prompts/versões/labels; estado vazio tratado
- [ ] Verificação manual (sem teste unit de UI)
- [ ] Gate passa (sem regressão backend)
**Tests**: none · **Gate**: build
**Commit**: `feat(dashboard): prompts tab`

---

## Parallel Execution Map

```
Fase 0:  T1 ──┬─ T2 [P] ─┐
              ├─ T3 [P] ─┼─→ T5
              └─ T4 [P] ─┘
Fase 1:  T6 → T7 ──┬─ T8 [P] ─┐
                   └─ T9 [P] ─┴─→ T10
Fase 2:  T11 ─┬─ T12 [P] ─┐
              └─ T13 [P] ─┴─→ T14
Fase 3:  T15 → T16
Fase 4:  (T7,T11,T1) → T17 → T18 ;  T19 (independente)
Fase 5:  T20 → T21 ─┬─ T22 [P] ─┐
                    └─ T23 [P] ─┴─→ T24
```

**Restrição [P]:** todos os `[P]` aqui são parallel-safe — escrevem arquivos distintos, sem estado
mutável compartilhado, e os testes (unit/integration por patch) não colidem. T2/T3/T4 tocam exporters
diferentes. T8/T9, T12/T13, T22/T23 idem.

---

## Check 1 — Task Granularity

| Task | Escopo | Status |
| ---- | ------ | ------ |
| T1 | 1 arquivo (base.py), contrato | ✅ |
| T2/T3/T4 | 1 exporter cada | ✅ |
| T5 | endpoints eval (1 arquivo router) | ✅ |
| T6 | 1 modelo | ✅ |
| T7 | API score + export_score (coeso, 1 conceito) | ⚠️ OK (1 conceito atravessa 3 exporters; coeso) |
| T8/T9/T10 | reader / endpoint / UI | ✅ |
| T11 | registry + presets LLM | ✅ |
| T12/T13 | 1 família de métrica cada | ✅ |
| T14 | integração no runner | ✅ |
| T15/T16 | core compare / view | ✅ |
| T17 | sampler | ✅ |
| T18/T19 | config / função dataset | ✅ |
| T20 | modelo + persistência prompt (coeso) | ⚠️ OK (1 domínio) |
| T21/T22/T23/T24 | client / link / endpoints / UI | ✅ |

T7 e T20 atravessam os 3 exporters por serem o mesmo conceito de persistência; aceitável como uma
task coesa (espelha como a Fase 0 já está fatiada). Se na execução passarem de ~5 passos, fatiar por
exporter (como T2/T3/T4).

---

## Check 2 — Diagram ↔ Definition Cross-Check

| Task | Depends on (corpo) | Diagrama | Status |
| ---- | ------------------ | -------- | ------ |
| T1 | None | raiz | ✅ |
| T2,T3,T4 | T1 | T1→ | ✅ |
| T5 | T2,T3,T4 | →T5 | ✅ |
| T6 | None | raiz | ✅ |
| T7 | T6 | T6→T7 | ✅ |
| T8,T9 | T7 | T7→ | ✅ |
| T10 | T8,T9 | →T10 | ✅ |
| T11 | None | raiz | ✅ |
| T12,T13 | T11 | T11→ | ✅ |
| T14 | T12,T13 | →T14 | ✅ |
| T15 | T1 | T1→T15 (Fase 4 box lista T1) | ✅ |
| T16 | T15,T5 | T15→T16 | ✅ |
| T17 | T7,T11,T1 | (T7,T11,T1)→T17 | ✅ |
| T18 | T17 | T17→T18 | ✅ |
| T19 | None | independente | ✅ |
| T20 | T1 | T1→T20 | ✅ |
| T21 | T20 | T20→T21 | ✅ |
| T22,T23 | T21 / T20 | T21→ | ✅ (T23 depende de T20; mostrado sob T21 por ser ≥T20 — ver nota) |
| T24 | T22,T23 | →T24 | ✅ |

Nota: T23 depende só de T20 (não de T21); aparece no ramo de T21 no diagrama por ordenação visual.
Sem ciclo, sem `[P]` interdependente.

---

## Check 3 — Test Co-location Validation

Sem TESTING.md → matriz default: todo código Python (models/core/exporters/eval/prompts) = **unit**;
endpoints de dashboard = **integration** (TestClient); UI estática = **none** (verificação manual,
convenção atual do repo — frontend não tem suíte unit).

| Task | Camada criada | Exigido | Task diz | Status |
| ---- | ------------- | ------- | -------- | ------ |
| T1 | exporter base | unit | unit | ✅ |
| T2–T4 | exporter | unit | unit | ✅ |
| T5 | endpoint | integration | integration | ✅ |
| T6 | model | unit | unit | ✅ |
| T7 | core+exporter | unit | unit | ✅ |
| T8 | reader | unit | unit | ✅ |
| T9 | endpoint | integration | integration | ✅ |
| T10 | UI estática | none | none | ✅ |
| T11 | eval | unit | unit | ✅ |
| T12,T13 | eval | unit | unit | ✅ |
| T14 | eval (runner) | integration | integration | ✅ |
| T15 | eval | unit | unit | ✅ |
| T16 | endpoint+UI | integration | integration | ✅ |
| T17 | eval+tracer | unit | unit | ✅ |
| T18 | core (config) | integration | integration | ✅ |
| T19 | eval | unit | unit | ✅ |
| T20 | model+exporter | unit | unit | ✅ |
| T21 | client | unit | unit | ✅ |
| T22 | client | unit | unit | ✅ |
| T23 | endpoint | integration | integration | ✅ |
| T24 | UI estática | none | none | ✅ |

Sem violações. UI `none` é legítimo (matriz default do repo p/ frontend), não deferral de teste de
backend.

---

## Tools / Skills por fase

- **MCP**: `context7` ao mexer com pymongo/psycopg2/fastapi/detoxify (verificar API atual).
- **Skill**: `superpowers:test-driven-development` em cada task de código; `verify`/`run` p/ UI (T10/T24).
- **Sub-agentes**: delegar T2/T3/T4, T12/T13, T22/T23 em paralelo (um por task).

## Pergunta ao usuário antes de Executar

1. Confirmar ordem de entrega (0→1→2→3→4→5) ou priorizar subconjunto (ex.: só 0+1+2)?
2. `toxicity`: aceitar `detoxify` como dep opcional, ou só fallback heurístico (zero dep)?
3. Frontend (T10/T16/T24): buildar nova UI agora ou deixar abas como fase posterior e entregar só backend+endpoints primeiro?
