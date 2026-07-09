# ROADMAP — TraceCast

## Entregue

| Milestone | Feature SDD | Status |
|-----------|-------------|--------|
| Observabilidade confiável (schema v2, grafo, save visível, pushdown) | `features/observability-reliability` | ✅ |
| Plataforma (eval persist, scores, metrics, compare, online eval, prompts) | `features/observability-platform` | ✅ backend · UI parcial |
| Export queue + batch + truncate + sample (Langfuse/LangSmith-style) | (inline / sessão 2026-07-09) | ✅ código |

## Em especificação / próximo

| Milestone | Feature SDD | Prioridade |
|-----------|-------------|------------|
| **Export resilience** — fallback de resumo, retry, health, projeção leve | `features/export-resilience` | **P0 agora** |
| Dashboard debug UX (trace detail rico, erros 100% sample, Overview acionável) | TBD | P1 |
| Spool em disco + sampling inteligente (erros 100%) | TBD | P1 |
| Aggregates nativos no DB + retention Postgres | TBD | P2 |
| Mask PII + `tracecast doctor` | TBD | P2 |

## Princípio de priorização

Tudo que reforça **self-host leve + confiança no save** vem antes de features “SaaS-like”.
