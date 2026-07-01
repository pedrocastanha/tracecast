# Dashboard UI/UX Refresh — Specification

> **Status:** Specify (design.md/tasks.md pendentes — aprofundar depois de priorização)
> **Escopo:** Large (toca as 8 páginas + 6 componentes do `tracecast-dashboard`, sem mudança de
> backend)
> **Branch sugerida:** `feature/dashboard-ux-refresh`
> **Depende de:** nada novo no backend — 100% frontend (`packages/tracecast-dashboard`)
> **Relacionado:** `.specs/research/langfuse-comparison.md`
> **Última atualização:** 2026-06-30

## Problem Statement

Inspeção do código atual (`packages/tracecast-dashboard/src/`, React 18 + Vite, sem Tailwind/
design system, estilo inline + CSS vars) mostra 8 páginas e 6 componentes funcionais (Overview,
Traces, TraceDetail, Sessions, Projects, Models, Evaluators, EvalRunDetail, EvalCompare, Prompts)
já com dados reais (T10/T16-UI/T24 do SDD `observability-platform` já foram entregues — commit
`d10ffbf`). O que falta não é funcionalidade, é **acabamento e ergonomia**: sem sistema de design
consistente, sem P50/P99 de latência em nenhuma página, sem estado vazio/loading padronizado, sem
busca/command-palette, sem forma de um humano não-engenheiro (PM/QA) revisar e anotar traces sem
mexer em código.

Pesquisa de mercado (2026) confirma que "cross-functional workflows" (revisão de trace por
não-engenheiros) é um diferencial citado repetidamente entre as ferramentas líderes — mas isso
não precisa de fila multiusuário completa (fora de escopo, ver `ROADMAP.md` M "Future
Considerations") para gerar valor: uma versão "lite" (anotação de um trace por qualquer pessoa
com acesso ao dashboard, sem workflow de fila) já fecha boa parte do gap sem infraestrutura nova.

## Goals

- [ ] Sistema de design mínimo e consistente (tokens de cor/espaçamento/tipografia centralizados)
      substituindo estilo inline espalhado — sem adotar uma lib pesada (Tailwind é aceitável por
      ser build-time, zero runtime cost; MUI/AntD não, por peso de bundle).
- [ ] Estados vazio/loading/erro padronizados em todas as páginas (hoje inconsistentes — algumas
      têm, outras não).
- [ ] P50/P95/P99 de latência e custo visíveis no Overview e no detalhe de Models — métrica
      citada como padrão de mercado que hoje não existe em nenhuma página.
- [ ] Busca global / jump-to-trace (command palette leve, `cmd+k`) — reduz fricção de navegação
      em bases com muitos traces.
- [ ] Anotação "lite" de trace (nota de texto livre + tag de status manual, sem fila/workflow) —
      permite revisão por não-engenheiros sem novo backend de auth/permissão.
- [ ] Nenhuma regressão de performance de build/bundle — orçamento de bundle size definido e
      verificado (ver Success Criteria).

## Out of Scope

| Item | Razão |
| ---- | ----- |
| Migração de framework (React→outro) | Custo altíssimo, zero ganho de UX proporcional |
| Dark mode completo com theming dinâmico | CSS vars já existem (`var(--border)` etc.) — expandir para tema completo é trabalho real mas não é o gap relatado; vira item P3 se sobrar tempo, não bloqueia o resto |
| Fila de anotação multiusuário com workflow de aprovação | Precisa auth real — infra nova, contraria princípio do projeto (ver `ROADMAP.md`) |
| Redesign de IA generativa (resumo automático de trace via LLM) | Feature nova de produto, não de UX; avaliar separadamente se houver demanda |

---

## User Stories

### P1: Sistema de design mínimo ⭐ MVP

**User Story**: Como usuário do dashboard, quero uma UI visualmente consistente (cores, espaçamento,
tipografia) em todas as páginas, para não sentir que estou em 8 telas desenhadas separadamente.

**Why P1**: Base para qualquer melhoria subsequente — sem tokens centralizados, cada nova página
reintroduz inconsistência.

**Acceptance Criteria**:

1. WHEN qualquer página do dashboard renderiza THEN cores, espaçamento e tipografia SHALL vir de
   um arquivo de tokens central (`src/theme.ts` ou CSS vars centralizadas em `src/index.css`),
   não de valores literais espalhados em cada componente.
2. WHEN um novo componente é criado THEN SHALL reusar os tokens existentes por padrão (verificado
   em code review, não automatizável totalmente).

**Independent Test**: grep por cores hex literais (`#[0-9a-fA-F]{3,6}`) fora do arquivo de tokens
retorna zero ocorrências nas páginas migradas.

---

### P1: Estados vazio/loading/erro padronizados ⭐ MVP

**User Story**: Como usuário, quero feedback visual consistente quando uma página está carregando,
vazia ou com erro, em vez de tela branca ou comportamento diferente por página.

**Why P1**: Baixo esforço, alto impacto percebido — problema visível em qualquer demo do produto.

**Acceptance Criteria**:

1. WHEN uma chamada `useApi` está em andamento THEN a página SHALL mostrar um componente
   `<LoadingState />` padronizado (não um "Loading..." de texto solto por página).
2. WHEN uma lista (traces, sessions, evals, prompts) retorna vazia THEN a página SHALL mostrar um
   `<EmptyState />` com mensagem contextual (não uma tabela vazia sem explicação).
3. WHEN `useApi` retorna erro THEN a página SHALL mostrar um `<ErrorState />` com opção de retry,
   não falhar silenciosamente nem quebrar o layout.

**Independent Test**: simular erro de rede na API e verificar que toda página testada mostra
`<ErrorState />` com botão de retry funcional.

---

### P2: Percentis de latência/custo (P50/P95/P99)

**User Story**: Como dev investigando performance, quero ver P50/P95/P99 de latência (e não só
média) no Overview e em Models, para identificar cauda longa de latência que a média esconde.

**Why P2**: Gap confirmado contra o padrão de mercado (LangSmith expõe P50/P99 nativamente); não é
P1 porque é aditivo a uma página que já funciona, não corrige algo quebrado.

**Acceptance Criteria**:

1. WHEN o Overview carrega THEN SHALL mostrar P50/P95/P99 de latência de trace ao lado da média
   já existente.
2. WHEN a página Models carrega THEN SHALL mostrar P50/P95/P99 de latência por modelo.
3. WHEN há menos de 2 traces no período filtrado THEN percentis SHALL degradar graciosamente
   (mostrar o único valor disponível ou "dados insuficientes", nunca erro/`NaN`).

**Independent Test**: gerar 20 traces com latências variadas via fixture de teste, verificar que
P95 exibido corresponde ao cálculo esperado (`numpy.percentile` ou implementação equivalente sem
dependência nova — cálculo simples em JS/Python, não precisa de lib).

---

### P2: Busca global / jump-to-trace (`cmd+k`)

**User Story**: Como dev depurando um problema, quero abrir um command palette (`cmd+k`) e pular
direto para um trace por ID parcial, sessão ou projeto, sem navegar por menus.

**Why P2**: Reduz fricção real em bases com volume — mas não é bloqueador de nenhum outro fluxo.

**Acceptance Criteria**:

1. WHEN pressiono `cmd+k`/`ctrl+k` em qualquer página THEN um modal de busca SHALL abrir.
2. WHEN digito um `trace_id` parcial (mínimo 6 caracteres) THEN o sistema SHALL sugerir matches
   via `GET /api/traces?search=` (endpoint pode precisar de suporte a busca parcial — verificar em
   `dashboard/reader.py` se já existe; se não, é sub-tarefa de design, não bloqueia esta spec).
3. WHEN seleciono um resultado THEN o sistema SHALL navegar direto para `TraceDetail` daquele
   trace.

**Independent Test**: abrir `cmd+k`, digitar 6 caracteres de um `trace_id` conhecido, ver
sugestão, clicar, chegar em `TraceDetail` correto.

---

### P3: Anotação "lite" de trace (nota + tag manual)

**User Story**: Como PM/QA sem acesso ao código, quero adicionar uma nota de texto e marcar um
trace como "revisado"/"problema encontrado" direto no dashboard, sem precisar do SDK.

**Why P3**: Fecha parte do gap de "cross-functional workflows" citado no mercado, mas é a menor
prioridade das 5 — depende de UI nova + endpoint novo de escrita (maior superfície que as
anteriores).

**Acceptance Criteria**:

1. WHEN abro `TraceDetail` THEN SHALL existir um campo de nota livre + seletor de tag
   (`reviewed`/`issue`/`none`) editável direto na página.
2. WHEN salvo a nota/tag THEN o sistema SHALL persistir via `tracecast.score()` já existente
   (`kind="human"`, `data_type="categorical"` para a tag, mais um score `comment`-only para a
   nota) — **reuso total do modelo `Score` já implementado**, sem tabela nova.

**Independent Test**: adicionar nota + tag num trace, recarregar a página, ver a nota persistida
(via `GET /api/traces/{id}/scores`, endpoint já existente).

---

## Edge Cases

- WHEN o dashboard é servido pelo `tracecast-server` standalone (read-only, ver AD-9 do SDD
  anterior) THEN a anotação lite (P3, escrita) SHALL ficar desabilitada nessa superfície — mesma
  regra já aplicada a `run_evaluation`/`add_to_dataset`.
- WHEN a base de traces é muito grande (>10k) THEN percentis SHALL ser calculados no backend
  (endpoint), não no frontend buscando tudo — evitar transferir payload gigante só para calcular
  P95 no cliente.
- WHEN não há dados suficientes para nenhuma métrica nova THEN a página SHALL renderizar
  normalmente sem o widget (não quebrar layout com espaço vazio).

## Requirement Traceability

| Requirement ID | Story | Fase | Status |
| -------------- | ----- | ---- | ------ |
| UX-01 | P1 Tokens de design centralizados | Design | Pending |
| UX-02 | P1 `LoadingState`/`EmptyState`/`ErrorState` padronizados | Design | Pending |
| UX-03 | P2 P50/P95/P99 no Overview | Design | Pending |
| UX-04 | P2 P50/P95/P99 em Models | Design | Pending |
| UX-05 | P2 Command palette `cmd+k` | Design | Pending |
| UX-06 | P3 Anotação lite (nota + tag) via `Score` reusado | Design | Pending |

**Status values:** Pending → In Design → In Tasks → Implementing → Verified
**Coverage:** 6 requisitos.

## Success Criteria

- [ ] Bundle size do dashboard (`npm run build`, `dist/assets/*.js` total) não cresce mais que
      15% em relação ao baseline atual — medir antes de começar.
- [ ] Zero cor hex literal fora do arquivo de tokens nas páginas migradas.
- [ ] Todas as 9 páginas usam os 3 estados padronizados.
- [ ] P50/P95/P99 corretos verificados contra cálculo de referência em teste automatizado.
- [ ] Nenhuma regressão nos testes de backend (`/api/traces/{id}/graph` etc. inalterados).
