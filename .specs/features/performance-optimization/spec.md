# Latency & Resource Optimization — Specification

> **Status:** Specify (design.md/tasks.md pendentes — aprofundar depois de priorização)
> **Escopo:** Large (toca `core/tracer.py`, `exporters/base.py` e os 4 exporters concretos)
> **Branch sugerida:** `feature/export-performance`
> **Depende de:** nada novo — otimização de código existente
> **Relacionado:** `.specs/codebase/CONCERNS.md` item **C10** (ainda parcialmente aberto)
> **Última atualização:** 2026-06-30

## Problem Statement

Leitura direta de `core/tracer.py` e `exporters/base.py` (2026-06-30) confirma que **C10 do
`CONCERNS.md` continua parcialmente aberto**: `Tracer.trace()` (o caminho síncrono, o mais comum
em código de aplicação) chama `self._export(t)` **dentro do bloco `finally` do context manager**
(`tracer.py:101`) — ou seja, `exporter.export(trace)` roda de forma **bloqueante, inline**, antes
do `with tracer.trace(...)` devolver controle ao chamador. Para qualquer exporter com I/O real
(Mongo, Postgres, arquivo em disco de rede), isso soma latência do exporter à latência percebida
pelo usuário final da aplicação que usa o TraceCast — o oposto do que uma lib de observabilidade
deveria fazer (nunca no caminho crítico do request).

`atrace()` (caminho async) já offloada via `asyncio.to_thread` (`exporters/base.py:16`), mas
**um thread por exporter por trace**, sem pool dedicado nem batching — sob throughput alto (muitos
traces/segundo, múltiplos exporters configurados), isso pressiona o thread pool default do
`asyncio` (compartilhado com outras tarefas do processo) e gera N round-trips de rede em vez de
writes em lote.

Nenhum exporter usa `export_batch` (método já existe em `BaseExporter`, mas nada no `Tracer` o
invoca) — cada trace é 1 write individual, mesmo quando múltiplos traces terminam próximos no
tempo.

## Goals

- [ ] `tracer.trace()` (síncrono) nunca bloqueia o caminho de retorno do `with` na I/O do
      exporter, por padrão — mesma garantia que `atrace()` já tenta dar, mas sem thread-per-trace.
- [ ] Writes de exporter podem ser agrupados em lote (batching com flush por tamanho/tempo),
      opcional e configurável, sem quebrar o comportamento atual (1 trace = 1 write) para quem não
      habilitar.
- [ ] Amostragem (sampling) **opt-in**, nunca default — TraceCast não repete o erro do LangSmith
      (sampling forçado por custo de storage, citado como ponto de dor real em 2026: "the whole
      point of observability is comprehensive visibility... once you start sampling, you risk
      missing the trace that would have helped"). Aqui sampling é ferramenta de controle de
      recursos para quem já decidiu que quer, não imposição do produto.
- [ ] Medir antes de otimizar — nenhuma mudança "porque parece mais rápido" sem benchmark antes/
      depois no `design.md`.

## Out of Scope

| Item | Razão |
| ---- | ----- |
| Reescrever exporters em Rust/C extension | Complexidade desproporcional ao ganho; gargalo é I/O de rede, não CPU |
| Fila durável (disco + retry + backoff) | Já é ideia diferida v0.4+ em `STATE.md` — feature maior, não cabe aqui (esta spec é sobre não bloquear o caminho síncrono, não sobre durabilidade) |
| Drivers async nativos (asyncpg/motor) | Também já diferida em `STATE.md` — trocar driver é mudança maior que o escopo desta feature (que é: tirar I/O do caminho síncrono com o driver atual) |
| Otimizar `token_counter.py`/`cost_calculator.py` | Ambos são CPU-only, in-process, sem I/O — não são o gargalo real; confirmar com profiling antes de mexer (provável não-issue) |

---

## User Stories

### P1: Export síncrono não bloqueia o caminho de retorno ⭐ MVP

**User Story**: Como dev usando `with tracer.trace(...)` num handler de request síncrono, quero
que o `with` retorne sem esperar a escrita no exporter terminar, para o TraceCast nunca ser a
causa de latência adicional percebida pelo usuário da minha aplicação.

**Why P1**: É o gargalo mais direto e mais fácil de demonstrar com benchmark simples
(`time.perf_counter()` ao redor do `with`, comparando com/sem exporter lento simulado).

**Acceptance Criteria**:

1. WHEN `Tracer(exporters=[...], async_export=True)` (novo parâmetro, default a decidir em
   design — ver Tech Decision pendente) THEN `tracer.trace()` SHALL agendar o export num worker
   dedicado (thread pool próprio do `Tracer`, não thread ad-hoc por chamada) e retornar
   imediatamente do `with`.
2. WHEN o processo termina (interpretador finaliza) THEN o sistema SHALL tentar dar flush nos
   exports pendentes dentro de um timeout curto configurável (não perder dados silenciosamente por
   causa do offload — mesmo espírito do ADR-004 "save best-effort + erros visíveis").
3. WHEN o worker dedicado falha ao exportar THEN o sistema SHALL chamar `on_export_error` (mesmo
   hook já existente), preservando o contrato atual de erro visível.

**Independent Test**: benchmark com exporter fake que dorme 200ms; medir tempo do `with
tracer.trace(...): pass` — com a feature habilitada, tempo SHALL ser < 10ms (não os 200ms do
exporter).

---

### P2: Batching opcional de writes

**User Story**: Como dev com throughput alto de traces, quero configurar `batch_size`/
`batch_interval_ms` para o `Tracer` agrupar múltiplos traces num único `export_batch` por
exporter, reduzindo round-trips de rede.

**Why P2**: Ganho real só aparece em throughput alto — não é o problema nº1 (esse é P1, que afeta
qualquer volume), é otimização de custo de infra para quem já tem volume.

**Acceptance Criteria**:

1. WHEN configuro `Tracer(exporters=[...], batch_size=50, batch_interval_ms=1000)` THEN o sistema
   SHALL acumular traces finalizados e chamar `exporter.export_batch(traces)` quando atingir 50
   traces OU 1000ms desde o primeiro trace acumulado (o que vier primeiro).
2. WHEN nenhum `batch_size` é configurado THEN o comportamento SHALL ser o atual (1 trace = 1
   write), sem regressão para quem não optar.
3. WHEN um exporter não sobrescreve `export_batch` (usa o default de `BaseExporter`, que já faz
   loop chamando `export` um a um) THEN o batching no nível do `Tracer` SHALL continuar
   funcionando (menos round-trips de rede só existem de fato para exporters que implementam
   `export_batch` com write real em lote — Mongo `insert_many`, Postgres `execute_values` — mas o
   acúmulo/flush no `Tracer` é transparente independente disso).

**Independent Test**: configurar `batch_size=10`, gerar 25 traces rapidamente, verificar que o
exporter fake recebe 3 chamadas de `export_batch` (10+10+5), não 25 chamadas de `export`.

---

### P2: Sampling opt-in (nunca default)

**User Story**: Como dev com volume alto e exporter caro (ex.: Postgres gerenciado cobrando por
IOPS), quero configurar `sample_rate` para exportar só uma fração dos traces, mantendo controle
total sobre quando isso se aplica.

**Why P2**: Ferramenta de controle de custo/recurso para quem decide usar — não resolve o problema
de latência (P1 resolve isso), resolve o problema de **volume de storage/IOPS**.

**Acceptance Criteria**:

1. WHEN `Tracer(exporters=[...], sample_rate=0.1)` THEN aproximadamente 10% dos traces
   finalizados SHALL ser exportados; os demais SHALL ainda ser processados normalmente em memória
   (custo/tokens calculados) mas não persistidos.
2. WHEN `sample_rate` não é configurado THEN o default SHALL ser `1.0` (exporta tudo, comportamento
   atual, sem regressão).
3. WHEN um trace tem `status=error` THEN o sistema SHALL **sempre exportar**, independente do
   `sample_rate` (traces com erro são desproporcionalmente valiosos para debug — não pode ser a
   exata trace que "escapou da amostra", ecoando o ponto de dor citado sobre LangSmith).

**Independent Test**: `sample_rate=0.0` + um trace com erro forçado → trace com erro é exportado
mesmo assim; `sample_rate=0.0` + trace sem erro → não é exportado.

---

## Edge Cases

- WHEN `async_export=True` E o processo recebe `SIGTERM`/`SIGINT` THEN o sistema SHALL tentar
  flush do que está pendente antes de finalizar (best-effort, com timeout — não travar shutdown
  indefinidamente).
- WHEN `batch_size` está configurado mas o processo morre antes do flush THEN os traces
  acumulados e não exportados SHALL ser perdidos — **documentar explicitamente** essa troca (é o
  preço de não ter fila durável, que é escopo de outra feature diferida). Não fingir durabilidade
  que não existe.
- WHEN `sample_rate < 1.0` E `online_eval` está configurado THEN online eval SHALL rodar sobre a
  amostra que **foi** exportada, não sobre todos os traces gerados (consistência: eval sobre o que
  existe em storage).
- WHEN dois `Tracer` instances compartilham o mesmo worker pool (não deveria, mas defensivamente)
  THEN cada `Tracer` SHALL ter seu próprio worker isolado (sem estado global compartilhado — mesmo
  cuidado que `ContextVar`s já tomam no projeto).

## Requirement Traceability

| Requirement ID | Story | Fase | Status |
| -------------- | ----- | ---- | ------ |
| PERF-01 | P1 `async_export` não bloqueia `with tracer.trace()` | Design | Pending |
| PERF-02 | P1 Flush best-effort no shutdown | Design | Pending |
| PERF-03 | P1 Erro de worker chama `on_export_error` | Design | Pending |
| PERF-04 | P2 Batching por tamanho/intervalo | Design | Pending |
| PERF-05 | P2 Batching sem regressão quando não configurado | Design | Pending |
| PERF-06 | P2 `sample_rate` opt-in | Design | Pending |
| PERF-07 | P2 Traces com erro sempre exportados mesmo com sampling | Design | Pending |

**Status values:** Pending → In Design → In Tasks → Implementing → Verified
**Coverage:** 7 requisitos.

## Success Criteria

- [ ] Benchmark antes/depois documentado no `design.md` (não só "deve ser mais rápido" —
      número real, exporter fake com latência simulada).
- [ ] `with tracer.trace(...)` com `async_export=True` e exporter de 200ms retorna em <10ms.
- [ ] Nenhuma regressão de comportamento para quem não configurar nenhuma das 3 opções novas
      (`async_export`, `batch_size`, `sample_rate`) — suite atual 100% verde sem flags novas.
- [ ] Trace com erro nunca é descartado por sampling, verificado em teste automatizado.
