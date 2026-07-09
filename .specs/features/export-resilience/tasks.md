# Export Resilience — Tasks

**Design**: `.specs/features/export-resilience/design.md`  
**Spec**: `.specs/features/export-resilience/spec.md`  
**Status**: Ready for Execute  

> **TESTING:** `cd packages/tracecast-py && python -m pytest tests/ -q`  
> Baseline recente: ~416 passed.  
> Testes **co-localizados** na mesma task. **Commit atômico** por task.  
> TDD imutável: escrever testes do contrato da task antes/junto; não enfraquecer assert para verde.

---

## Execution Plan

### Fase 0 — Foundation (summary model + stats + retry)

```
T1 → T2 → T3
```

### Fase 1 — Tracer wiring (MVP valor)

```
T3 → T4 → T5
```

### Fase 2 — Exporters

```
T5 → (T6, T7, T8, T9)[P]
```

### Fase 3 — Read path + health

```
(T6–T9) → T10 → T11
```

### Fase 4 — UI

```
T10 → (T12, T13)[P]
```

### Fase 5 — P2/P3 polish

```
T11 → T14
T10 → T15
T11 → T16
```

**Ordem recomendada:** T1→T16 sequencial quando em dúvida; paralelizar só T6–T9 e T12–T13.

---

## Task Breakdown

### Fase 0 — Foundation

#### T1: `build_trace_summary` + testes de contrato
**What**: Criar `core/trace_summary.py` com `build_trace_summary(source, error) -> dict` cobrindo FB-02/03 (campos mínimos, spans/edges vazios, error truncado, aceita Trace e dict).  
**Where**: `packages/tracecast-py/tracecast/core/trace_summary.py`, `tests/test_trace_summary.py`  
**Depends on**: None  
**Reuses**: campos de `Trace.to_dict()`  
**Requirement**: FB-01, FB-02, FB-03  
**Done when**:
- [x] Summary a partir de Trace e de dict com tokens/projeto/name/data
- [x] `spans == []`, `edges == []`, `export_status == "summary_only"`, `is_summary is True`
- [x] `export_error` truncado ≤ 500
- [x] Tokens zero ainda produz summary válido
- [x] Gate pytest (arquivo + suite se rápido)
**Status**: ✅ Complete (2026-07-09)  
**Tests**: unit · **Gate**: `pytest tests/test_trace_summary.py -q`  
**Commit**: `feat(core): build_trace_summary for export fallback`

#### T2: `ExportStats` thread-safe
**What**: `core/export_stats.py` com incr/snapshot/last_error.  
**Where**: `core/export_stats.py`, `tests/test_export_stats.py`  
**Depends on**: None `[P com T1]`  
**Reuses**: `threading.Lock`  
**Requirement**: HL-01  
**Done when**:
- [ ] snapshot contém keys documentadas
- [ ] incr concorrente não corrompe (smoke com 2 threads)
- [ ] Gate ok
**Tests**: unit · **Gate**: `pytest tests/test_export_stats.py -q`  
**Commit**: `feat(core): ExportStats counters for export health`

#### T3: Retry helper configurável por env
**What**: `retry_call` com attempts + exponential backoff + contagem de retries.  
**Where**: `core/export_retry.py`, `tests/test_export_retry.py`  
**Depends on**: None `[P com T1/T2]`  
**Reuses**: `os.environ` pattern de `payload.py`/`export_queue.py`  
**Requirement**: RT-01  
**Done when**:
- [ ] sucesso na 2ª tentativa não propaga
- [ ] esgota attempts e re-raise última exceção
- [ ] defaults 3 / 0.2s; env override
- [ ] Gate ok
**Tests**: unit (mock sleep se necessário) · **Gate**: `pytest tests/test_export_retry.py -q`  
**Commit**: `feat(core): export retry with backoff`

---

### Fase 1 — Tracer

#### T4: Integrar retry + summary + stats no caminho sync `_export`
**What**: `_export` usa retry por exporter; em falha final chama summary + stats + `on_export_error`; online_eval só se ≥1 full ok.  
**Where**: `core/tracer.py`, `tests/test_export_fallback.py`  
**Depends on**: T1, T2, T3  
**Reuses**: `_handle_export_error`  
**Requirement**: FB-01…07, RT-02, HL-01  
**Done when**:
- [ ] Exporter sempre-fail → DictExporter (ou mock `export_summary`) recebe summary com tokens/projeto
- [ ] Exporter ok → sem summary
- [ ] Dois exporters: fail+ok → summary só no fail; full no ok
- [ ] stats: summary_fallback / exported_ok corretos
- [ ] App não levanta
- [ ] Gate: `pytest tests/test_export_fallback.py tests/test_tracer.py -q`
**Tests**: unit · **Gate**: targeted + full no fim da fase  
**Commit**: `feat(tracer): retry and summary fallback on export failure`

#### T5: Integrar no `_export_batch_items` (background path)
**What**: Batch com retry; se batch falhar, per-item `export_doc` + summary; enfileirado continua dict. Hook dropped → stats.  
**Where**: `core/tracer.py`, `core/export_queue.py` (callback on_drop opcional), `tests/test_export_fallback.py`  
**Depends on**: T4  
**Reuses**: `ExportWorker`, `export_docs_batch`  
**Requirement**: FB-01, FB-07, RT-02, HL-01  
**Done when**:
- [ ] `background_export=True` + flush + exporter fail → summary persistido
- [ ] batch partial recovery per-item testado
- [ ] queue drop incrementa stats (via callback ou sync de `worker.dropped` no snapshot)
- [ ] Gate ok
**Tests**: unit · **Gate**: `pytest tests/test_export_fallback.py tests/test_export_queue.py -q`  
**Commit**: `feat(tracer): summary fallback on background batch export`

---

### Fase 2 — Exporters

#### T6: `export_summary` no `BaseExporter` + `DictExporter` [P]
**What**: Default `export_summary` → `export_doc`; DictExporter grava na lista `traces` com flag.  
**Where**: `exporters/base.py`, `exporters/dict_exporter.py`, tests  
**Depends on**: T1  
**Requirement**: FB-04  
**Done when**:
- [ ] Default não quebra exporters custom só com `export`
- [ ] Dict round-trip summary
- [ ] Gate ok
**Tests**: unit · **Gate**: pytest targeted  
**Commit**: `feat(exporters): export_summary on BaseExporter and DictExporter`

#### T7: `export_summary` no `JsonFileExporter` [P]
**What**: Append summary JSONL na mesma path.  
**Where**: `exporters/json_file.py`, tests  
**Depends on**: T6 (interface)  
**Requirement**: FB-04  
**Done when**:
- [ ] Linha JSONL com `export_status=summary_only` legível
- [ ] Gate ok
**Tests**: unit (tmp_path) · **Gate**: pytest targeted  
**Commit**: `feat(exporters): export_summary for JsonFileExporter`

#### T8: `export_summary` no `MongoExporter` [P]
**What**: Upsert na collection de traces.  
**Where**: `exporters/mongo.py`, tests (mock collection)  
**Depends on**: T6  
**Requirement**: FB-04  
**Done when**:
- [ ] replace_one upsert com summary
- [ ] Gate ok
**Tests**: unit mock · **Gate**: pytest targeted  
**Commit**: `feat(exporters): export_summary for MongoExporter`

#### T9: `export_summary` no `PostgresExporter` [P]
**What**: Upsert row; metadata fallback se colunas rígidas.  
**Where**: `exporters/postgres.py`, tests mock  
**Depends on**: T6  
**Requirement**: FB-04  
**Done when**:
- [ ] summary persiste e relê com status (top-level ou metadata hidratável)
- [ ] Gate ok
**Tests**: unit mock · **Gate**: pytest targeted  
**Commit**: `feat(exporters): export_summary for PostgresExporter`

---

### Fase 3 — Read + Health

#### T10: Hydrate + list/detail/graph para summary
**What**: Reader/aggregator expõem `export_status`/`is_summary`/`export_error`; graph vazio seguro.  
**Where**: `dashboard/reader.py`, `dashboard/aggregator.py`, tests  
**Depends on**: T6–T9 (pelo menos Dict)  
**Requirement**: UI-01, UI-02, UI-03  
**Done when**:
- [ ] hydrate preenche defaults
- [ ] `_trace_summary` inclui flags
- [ ] graph de summary → nodes/edges vazios sem exception
- [ ] Gate ok
**Tests**: unit · **Gate**: pytest dashboard/reader tests  
**Commit**: `feat(dashboard): read and summarize partial export traces`

#### T11: `/api/health` com bloco `export`
**What**: Wire stats + queue no health; mount seta refs no reader; standalone read_only seguro.  
**Where**: `dashboard/router.py`, `core/tracer.py` mount, `tests/test_health_export.py`  
**Depends on**: T2, T4, T5, T10  
**Requirement**: HL-02  
**Done when**:
- [ ] JSON shape conforme design
- [ ] standalone/read_only não 500
- [ ] após fallback forçado, contadores > 0
- [ ] Gate ok
**Tests**: unit/integration FastAPI TestClient se já usado no repo  
**Commit**: `feat(dashboard): expose export stats on /api/health`

---

### Fase 4 — UI

#### T12: Badge na lista de traces [P]
**What**: Badge “Partial” / “Summary” na lista.  
**Where**: `packages/tracecast-dashboard/src/pages/Traces.tsx` (+ tipos se houver)  
**Depends on**: T10  
**Requirement**: UI-01  
**Done when**:
- [ ] Flag da API reflete no UI
- [ ] Build dashboard ok (`npm run build` no pacote dashboard)
**Tests**: manual / build gate  
**Commit**: `feat(dashboard-ui): badge for summary_only traces`

#### T13: Banner no TraceDetail [P]
**What**: Banner + empty state grafo quando summary.  
**Where**: `pages/TraceDetail.tsx`, possivelmente `TraceGraph.tsx`  
**Depends on**: T10  
**Requirement**: UI-02, UI-03  
**Done when**:
- [ ] Mensagem clara; sem crash
- [ ] Build ok
**Tests**: build gate  
**Commit**: `feat(dashboard-ui): partial export banner on trace detail`

---

### Fase 5 — P2/P3

#### T14: Warn sem `background_export` em sink persistente
**What**: `warnings.warn` no `Tracer.__init__` conforme OP-01.  
**Where**: `core/tracer.py`, test  
**Depends on**: None (pode após T4)  
**Requirement**: OP-01  
**Done when**:
- [ ] Mongo/PG/Json sem background → warn
- [ ] Dict ou background=True → sem warn
- [ ] Gate ok
**Tests**: unit  
**Commit**: `feat(tracer): warn when persistent exporter lacks background_export`

#### T15: Strip/projection de payloads na listagem
**What**: List/query_page não carrega input/output de spans; get detalhe intacto.  
**Where**: `dashboard/reader.py` e/ou exporters query  
**Depends on**: T10  
**Requirement**: PR-01  
**Done when**:
- [ ] Lista stripped; get full
- [ ] Gate ok
**Tests**: unit  
**Commit**: `perf(dashboard): strip span payloads on trace list`

#### T16: Overview card Export health
**What**: Card consumindo `/api/health` export.  
**Where**: `pages/Overview.tsx`  
**Depends on**: T11  
**Requirement**: OV-01  
**Done when**:
- [ ] Mostra contadores ou N/A
- [ ] Build ok
**Tests**: build  
**Commit**: `feat(dashboard-ui): export health card on overview`

---

## Traceability Matrix

| Req | Tasks |
|-----|-------|
| FB-01 | T1, T4, T5 |
| FB-02 | T1 |
| FB-03 | T1, T10 |
| FB-04 | T6, T7, T8, T9 |
| FB-05 | T4, T5 |
| FB-06 | T4, T5 |
| FB-07 | T4, T5 |
| RT-01 | T3 |
| RT-02 | T4, T5 |
| HL-01 | T2, T4, T5 |
| HL-02 | T11 |
| UI-01 | T10, T12 |
| UI-02 | T10, T13 |
| UI-03 | T10, T13 |
| OP-01 | T14 |
| PR-01 | T15 |
| OV-01 | T16 |

---

## Pre-approval checks

### 1. Granularity
Cada task = um deliverable (um módulo ou um wiring focado) + testes + commit. ✅

### 2. Diagram ↔ Depends on

| Task | Depends on (field) | Matches plan |
|------|-------------------|--------------|
| T1 | None | ✅ |
| T2 | None | ✅ |
| T3 | None | ✅ |
| T4 | T1,T2,T3 | ✅ |
| T5 | T4 | ✅ |
| T6 | T1 | ✅ (interface; pode ir em paralelo pós-T1) |
| T7–T9 | T6 | ✅ |
| T10 | T6–T9 | ✅ |
| T11 | T2,T4,T5,T10 | ✅ |
| T12–T13 | T10 | ✅ |
| T14 | — (após T4 ok) | ✅ |
| T15 | T10 | ✅ |
| T16 | T11 | ✅ |

### 3. Test co-location

| Task | Tests in same task? |
|------|---------------------|
| T1–T11, T14–T15 | unit pytest ✅ |
| T12, T13, T16 | build UI (sem harness e2e no repo) ✅ documentado |

---

## Definition of Done (feature)

- [ ] Todas as tasks P1 (T1–T13) complete
- [ ] `pytest tests/ -q` verde
- [ ] Demo manual: exporter que falha → summary no store com data/tokens/projeto/name
- [ ] `/api/health` mostra contadores
- [ ] Lista/detail UI mostram partial
- [ ] STATE.md atualizado
- [ ] P2/P3 (T14–T16) opcionais no mesmo PR ou follow-up

---

## Execute notes (cast-skills)

1. Branch `feature/export-resilience`
2. Por task: testes do contrato → implementação → gate → commit atômico
3. **Não** editar teste para forçar verde; se contrato errado → voltar ao spec
4. Após feature: `validate` / UAT curto no demo FastAPI com Mongo mock ou DictExporter
