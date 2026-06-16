# Tasks — Evaluation por Golden Dataset

Tarefas atômicas, commit por tarefa. `[P]` = paralelizável. Cada uma referencia requisito(s) de `spec.md`.
Done-when = critério verificável. Gate = comando que precisa passar.

Ordem sugerida: E1 → E2 → E3 ∥ E4 → E5 → E6 → E7 → E8 → E9 → E10 → E11.

---

## Fase 1 — Núcleo (dados, dataset, decorator)

### E1 Modelos de eval (FR-4.1, FR-3.3)
- **O quê:** `eval/models.py` — `CriterionScore`, `TurnResult`, `EvalCase`, `EvalRun` com
  `to_dict/from_dict` e `EvalRun.finalize()` (agrega pass_rate, avg_score, totais).
- **Reusa:** padrão de `models/trace.py`.
- **Done-when:** round-trip dict de uma run com casos/turns/scores preserva tudo; finalize calcula
  pass_rate correto.
- **Gate:** `pytest tests/eval/test_models.py`.

### E2 Loader de golden dataset (FR-2.1, AD-2)
- **O quê:** `eval/dataset.py` — `load_dataset(path) -> GoldenDataset`; normaliza single-turn e
  multi-turn para `GoldenCase(turns=[...])`; valida (erros claros).
- **Reusa:** —
- **Depends:** —
- **Done-when:** carrega fixtures single+multi-turn; dataset sem `cases` ou turn inválido levanta erro.
- **Gate:** `pytest tests/eval/test_dataset.py`.

### E3 Decorator `@evaluator` + registry (FR-1.1, FR-1.2, FR-1.3)
- **O quê:** `eval/decorator.py` — registra `EvalTarget`; wrapper transparente; aceita `dataset` str|list.
- **Reusa:** padrão de `decorators.py`.
- **Depends:** E1, E2.
- **Done-when:** função decorada roda inalterada; target recuperável do registry por nome; multi-dataset.
- **Gate:** `pytest tests/eval/test_decorator.py`.

---

## Fase 2 — Judge + scorers + runner

### E4 `[P]` Scorers determinísticos (FR-3.2)
- **O quê:** `eval/scorers.py` — `exact_match`, `contains`, `regex`, `similarity` → `CriterionScore`.
- **Depends:** E1.
- **Done-when:** cada scorer retorna 0–1 esperado em casos conhecidos.
- **Gate:** `pytest tests/eval/test_scorers.py`.

### E5 LLM judge (FR-3.1, FR-3.4, NFR-3.1)
- **O quê:** `eval/judge.py` — `Judge` Protocol + `LLMJudge(model, call_fn)`; prompt com rubrica; parse
  robusto de JSON; custo via `calculate_cost`; `call_fn` injetável.
- **Reusa:** `core/cost_calculator.py`, wrappers LLM.
- **Depends:** E1.
- **Done-when:** judge fake retorna scores; JSON ruidoso é parseado; JSON inválido → score 0 + reasoning
  parse_error; tokens/custo contabilizados.
- **Gate:** `pytest tests/eval/test_judge.py`.

### E6 Runner (FR-2.2, FR-2.3, FR-2.4, FR-3.3)
- **O quê:** `eval/runner.py` — `run_evaluation(target, exporters, judge, tracer, project_id)`; executa
  cada caso traceado (linka `trace_id`), roda turns, scorers + judge, agrega, persiste. Erros isolados.
- **Reusa:** `core/tracer.py`, E1–E5, `exporters`.
- **Depends:** E1–E5, E7.
- **Done-when:** dataset de 3 casos + judge fake → EvalRun com pass_rate correto; caso com exceção =
  `status=error` sem abortar; cada caso tem `trace_id` de um trace persistido.
- **Gate:** `pytest tests/eval/test_runner.py`.

---

## Fase 3 — Persistência

### E7 Persistência de evals nos exporters (FR-4.1, FR-4.2, FR-4.3)
- **O quê:** métodos `export_eval/query_evals/get_eval` em Mongo (`*_evals`, upsert), Postgres
  (`*_evals`, ON CONFLICT, conn read dedicada), JSONL (`*.evals.jsonl`), Dict. Reusa tratamento de erro.
- **Reusa:** `exporters/*`, `exporters/query.py`.
- **Depends:** E1.
- **Done-when:** round-trip por exporter; upsert por `run_id`; query filtra por dataset/project/data.
- **Gate:** `pytest tests/eval/test_eval_store.py`.

---

## Fase 4 — Disparo (CLI / script / endpoint)

### E8 CLI `tracecast-eval` + console_script (AD-3)
- **O quê:** `eval/cli.py` — `--target mod:fn --store dsn [--dataset --judge-model]`; reusa
  `build_exporter_from_dsn`; roda `run_evaluation`; exit code != 0 se `pass_rate < threshold`. Script
  Python via `from tracecast.eval import run_evaluation`. Console_script no `pyproject.toml`.
- **Reusa:** `serve.py:build_exporter_from_dsn`, E6.
- **Depends:** E6.
- **Done-when:** `tracecast-eval` roda um dataset fake e imprime resumo; exit code reflete pass_rate.
- **Gate:** `pytest tests/eval/test_cli.py`.

### E9 Endpoint `POST /api/evals/run` (embutido) (FR-5.5, AD-3)
- **O quê:** rota que dispara `run_evaluation` em background para um target do registry; retorna `run_id`.
  Desabilitada/501 quando standalone (registry vazio).
- **Reusa:** `dashboard/router.py`, registry.
- **Depends:** E6.
- **Done-when:** com target registrado → 200 + run_id; sem registro → 501.
- **Gate:** `pytest tests/eval/test_eval_endpoint.py`.

---

## Fase 5 — Dashboard

### E10 API de leitura de evals + EvalReader (FR-5.1, FR-5.2, FR-5.3, FR-5.5)
- **O quê:** `GET /api/evals` (lista+filtros), `GET /api/evals/{run_id}` (detalhe casos/turns/scores);
  `EvalReader` (pushdown + fallback); aggregator `eval_summary`.
- **Reusa:** `dashboard/reader.py`, `dashboard/router.py`, E7.
- **Depends:** E7.
- **Done-when:** lista filtra por dataset/projeto/data; detalhe retorna casos com turns e CriterionScores.
- **Gate:** `pytest tests/eval/test_eval_api.py`.

### E11 Frontend aba Evaluators (FR-5.1, FR-5.2, FR-5.3, FR-5.4)
- **O quê:** `Layout` += nav `Evaluators`; `Evaluators.tsx` (lista runs + filtros); `EvalRunDetail.tsx`
  (casos → painel por turn: input/output/expected + tabela de critérios score+justificativa; botão
  "ver trace" → `/traces/{trace_id}`). Rotas no `App.tsx`. Build + copy:py.
- **Reusa:** `useApi`, estilos, view de grafo existente.
- **Depends:** E10.
- **Done-when:** `npm run build` ok; aba lista runs; detalhe mostra turns + scores do judge; link p/ trace.
- **Gate:** `npm --prefix packages/tracecast-dashboard run build`.

---

## Fase 6 — Validação E2E

### E12 E2E eval (todos os FR)
- **O quê:** dataset fake (1 single + 1 multi-turn), agente decorado, judge fake → `run_evaluation` →
  store → API `/api/evals/{id}` → assert turns/scores/pass_rate + `trace_id` navegável.
- **Depends:** E1–E11.
- **Done-when:** checklist UAT de `spec.md` §3 verde.
- **Gate:** `pytest tests/eval/test_e2e_eval.py`.

---

## Matriz de rastreabilidade

| Requisito | Tarefas |
|-----------|---------|
| FR-1.1/1.2/1.3 | E3 |
| FR-2.1 | E2 |
| FR-2.2/2.3/2.4 | E6 |
| FR-3.1/3.4 | E5 |
| FR-3.2 | E4 |
| FR-3.3 | E1, E6 |
| NFR-3.1 | E5 |
| FR-4.1/4.2/4.3 | E1, E7 |
| FR-5.1/5.2/5.3 | E10, E11 |
| FR-5.4 | E11 |
| FR-5.5 | E9, E10 |
| AD-3 | E8, E9 |
