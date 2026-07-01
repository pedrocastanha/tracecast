# Dynamic Guardrails & Evaluator Ergonomics — Specification

> **Status:** Specify (design.md/tasks.md pendentes — aprofundar depois de priorização)
> **Escopo:** Large (novo módulo `guardrails/`, hook no `Tracer`, integra com `eval/` existente)
> **Branch sugerida:** `feature/dynamic-guardrails`
> **Depende de:** `eval/` (judge, scorers, `METRICS` registry — já implementados no SDD
> `observability-platform`), `core/tracer.py`
> **Relacionado:** `.specs/research/langfuse-comparison.md` (addendum guardrails),
> `.specs/codebase/CONCERNS.md` item **C5**
> **Última atualização:** 2026-06-30

## Problem Statement

Hoje "guardrail" no TraceCast é só uma convenção informal: uma função Python pura decorada com
`@trace_span(type=SpanType.TOOL)` (ver `real_examples/langchain_agent.py`), sem política, sem
decisão de bloqueio, sem reuso do `eval/` que já existe para métricas (`METRICS` registry,
`LLMJudge`, scorers heurísticos). Cada projeto reimplementa a guarda do zero. C5 do
`CONCERNS.md` já flagava isso: "guardrails implementados como função Python pura são invisíveis"
— hoje pelo menos ficam visíveis (via `@trace_span`), mas continuam sem reuso nem política.

Pesquisa de mercado (2026): as bibliotecas dominantes são **LLM Guard** (Protect AI, MIT, scanners
de input/output para PII/prompt-injection/toxicidade) e **NeMo Guardrails** (NVIDIA, Colang DSL
para controle de diálogo). Ambas são frameworks completos e pesados — rodar qualquer uma delas
integralmente contraria o princípio "leve, zero infra nova" do projeto. A oportunidade real não é
reimplementar scanners (ficaria atrás das libs especializadas), é **dar ao guardrail um contrato
de primeira classe dentro do TraceCast**: decisão (`allow`/`block`/`flag`) visível no trace,
reuso do `eval/` já existente para os casos que precisam de LLM-as-judge, e integração opcional
com libs externas (LLM Guard, Presidio) sem forçar dependência.

## Goals

- [ ] Guardrail vira um tipo de span de primeira classe com resultado estruturado (`allow` /
      `block` / `flag`), não uma convenção informal de nome de função.
- [ ] Guardrails podem ser **estáticos** (heurística determinística, ex.: regex, lista de termos,
      Presidio/PII opcional) ou **dinâmicos** (LLM-as-judge via `eval/LLMJudge` reaproveitado,
      critério configurável em runtime — não hardcoded no código).
- [ ] Decisão de bloqueio interrompe o fluxo (levanta exceção tipada) de forma que o app consumidor
      decida o que fazer — TraceCast nunca decide silenciosamente por conta própria além de
      registrar.
- [ ] Zero dependência obrigatória nova — libs de terceiros (LLM Guard, Presidio, detoxify) são
      100% opcionais, mesmo padrão de degradação graciosa já usado para `pymongo`/`psycopg2`/
      `detoxify`.

## Out of Scope

| Item | Razão |
| ---- | ----- |
| Reimplementar scanners de PII/prompt-injection do zero | LLM Guard/Presidio já fazem isso bem; TraceCast integra, não compete |
| Colang / DSL de fluxo de diálogo (estilo NeMo Guardrails) | Overkill para o público-alvo (devs Python instrumentando um agente já existente, não construindo do zero um assistente conversacional) |
| Guardrail em gateway/proxy (estilo Bifrost) | Muda a arquitetura do projeto inteiro (de "lib in-process" para "gateway de rede") — incompatível com o princípio de tracing in-process já decidido (ver lição em `STATE.md`) |
| UI de configuração visual de política | Política é código Python (`GuardrailPolicy`), não YAML/UI — mantém "leve", sem novo editor no dashboard nesta fase |

---

## User Stories

### P1: Guardrail como span de primeira classe ⭐ MVP

**User Story**: Como dev, quero decorar uma função de checagem com `@guardrail(...)` e ter o
resultado (`allow`/`block`/`flag` + motivo) capturado como span estruturado no trace, para ver no
dashboard exatamente o que foi bloqueado e por quê.

**Why P1**: É o mínimo que já resolve C5 de forma real (hoje é só um `@trace_span` sem semântica).

**Acceptance Criteria**:

1. WHEN uma função decorada com `@guardrail(name=..., on_block="raise"|"flag")` retorna um
   `GuardrailResult(decision, reason, score=None)` THEN o sistema SHALL criar um span
   `type=SpanType.GUARDRAIL` com `metadata={"decision": ..., "reason": ...}`.
2. WHEN `decision == "block"` E `on_block="raise"` THEN o sistema SHALL levantar
   `GuardrailBlocked(reason)` imediatamente após fechar o span (span sempre grava, mesmo quando
   bloqueia).
3. WHEN `decision == "block"` E `on_block="flag"` THEN o sistema SHALL apenas marcar o span e
   retornar o input original ao chamador (sem interromper), para casos de "observar antes de
   aplicar".
4. WHEN `decision == "allow"` THEN o sistema SHALL seguir o fluxo normalmente, span registrado
   como `allow`.

**Independent Test**: decorar uma função `block_if_contains_secret(text)` retornando `block` para
texto com padrão de API key; chamar com `on_block="raise"` e verificar que `GuardrailBlocked` é
levantada e o span aparece no trace com `decision="block"`.

---

### P1: Guardrail dinâmico via `eval/LLMJudge` reaproveitado ⭐ MVP

**User Story**: Como dev, quero um guardrail cujo critério é avaliado por LLM-as-judge (ex.:
"a resposta vaza informação da empresa concorrente?") sem escrever um novo motor de judge — reusar
o `LLMJudge` que já existe para eval offline.

**Why P1**: É o "dynamic" do pedido — política não é fixa em regex, é resolvida em runtime por um
critério em linguagem natural, com o mesmo motor já testado do módulo `eval/`.

**Acceptance Criteria**:

1. WHEN configuro `LLMGuardrail(criteria="não deve vazar nome de concorrentes", threshold=0.5)`
   THEN o sistema SHALL usar `eval.judge.LLMJudge` internamente para pontuar o texto, sem duplicar
   lógica de prompt de judge.
2. WHEN o score do judge for `< threshold` THEN a decisão SHALL ser `block`; caso contrário
   `allow`.
3. WHEN o judge falha (erro de API, timeout) THEN o sistema SHALL aplicar uma política de
   `fail_mode` configurável (`"open"` = allow silencioso ou `"closed"` = block) — default
   `"open"` documentado explicitamente (fail-open é a escolha mais segura para não derrubar
   produção por instabilidade do provider de LLM).

**Independent Test**: configurar `LLMGuardrail` com um `FakeChatModel` de teste que sempre retorna
score baixo, ver decisão `block`; simular exceção do judge e ver fallback para `allow` (fail-open
default).

---

### P2: Guardrails estáticos prontos (heurística, sem LLM)

**User Story**: Como dev, quero guardrails prontos para os casos mais comuns (PII básico via
regex, lista de termos bloqueados, limite de tamanho de output) sem escrever heurística do zero,
inspirados nos scanners do LLM Guard mas sem a dependência obrigatória.

**Why P2**: Cobre 80% dos casos simples sem custo de LLM call nem dependência pesada; P1 (LLM
judge) cobre os 20% que precisam de julgamento semântico.

**Acceptance Criteria**:

1. WHEN uso `guardrails.presets.regex_pii(fields=["email", "cpf", "credit_card"])` THEN o sistema
   SHALL aplicar os padrões prontos e retornar `block` se qualquer um casar.
2. WHEN uso `guardrails.presets.banned_terms(["termo1", "termo2"])` THEN o sistema SHALL bloquear
   se qualquer termo aparecer (case-insensitive).
3. WHEN a lib opcional `presidio-analyzer` está instalada THEN
   `guardrails.presets.pii_advanced()` SHALL usá-la para detecção de PII mais robusta que regex;
   quando ausente, SHALL levantar erro claro apontando para instalar o extra opcional
   (`pip install tracecast[guardrails]`), nunca falhar silenciosamente.

**Independent Test**: rodar `regex_pii` contra um texto com um e-mail válido, ver `block`; contra
texto sem PII, ver `allow`.

---

### P3: Reuso de `METRICS` do eval como guardrail

**User Story**: Como dev que já configurou métricas de eval (`toxicity`, `hallucination`), quero
usar a mesma métrica como guardrail de produção sem duplicar definição.

**Why P3**: Elegância de API — não é bloqueador, mas fecha o círculo entre eval offline e guarda
online (mesmo espírito do `OnlineEval` já implementado, que já faz algo parecido gravando `Score`
em vez de bloquear).

**Acceptance Criteria**:

1. WHEN configuro `MetricGuardrail(metric="toxicity", threshold=0.3)` THEN o sistema SHALL
   resolver a métrica do registry `METRICS` (mesmo reuso do `eval/metrics.py`) e aplicar como
   guardrail.

**Independent Test**: `MetricGuardrail(metric="toxicity", threshold=0.3)` contra texto tóxico
sintético, ver `block`.

---

## Edge Cases

- WHEN um guardrail é aplicado fora de um trace ativo (`Tracer.current()` é `None`) THEN o sistema
  SHALL ainda executar a checagem e aplicar a decisão (`raise`/`flag`), só não grava span (mesmo
  padrão de `@trace_span` hoje, que não falha fora de trace).
- WHEN múltiplos guardrails estão encadeados (`@guardrail` empilhados) THEN o sistema SHALL
  avaliar em ordem e parar no primeiro `block` com `on_block="raise"` (short-circuit).
- WHEN `GuardrailBlocked` não é capturada pelo app THEN ela SHALL se propagar como qualquer
  exceção Python normal — TraceCast não engole (consistente com ADR-004: parar de engolir
  exceções).
- WHEN o texto de input é vazio/`None` THEN presets estáticos SHALL retornar `allow` (nada para
  checar), não erro.

## Requirement Traceability

| Requirement ID | Story | Fase | Status |
| -------------- | ----- | ---- | ------ |
| GUARD-01 | P1 `@guardrail` decorator + `GuardrailResult` + span `GUARDRAIL` | Design | Pending |
| GUARD-02 | P1 `on_block="raise"` levanta `GuardrailBlocked` | Design | Pending |
| GUARD-03 | P1 `on_block="flag"` não interrompe | Design | Pending |
| GUARD-04 | P1 `LLMGuardrail` reusa `eval.judge.LLMJudge` | Design | Pending |
| GUARD-05 | P1 `fail_mode` open/closed em erro de judge | Design | Pending |
| GUARD-06 | P2 presets `regex_pii`/`banned_terms` | Design | Pending |
| GUARD-07 | P2 `pii_advanced` via Presidio opcional | Design | Pending |
| GUARD-08 | P3 `MetricGuardrail` reusa `METRICS` registry | Design | Pending |

**Status values:** Pending → In Design → In Tasks → Implementing → Verified
**Coverage:** 8 requisitos.

## Success Criteria

- [ ] `@guardrail` decorator funciona standalone (sem trace ativo) e integrado (com trace ativo,
      span visível no dashboard).
- [ ] `LLMGuardrail` não duplica nenhuma linha de prompt/parsing do `eval/judge.py` — 100% reuso.
- [ ] Nenhuma dependência nova é obrigatória (`presidio-analyzer`, `detoxify` continuam opcionais).
- [ ] Suite Python verde, sem regressão.
