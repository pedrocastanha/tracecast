# TraceCast — API Reference (Python)

Referência completa de todas as classes, funções e utilitários públicos do TraceCast.

## Índice

1. [Tracer](#tracer) — Gerenciador de contexto de trace
2. [trace_cast](#trace_cast) — Decorator para funções e endpoints
3. [set_default_tracer](#set_default_tracer) — Configura tracer global
4. [Trace](#trace) — Modelo de dados do trace
5. [Span](#span) — Modelo de dados do span
6. [SpanType](#spantype) — Enum de tipos de span
7. [calculate_cost](#calculate_cost) — Calculadora de custo
8. [extract_tokens](#extract_tokens) — Extrator de tokens de respostas SDK
9. [trace_llm_call](#trace_llm_call) — Wrapper de chamada LLM
10. [wrap_openai](#wrap_openai) — Proxy OpenAI com auto-tracing
11. [wrap_anthropic](#wrap_anthropic) — Proxy Anthropic com auto-tracing
12. [TraceCastCallback](#tracecastcallback) — Callback LangChain
13. [TraceCastMiddleware](#tracecastmiddleware) — Middleware ASGI
14. [Exporters](#exporters) — JsonFile, Dict, Mongo, Postgres, Custom
15. [TraceCastLogger](#tracecastlogger) — Sistema de logging estruturado

---

## Tracer

**Localização:** `tracecast.core.tracer.Tracer`  
**Exportado via:** `from tracecast import Tracer`

Classe principal do TraceCast. Gerencia traces via context manager (`with`/`async with`), isola contextos de execução usando `ContextVar`, e orquestra a exportação.

### Construtor

```python
Tracer(
    exporters: Optional[List[BaseExporter]] = None,
    logging: bool = False,
    log_prefix: Optional[str] = None,
)
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `exporters` | `List[BaseExporter] \| None` | `None` | Lista de exporters que receberão cada trace finalizado |
| `logging` | `bool` | `False` | Habilita logging estruturado de eventos LLM/Tool/Chain |
| `log_prefix` | `str \| None` | `None` | Prefixo opcional para as mensagens de log |

### Métodos

#### `trace(name, session_id=None, user_id=None, project_id=None, metadata=None)`

Context manager síncrono que cria um trace. O trace é automaticamente finalizado e exportado ao sair do bloco.

```python
tracer = Tracer(exporters=[JsonFileExporter("./traces.jsonl")])

with tracer.trace("pesquisa_web", user_id="usr_42", session_id="sess_abc") as trace:
    span = Span(span_id="...", type=SpanType.LLM, name="llm:gpt-4o", ...)
    trace.spans.append(span)
# Trace exportado aqui (finally)
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `name` | `str` | — | Nome lógico do trace (ex: `"pesquisa_web"`, `"gerar_resposta"`) |
| `session_id` | `str \| None` | `None` | ID da sessão/conversa |
| `user_id` | `str \| None` | `None` | ID do usuário final |
| `project_id` | `str \| None` | `None` | ID do projeto |
| `metadata` | `dict \| None` | `None` | Dicionário livre para tags/metadados extras |

**Retorno:** `Trace` — o objeto trace criado (via `as`).

**Resiliência:** se o código dentro do bloco lançar exceção, o trace é finalizado com `metadata["_error"]` e exportado antes de relançar a exceção.

---

#### `atrace(name, session_id=None, user_id=None, project_id=None, metadata=None)`

Versão assíncrona de `trace()`. Usa `async with`.

```python
async with tracer.atrace("async_task", user_id="usr_1") as trace:
    await algum_llm_call()
```

Mesmos parâmetros de `trace()`.

---

#### `current() -> Optional[Trace]`

Método estático. Retorna o trace ativo no contexto atual (thread/coroutine), ou `None` se não houver.

```python
trace = Tracer.current()
if trace:
    span = Span(...)
    trace.spans.append(span)
```

---

#### `addSpan(span) -> None`

Adiciona um span ao trace ativo. Equivalente a `Tracer.current().spans.append(span)`, mas seguro (ignora se não houver trace ativo).

```python
tracer.addSpan(meu_span)
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `span` | `Span` | Span a ser adicionado ao trace atual |

---

## trace_cast

**Localização:** `tracecast.decorators.trace_cast`  
**Exportado via:** `from tracecast import trace_cast`

Decorator que substitui o context manager `with tracer.trace(...)` por uma anotação na função. Suporta funções síncronas e assíncronas. Detecta automaticamente o tipo.

### Assinatura

```python
@trace_cast                                    # Uso bare
@trace_cast(name="...", tracer=..., ...)       # Uso parametrizado
def minha_funcao():
    ...
```

### Uso Bare (sem parênteses)

```python
from tracecast import trace_cast, set_default_tracer

set_default_tracer(Tracer(exporters=[...]))

@trace_cast
def minha_rota(x, y):
    return x + y

@trace_cast
async def endpoint_llm(prompt: str):
    ...
```

O nome do trace será `"modulo.funcao"` automaticamente (ex: `"__main__.minha_rota"`).

### Uso Parametrizado

```python
@trace_cast(
    name="gerar-resposta",       # Nome customizado do trace
    session_id="sess-123",       # Opcional
    user_id="usr_42",            # Opcional
    project_id="proj-x",         # Opcional
    metadata={"env": "prod"},    # Opcional
    tracer=Tracer(exporters=[...]),  # Tracer específico (opcional)
)
async def chat_endpoint(message: str):
    ...
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `name` | `str \| None` | `"modulo.funcao"` | Nome do trace |
| `session_id` | `str \| None` | `None` | ID da sessão |
| `user_id` | `str \| None` | `None` | ID do usuário |
| `project_id` | `str \| None` | `None` | ID do projeto |
| `metadata` | `dict \| None` | `None` | Metadados extras |
| `tracer` | `Tracer \| None` | `None` | Instância específica de Tracer. Se omitido, usa o default tracer configurado via `set_default_tracer()`, ou cria um novo Tracer sem exporters. |

**Ordem de resolução do tracer:** `tracer` explícito → `_default_tracer` (setado via `set_default_tracer`) → `Tracer()` vazio.

---

## set_default_tracer

**Localização:** `tracecast.decorators.set_default_tracer`  
**Exportado via:** `from tracecast import set_default_tracer`

Define o tracer padrão usado por `@trace_cast` e `@trace_cast()` quando nenhum tracer explícito é passado.

```python
from tracecast import Tracer, set_default_tracer
from tracecast.exporters import JsonFileExporter

tracer = Tracer(
    exporters=[JsonFileExporter("./traces.jsonl")],
    logging=True,
    log_prefix="api",
)
set_default_tracer(tracer)

# Agora @trace_cast usa esse tracer automaticamente
@trace_cast
def qualquer_funcao():
    ...
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `tracer` | `Tracer` | Instância de Tracer a ser usada como default |

---

## Trace

**Localização:** `tracecast.models.trace.Trace`  
**Exportado via:** `from tracecast import Trace`

Dataclass que representa uma execução completa rastreada. Contém metadados do trace e uma lista de spans.

### Campos

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `trace_id` | `str` | — | UUID v4 único do trace |
| `name` | `str` | — | Nome lógico da tarefa |
| `started_at` | `datetime` | — | Timestamp UTC de início |
| `finished_at` | `datetime \| None` | `None` | Timestamp UTC de conclusão |
| `session_id` | `str \| None` | `None` | ID da sessão/conversa |
| `user_id` | `str \| None` | `None` | ID do usuário final |
| `project_id` | `str \| None` | `None` | ID do projeto |
| `model` | `str \| None` | `None` | Modelo dominante (mais tokens consumidos) |
| `total_tokens_in` | `int` | `0` | Soma de `tokens_in` de todos os spans LLM |
| `total_tokens_out` | `int` | `0` | Soma de `tokens_out` de todos os spans LLM |
| `total_tokens_in_cached` | `int` | `0` | Soma de `tokens_in_cached` de todos os spans LLM |
| `total_tokens` | `int` | `0` | `total_tokens_in + total_tokens_out` |
| `cost_usd` | `float` | `0.0` | Custo total em USD |
| `latency_ms` | `int \| None` | `None` | Latência total em ms |
| `tools_used` | `dict[str, int]` | `{}` | Mapa `{nome_tool: contagem}` |
| `spans` | `list[Span]` | `[]` | Lista de spans |
| `metadata` | `dict` | `{}` | Metadados livres |

### Métodos

#### `_finalize() -> None`

Chamado internamente pelo Tracer ao fechar o trace. Agrega totais de todos os spans. Não deve ser chamado manualmente.

#### `to_dict() -> dict`

Serializa o trace para dicionário. Inclui todos os campos como tipos nativos (datetimes viram ISO8601, spans viram dicts recursivamente).

---

## Span

**Localização:** `tracecast.models.span.Span`  
**Exportado via:** `from tracecast import Span`

Dataclass que representa um evento individual dentro de um trace (chamada LLM, tool call, passo de chain).

### Campos

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `span_id` | `str` | — | UUID do span |
| `type` | `SpanType` | — | Tipo: `LLM`, `TOOL`, ou `AGENT` |
| `name` | `str` | — | Nome descritivo (ex: `"llm:gpt-4o"`, `"search_web"`) |
| `started_at` | `datetime` | — | Timestamp UTC de início |
| `finished_at` | `datetime \| None` | `None` | Timestamp UTC de conclusão |
| `model` | `str \| None` | `None` | Modelo usado (para spans LLM) |
| `tokens_in` | `int` | `0` | Tokens de entrada (prompt) |
| `tokens_out` | `int` | `0` | Tokens de saída (completion) |
| `tokens_in_cached` | `int` | `0` | Tokens de entrada cacheados (reduz custo) |
| `cost_usd` | `float` | `0.0` | Custo em USD deste span |
| `metadata` | `dict` | `{}` | Metadados livres (erros em `metadata["_error"]`) |

### Propriedades

#### `latency_ms -> int | None`
Calculado: `(finished_at - started_at) * 1000`. `None` se `finished_at` não definido.

#### `total_tokens -> int`
`tokens_in + tokens_out`.

#### `to_dict() -> dict`
Serializa o span para dicionário.

---

## SpanType

**Localização:** `tracecast.models.span.SpanType`  
**Exportado via:** `from tracecast import SpanType`

Enum com os tipos de span suportados:

| Valor | Uso |
|-------|-----|
| `SpanType.LLM` | Chamada a um modelo de linguagem |
| `SpanType.TOOL` | Invocação de ferramenta/função |
| `SpanType.AGENT` | Passo intermediário de chain/grafo |

```python
span = Span(span_id="...", type=SpanType.LLM, name="llm:gpt-4o", ...)
```

---

## calculate_cost

**Localização:** `tracecast.core.cost_calculator.calculate_cost`  
**Exportado via:** `from tracecast import calculate_cost`

Calcula o custo em USD de uma chamada LLM usando a tabela de preços built-in (22+ modelos).

### Assinatura

```python
calculate_cost(
    model: str,
    tokens_in: int,
    tokens_out: int,
    custom_prices: Optional[Dict] = None,
    tokens_in_cached: int = 0,
) -> float
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `model` | `str` | — | Nome do modelo (ex: `"gpt-4o"`, `"claude-sonnet-4-6"`) |
| `tokens_in` | `int` | — | Tokens de entrada (prompt) |
| `tokens_out` | `int` | — | Tokens de saída (completion) |
| `custom_prices` | `dict \| None` | `None` | Dicionário `{"modelo": {"input": X, "output": Y, "cached"?: Z}}` para sobrescrever/adicionar preços |
| `tokens_in_cached` | `int` | `0` | Quantos tokens de entrada vieram do cache (preço reduzido) |

**Retorno:** `float` — custo em USD.

**Fallback:** se o modelo não for encontrado na tabela, tenta prefix match (ex: `ollama/llama3` → `ollama/*`). Se nada bater, retorna `0.0`.

### Exemplos

```python
# Preço padrão
custo = calculate_cost("gpt-4o", tokens_in=100, tokens_out=50)
# → 0.00075

# Com cache hit
custo = calculate_cost("gpt-4o", tokens_in=100, tokens_out=50, tokens_in_cached=40)
# → (60/1000 * 0.0025) + (40/1000 * 0.00125) + (50/1000 * 0.01) = 0.00070

# Preço customizado
custo = calculate_cost("meu-modelo", tokens_in=100, tokens_out=50,
                       custom_prices={"meu-modelo": {"input": 0.001, "output": 0.002}})
```

---

## extract_tokens

**Localização:** `tracecast.core.token_counter.extract_tokens`  
**Exportado via:** `from tracecast import extract_tokens`

Extrai contagem de tokens de respostas dos SDKs OpenAI, Anthropic e LangChain.

### Assinatura

```python
extract_tokens(response: Any, provider: str) -> dict
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `response` | `Any` | Objeto de resposta do SDK |
| `provider` | `str` | `"openai"`, `"anthropic"`, ou `"langchain"` |

**Retorno:** `dict` com chaves:
- `"input"` — tokens de entrada
- `"output"` — tokens de saída  
- `"cached"` — tokens cacheados (0 se não aplicável)

### Exemplo

```python
import openai
from tracecast import extract_tokens

resp = openai.OpenAI().chat.completions.create(
    model="gpt-4o", messages=[{"role": "user", "content": "Olá"}]
)
tokens = extract_tokens(resp, "openai")
# → {"input": 7, "output": 5, "cached": 0}
```

---

## trace_llm_call

**Localização:** `tracecast.integrations.llm.trace_llm_call`  
**Exportado via:** `from tracecast import trace_llm_call`

Wrapper de baixo nível que executa uma chamada LLM e automaticamente cria um span com tokens e custo no trace ativo.

### Assinatura

```python
trace_llm_call(
    fn: Callable[..., T],
    *,
    provider: str,
    model: str,
    metadata: Optional[dict] = None,
) -> T
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `fn` | `Callable` | Função zero-argumento que faz a chamada LLM e retorna a resposta |
| `provider` | `str` | `"openai"` ou `"anthropic"` — usado para extrair tokens da resposta |
| `model` | `str` | Nome do modelo (ex: `"gpt-4o"`) |
| `metadata` | `dict \| None` | Metadados extras para o span |

**Retorno:** O valor retornado por `fn()`.

**Comportamento:** se `Tracer.current()` for `None`, `fn()` é chamada diretamente sem criar span.

### Exemplo

```python
from tracecast import Tracer, trace_llm_call
import openai

client = openai.OpenAI()

with tracer.trace("chat"):
    resp = trace_llm_call(
        lambda: client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Explique IA"}]
        ),
        provider="openai",
        model="gpt-4o",
    )
# Span criado automaticamente com tokens extraídos e custo calculado
```

---

## wrap_openai

**Localização:** `tracecast.integrations.llm.wrap_openai`  
**Exportado via:** `from tracecast import wrap_openai`

Cria um proxy em volta de um cliente OpenAI. Todas as chamadas a `client.chat.completions.create(...)` são automaticamente interceptadas, criando spans com tokens e custo.

### Assinatura

```python
wrap_openai(client: Any) -> Any
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `client` | `openai.OpenAI` | Cliente OpenAI original |

**Retorno:** Proxy que delega todas as chamadas ao cliente original, interceptando `chat.completions.create()`. O proxy extrai o nome do modelo do parâmetro `model=` passado à chamada.

### Exemplo

```python
from tracecast import Tracer, wrap_openai, set_default_tracer
import openai

client = wrap_openai(openai.OpenAI())

with tracer.trace("chat"):
    # Span + tokens + custo automáticos
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Olá mundo!"}],
    )
```

---

## wrap_anthropic

**Localização:** `tracecast.integrations.llm.wrap_anthropic`  
**Exportado via:** `from tracecast import wrap_anthropic`

Idêntico a `wrap_openai`, mas para o SDK Anthropic. Intercepta `client.messages.create(...)`.

### Assinatura

```python
wrap_anthropic(client: Any) -> Any
```

### Exemplo

```python
from tracecast import Tracer, wrap_anthropic
import anthropic

client = wrap_anthropic(anthropic.Anthropic())

with tracer.trace("claude_chat"):
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Olá!"}],
    )
```

---

## TraceCastCallback

**Localização:** `tracecast.integrations.langchain.TraceCastCallback`  
**Import:** `from tracecast.integrations.langchain import TraceCastCallback`

Handler que intercepta callbacks do LangChain/LangGraph para criar spans automaticamente.

### Construtor

```python
TraceCastCallback(tracer: Tracer)
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `tracer` | `Tracer` | Instância de Tracer à qual os spans serão adicionados |

### Eventos interceptados

| Evento LangChain | Ação TraceCast |
|------------------|----------------|
| `on_llm_start` | Cria `Span(type=LLM)` com modelo extraído dos metadados |
| `on_llm_end` | Fecha span, extrai tokens do `response.llm_output`, calcula custo |
| `on_llm_error` | Fecha span com `metadata["_error"]` |
| `on_tool_start` | Cria `Span(type=TOOL)` |
| `on_tool_end` | Fecha span de tool com latência |
| `on_tool_error` | Fecha span de tool com erro |
| `on_chain_start` | Cria `Span(type=AGENT)` para o nó raiz (sub-nós ignorados) |
| `on_chain_end` | Fecha span de chain |
| `on_chain_error` | Fecha span de chain com erro |

### Exemplo

```python
from tracecast import Tracer
from tracecast.integrations.langchain import TraceCastCallback
from langchain_openai import ChatOpenAI

tracer = Tracer(logging=True)
callback = TraceCastCallback(tracer=tracer)

llm = ChatOpenAI(model="gpt-4o-mini", stream_usage=True)
chain = llm  # ou chain mais complexa

with tracer.trace("langchain-run"):
    chain.invoke("Olá!", config={"callbacks": [callback]})
```

---

## TraceCastMiddleware

**Localização:** `tracecast.middleware.TraceCastMiddleware`  
**Import:** `from tracecast.middleware import TraceCastMiddleware`

Middleware ASGI que cria automaticamente um trace para cada requisição HTTP. Compatível com FastAPI, Starlette, e qualquer framework ASGI.

### Construtor

```python
TraceCastMiddleware(
    app: Callable,
    *,
    tracer: Optional[Tracer] = None,
    name_prefix: str = "",
)
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `app` | `Callable` | — | Aplicação ASGI a ser envolvida |
| `tracer` | `Tracer \| None` | `None` | Instância de Tracer. Se omitido, usa `_default_tracer` ou cria Tracer vazio |
| `name_prefix` | `str` | `""` | Prefixo para o nome do trace (ex: `"api-v2"` → `"api-v2GET /chat"`) |

**Nome do trace:** `"{prefix}{method} {path}"` — ex: `"POST /api/chat"`, `"GET /health"`.

**Requisições não-HTTP** (ex: WebSocket upgrade) são passadas direto sem trace.

### Exemplo

```python
from fastapi import FastAPI
from tracecast import Tracer
from tracecast.exporters import JsonFileExporter
from tracecast.middleware import TraceCastMiddleware

app = FastAPI()

tracer = Tracer(
    exporters=[JsonFileExporter("./api_traces.jsonl")],
    logging=True,
    log_prefix="api",
)

app.add_middleware(TraceCastMiddleware, tracer=tracer)

@app.get("/chat")
async def chat(message: str):
    return {"reply": f"Echo: {message}"}
# Toda request GET /chat gera um trace automaticamente
```

---

## Exporters

### BaseExporter

**Localização:** `tracecast.exporters.base.BaseExporter`

Classe abstrata base para todos os exporters.

```python
class BaseExporter(ABC):
    @abstractmethod
    def export(self, trace: Trace) -> None: ...
    def export_batch(self, traces: list) -> None: ...  # export() em loop
    async def aexport(self, trace: Trace) -> None: ...  # chama export() sync
```

Para criar um exporter customizado, estenda `BaseExporter` e implemente `export()`.

```python
from tracecast.exporters.base import BaseExporter
from tracecast import Trace

class WebhookExporter(BaseExporter):
    def __init__(self, url: str):
        self.url = url

    def export(self, trace: Trace) -> None:
        import httpx
        httpx.post(self.url, json=trace.to_dict())
```

### JsonFileExporter

**Localização:** `tracecast.exporters.json_file.JsonFileExporter`  
**Import:** `from tracecast.exporters import JsonFileExporter`

Exporta traces para arquivo JSONL (uma linha JSON por trace).

```python
JsonFileExporter(
    path: str = "./traces.jsonl",
    include_fields: Optional[Iterable[str]] = None,
    exclude_fields: Optional[Iterable[str]] = None,
)
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `path` | `str` | `"./traces.jsonl"` | Caminho do arquivo JSONL |
| `include_fields` | `Iterable[str] \| None` | `None` | Se definido, só exporta estes campos |
| `exclude_fields` | `Iterable[str] \| None` | `None` | Se definido, exclui estes campos |

### DictExporter

**Localização:** `tracecast.exporters.dict_exporter.DictExporter`  
**Import:** `from tracecast.exporters import DictExporter`

Exporta traces para uma lista em memória ou callback customizado. Ideal para testes e pipelines.

```python
DictExporter(
    on_trace: Optional[Callable[[dict], None]] = None,
    include_fields: Optional[Iterable[str]] = None,
    exclude_fields: Optional[Iterable[str]] = None,
)
```

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `on_trace` | `Callable[[dict], None] \| None` | `None` | Callback chamado com cada trace serializado |
| `include_fields` | `Iterable[str] \| None` | `None` | Se definido, só exporta estes campos |
| `exclude_fields` | `Iterable[str] \| None` | `None` | Se definido, exclui estes campos |

**Atributo:** `exporter.traces: list[dict]` — lista acumulada (quando `on_trace=None`).

**Método:** `exporter.clear()` — limpa a lista acumulada.

### MongoExporter

**Import:** `from tracecast.exporters.mongo import MongoExporter`  
**Requer:** `pip install "tracecast[mongo]"`

```python
MongoExporter(
    uri: str,
    db: str,
    collection: str,
    include_fields: Optional[Iterable[str]] = None,
    exclude_fields: Optional[Iterable[str]] = None,
)
```

### PostgresExporter

**Import:** `from tracecast.exporters.postgres import PostgresExporter`  
**Requer:** `pip install "tracecast[postgres]"`

```python
PostgresExporter(
    dsn: str,
    table: str = "traces",
    include_fields: Optional[Iterable[str]] = None,
    exclude_fields: Optional[Iterable[str]] = None,
)
```

Usável como context manager (`with PostgresExporter(...) as exporter:`) para garantir `close()` da conexão.

---

## TraceCastLogger

**Localização:** `tracecast.core.logger.TraceCastLogger`

Sistema de logging estruturado usado internamente quando `Tracer(logging=True)`. Emite logs formatados via `logging.getLogger("tracecast")`.

### Eventos logados

| Método | Quando | Formato |
|--------|--------|---------|
| `trace_start(name)` | Início do trace | `[prefix] Trace started` |
| `trace_end(name, ...)` | Fim do trace | `[prefix] Trace finished → total: N tokens \| $X.XXXX \| X.XXs \| tools: nome×N` |
| `llm_start(name, model)` | Início de chamada LLM | `[prefix] LLM started → gpt-4o` |
| `llm_end(name, ...)` | Fim de chamada LLM | `[prefix] LLM end → gpt-4o \| tokens: X in (Y cached) / Z out \| $X.XXXX \| X.XXs` |
| `llm_error(name, model, error)` | Erro em chamada LLM | `[prefix] LLM error → gpt-4o \| ⚠ mensagem` |
| `tool_start(name, name, input_str)` | Início de tool | `[prefix] Tool call → nome \| input` |
| `tool_end(name, name, latency_ms)` | Fim de tool | `[prefix] Tool end → nome \| X.XXs` |
| `tool_error(name, name, error)` | Erro em tool | `[prefix] Tool error → nome \| ⚠ mensagem` |
| `chain_start(name, name)` | Início de chain | `[prefix] Chain → nome` |
| `chain_error(name, name, error)` | Erro em chain | `[prefix] Chain error → nome \| ⚠ mensagem` |

---

## Receita: Endpoint FastAPI com tracing completo

```python
from fastapi import FastAPI
from tracecast import (
    trace_cast, set_default_tracer, Tracer, wrap_openai,
)
from tracecast.exporters import JsonFileExporter
from tracecast.middleware import TraceCastMiddleware
import openai

# Setup global
tracer = Tracer(
    exporters=[JsonFileExporter("./api_traces.jsonl")],
    logging=True,
    log_prefix="api",
)
set_default_tracer(tracer)
client = wrap_openai(openai.OpenAI())

app = FastAPI()
app.add_middleware(TraceCastMiddleware, tracer=tracer)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/chat")
@trace_cast(user_id="from_auth_middleware")
async def chat(message: str):
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": message}],
    )
    return {"reply": resp.choices[0].message.content}

# Exemplo de saída no traces.jsonl:
# {"trace_id":"...","name":"POST /chat","total_tokens":150,"cost_usd":0.00075,...}
```
