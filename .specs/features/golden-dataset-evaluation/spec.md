# SDD — Evaluation por Golden Dataset (LLM-as-judge + scorers)

> **Status:** Specify
> **Escopo:** Large/Complex (novo domínio: avaliação offline, judge, novo modelo de dados, nova aba)
> **Branch:** `feature/v0.2.0`
> **Depende de:** feature `observability-reliability` (schema v2, exporters, dashboard, tracer)
> **Última atualização:** 2026-06-13

## 1. Problema

Além de observar produção (tracing), o usuário precisa **avaliar** a qualidade do agente contra um
conjunto de casos de referência (golden dataset). O fluxo desejado:

1. Um **decorator** (diferente de `@trace_cast`) marca a função/rota do agente como alvo de avaliação e
   define o(s) **path(s) de golden dataset** (JSON).
2. Um **runner** executa o agente sobre cada caso do dataset, captura a resposta da LLM, e um **judge**
   (LLM-as-judge + scorers determinísticos) pontua cada resposta contra o `expected`.
3. O resultado é salvo de forma re-consumível.
4. A **interface** ganha uma aba **Evaluators** onde se vê, com detalhe: cada run, cada caso, **cada turn
   de conversa**, a resposta da LLM, a avaliação do judge (score por critério + justificativa) e o link
   para o trace/grafo daquela execução.

## 2. Decisões (confirmadas com o usuário)

- **AD-1** Judge **híbrido**: LLM-as-judge com **rubrica multi-critério** (cada critério com nome +
  descrição) **+ scorers determinísticos** (exact match, contains, regex, similaridade). LLM produz
  score 0–1 + justificativa por critério; scorers produzem 0–1 objetivo.
- **AD-2** Golden dataset suporta **single-turn e multi-turn**. Caso simples = `{input, expected}`; caso
  conversacional = lista de `turns` (role/content) com `expected` no(s) turn(s) de assistant.
- **AD-3** Disparo por **CLI** (`tracecast-eval`), por **script Python** (`run_evaluation(...)`) e por
  **endpoint HTTP** (`POST /api/evals/run`). O endpoint só funciona com o dashboard **embutido** no
  processo do agente (precisa da função decorada em memória). O **server standalone** é **read-only**
  para evals (consome resultados; não dispara).
- **AD-4** Score por caso = **rubrica multi-critério 0–1** agregada + `pass/fail` por `threshold`. O run
  agrega `pass_rate` e `avg_score`. Multi-turn: score por turn + agregado do caso.
- **AD-5** Cada execução de caso é **traceada** (reusa o tracer existente) → `EvalCase.trace_id` linka ao
  trace/grafo. O dashboard reaproveita a view de grafo já existente para "como chegou no resultado".
- **AD-6** Resultados de eval são **persistidos pelos mesmos exporters** (Mongo/Postgres/JSONL), em
  coleção/tabela separada (`tracecast_evals`). Nada de novo backend.

## 3. Requisitos

### G1 — Decorator de evaluation

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-1.1 | `@evaluator(dataset=..., name=..., judge=..., scorers=[...], threshold=...)` marca a função alvo (SUT). | Decorar uma função registra um alvo de eval com o(s) dataset(s) e config do judge. |
| FR-1.2 | O decorator é **transparente** em runtime normal. | Chamar a função decorada fora de uma run de eval executa-a inalterada (zero overhead, zero latência). |
| FR-1.3 | `dataset` aceita path único ou lista de paths JSON. | Múltiplos datasets geram múltiplas runs (ou uma run por dataset). |

### G2 — Golden dataset + execução

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-2.1 | Loader de dataset JSON valida e normaliza casos single-turn e multi-turn. | Dataset malformado falha com erro claro; ambos os formatos carregam para um modelo único. |
| FR-2.2 | O runner executa a função alvo para cada caso, alimentando input/turns. | N casos → N execuções; multi-turn replica os turns em ordem. |
| FR-2.3 | Cada execução de caso é traceada e linkada. | `EvalCase.trace_id` aponta para um Trace persistido e visível no dashboard. |
| FR-2.4 | Falha de um caso não aborta a run. | Caso com exceção vira `status="error"` com mensagem; demais casos seguem. |

### G3 — Judge + scoring

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-3.1 | LLM-as-judge pontua cada critério da rubrica 0–1 + justificativa. | Resposta do judge é parseada para `{criterion: {score, reasoning}}`; parse robusto a ruído. |
| FR-3.2 | Scorers determinísticos: `exact_match`, `contains`, `regex`, `similarity`. | Cada scorer retorna 0–1; compõem com os critérios LLM. |
| FR-3.3 | Agregação por caso + `pass/fail` por threshold; run agrega `pass_rate`/`avg_score`. | Resultados batem com cálculo manual em fixtures conhecidas. |
| FR-3.4 | Judge é injetável/configurável (modelo, provider, rubrica) e mockável em teste. | Trocar o judge_fn não altera o pipeline; testes usam judge fake determinístico. |
| NFR-3.1 | Custo/tokens do judge são contabilizados separados do SUT. | Run reporta `judge_cost_usd`/`judge_tokens` sem poluir os spans do agente. |

### G4 — Persistência

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-4.1 | `EvalRun`/`EvalCase`/`TurnResult`/`CriterionScore` serializam para dict e re-hidratam. | Round-trip íntegro por exporter (Dict/JSONL/Mongo/Postgres). |
| FR-4.2 | Evals salvos em store separado (`tracecast_evals`), idempotente por `run_id`. | Re-salvar a mesma run faz upsert; sem duplicatas. |
| FR-4.3 | Falha de save de eval não é silenciosa. | Reaproveita o tratamento de erro do tracer (log ERROR + hook). |

### G5 — Dashboard (aba Evaluators)

| ID | Requisito | Critério de aceite |
|----|-----------|--------------------|
| FR-5.1 | Nova aba **Evaluators** lista runs (dataset, data, pass_rate, avg_score, target). | Aba aparece no nav; lista ordena por data desc; filtra por dataset/projeto/data. |
| FR-5.2 | Detalhe da run mostra cada caso, status, score agregado. | Clicar numa run abre lista de casos com pass/fail e score. |
| FR-5.3 | Detalhe do caso mostra **cada turn**, a resposta da LLM, o `expected`, e a avaliação do judge (score por critério + justificativa). | Painel por turn com input/output/expected + tabela de critérios (score+reasoning). |
| FR-5.4 | Link do caso para o **grafo do trace** correspondente. | Botão "ver trace" abre a view de grafo já existente para o `trace_id`. |
| FR-5.5 | API REST de evals exposta no router. | `GET /api/evals`, `GET /api/evals/{run_id}`; `POST /api/evals/run` apenas embutido. |

## 4. Fora de escopo (desta fase)

- Eval contínuo por amostragem de produção (online eval) — fase futura.
- Comparação A/B entre runs / regressão automática com gate de CI (pode vir depois; os dados já permitem).
- Datasets versionados / UI de edição de dataset (datasets são arquivos JSON versionados em git pelo usuário).
- Fine-tuning / geração automática de golden datasets.

## 5. Rastreabilidade

Mapa requisito → tarefa em `tasks.md`.
