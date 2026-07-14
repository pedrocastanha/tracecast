# Light HTTP Ingest — Specification

> **Status:** Specify · Design · Tasks · Execute  
> **Escopo:** Medium (HttpExporter + ingest API + server queue + spool)  
> **Branch:** `feature/light-http-ingest`  
> **Última atualização:** 2026-07-14  
> **Contexto:** VM 2 vCPU / 4 GB; vários bots batem Mongo direto → OOM/timeout; client deve ser fire-and-forget e payloads leves (LLM-only).

## Problem Statement

Hoje cada bot abre `MongoExporter` contra a VM. Sob carga:

1. N conexões pymongo competem com dashboard + mongod na mesma máquina pequena.
2. Bots sem `background_export` bloqueiam request path no save.
3. Traces `span_filter=all` incham documento (LangGraph noise).
4. Se Mongo/rede falha, app pode degradar mesmo com retries.

Meta: paridade **leve** com LangSmith/Langfuse (capture → export assíncrono → store → UI) sem stack pesada.

## Goals

- [ ] Client SHALL exportar via HTTP (`HttpExporter`) sem bloquear request path quando `background_export=True`
- [ ] Server SHALL aceitar `POST /api/ingest` e `POST /api/ingest/batch`, enfileirar, batch-write no store
- [ ] WHEN fila server cheia e spool habilitado THEN aceitar em disco (JSONL) e drenar depois
- [ ] WHEN fila cheia e sem spool THEN retornar 503 com dropped count; client NÃO crasha
- [ ] Health SHALL expor `ingest` (queue_size, dropped, accepted, spool_pending)
- [ ] Consumers default: `background_export=True`, `span_filter=llm_tool` (ou flow), timeout curto

## Out of Scope

| Item | Reason |
|------|--------|
| OTEL nativo | Escopo maior |
| Auth JWT multi-tenant | Basic auth existente basta no MVP |
| Sampling inteligente 100% erros | Já existe sample_rate |
| UI nova | Health/API bastam |

## User Stories

### P1: HttpExporter fire-and-forget

1. WHEN `HttpExporter.export_docs_batch(docs)` THEN POST JSON batch ao endpoint configurado com timeout curto (default 2s).
2. WHEN rede/timeout THEN raise (Tracer retry/summary path); com `background_export` request path já retornou.
3. WHEN HTTP 202/200 THEN contagem accepted; 4xx/5xx raise.

### P1: Ingest API + fila server

1. WHEN `POST .../api/ingest` body=trace dict OR `{ "trace": {...} }` THEN enqueue + 202.
2. WHEN `POST .../api/ingest/batch` body=`{ "traces": [...] }` OR list THEN enqueue all + 202.
3. Worker batch-write via `export_docs_batch` no store (Mongo/Postgres/JSONL).
4. Payload max size configurável (env); doc sem `trace_id` → 400.

### P1: Spool opcional

1. WHEN `TRACECAST_INGEST_SPOOL=/path/file.jsonl` e queue full THEN append JSONL e count `spool_written`.
2. Worker/reaper drena spool quando queue tem espaço.

### P1: Health

`GET /api/health` inclui:

```json
"ingest": {
  "enabled": true,
  "queue_size": 3,
  "queue_max": 500,
  "accepted": 100,
  "dropped": 0,
  "spool_written": 2,
  "spool_drained": 1,
  "last_error": null
}
```

### P2: Defaults leves nos consumers

- `background_export=True`
- `span_filter=llm_tool` (LLM+tools; user pediu só LLM)
- Prefer `HttpExporter` → VM quando `TRACECAST_HTTP_URL` set
- Fallback Mongo só se HTTP não configurado

## Success Metrics

| Métrica | Alvo |
|---------|------|
| curl ingest + list trace | 202 → trace aparece em GET |
| Load 200 concurrent POSTs | VM sem reboot; queue absorve; < few drops |
| Bot request path | 0 block em export HTTP/Mongo |
| Suite pytest | gate verde |
