# TraceCast

**Vision:** SDK Python self-hosted de observabilidade para agentes LLM — captura, persiste e visualiza traces com eval no mesmo pacote, cabendo em VMs pequenas (2 vCPU / 4 GB).

**For:** Devs e times que rodam agentes Python (LangChain/LangGraph/OpenAI/etc.) e querem Langfuse/LangSmith-like **sem** SaaS nem infra pesada.

**Solves:** Tracing de fluxo LLM/agent + dashboard + evaluation offline/online, com save resiliente e footprint controlado.

## Goals

- Captura transparente (decorator, instrumentors, middleware) com hierarquia de spans e grafo
- Persistência best-effort mas **visível** (nunca perda silenciosa total — fallback de resumo no mínimo)
- Dashboard embutido ou standalone lendo o mesmo storage
- Eval (golden dataset + scores + online sample) reusando as mesmas camadas
- Sobreviver em VM 2 vCPU / 4 GB sob carga real

## Tech Stack

**Core:**

- Language: Python 3.10+
- Package: `packages/tracecast-py` (pip / pyproject)
- Frontend: React + Vite SPA em `packages/tracecast-dashboard` (estático no backend)
- Storage: MongoDB, PostgreSQL, JSONL (dev)

**Key dependencies:** FastAPI (dashboard), pymongo/psycopg2 (opcionais), langchain hooks (opcionais)

## Scope

**v1 / atual inclui:**

- Tracer + ContextVar + exporters + dashboard + eval + prompts + background export queue/batch

**Explicitamente fora (por ora):**

- SDK TypeScript de captura
- Kafka/ClickHouse/multi-region
- OTEL-first rewrite completo
- RBAC multi-tenant enterprise

## Constraints

- Technical: RAM/CPU limitados em deploy GCP típico do autor
- Preferência: PT-BR, commits atômicos, TDD imutável no Execute
- Save é best-effort sob overload (drop de fila); métricas e fallback de resumo mitigam cegueira
