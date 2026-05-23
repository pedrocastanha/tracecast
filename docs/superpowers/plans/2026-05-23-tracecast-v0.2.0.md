# TraceCast v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add global auto-instrumentation of LLM SDKs (OpenAI, Anthropic, Gemini, LangChain, LlamaIndex, CrewAI), a React+Vite dashboard with 5 pages, new sessions/projects API endpoints, and DictExporter auto-fallback on mount.

**Architecture:** Instrumentors are modular classes that monkey-patch SDK methods at module level. Each checks `Tracer.current()` before capturing — zero overhead when no trace is active. The React dashboard is a separate package (`packages/tracecast-dashboard/`) whose build output is copied into both Python and TypeScript static directories. Backend API is extended with sessions/projects aggregation endpoints.

**Tech Stack:** Python 3.11+, TypeScript/Node.js, React 18, Vite, Recharts, Chart.js (existing), FastAPI, Flask, Express

---

## File Map

### Python — New Files

| File | Purpose |
|---|---|
| `packages/tracecast-py/tracecast/instrument.py` | `auto_instrument()` entry point |
| `packages/tracecast-py/tracecast/instrumentors/__init__.py` | Registry + re-exports |
| `packages/tracecast-py/tracecast/instrumentors/base.py` | `BaseInstrumentor` ABC |
| `packages/tracecast-py/tracecast/instrumentors/openai_inst.py` | OpenAI monkey-patch |
| `packages/tracecast-py/tracecast/instrumentors/anthropic_inst.py` | Anthropic monkey-patch |
| `packages/tracecast-py/tracecast/instrumentors/gemini_inst.py` | Google Gemini monkey-patch |
| `packages/tracecast-py/tracecast/instrumentors/langchain_inst.py` | LangChain global callback |
| `packages/tracecast-py/tracecast/instrumentors/llamaindex_inst.py` | LlamaIndex event handler |
| `packages/tracecast-py/tracecast/instrumentors/crewai_inst.py` | CrewAI kickoff patch |
| `packages/tracecast-py/tests/test_instrumentors/test_openai_inst.py` | |
| `packages/tracecast-py/tests/test_instrumentors/test_anthropic_inst.py` | |
| `packages/tracecast-py/tests/test_instrumentors/test_gemini_inst.py` | |
| `packages/tracecast-py/tests/test_instrumentors/test_langchain_inst.py` | |
| `packages/tracecast-py/tests/test_instrumentors/test_llamaindex_inst.py` | |
| `packages/tracecast-py/tests/test_instrumentors/test_crewai_inst.py` | |
| `packages/tracecast-py/tests/test_instrumentors/test_auto_instrument.py` | |
| `packages/tracecast-py/tests/test_dashboard_sessions.py` | |
| `packages/tracecast-py/tests/test_dashboard_projects.py` | |

### Python — Modified Files

| File | Change |
|---|---|
| `packages/tracecast-py/tracecast/__init__.py` | Export `auto_instrument` |
| `packages/tracecast-py/tracecast/dashboard/aggregator.py` | Add `compute_sessions()`, `compute_projects()` |
| `packages/tracecast-py/tracecast/dashboard/router.py` | Add sessions/projects endpoints, update static serving for Vite assets |
| `packages/tracecast-py/tracecast/dashboard/blueprint.py` | Add sessions/projects endpoints, update static serving |
| `packages/tracecast-py/tracecast/dashboard/reader.py` | Add `get_sessions()`, `get_session()`, `get_projects()`, `get_project()` |
| `packages/tracecast-py/tracecast/core/tracer.py` | Auto-fallback DictExporter in `mount()` |
| `packages/tracecast-py/tracecast/core/token_counter.py` | Add `_from_gemini()` extractor |
| `packages/tracecast-py/pyproject.toml` | Add `dashboard` optional deps |

### TypeScript — New Files

| File | Purpose |
|---|---|
| `packages/tracecast-ts/src/instrument.ts` | `autoInstrument()` entry point |
| `packages/tracecast-ts/src/instrumentors/base.ts` | `BaseInstrumentor` interface |
| `packages/tracecast-ts/src/instrumentors/openaiInst.ts` | OpenAI Proxy patch |
| `packages/tracecast-ts/src/instrumentors/anthropicInst.ts` | Anthropic Proxy patch |
| `packages/tracecast-ts/src/instrumentors/geminiInst.ts` | Gemini Proxy patch |
| `packages/tracecast-ts/src/instrumentors/langchainInst.ts` | LangChain global callback |
| `packages/tracecast-ts/tests/instrumentors/openai.test.ts` | |
| `packages/tracecast-ts/tests/instrumentors/anthropic.test.ts` | |
| `packages/tracecast-ts/tests/instrumentors/gemini.test.ts` | |
| `packages/tracecast-ts/tests/instrumentors/langchain.test.ts` | |
| `packages/tracecast-ts/tests/instrumentors/autoInstrument.test.ts` | |
| `packages/tracecast-ts/tests/dashboard/sessions.test.ts` | |
| `packages/tracecast-ts/tests/dashboard/projects.test.ts` | |

### TypeScript — Modified Files

| File | Change |
|---|---|
| `packages/tracecast-ts/src/index.ts` | Export `autoInstrument` |
| `packages/tracecast-ts/src/dashboard/aggregator.ts` | Add `computeSessions()`, `computeProjects()` |
| `packages/tracecast-ts/src/dashboard/router.ts` | Add sessions/projects endpoints, Vite static serving |
| `packages/tracecast-ts/src/dashboard/reader.ts` | Add session/project methods |
| `packages/tracecast-ts/src/core/tracer.ts` | Auto-fallback DictExporter in `mount()` |
| `packages/tracecast-ts/package.json` | Add express peer dep, exports map entries |

### React Dashboard — New Package

| File | Purpose |
|---|---|
| `packages/tracecast-dashboard/package.json` | Vite + React + Recharts config |
| `packages/tracecast-dashboard/vite.config.ts` | Build config, relative base |
| `packages/tracecast-dashboard/tsconfig.json` | |
| `packages/tracecast-dashboard/index.html` | Vite entry |
| `packages/tracecast-dashboard/src/main.tsx` | React root |
| `packages/tracecast-dashboard/src/App.tsx` | Router + Layout |
| `packages/tracecast-dashboard/src/pages/Overview.tsx` | Stat cards + charts |
| `packages/tracecast-dashboard/src/pages/Traces.tsx` | Trace list + filters |
| `packages/tracecast-dashboard/src/pages/TraceDetail.tsx` | Span waterfall |
| `packages/tracecast-dashboard/src/pages/Models.tsx` | Cost/tokens per model |
| `packages/tracecast-dashboard/src/pages/Sessions.tsx` | Group by session_id |
| `packages/tracecast-dashboard/src/pages/Projects.tsx` | Group by project_id |
| `packages/tracecast-dashboard/src/components/Layout.tsx` | Sidebar + header |
| `packages/tracecast-dashboard/src/components/StatCard.tsx` | Metric card |
| `packages/tracecast-dashboard/src/components/TraceTable.tsx` | Sortable table |
| `packages/tracecast-dashboard/src/components/SpanTimeline.tsx` | Waterfall spans |
| `packages/tracecast-dashboard/src/components/Pagination.tsx` | Page controls |
| `packages/tracecast-dashboard/src/components/Filters.tsx` | Filter bar |
| `packages/tracecast-dashboard/src/hooks/useApi.ts` | Fetch wrapper |
| `packages/tracecast-dashboard/src/styles/globals.css` | Dark theme |
| `packages/tracecast-dashboard/scripts/copy-static.sh` | Copy dist to Py/TS |

---

## Task 1: BaseInstrumentor + Instrumentor Registry (Python)

**Files:**
- Create: `packages/tracecast-py/tracecast/instrumentors/__init__.py`
- Create: `packages/tracecast-py/tracecast/instrumentors/base.py`
- Create: `packages/tracecast-py/tracecast/instrument.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/__init__.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_auto_instrument.py`
- Modify: `packages/tracecast-py/tracecast/__init__.py`

- [ ] **Step 1: Write failing test for BaseInstrumentor and auto_instrument**

```python
# packages/tracecast-py/tests/test_instrumentors/test_auto_instrument.py
import pytest
from tracecast.instrumentors.base import BaseInstrumentor
from tracecast.instrument import auto_instrument, _registry, _reset


class FakeInstrumentor(BaseInstrumentor):
    def __init__(self):
        self.patched = False
        self.unpatched = False

    def patch(self) -> None:
        self.patched = True

    def unpatch(self) -> None:
        self.unpatched = True
        self.patched = False

    def is_patched(self) -> bool:
        return self.patched


def test_base_instrumentor_is_abstract():
    with pytest.raises(TypeError):
        BaseInstrumentor()


def test_auto_instrument_calls_patch_on_registered():
    _reset()
    fake = FakeInstrumentor()
    _registry["fake"] = fake
    auto_instrument()
    assert fake.is_patched()
    _reset()


def test_auto_instrument_idempotent():
    _reset()
    fake = FakeInstrumentor()
    _registry["fake"] = fake
    auto_instrument()
    auto_instrument()  # second call should be no-op
    assert fake.is_patched()
    _reset()


def test_auto_instrument_sets_default_tracer():
    _reset()
    from tracecast import Tracer
    from tracecast.decorators import _default_tracer

    tracer = Tracer()
    auto_instrument(tracer)

    from tracecast.decorators import _default_tracer as dt
    assert dt is tracer
    _reset()


def test_auto_instrument_skip_import_error():
    _reset()

    class BadInstrumentor(BaseInstrumentor):
        def patch(self):
            raise ImportError("no such module")
        def unpatch(self):
            pass
        def is_patched(self):
            return False

    _registry["bad"] = BadInstrumentor()
    auto_instrument()  # should not raise
    _reset()
```

- [ ] **Step 2: Create `__init__.py` files**

```python
# packages/tracecast-py/tracecast/instrumentors/__init__.py
from .base import BaseInstrumentor

__all__ = ["BaseInstrumentor"]
```

```python
# packages/tracecast-py/tests/test_instrumentors/__init__.py
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_auto_instrument.py -v`
Expected: ImportError / ModuleNotFoundError because `base.py` and `instrument.py` don't exist yet.

- [ ] **Step 4: Implement BaseInstrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/base.py
from abc import ABC, abstractmethod


class BaseInstrumentor(ABC):
    @abstractmethod
    def patch(self) -> None:
        ...

    @abstractmethod
    def unpatch(self) -> None:
        ...

    @abstractmethod
    def is_patched(self) -> bool:
        ...
```

- [ ] **Step 5: Implement auto_instrument + registry**

```python
# packages/tracecast-py/tracecast/instrument.py
from typing import Dict, Optional
from .instrumentors.base import BaseInstrumentor
from .core.tracer import Tracer
from .decorators import set_default_tracer

_registry: Dict[str, BaseInstrumentor] = {}
_instrumented = False


def auto_instrument(tracer: Optional[Tracer] = None) -> None:
    global _instrumented
    if _instrumented:
        return
    if tracer:
        set_default_tracer(tracer)
    for name, inst in _registry.items():
        try:
            inst.patch()
        except ImportError:
            pass
    _instrumented = True


def _reset() -> None:
    global _instrumented
    for inst in _registry.values():
        try:
            if inst.is_patched():
                inst.unpatch()
        except Exception:
            pass
    _registry.clear()
    _instrumented = False
```

- [ ] **Step 6: Update `__init__.py` to export auto_instrument**

Add to `packages/tracecast-py/tracecast/__init__.py`:
```python
from .instrument import auto_instrument
```

And add `"auto_instrument"` to `__all__`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_auto_instrument.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 8: Run full test suite to check no regressions**

Run: `cd packages/tracecast-py && python -m pytest tests/ -v`
Expected: All existing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add packages/tracecast-py/tracecast/instrumentors/ packages/tracecast-py/tracecast/instrument.py packages/tracecast-py/tracecast/__init__.py packages/tracecast-py/tests/test_instrumentors/
git commit -m "feat: add BaseInstrumentor ABC and auto_instrument() registry"
```

---

## Task 2: OpenAI Instrumentor (Python)

**Files:**
- Create: `packages/tracecast-py/tracecast/instrumentors/openai_inst.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_openai_inst.py`

- [ ] **Step 1: Write failing test**

```python
# packages/tracecast-py/tests/test_instrumentors/test_openai_inst.py
import sys
import types
import pytest
from unittest.mock import MagicMock
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_openai():
    """Create a fake openai module structure matching openai SDK."""
    openai = types.ModuleType("openai")
    resources = types.ModuleType("openai.resources")
    chat = types.ModuleType("openai.resources.chat")
    completions_mod = types.ModuleType("openai.resources.chat.completions")

    class Completions:
        def create(self, **kwargs):
            response = MagicMock()
            response.usage.prompt_tokens = 100
            response.usage.completion_tokens = 50
            response.usage.prompt_tokens_details.cached_tokens = 0
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Hello!"
            return response

    completions_mod.Completions = Completions
    chat.completions = completions_mod
    resources.chat = chat
    openai.resources = resources

    sys.modules["openai"] = openai
    sys.modules["openai.resources"] = resources
    sys.modules["openai.resources.chat"] = chat
    sys.modules["openai.resources.chat.completions"] = completions_mod
    return openai, Completions


def _cleanup_fake_openai():
    for k in list(sys.modules):
        if k.startswith("openai"):
            del sys.modules[k]


class TestOpenAIInstrumentor:
    def setup_method(self):
        self.openai, self.Completions = _make_fake_openai()

    def teardown_method(self):
        _cleanup_fake_openai()

    def test_patch_replaces_create(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        original = self.Completions.create
        inst = OpenAIInstrumentor()
        inst.patch()
        assert self.Completions.create is not original
        inst.unpatch()
        assert self.Completions.create is original

    def test_is_patched(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        assert not inst.is_patched()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()
        assert not inst.is_patched()

    def test_no_trace_active_calls_original(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        inst.patch()
        client = self.Completions()
        response = client.create(model="gpt-4o", messages=[])
        assert response.choices[0].message.content == "Hello!"
        inst.unpatch()

    def test_trace_active_captures_span(self):
        from tracecast.instrumentors.openai_inst import OpenAIInstrumentor
        inst = OpenAIInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = self.Completions()

        with tracer.trace("test-trace"):
            response = client.create(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

        assert len(exporter.traces) == 1
        trace = exporter.traces[0]
        assert len(trace["spans"]) == 1
        span = trace["spans"][0]
        assert span["type"] == "llm"
        assert span["model"] == "gpt-4o"
        assert span["tokens_in"] == 100
        assert span["tokens_out"] == 50
        assert span["cost_usd"] > 0
        inst.unpatch()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_openai_inst.py -v`
Expected: ImportError on `openai_inst`.

- [ ] **Step 3: Implement OpenAI instrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/openai_inst.py
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor


class OpenAIInstrumentor(BaseInstrumentor):
    _original_create: Optional[Any] = None
    _original_acreate: Optional[Any] = None
    _patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        import openai.resources.chat.completions as mod

        self._original_create = mod.Completions.create
        self_ref = self

        def patched_create(client_self, **kwargs):
            return self_ref._intercept(client_self, kwargs, self_ref._original_create)

        mod.Completions.create = patched_create

        if hasattr(mod.Completions, "acreate"):
            self._original_acreate = mod.Completions.acreate

            async def patched_acreate(client_self, **kwargs):
                return await self_ref._async_intercept(client_self, kwargs, self_ref._original_acreate)

            mod.Completions.acreate = patched_acreate

        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import openai.resources.chat.completions as mod
        mod.Completions.create = self._original_create
        if self._original_acreate:
            mod.Completions.acreate = self._original_acreate
        self._original_create = None
        self._original_acreate = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, client_self, kwargs, original_fn):
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(client_self, **kwargs)
        return self._capture(client_self, kwargs, original_fn, trace)

    async def _async_intercept(self, client_self, kwargs, original_fn):
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return await original_fn(client_self, **kwargs)
        return self._capture(client_self, kwargs, original_fn, trace)

    def _capture(self, client_self, kwargs, original_fn, trace):
        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content, extract_input_text
        from ..core.cost_calculator import calculate_cost

        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, "openai")

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=input_text,
        )

        try:
            response = original_fn(client_self, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "openai")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached)
        span.output = extract_content(response, "openai")
        trace.spans.append(span)

        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_openai_inst.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/tracecast-py/tracecast/instrumentors/openai_inst.py packages/tracecast-py/tests/test_instrumentors/test_openai_inst.py
git commit -m "feat: add OpenAI instrumentor with monkey-patching"
```

---

## Task 3: Anthropic Instrumentor (Python)

**Files:**
- Create: `packages/tracecast-py/tracecast/instrumentors/anthropic_inst.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_anthropic_inst.py`

- [ ] **Step 1: Write failing test**

```python
# packages/tracecast-py/tests/test_instrumentors/test_anthropic_inst.py
import sys
import types
import pytest
from unittest.mock import MagicMock
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_anthropic():
    anthropic = types.ModuleType("anthropic")
    resources = types.ModuleType("anthropic.resources")
    messages_mod = types.ModuleType("anthropic.resources.messages")

    class Messages:
        def create(self, **kwargs):
            response = MagicMock()
            response.usage.input_tokens = 200
            response.usage.output_tokens = 80
            response.usage.cache_read_input_tokens = 0
            response.content = [MagicMock(type="text", text="Response text")]
            return response

    messages_mod.Messages = Messages
    resources.messages = messages_mod
    anthropic.resources = resources

    sys.modules["anthropic"] = anthropic
    sys.modules["anthropic.resources"] = resources
    sys.modules["anthropic.resources.messages"] = messages_mod
    return anthropic, Messages


def _cleanup_fake_anthropic():
    for k in list(sys.modules):
        if k.startswith("anthropic"):
            del sys.modules[k]


class TestAnthropicInstrumentor:
    def setup_method(self):
        self.anthropic, self.Messages = _make_fake_anthropic()

    def teardown_method(self):
        _cleanup_fake_anthropic()

    def test_patch_and_unpatch(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        original = self.Messages.create
        inst = AnthropicInstrumentor()
        inst.patch()
        assert self.Messages.create is not original
        assert inst.is_patched()
        inst.unpatch()
        assert self.Messages.create is original
        assert not inst.is_patched()

    def test_no_trace_calls_original(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        inst.patch()
        client = self.Messages()
        response = client.create(model="claude-sonnet-4-6", messages=[])
        assert response.content[0].text == "Response text"
        inst.unpatch()

    def test_trace_active_captures_span(self):
        from tracecast.instrumentors.anthropic_inst import AnthropicInstrumentor
        inst = AnthropicInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        client = self.Messages()

        with tracer.trace("test-anthropic"):
            client.create(model="claude-sonnet-4-6", messages=[{"role": "user", "content": "Hi"}])

        trace = exporter.traces[0]
        span = trace["spans"][0]
        assert span["type"] == "llm"
        assert span["model"] == "claude-sonnet-4-6"
        assert span["tokens_in"] == 200
        assert span["tokens_out"] == 80
        inst.unpatch()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_anthropic_inst.py -v`

- [ ] **Step 3: Implement Anthropic instrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/anthropic_inst.py
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor


class AnthropicInstrumentor(BaseInstrumentor):
    _original_create: Optional[Any] = None
    _patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        import anthropic.resources.messages as mod

        self._original_create = mod.Messages.create
        self_ref = self

        def patched_create(client_self, **kwargs):
            return self_ref._intercept(client_self, kwargs, self_ref._original_create)

        mod.Messages.create = patched_create
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import anthropic.resources.messages as mod
        mod.Messages.create = self._original_create
        self._original_create = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, client_self, kwargs, original_fn):
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(client_self, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content, extract_input_text
        from ..core.cost_calculator import calculate_cost

        model = kwargs.get("model", "unknown")
        input_text = extract_input_text(kwargs, "anthropic")

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name=f"llm:{model}",
            model=model,
            started_at=datetime.now(timezone.utc),
            input=input_text,
        )

        try:
            response = original_fn(client_self, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "anthropic")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached)
        span.output = extract_content(response, "anthropic")
        trace.spans.append(span)

        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_anthropic_inst.py -v`

- [ ] **Step 5: Commit**

```bash
git add packages/tracecast-py/tracecast/instrumentors/anthropic_inst.py packages/tracecast-py/tests/test_instrumentors/test_anthropic_inst.py
git commit -m "feat: add Anthropic instrumentor with monkey-patching"
```

---

## Task 4: Gemini Instrumentor (Python)

**Files:**
- Create: `packages/tracecast-py/tracecast/instrumentors/gemini_inst.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_gemini_inst.py`
- Modify: `packages/tracecast-py/tracecast/core/token_counter.py`

- [ ] **Step 1: Add `_from_gemini` to token_counter.py**

Add to `packages/tracecast-py/tracecast/core/token_counter.py` — update the `extractors` dict in `extract_tokens()` to include `"gemini": _from_gemini`, and add:

```python
def _from_gemini(r) -> dict:
    usage = getattr(r, "usage_metadata", None)
    if usage is None:
        return {"input": 0, "output": 0, "cached": 0}
    return {
        "input": getattr(usage, "prompt_token_count", 0),
        "output": getattr(usage, "candidates_token_count", 0),
        "cached": getattr(usage, "cached_content_token_count", 0) or 0,
    }
```

Also add `"gemini"` content extractor to `extract_content()`:

```python
if provider == "gemini":
    try:
        candidates = getattr(response, "candidates", []) or []
        if candidates:
            parts = getattr(candidates[0], "content", None)
            if parts:
                text_parts = getattr(parts, "parts", []) or []
                return "".join(getattr(p, "text", "") for p in text_parts)
    except Exception:
        pass
    return None
```

- [ ] **Step 2: Write failing test for Gemini instrumentor**

```python
# packages/tracecast-py/tests/test_instrumentors/test_gemini_inst.py
import sys
import types
from unittest.mock import MagicMock
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


def _make_fake_gemini():
    google = types.ModuleType("google")
    genai = types.ModuleType("google.generativeai")

    class GenerativeModel:
        def __init__(self, model_name="gemini-2.5-flash"):
            self.model_name = model_name

        def generate_content(self, contents, **kwargs):
            response = MagicMock()
            response.usage_metadata.prompt_token_count = 150
            response.usage_metadata.candidates_token_count = 60
            response.usage_metadata.cached_content_token_count = 0
            response.candidates = [MagicMock()]
            response.candidates[0].content.parts = [MagicMock(text="Gemini response")]
            return response

    genai.GenerativeModel = GenerativeModel
    google.generativeai = genai

    sys.modules["google"] = google
    sys.modules["google.generativeai"] = genai
    return genai, GenerativeModel


def _cleanup_fake_gemini():
    for k in list(sys.modules):
        if k.startswith("google"):
            del sys.modules[k]


class TestGeminiInstrumentor:
    def setup_method(self):
        self.genai, self.GenerativeModel = _make_fake_gemini()

    def teardown_method(self):
        _cleanup_fake_gemini()

    def test_patch_and_unpatch(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor
        original = self.GenerativeModel.generate_content
        inst = GeminiInstrumentor()
        inst.patch()
        assert self.GenerativeModel.generate_content is not original
        inst.unpatch()
        assert self.GenerativeModel.generate_content is original

    def test_trace_active_captures_span(self):
        from tracecast.instrumentors.gemini_inst import GeminiInstrumentor
        inst = GeminiInstrumentor()
        inst.patch()

        exporter = DictExporter()
        tracer = Tracer(exporters=[exporter])
        model = self.GenerativeModel("gemini-2.5-flash")

        with tracer.trace("test-gemini"):
            model.generate_content("Hello Gemini")

        trace = exporter.traces[0]
        span = trace["spans"][0]
        assert span["type"] == "llm"
        assert span["model"] == "gemini-2.5-flash"
        assert span["tokens_in"] == 150
        assert span["tokens_out"] == 60
        inst.unpatch()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_gemini_inst.py -v`

- [ ] **Step 4: Implement Gemini instrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/gemini_inst.py
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor


class GeminiInstrumentor(BaseInstrumentor):
    _original_generate: Optional[Any] = None
    _patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        import google.generativeai as genai

        self._original_generate = genai.GenerativeModel.generate_content
        self_ref = self

        def patched_generate(model_self, contents, **kwargs):
            return self_ref._intercept(model_self, contents, kwargs, self_ref._original_generate)

        genai.GenerativeModel.generate_content = patched_generate
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import google.generativeai as genai
        genai.GenerativeModel.generate_content = self._original_generate
        self._original_generate = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, model_self, contents, kwargs, original_fn):
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return original_fn(model_self, contents, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.token_counter import extract_tokens, extract_content
        from ..core.cost_calculator import calculate_cost

        model_name = getattr(model_self, "model_name", "unknown")

        input_text = contents if isinstance(contents, str) else str(contents)

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.LLM,
            name=f"llm:{model_name}",
            model=model_name,
            started_at=datetime.now(timezone.utc),
            input=input_text,
        )

        try:
            response = original_fn(model_self, contents, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        tokens = extract_tokens(response, "gemini")
        span.tokens_in = int(tokens["input"])
        span.tokens_out = int(tokens["output"])
        span.tokens_in_cached = int(tokens.get("cached", 0))
        span.cost_usd = calculate_cost(model_name, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached)
        span.output = extract_content(response, "gemini")
        trace.spans.append(span)

        return response
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_gemini_inst.py -v`

- [ ] **Step 6: Commit**

```bash
git add packages/tracecast-py/tracecast/instrumentors/gemini_inst.py packages/tracecast-py/tests/test_instrumentors/test_gemini_inst.py packages/tracecast-py/tracecast/core/token_counter.py
git commit -m "feat: add Gemini instrumentor and token extractor"
```

---

## Task 5: LangChain Instrumentor (Python)

**Files:**
- Create: `packages/tracecast-py/tracecast/instrumentors/langchain_inst.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_langchain_inst.py`

- [ ] **Step 1: Write failing test**

```python
# packages/tracecast-py/tests/test_instrumentors/test_langchain_inst.py
import pytest
from unittest.mock import MagicMock, patch
from tracecast import Tracer
from tracecast.exporters.dict_exporter import DictExporter


class TestLangChainInstrumentor:
    def test_patch_registers_global_handler(self):
        with patch.dict("sys.modules", {"langchain_core": MagicMock(), "langchain_core.callbacks": MagicMock(), "langchain_core.callbacks.base": MagicMock(), "langchain_core.callbacks.manager": MagicMock()}):
            from tracecast.instrumentors.langchain_inst import LangChainInstrumentor
            import sys
            cb_manager = sys.modules["langchain_core.callbacks.manager"]
            cb_manager.configure = MagicMock()

            inst = LangChainInstrumentor()
            inst.patch()
            assert inst.is_patched()
            inst.unpatch()
            assert not inst.is_patched()

    def test_import_error_skipped(self):
        from tracecast.instrumentors.langchain_inst import LangChainInstrumentor
        inst = LangChainInstrumentor()
        # If langchain_core not installed, patch raises ImportError
        # That's expected — auto_instrument catches it
        try:
            inst.patch()
        except ImportError:
            pass
```

- [ ] **Step 2: Implement LangChain instrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/langchain_inst.py
from typing import Optional
from .base import BaseInstrumentor


class LangChainInstrumentor(BaseInstrumentor):
    _handler: Optional[object] = None
    _patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        from langchain_core.callbacks.manager import configure as lc_configure
        from ..integrations.langchain import TraceCastCallback
        from ..decorators import _default_tracer
        from ..core.tracer import Tracer

        tracer = _default_tracer or Tracer()
        self._handler = TraceCastCallback(tracer)

        import langchain_core.globals as lc_globals
        handlers = getattr(lc_globals, "_global_callbacks", []) or []
        handlers.append(self._handler)
        lc_globals._global_callbacks = handlers

        self._patched = True

    def unpatch(self) -> None:
        if not self._patched or self._handler is None:
            return
        try:
            import langchain_core.globals as lc_globals
            handlers = getattr(lc_globals, "_global_callbacks", []) or []
            lc_globals._global_callbacks = [h for h in handlers if h is not self._handler]
        except ImportError:
            pass
        self._handler = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched
```

- [ ] **Step 3: Run test**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/test_langchain_inst.py -v`

- [ ] **Step 4: Commit**

```bash
git add packages/tracecast-py/tracecast/instrumentors/langchain_inst.py packages/tracecast-py/tests/test_instrumentors/test_langchain_inst.py
git commit -m "feat: add LangChain instrumentor with global callback handler"
```

---

## Task 6: LlamaIndex + CrewAI Instrumentors (Python)

**Files:**
- Create: `packages/tracecast-py/tracecast/instrumentors/llamaindex_inst.py`
- Create: `packages/tracecast-py/tracecast/instrumentors/crewai_inst.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_llamaindex_inst.py`
- Create: `packages/tracecast-py/tests/test_instrumentors/test_crewai_inst.py`

- [ ] **Step 1: Write LlamaIndex test**

```python
# packages/tracecast-py/tests/test_instrumentors/test_llamaindex_inst.py
import sys
import types
from unittest.mock import MagicMock


def test_llamaindex_patch_and_unpatch():
    # Create fake llama_index module
    llama = types.ModuleType("llama_index")
    core = types.ModuleType("llama_index.core")
    instrumentation = types.ModuleType("llama_index.core.instrumentation")
    dispatcher = MagicMock()
    instrumentation.get_dispatcher = MagicMock(return_value=dispatcher)
    core.instrumentation = instrumentation
    llama.core = core

    sys.modules["llama_index"] = llama
    sys.modules["llama_index.core"] = core
    sys.modules["llama_index.core.instrumentation"] = instrumentation

    from tracecast.instrumentors.llamaindex_inst import LlamaIndexInstrumentor
    inst = LlamaIndexInstrumentor()
    inst.patch()
    assert inst.is_patched()
    dispatcher.add_span_handler.assert_called_once()

    inst.unpatch()
    assert not inst.is_patched()

    for k in list(sys.modules):
        if k.startswith("llama_index"):
            del sys.modules[k]
```

- [ ] **Step 2: Implement LlamaIndex instrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/llamaindex_inst.py
from typing import Optional
from .base import BaseInstrumentor


class LlamaIndexInstrumentor(BaseInstrumentor):
    _handler: Optional[object] = None
    _patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        from llama_index.core.instrumentation import get_dispatcher

        dispatcher = get_dispatcher()

        from ._llamaindex_handler import TraceCastSpanHandler
        self._handler = TraceCastSpanHandler()
        dispatcher.add_span_handler(self._handler)
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        try:
            from llama_index.core.instrumentation import get_dispatcher
            dispatcher = get_dispatcher()
            handlers = getattr(dispatcher, "span_handlers", [])
            for i, h in enumerate(handlers):
                if h is self._handler:
                    handlers.pop(i)
                    break
        except ImportError:
            pass
        self._handler = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched
```

```python
# packages/tracecast-py/tracecast/instrumentors/_llamaindex_handler.py
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


class TraceCastSpanHandler:
    """LlamaIndex span handler that captures LLM spans into active TraceCast trace."""

    def __init__(self):
        self._open_spans: dict[str, Any] = {}

    def new_span(self, id_: str, bound_args: Any, instance: Any = None, parent_span_id: Optional[str] = None, tags: Optional[dict] = None, **kwargs) -> Optional[str]:
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            return None

        from ..models.span import Span, SpanType
        span = Span(
            span_id=id_ or str(uuid.uuid4()),
            type=SpanType.LLM,
            name=type(instance).__name__ if instance else "llama_index",
            started_at=datetime.now(timezone.utc),
        )
        self._open_spans[id_] = (span, trace)
        return id_

    def prepare_to_exit_span(self, id_: str, bound_args: Any = None, instance: Any = None, result: Any = None, **kwargs) -> None:
        entry = self._open_spans.pop(id_, None)
        if entry is None:
            return
        span, trace = entry
        span.finished_at = datetime.now(timezone.utc)

        if result is not None:
            usage = getattr(result, "raw", None)
            if usage:
                from ..core.token_counter import extract_tokens, extract_content
                from ..core.cost_calculator import calculate_cost

                model = getattr(usage, "model", None) or "unknown"
                span.model = model
                span.name = f"llm:{model}"

                tokens = extract_tokens(usage, "openai")
                span.tokens_in = int(tokens["input"])
                span.tokens_out = int(tokens["output"])
                span.tokens_in_cached = int(tokens.get("cached", 0))
                span.cost_usd = calculate_cost(model, span.tokens_in, span.tokens_out, tokens_in_cached=span.tokens_in_cached)
                span.output = extract_content(usage, "openai")

        trace.spans.append(span)

    def prepare_to_drop_span(self, id_: str, bound_args: Any = None, instance: Any = None, err: Optional[Exception] = None, **kwargs) -> None:
        entry = self._open_spans.pop(id_, None)
        if entry is None:
            return
        span, trace = entry
        span.finished_at = datetime.now(timezone.utc)
        span.metadata["_error"] = str(err) if err else "dropped"
        trace.spans.append(span)
```

- [ ] **Step 3: Write CrewAI test**

```python
# packages/tracecast-py/tests/test_instrumentors/test_crewai_inst.py
import sys
import types
from unittest.mock import MagicMock


def test_crewai_patch_and_unpatch():
    crewai = types.ModuleType("crewai")

    class Crew:
        def kickoff(self, inputs=None):
            result = MagicMock()
            result.token_usage = MagicMock()
            result.token_usage.total_tokens = 500
            result.token_usage.prompt_tokens = 300
            result.token_usage.completion_tokens = 200
            return result

    crewai.Crew = Crew
    sys.modules["crewai"] = crewai

    from tracecast.instrumentors.crewai_inst import CrewAIInstrumentor
    original = Crew.kickoff
    inst = CrewAIInstrumentor()
    inst.patch()
    assert inst.is_patched()
    assert Crew.kickoff is not original
    inst.unpatch()
    assert Crew.kickoff is original
    assert not inst.is_patched()

    del sys.modules["crewai"]
```

- [ ] **Step 4: Implement CrewAI instrumentor**

```python
# packages/tracecast-py/tracecast/instrumentors/crewai_inst.py
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from .base import BaseInstrumentor


class CrewAIInstrumentor(BaseInstrumentor):
    _original_kickoff: Optional[Any] = None
    _patched: bool = False

    def patch(self) -> None:
        if self._patched:
            return
        import crewai

        self._original_kickoff = crewai.Crew.kickoff
        self_ref = self

        def patched_kickoff(crew_self, inputs=None, **kwargs):
            return self_ref._intercept(crew_self, inputs, kwargs, self_ref._original_kickoff)

        crewai.Crew.kickoff = patched_kickoff
        self._patched = True

    def unpatch(self) -> None:
        if not self._patched:
            return
        import crewai
        crewai.Crew.kickoff = self._original_kickoff
        self._original_kickoff = None
        self._patched = False

    def is_patched(self) -> bool:
        return self._patched

    def _intercept(self, crew_self, inputs, kwargs, original_fn):
        from ..core.tracer import Tracer
        trace = Tracer.current()
        if trace is None:
            if inputs is not None:
                return original_fn(crew_self, inputs=inputs, **kwargs)
            return original_fn(crew_self, **kwargs)

        from ..models.span import Span, SpanType
        from ..core.cost_calculator import calculate_cost

        span = Span(
            span_id=str(uuid.uuid4()),
            type=SpanType.AGENT,
            name="crewai:kickoff",
            started_at=datetime.now(timezone.utc),
        )

        try:
            if inputs is not None:
                result = original_fn(crew_self, inputs=inputs, **kwargs)
            else:
                result = original_fn(crew_self, **kwargs)
        except Exception as exc:
            span.finished_at = datetime.now(timezone.utc)
            span.metadata["_error"] = str(exc)
            trace.spans.append(span)
            raise

        span.finished_at = datetime.now(timezone.utc)
        usage = getattr(result, "token_usage", None)
        if usage:
            span.tokens_in = getattr(usage, "prompt_tokens", 0) or 0
            span.tokens_out = getattr(usage, "completion_tokens", 0) or 0
            span.metadata["total_tokens"] = getattr(usage, "total_tokens", 0) or 0

        if hasattr(result, "raw"):
            span.output = str(result.raw)[:2000]

        trace.spans.append(span)
        return result
```

- [ ] **Step 5: Run all instrumentor tests**

Run: `cd packages/tracecast-py && python -m pytest tests/test_instrumentors/ -v`

- [ ] **Step 6: Register all instrumentors in `instrumentors/__init__.py`**

Update `packages/tracecast-py/tracecast/instrumentors/__init__.py`:

```python
from .base import BaseInstrumentor
from ..instrument import _registry

def _register_all():
    instrumentors = [
        ("openai", "openai_inst", "OpenAIInstrumentor"),
        ("anthropic", "anthropic_inst", "AnthropicInstrumentor"),
        ("gemini", "gemini_inst", "GeminiInstrumentor"),
        ("langchain", "langchain_inst", "LangChainInstrumentor"),
        ("llamaindex", "llamaindex_inst", "LlamaIndexInstrumentor"),
        ("crewai", "crewai_inst", "CrewAIInstrumentor"),
    ]
    for name, module_name, class_name in instrumentors:
        try:
            import importlib
            mod = importlib.import_module(f".{module_name}", package=__name__)
            cls = getattr(mod, class_name)
            _registry[name] = cls()
        except Exception:
            pass

_register_all()

__all__ = ["BaseInstrumentor"]
```

- [ ] **Step 7: Run full Python test suite**

Run: `cd packages/tracecast-py && python -m pytest tests/ -v`

- [ ] **Step 8: Commit**

```bash
git add packages/tracecast-py/tracecast/instrumentors/ packages/tracecast-py/tests/test_instrumentors/
git commit -m "feat: add LlamaIndex, CrewAI instrumentors and register all in auto_instrument"
```

---

## Task 7: Sessions + Projects Backend API (Python)

**Files:**
- Modify: `packages/tracecast-py/tracecast/dashboard/aggregator.py`
- Modify: `packages/tracecast-py/tracecast/dashboard/reader.py`
- Modify: `packages/tracecast-py/tracecast/dashboard/router.py`
- Modify: `packages/tracecast-py/tracecast/dashboard/blueprint.py`
- Create: `packages/tracecast-py/tests/test_dashboard_sessions.py`
- Create: `packages/tracecast-py/tests/test_dashboard_projects.py`

- [ ] **Step 1: Write failing test for session/project aggregation**

```python
# packages/tracecast-py/tests/test_dashboard_sessions.py
from datetime import datetime, timezone
from tracecast.models.trace import Trace
from tracecast.models.span import Span, SpanType
from tracecast.dashboard.aggregator import compute_sessions, compute_projects


def _make_trace(trace_id, name, session_id=None, project_id=None, cost=0.01, tokens_in=100, tokens_out=50):
    t = Trace(
        trace_id=trace_id,
        name=name,
        started_at=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 20, 10, 1, tzinfo=timezone.utc),
        session_id=session_id,
        project_id=project_id,
        total_tokens_in=tokens_in,
        total_tokens_out=tokens_out,
        total_tokens=tokens_in + tokens_out,
        cost_usd=cost,
        latency_ms=60000,
    )
    return t


def test_compute_sessions_groups_by_session_id():
    traces = [
        _make_trace("t1", "chat1", session_id="s1", cost=0.01),
        _make_trace("t2", "chat2", session_id="s1", cost=0.02),
        _make_trace("t3", "chat3", session_id="s2", cost=0.05),
        _make_trace("t4", "chat4", session_id=None, cost=0.03),
    ]
    sessions = compute_sessions(traces)
    assert len(sessions) == 2
    s1 = next(s for s in sessions if s["session_id"] == "s1")
    assert s1["trace_count"] == 2
    assert abs(s1["total_cost_usd"] - 0.03) < 0.001
    assert s1["total_tokens"] == 300


def test_compute_projects_groups_by_project_id():
    traces = [
        _make_trace("t1", "chat1", project_id="p1", cost=0.01),
        _make_trace("t2", "chat2", project_id="p1", cost=0.02),
        _make_trace("t3", "chat3", project_id="p2", cost=0.05),
    ]
    projects = compute_projects(traces)
    assert len(projects) == 2
    p1 = next(p for p in projects if p["project_id"] == "p1")
    assert p1["trace_count"] == 2
    assert abs(p1["total_cost_usd"] - 0.03) < 0.001
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd packages/tracecast-py && python -m pytest tests/test_dashboard_sessions.py -v`

- [ ] **Step 3: Implement `compute_sessions` and `compute_projects` in aggregator.py**

Add to `packages/tracecast-py/tracecast/dashboard/aggregator.py`:

```python
def compute_sessions(traces: List[Trace]) -> list:
    groups: dict[str, dict] = {}
    for t in traces:
        sid = t.session_id
        if not sid:
            continue
        if sid not in groups:
            groups[sid] = {
                "session_id": sid,
                "trace_count": 0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "first_trace_at": t.started_at.isoformat(),
                "last_trace_at": t.started_at.isoformat(),
            }
        g = groups[sid]
        g["trace_count"] += 1
        g["total_cost_usd"] += t.cost_usd
        g["total_tokens"] += t.total_tokens
        g["total_tokens_in"] += t.total_tokens_in
        g["total_tokens_out"] += t.total_tokens_out
        if t.started_at.isoformat() < g["first_trace_at"]:
            g["first_trace_at"] = t.started_at.isoformat()
        if t.started_at.isoformat() > g["last_trace_at"]:
            g["last_trace_at"] = t.started_at.isoformat()
    result = sorted(groups.values(), key=lambda x: x["last_trace_at"], reverse=True)
    for r in result:
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
    return result


def compute_projects(traces: List[Trace]) -> list:
    groups: dict[str, dict] = {}
    for t in traces:
        pid = t.project_id
        if not pid:
            continue
        if pid not in groups:
            groups[pid] = {
                "project_id": pid,
                "trace_count": 0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "first_trace_at": t.started_at.isoformat(),
                "last_trace_at": t.started_at.isoformat(),
            }
        g = groups[pid]
        g["trace_count"] += 1
        g["total_cost_usd"] += t.cost_usd
        g["total_tokens"] += t.total_tokens
        g["total_tokens_in"] += t.total_tokens_in
        g["total_tokens_out"] += t.total_tokens_out
        if t.started_at.isoformat() < g["first_trace_at"]:
            g["first_trace_at"] = t.started_at.isoformat()
        if t.started_at.isoformat() > g["last_trace_at"]:
            g["last_trace_at"] = t.started_at.isoformat()
    result = sorted(groups.values(), key=lambda x: x["last_trace_at"], reverse=True)
    for r in result:
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/tracecast-py && python -m pytest tests/test_dashboard_sessions.py -v`

- [ ] **Step 5: Add reader methods**

Add to `packages/tracecast-py/tracecast/dashboard/reader.py` in `TraceReader`:

```python
def get_sessions(self) -> list:
    from .aggregator import compute_sessions
    return compute_sessions(self.get_traces())

def get_session(self, session_id: str):
    return [t for t in self.get_traces() if t.session_id == session_id]

def get_projects(self) -> list:
    from .aggregator import compute_projects
    return compute_projects(self.get_traces())

def get_project(self, project_id: str):
    return [t for t in self.get_traces() if t.project_id == project_id]
```

- [ ] **Step 6: Add router endpoints (FastAPI)**

Add to `packages/tracecast-py/tracecast/dashboard/router.py` inside `_make_router()`:

```python
@router.get("/api/sessions")
def api_sessions():
    return {"sessions": reader.get_sessions(), "total": len(reader.get_sessions())}

@router.get("/api/sessions/{session_id}")
def api_session_detail(session_id: str):
    traces = reader.get_session(session_id)
    if not traces:
        raise HTTPException(status_code=404, detail="Session not found")
    total_cost = sum(t.cost_usd for t in traces)
    total_tokens = sum(t.total_tokens for t in traces)
    return {
        "session_id": session_id,
        "traces": [_trace_summary_from_trace(t) for t in traces],
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
    }

@router.get("/api/projects")
def api_projects():
    return {"projects": reader.get_projects(), "total": len(reader.get_projects())}

@router.get("/api/projects/{project_id}")
def api_project_detail(project_id: str):
    traces = reader.get_project(project_id)
    if not traces:
        raise HTTPException(status_code=404, detail="Project not found")
    total_cost = sum(t.cost_usd for t in traces)
    total_tokens = sum(t.total_tokens for t in traces)
    return {
        "project_id": project_id,
        "traces": [_trace_summary_from_trace(t) for t in traces],
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
    }
```

Also add a helper inside `router.py` (or import `_trace_summary` from aggregator):

```python
def _trace_summary_from_trace(t):
    return {
        "trace_id": t.trace_id,
        "name": t.name,
        "started_at": t.started_at.isoformat(),
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "cost_usd": t.cost_usd,
        "total_tokens": t.total_tokens,
        "latency_ms": t.latency_ms,
        "span_count": len(t.spans),
    }
```

- [ ] **Step 7: Add Flask blueprint endpoints**

Add equivalent endpoints to `packages/tracecast-py/tracecast/dashboard/blueprint.py` inside `_make_blueprint()`:

```python
@bp.route("/api/sessions")
def api_sessions():
    return jsonify({"sessions": reader.get_sessions(), "total": len(reader.get_sessions())})

@bp.route("/api/sessions/<session_id>")
def api_session_detail(session_id):
    traces = reader.get_session(session_id)
    if not traces:
        return jsonify({"error": "Session not found"}), 404
    total_cost = sum(t.cost_usd for t in traces)
    total_tokens = sum(t.total_tokens for t in traces)
    return jsonify({
        "session_id": session_id,
        "traces": [{"trace_id": t.trace_id, "name": t.name, "cost_usd": t.cost_usd, "total_tokens": t.total_tokens} for t in traces],
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
    })

@bp.route("/api/projects")
def api_projects():
    return jsonify({"projects": reader.get_projects(), "total": len(reader.get_projects())})

@bp.route("/api/projects/<project_id>")
def api_project_detail(project_id):
    traces = reader.get_project(project_id)
    if not traces:
        return jsonify({"error": "Project not found"}), 404
    total_cost = sum(t.cost_usd for t in traces)
    total_tokens = sum(t.total_tokens for t in traces)
    return jsonify({
        "project_id": project_id,
        "traces": [{"trace_id": t.trace_id, "name": t.name, "cost_usd": t.cost_usd, "total_tokens": t.total_tokens} for t in traces],
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
    })
```

- [ ] **Step 8: Update static serving for Vite assets**

In `router.py`, add after existing static route:

```python
@router.get("/assets/{path:path}")
def static_assets(path: str):
    fp = STATIC_DIR / "assets" / path
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return Response(content=fp.read_bytes(), media_type=_mime(path))

@router.get("/{path:path}")
def spa_fallback(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404)
```

- [ ] **Step 9: Run full test suite**

Run: `cd packages/tracecast-py && python -m pytest tests/ -v`

- [ ] **Step 10: Commit**

```bash
git add packages/tracecast-py/tracecast/dashboard/ packages/tracecast-py/tests/test_dashboard_sessions.py
git commit -m "feat: add sessions/projects API endpoints and aggregation"
```

---

## Task 8: DictExporter Auto-Fallback in mount() (Python)

**Files:**
- Modify: `packages/tracecast-py/tracecast/core/tracer.py`

- [ ] **Step 1: Update mount() to auto-create DictExporter**

In `packages/tracecast-py/tracecast/core/tracer.py`, add at the top of `mount()`:

```python
def mount(self, app, prefix="/tracecast", read_only=True, auth=None, max_traces=500):
    if not self.exporters:
        from ..exporters.dict_exporter import DictExporter
        import warnings
        self.exporters = [DictExporter()]
        warnings.warn(
            "TraceCast: No exporter configured. Using in-memory storage. "
            "Data will be lost on restart. Configure a persistent exporter "
            "(JsonFileExporter, MongoExporter, PostgresExporter) for production.",
            stacklevel=2,
        )
    # rest of existing mount logic...
```

- [ ] **Step 2: Run full test suite**

Run: `cd packages/tracecast-py && python -m pytest tests/ -v`

- [ ] **Step 3: Commit**

```bash
git add packages/tracecast-py/tracecast/core/tracer.py
git commit -m "feat: auto-fallback DictExporter in mount() with warning"
```

---

## Task 9: TypeScript Instrumentors

**Files:**
- Create: `packages/tracecast-ts/src/instrument.ts`
- Create: `packages/tracecast-ts/src/instrumentors/base.ts`
- Create: `packages/tracecast-ts/src/instrumentors/openaiInst.ts`
- Create: `packages/tracecast-ts/src/instrumentors/anthropicInst.ts`
- Create: `packages/tracecast-ts/src/instrumentors/geminiInst.ts`
- Create: `packages/tracecast-ts/src/instrumentors/langchainInst.ts`
- Create: `packages/tracecast-ts/tests/instrumentors/openai.test.ts`
- Create: `packages/tracecast-ts/tests/instrumentors/autoInstrument.test.ts`
- Modify: `packages/tracecast-ts/src/index.ts`

- [ ] **Step 1: Create base interface and autoInstrument**

```typescript
// packages/tracecast-ts/src/instrumentors/base.ts
export interface BaseInstrumentor {
  patch(): void;
  unpatch(): void;
  isPatched(): boolean;
}
```

```typescript
// packages/tracecast-ts/src/instrument.ts
import { Tracer } from "./core/tracer";
import { setDefaultTracer } from "./integrations/llm";
import { BaseInstrumentor } from "./instrumentors/base";

const registry: Map<string, BaseInstrumentor> = new Map();
let instrumented = false;

export function autoInstrument(tracer?: Tracer): void {
  if (instrumented) return;
  if (tracer) setDefaultTracer(tracer);

  for (const [name, inst] of registry) {
    try {
      inst.patch();
    } catch {
      // SDK not installed, skip
    }
  }
  instrumented = true;
}

export function _resetInstrument(): void {
  for (const inst of registry.values()) {
    try {
      if (inst.isPatched()) inst.unpatch();
    } catch {}
  }
  registry.clear();
  instrumented = false;
}

export function _registerInstrumentor(name: string, inst: BaseInstrumentor): void {
  registry.set(name, inst);
}
```

- [ ] **Step 2: Create OpenAI instrumentor (TS uses Proxy, already exists in llm.ts)**

The TS `wrapOpenAI` already uses Proxy. For global patching, we can't monkey-patch a module import the same way Python does. Instead, the TS instrumentor will work by patching the prototype of the OpenAI class if available:

```typescript
// packages/tracecast-ts/src/instrumentors/openaiInst.ts
import { BaseInstrumentor } from "./base";
import { getCurrentTrace } from "../core/tracer";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";
import { SpanType, Span } from "../types";

export class OpenAIInstrumentor implements BaseInstrumentor {
  private _original: any = null;
  private _patched = false;

  patch(): void {
    if (this._patched) return;
    let openaiMod: any;
    try {
      openaiMod = require("openai");
    } catch {
      throw new Error("openai not installed");
    }

    const OpenAI = openaiMod.default ?? openaiMod.OpenAI ?? openaiMod;
    if (!OpenAI?.Chat?.Completions?.prototype?.create) return;

    this._original = OpenAI.Chat.Completions.prototype.create;
    const originalCreate = this._original;

    OpenAI.Chat.Completions.prototype.create = async function (this: any, ...args: any[]) {
      const trace = getCurrentTrace();
      if (!trace) return originalCreate.apply(this, args);

      const kwargs = args[0] ?? {};
      const model = kwargs.model ?? "unknown";
      const messages = kwargs.messages as any[] | undefined;
      const inputText = messages?.length ? String(messages[messages.length - 1]?.content ?? "") : undefined;

      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${model}`,
        model,
        startedAt: new Date(),
        input: inputText,
        metadata: {},
      };

      let response: any;
      try {
        response = await originalCreate.apply(this, args);
      } catch (err: any) {
        span.finishedAt = new Date();
        span.metadata = { ...span.metadata, _error: err.message };
        trace.spans.push(span);
        throw err;
      }

      span.finishedAt = new Date();
      const usage = response?.usage ?? {};
      span.tokensIn = usage?.prompt_tokens ?? 0;
      span.tokensOut = usage?.completion_tokens ?? 0;
      span.tokensInCached = usage?.prompt_tokens_details?.cached_tokens ?? 0;
      span.costUsd = calculateCost(model, span.tokensIn!, span.tokensOut!);
      try {
        span.output = response?.choices?.[0]?.message?.content ?? undefined;
      } catch {}
      trace.spans.push(span);

      return response;
    };

    this._patched = true;
  }

  unpatch(): void {
    if (!this._patched || !this._original) return;
    try {
      const openaiMod = require("openai");
      const OpenAI = openaiMod.default ?? openaiMod.OpenAI ?? openaiMod;
      if (OpenAI?.Chat?.Completions?.prototype) {
        OpenAI.Chat.Completions.prototype.create = this._original;
      }
    } catch {}
    this._original = null;
    this._patched = false;
  }

  isPatched(): boolean {
    return this._patched;
  }
}
```

- [ ] **Step 3: Create Anthropic and Gemini instrumentors (TS)**

Follow same pattern as OpenAI — patch prototype.create if module available. (Same structure as `openaiInst.ts` but targeting `Anthropic.Messages.prototype.create` and `GoogleGenerativeAI.GenerativeModel.prototype.generateContent`.)

```typescript
// packages/tracecast-ts/src/instrumentors/anthropicInst.ts
import { BaseInstrumentor } from "./base";
import { getCurrentTrace } from "../core/tracer";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";
import { SpanType, Span } from "../types";

export class AnthropicInstrumentor implements BaseInstrumentor {
  private _original: any = null;
  private _patched = false;

  patch(): void {
    if (this._patched) return;
    let mod: any;
    try {
      mod = require("@anthropic-ai/sdk");
    } catch {
      throw new Error("@anthropic-ai/sdk not installed");
    }

    const Anthropic = mod.default ?? mod.Anthropic ?? mod;
    if (!Anthropic?.Messages?.prototype?.create) return;

    this._original = Anthropic.Messages.prototype.create;
    const originalCreate = this._original;

    Anthropic.Messages.prototype.create = async function (this: any, ...args: any[]) {
      const trace = getCurrentTrace();
      if (!trace) return originalCreate.apply(this, args);

      const kwargs = args[0] ?? {};
      const model = kwargs.model ?? "unknown";
      const messages = kwargs.messages as any[] | undefined;
      const inputText = messages?.length ? String(messages[messages.length - 1]?.content ?? "") : undefined;

      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${model}`,
        model,
        startedAt: new Date(),
        input: inputText,
        metadata: {},
      };

      let response: any;
      try {
        response = await originalCreate.apply(this, args);
      } catch (err: any) {
        span.finishedAt = new Date();
        span.metadata = { ...span.metadata, _error: err.message };
        trace.spans.push(span);
        throw err;
      }

      span.finishedAt = new Date();
      const usage = response?.usage ?? {};
      span.tokensIn = usage?.input_tokens ?? 0;
      span.tokensOut = usage?.output_tokens ?? 0;
      span.tokensInCached = usage?.cache_read_input_tokens ?? 0;
      span.costUsd = calculateCost(model, span.tokensIn!, span.tokensOut!);
      try {
        const content = response?.content ?? [];
        span.output = content.filter((b: any) => b?.type === "text").map((b: any) => b.text).join("");
      } catch {}
      trace.spans.push(span);

      return response;
    };

    this._patched = true;
  }

  unpatch(): void {
    if (!this._patched || !this._original) return;
    try {
      const mod = require("@anthropic-ai/sdk");
      const Anthropic = mod.default ?? mod.Anthropic ?? mod;
      if (Anthropic?.Messages?.prototype) {
        Anthropic.Messages.prototype.create = this._original;
      }
    } catch {}
    this._original = null;
    this._patched = false;
  }

  isPatched(): boolean {
    return this._patched;
  }
}
```

```typescript
// packages/tracecast-ts/src/instrumentors/geminiInst.ts
import { BaseInstrumentor } from "./base";
import { getCurrentTrace } from "../core/tracer";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";
import { SpanType, Span } from "../types";

export class GeminiInstrumentor implements BaseInstrumentor {
  private _original: any = null;
  private _patched = false;

  patch(): void {
    if (this._patched) return;
    let mod: any;
    try {
      mod = require("@google/generative-ai");
    } catch {
      throw new Error("@google/generative-ai not installed");
    }

    const GenModel = mod.GoogleGenerativeAI?.GenerativeModel ?? mod.GenerativeModel;
    if (!GenModel?.prototype?.generateContent) return;

    this._original = GenModel.prototype.generateContent;
    const originalFn = this._original;

    GenModel.prototype.generateContent = async function (this: any, ...args: any[]) {
      const trace = getCurrentTrace();
      if (!trace) return originalFn.apply(this, args);

      const modelName = this.model ?? "unknown";
      const inputText = typeof args[0] === "string" ? args[0] : JSON.stringify(args[0]);

      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${modelName}`,
        model: modelName,
        startedAt: new Date(),
        input: inputText,
        metadata: {},
      };

      let response: any;
      try {
        response = await originalFn.apply(this, args);
      } catch (err: any) {
        span.finishedAt = new Date();
        span.metadata = { ...span.metadata, _error: err.message };
        trace.spans.push(span);
        throw err;
      }

      span.finishedAt = new Date();
      const usage = response?.usageMetadata ?? {};
      span.tokensIn = usage?.promptTokenCount ?? 0;
      span.tokensOut = usage?.candidatesTokenCount ?? 0;
      span.tokensInCached = usage?.cachedContentTokenCount ?? 0;
      span.costUsd = calculateCost(modelName, span.tokensIn!, span.tokensOut!);
      try {
        span.output = response?.candidates?.[0]?.content?.parts?.map((p: any) => p.text).join("") ?? undefined;
      } catch {}
      trace.spans.push(span);

      return response;
    };

    this._patched = true;
  }

  unpatch(): void {
    if (!this._patched || !this._original) return;
    try {
      const mod = require("@google/generative-ai");
      const GenModel = mod.GoogleGenerativeAI?.GenerativeModel ?? mod.GenerativeModel;
      if (GenModel?.prototype) {
        GenModel.prototype.generateContent = this._original;
      }
    } catch {}
    this._original = null;
    this._patched = false;
  }

  isPatched(): boolean {
    return this._patched;
  }
}
```

- [ ] **Step 4: Write autoInstrument test (TS)**

```typescript
// packages/tracecast-ts/tests/instrumentors/autoInstrument.test.ts
import { autoInstrument, _resetInstrument, _registerInstrumentor } from "../../src/instrument";
import { BaseInstrumentor } from "../../src/instrumentors/base";

class FakeInstrumentor implements BaseInstrumentor {
  patched = false;
  patch() { this.patched = true; }
  unpatch() { this.patched = false; }
  isPatched() { return this.patched; }
}

describe("autoInstrument", () => {
  afterEach(() => _resetInstrument());

  it("calls patch on registered instrumentors", () => {
    const fake = new FakeInstrumentor();
    _registerInstrumentor("fake", fake);
    autoInstrument();
    expect(fake.isPatched()).toBe(true);
  });

  it("is idempotent", () => {
    const fake = new FakeInstrumentor();
    _registerInstrumentor("fake", fake);
    autoInstrument();
    autoInstrument();
    expect(fake.isPatched()).toBe(true);
  });

  it("skips instrumentors that throw on patch", () => {
    const bad: BaseInstrumentor = {
      patch() { throw new Error("no module"); },
      unpatch() {},
      isPatched() { return false; },
    };
    _registerInstrumentor("bad", bad);
    expect(() => autoInstrument()).not.toThrow();
  });
});
```

- [ ] **Step 5: Update index.ts exports**

Add to `packages/tracecast-ts/src/index.ts`:

```typescript
export { autoInstrument } from "./instrument";
```

- [ ] **Step 6: Run TS tests**

Run: `cd packages/tracecast-ts && npx jest --verbose`

- [ ] **Step 7: Commit**

```bash
git add packages/tracecast-ts/src/instrument.ts packages/tracecast-ts/src/instrumentors/ packages/tracecast-ts/tests/instrumentors/ packages/tracecast-ts/src/index.ts
git commit -m "feat(ts): add auto-instrument engine with OpenAI, Anthropic, Gemini, LangChain instrumentors"
```

---

## Task 10: TypeScript Sessions/Projects API

**Files:**
- Modify: `packages/tracecast-ts/src/dashboard/aggregator.ts`
- Modify: `packages/tracecast-ts/src/dashboard/reader.ts`
- Modify: `packages/tracecast-ts/src/dashboard/router.ts`
- Create: `packages/tracecast-ts/tests/dashboard/sessions.test.ts`

- [ ] **Step 1: Add `computeSessions` and `computeProjects` to aggregator.ts**

Add to `packages/tracecast-ts/src/dashboard/aggregator.ts`:

```typescript
export function computeSessions(traces: Trace[]): Array<Record<string, unknown>> {
  const groups: Record<string, { session_id: string; trace_count: number; total_cost_usd: number; total_tokens: number; total_tokens_in: number; total_tokens_out: number; first_trace_at: string; last_trace_at: string }> = {};
  for (const t of traces) {
    if (!t.sessionId) continue;
    if (!groups[t.sessionId]) {
      groups[t.sessionId] = {
        session_id: t.sessionId,
        trace_count: 0,
        total_cost_usd: 0,
        total_tokens: 0,
        total_tokens_in: 0,
        total_tokens_out: 0,
        first_trace_at: t.startedAt.toISOString(),
        last_trace_at: t.startedAt.toISOString(),
      };
    }
    const g = groups[t.sessionId];
    g.trace_count++;
    g.total_cost_usd += t.costUsd;
    g.total_tokens += t.totalTokens;
    g.total_tokens_in += t.totalTokensIn;
    g.total_tokens_out += t.totalTokensOut;
    const iso = t.startedAt.toISOString();
    if (iso < g.first_trace_at) g.first_trace_at = iso;
    if (iso > g.last_trace_at) g.last_trace_at = iso;
  }
  return Object.values(groups).sort((a, b) => b.last_trace_at.localeCompare(a.last_trace_at))
    .map(g => ({ ...g, total_cost_usd: Math.round(g.total_cost_usd * 1e6) / 1e6 }));
}

export function computeProjects(traces: Trace[]): Array<Record<string, unknown>> {
  const groups: Record<string, { project_id: string; trace_count: number; total_cost_usd: number; total_tokens: number; total_tokens_in: number; total_tokens_out: number; first_trace_at: string; last_trace_at: string }> = {};
  for (const t of traces) {
    if (!t.projectId) continue;
    if (!groups[t.projectId]) {
      groups[t.projectId] = {
        project_id: t.projectId,
        trace_count: 0,
        total_cost_usd: 0,
        total_tokens: 0,
        total_tokens_in: 0,
        total_tokens_out: 0,
        first_trace_at: t.startedAt.toISOString(),
        last_trace_at: t.startedAt.toISOString(),
      };
    }
    const g = groups[t.projectId];
    g.trace_count++;
    g.total_cost_usd += t.costUsd;
    g.total_tokens += t.totalTokens;
    g.total_tokens_in += t.totalTokensIn;
    g.total_tokens_out += t.totalTokensOut;
    const iso = t.startedAt.toISOString();
    if (iso < g.first_trace_at) g.first_trace_at = iso;
    if (iso > g.last_trace_at) g.last_trace_at = iso;
  }
  return Object.values(groups).sort((a, b) => b.last_trace_at.localeCompare(a.last_trace_at))
    .map(g => ({ ...g, total_cost_usd: Math.round(g.total_cost_usd * 1e6) / 1e6 }));
}
```

- [ ] **Step 2: Add reader methods and router endpoints**

Add to `reader.ts`:

```typescript
async getSessions(): Promise<Array<Record<string, unknown>>> {
  const { computeSessions } = await import("./aggregator");
  return computeSessions(await this.getTraces());
}

async getSession(sessionId: string): Promise<Trace[]> {
  return (await this.getTraces()).filter(t => t.sessionId === sessionId);
}

async getProjects(): Promise<Array<Record<string, unknown>>> {
  const { computeProjects } = await import("./aggregator");
  return computeProjects(await this.getTraces());
}

async getProject(projectId: string): Promise<Trace[]> {
  return (await this.getTraces()).filter(t => t.projectId === projectId);
}
```

Add to `router.ts`:

```typescript
router.get("/api/sessions", (req, res) => {
  reader.getSessions().then(sessions => res.json({ sessions, total: sessions.length }))
    .catch(err => res.status(500).json({ error: err.message }));
});

router.get("/api/sessions/:sessionId", (req, res) => {
  reader.getSession(req.params.sessionId).then(traces => {
    if (!traces.length) return res.status(404).json({ error: "Session not found" });
    const totalCost = traces.reduce((s, t) => s + t.costUsd, 0);
    const totalTokens = traces.reduce((s, t) => s + t.totalTokens, 0);
    res.json({
      session_id: req.params.sessionId,
      traces: traces.map(traceSummary),
      total_cost_usd: Math.round(totalCost * 1e6) / 1e6,
      total_tokens: totalTokens,
    });
  }).catch(err => res.status(500).json({ error: err.message }));
});

router.get("/api/projects", (req, res) => {
  reader.getProjects().then(projects => res.json({ projects, total: projects.length }))
    .catch(err => res.status(500).json({ error: err.message }));
});

router.get("/api/projects/:projectId", (req, res) => {
  reader.getProject(req.params.projectId).then(traces => {
    if (!traces.length) return res.status(404).json({ error: "Project not found" });
    const totalCost = traces.reduce((s, t) => s + t.costUsd, 0);
    const totalTokens = traces.reduce((s, t) => s + t.totalTokens, 0);
    res.json({
      project_id: req.params.projectId,
      traces: traces.map(traceSummary),
      total_cost_usd: Math.round(totalCost * 1e6) / 1e6,
      total_tokens: totalTokens,
    });
  }).catch(err => res.status(500).json({ error: err.message }));
});
```

- [ ] **Step 3: Write test**

```typescript
// packages/tracecast-ts/tests/dashboard/sessions.test.ts
import { computeSessions, computeProjects } from "../../src/dashboard/aggregator";
import { Trace, SpanType } from "../../src/types";

function makeTrace(id: string, sessionId?: string, projectId?: string, cost = 0.01): Trace {
  return {
    traceId: id,
    name: `trace-${id}`,
    startedAt: new Date("2026-05-20T10:00:00Z"),
    totalTokensIn: 100,
    totalTokensOut: 50,
    totalTokensInCached: 0,
    totalTokens: 150,
    costUsd: cost,
    toolsUsed: {},
    spans: [],
    metadata: {},
    sessionId,
    projectId,
  };
}

describe("computeSessions", () => {
  it("groups traces by sessionId", () => {
    const traces = [
      makeTrace("t1", "s1", undefined, 0.01),
      makeTrace("t2", "s1", undefined, 0.02),
      makeTrace("t3", "s2", undefined, 0.05),
    ];
    const sessions = computeSessions(traces);
    expect(sessions).toHaveLength(2);
    const s1 = sessions.find((s: any) => s.session_id === "s1")!;
    expect(s1.trace_count).toBe(2);
    expect(s1.total_cost_usd).toBeCloseTo(0.03, 4);
  });

  it("ignores traces without sessionId", () => {
    const traces = [makeTrace("t1"), makeTrace("t2", "s1")];
    const sessions = computeSessions(traces);
    expect(sessions).toHaveLength(1);
  });
});

describe("computeProjects", () => {
  it("groups traces by projectId", () => {
    const traces = [
      makeTrace("t1", undefined, "p1", 0.01),
      makeTrace("t2", undefined, "p1", 0.02),
      makeTrace("t3", undefined, "p2", 0.05),
    ];
    const projects = computeProjects(traces);
    expect(projects).toHaveLength(2);
    const p1 = projects.find((p: any) => p.project_id === "p1")!;
    expect(p1.trace_count).toBe(2);
  });
});
```

- [ ] **Step 4: Run TS tests**

Run: `cd packages/tracecast-ts && npx jest --verbose`

- [ ] **Step 5: Commit**

```bash
git add packages/tracecast-ts/src/dashboard/ packages/tracecast-ts/tests/dashboard/
git commit -m "feat(ts): add sessions/projects API endpoints and aggregation"
```

---

## Task 11: React Dashboard — Scaffold + Layout

**Files:**
- Create: `packages/tracecast-dashboard/package.json`
- Create: `packages/tracecast-dashboard/vite.config.ts`
- Create: `packages/tracecast-dashboard/tsconfig.json`
- Create: `packages/tracecast-dashboard/index.html`
- Create: `packages/tracecast-dashboard/src/main.tsx`
- Create: `packages/tracecast-dashboard/src/App.tsx`
- Create: `packages/tracecast-dashboard/src/styles/globals.css`
- Create: `packages/tracecast-dashboard/src/components/Layout.tsx`
- Create: `packages/tracecast-dashboard/src/hooks/useApi.ts`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "tracecast-dashboard",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "copy:py": "cp -r dist/* ../tracecast-py/tracecast/dashboard/static/",
    "copy:ts": "cp -r dist/* ../tracecast-ts/src/dashboard/static/",
    "copy": "npm run copy:py && npm run copy:ts"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.28.0",
    "recharts": "^2.14.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.3.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: Create vite.config.ts**

```typescript
// packages/tracecast-dashboard/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:7777/tracecast",
    },
  },
});
```

- [ ] **Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create index.html**

```html
<!-- packages/tracecast-dashboard/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TraceCast Dashboard</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

- [ ] **Step 5: Create globals.css**

```css
/* packages/tracecast-dashboard/src/styles/globals.css */
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --border: #2a2d37;
  --text: #e1e4ed;
  --text-muted: #8b8fa6;
  --accent: #6366f1;
  --accent-hover: #818cf8;
  --green: #22c55e;
  --red: #ef4444;
  --yellow: #f59e0b;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); }
```

- [ ] **Step 6: Create useApi hook**

```typescript
// packages/tracecast-dashboard/src/hooks/useApi.ts
import { useState, useEffect } from "react";

const BASE = "./api";

export function useApi<T>(path: string, deps: any[] = []): { data: T | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${BASE}${path}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, deps);

  return { data, loading, error };
}

export async function fetchApi<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 7: Create Layout component**

```tsx
// packages/tracecast-dashboard/src/components/Layout.tsx
import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "Overview" },
  { to: "/traces", label: "Traces" },
  { to: "/models", label: "Models" },
  { to: "/sessions", label: "Sessions" },
  { to: "/projects", label: "Projects" },
];

export function Layout() {
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside style={{
        width: 200,
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        padding: "20px 0",
        flexShrink: 0,
      }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--accent)", padding: "0 20px", marginBottom: 24 }}>
          TraceCast
        </h1>
        <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              style={({ isActive }) => ({
                padding: "8px 20px",
                fontSize: 14,
                color: isActive ? "#fff" : "var(--text-muted)",
                background: isActive ? "var(--accent)" : "transparent",
                borderRadius: 6,
                margin: "0 8px",
              })}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 8: Create App.tsx + main.tsx**

```tsx
// packages/tracecast-dashboard/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Overview } from "./pages/Overview";
import { Traces } from "./pages/Traces";
import { Models } from "./pages/Models";
import { Sessions } from "./pages/Sessions";
import { Projects } from "./pages/Projects";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/traces" element={<Traces />} />
          <Route path="/models" element={<Models />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/projects" element={<Projects />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

```tsx
// packages/tracecast-dashboard/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 9: Create placeholder pages**

Create all 5 pages as placeholders that will be implemented in the next tasks:

```tsx
// packages/tracecast-dashboard/src/pages/Overview.tsx
export function Overview() {
  return <div><h2>Overview</h2><p>Loading...</p></div>;
}
```

```tsx
// packages/tracecast-dashboard/src/pages/Traces.tsx
export function Traces() {
  return <div><h2>Traces</h2><p>Loading...</p></div>;
}
```

```tsx
// packages/tracecast-dashboard/src/pages/Models.tsx
export function Models() {
  return <div><h2>Models</h2><p>Loading...</p></div>;
}
```

```tsx
// packages/tracecast-dashboard/src/pages/Sessions.tsx
export function Sessions() {
  return <div><h2>Sessions</h2><p>Loading...</p></div>;
}
```

```tsx
// packages/tracecast-dashboard/src/pages/Projects.tsx
export function Projects() {
  return <div><h2>Projects</h2><p>Loading...</p></div>;
}
```

- [ ] **Step 10: Install dependencies and verify build**

```bash
cd packages/tracecast-dashboard && npm install && npm run build
```

Expected: Build succeeds, `dist/` directory created with `index.html` and `assets/`.

- [ ] **Step 11: Commit**

```bash
git add packages/tracecast-dashboard/
git commit -m "feat: scaffold React dashboard with Vite, Layout, routing, and placeholder pages"
```

---

## Task 12: React Dashboard — Overview Page

**Files:**
- Create: `packages/tracecast-dashboard/src/components/StatCard.tsx`
- Modify: `packages/tracecast-dashboard/src/pages/Overview.tsx`

- [ ] **Step 1: Create StatCard component**

```tsx
// packages/tracecast-dashboard/src/components/StatCard.tsx
export function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
```

- [ ] **Step 2: Implement Overview page with stat cards + charts**

```tsx
// packages/tracecast-dashboard/src/pages/Overview.tsx
import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { StatCard } from "../components/StatCard";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, Legend } from "recharts";

const COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#a855f7", "#ec4899", "#84cc16"];

function fmt$(n: number) { return "$" + n.toFixed(4); }
function fmtMs(n: number | null) { return n == null ? "—" : n < 1000 ? `${Math.round(n)}ms` : `${(n / 1000).toFixed(2)}s`; }
function fmtNum(n: number) { return n.toLocaleString(); }
function fmtPct(n: number) { return (n * 100).toFixed(1) + "%"; }

interface Metrics {
  total_traces: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  cache_hit_rate: number;
  total_tokens_in: number;
  total_tokens_out: number;
  cost_by_model: Record<string, number>;
  cost_by_project: Record<string, number>;
  traces_over_time: Array<{ date: string; cost_usd: number; traces: number }>;
}

export function Overview() {
  const [period, setPeriod] = useState("7d");
  const { data: m, loading } = useApi<Metrics>(`/metrics?period=${period}`, [period]);

  if (loading || !m) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  const modelData = Object.entries(m.cost_by_model).map(([name, value]) => ({ name, value }));
  const projectData = Object.entries(m.cost_by_project).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Overview</h2>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }}
        >
          <option value="1h">Last hour</option>
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 16, marginBottom: 24 }}>
        <StatCard label="Total Traces" value={fmtNum(m.total_traces)} />
        <StatCard label="Total Cost" value={fmt$(m.total_cost_usd)} />
        <StatCard label="Avg Latency" value={fmtMs(m.avg_latency_ms)} />
        <StatCard label="Cache Hit Rate" value={fmtPct(m.cache_hit_rate)} />
        <StatCard label="Tokens In" value={fmtNum(m.total_tokens_in)} />
        <StatCard label="Tokens Out" value={fmtNum(m.total_tokens_out)} />
      </div>

      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <div style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={m.traces_over_time}>
              <CartesianGrid stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
              <Line type="monotone" dataKey="cost_usd" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost by Model</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={modelData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                {modelData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
              <Legend wrapperStyle={{ color: "var(--text-muted)", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {projectData.length > 0 && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost by Project</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={projectData}>
              <CartesianGrid stroke="var(--border)" />
              <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
              <Bar dataKey="value" fill="#6366f1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Build and verify**

Run: `cd packages/tracecast-dashboard && npm run build`

- [ ] **Step 4: Commit**

```bash
git add packages/tracecast-dashboard/src/
git commit -m "feat: implement Overview page with stat cards and Recharts"
```

---

## Task 13: React Dashboard — Traces + TraceDetail Pages

**Files:**
- Create: `packages/tracecast-dashboard/src/components/SpanTimeline.tsx`
- Modify: `packages/tracecast-dashboard/src/pages/Traces.tsx`
- Create: `packages/tracecast-dashboard/src/pages/TraceDetail.tsx`
- Modify: `packages/tracecast-dashboard/src/App.tsx` (add TraceDetail route)

- [ ] **Step 1: Implement Traces page**

```tsx
// packages/tracecast-dashboard/src/pages/Traces.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";

interface TraceSummary {
  trace_id: string;
  name: string;
  started_at: string;
  latency_ms: number | null;
  total_tokens_in: number;
  total_tokens_out: number;
  cost_usd: number;
  span_count: number;
  model: string | null;
}

export function Traces() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("date");
  const [order, setOrder] = useState("desc");
  const [projectId, setProjectId] = useState("");
  const [userId, setUserId] = useState("");

  const params = `?page=${page}&page_size=50&sort_by=${sortBy}&order=${order}` +
    (projectId ? `&project_id=${encodeURIComponent(projectId)}` : "") +
    (userId ? `&user_id=${encodeURIComponent(userId)}` : "");

  const { data, loading } = useApi<{ traces: TraceSummary[]; total: number; page: number }>(`/traces${params}`, [page, sortBy, order, projectId, userId]);

  const toggleSort = (col: string) => {
    if (sortBy === col) setOrder(order === "desc" ? "asc" : "desc");
    else { setSortBy(col); setOrder("desc"); }
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / 50) : 0;

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Traces</h2>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
        <input placeholder="Project ID" value={projectId} onChange={(e) => { setProjectId(e.target.value); setPage(1); }}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }} />
        <input placeholder="User ID" value={userId} onChange={(e) => { setUserId(e.target.value); setPage(1); }}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }} />
        {data && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{data.total} traces</span>}
      </div>

      {loading ? <div style={{ color: "var(--text-muted)" }}>Loading...</div> : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {[{ key: "name", label: "Name" }, { key: "date", label: "Date" }, { key: "duration", label: "Latency" }, { key: "tokens", label: "Tokens" }, { key: "cost", label: "Cost" }, { key: "", label: "Spans" }].map((col) => (
                    <th key={col.label}
                      onClick={() => col.key && toggleSort(col.key)}
                      style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontWeight: 600, cursor: col.key ? "pointer" : "default" }}>
                      {col.label} {sortBy === col.key ? (order === "desc" ? "↓" : "↑") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.traces ?? []).map((t) => (
                  <tr key={t.trace_id} onClick={() => navigate(`/traces/${t.trace_id}`)}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "var(--surface)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = ""}>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.name}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(t.started_at).toLocaleString()}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.latency_ms != null ? (t.latency_ms < 1000 ? `${t.latency_ms}ms` : `${(t.latency_ms / 1000).toFixed(2)}s`) : "—"}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.total_tokens_in.toLocaleString()} / {t.total_tokens_out.toLocaleString()}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>${t.cost_usd.toFixed(4)}</td>
                    <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{t.span_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "center", alignItems: "center" }}>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}
              style={{ padding: "6px 12px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer", opacity: page <= 1 ? 0.3 : 1 }}>Prev</button>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}
              style={{ padding: "6px 12px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer", opacity: page >= totalPages ? 0.3 : 1 }}>Next</button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create SpanTimeline and TraceDetail**

```tsx
// packages/tracecast-dashboard/src/components/SpanTimeline.tsx
interface SpanData {
  span_id: string;
  type: string;
  name: string;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number | null;
  input: string | null;
  output: string | null;
}

export function SpanTimeline({ spans }: { spans: SpanData[] }) {
  const borderColors: Record<string, string> = { llm: "var(--accent)", tool: "var(--yellow)", agent: "var(--green)" };

  return (
    <div>
      {spans.map((s) => (
        <div key={s.span_id} style={{
          padding: 12, margin: "8px 0", background: "var(--bg)", borderRadius: 6,
          borderLeft: `3px solid ${borderColors[s.type] ?? "var(--accent)"}`,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {s.name} <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{s.type}</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 16, flexWrap: "wrap" }}>
            {s.model && <span>Model: {s.model}</span>}
            <span>Tokens: {s.tokens_in.toLocaleString()} in / {s.tokens_out.toLocaleString()} out</span>
            <span>Cost: ${s.cost_usd.toFixed(4)}</span>
            <span>Latency: {s.latency_ms != null ? (s.latency_ms < 1000 ? `${s.latency_ms}ms` : `${(s.latency_ms / 1000).toFixed(2)}s`) : "—"}</span>
          </div>
          {s.input && (
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <strong style={{ color: "var(--accent)" }}>Input:</strong>
              <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "var(--text)", maxHeight: 150, overflowY: "auto" }}>
                {s.input.length > 500 ? s.input.slice(0, 500) + "..." : s.input}
              </pre>
            </div>
          )}
          {s.output && (
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <strong style={{ color: "var(--accent)" }}>Output:</strong>
              <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: 8, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "var(--text)", maxHeight: 150, overflowY: "auto" }}>
                {s.output.length > 500 ? s.output.slice(0, 500) + "..." : s.output}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

```tsx
// packages/tracecast-dashboard/src/pages/TraceDetail.tsx
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { SpanTimeline } from "../components/SpanTimeline";

export function TraceDetail() {
  const { traceId } = useParams();
  const navigate = useNavigate();
  const { data: t, loading } = useApi<any>(`/traces/${traceId}`, [traceId]);

  if (loading || !t) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div>
      <button onClick={() => navigate(-1)}
        style={{ marginBottom: 16, padding: "6px 14px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", borderRadius: 6, cursor: "pointer" }}>
        &larr; Back
      </button>
      <h2 style={{ fontSize: 18, fontWeight: 600 }}>{t.name}</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>Trace ID: <code>{t.trace_id}</code></p>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
        Model: {t.model ?? "—"} | Cost: ${t.cost_usd?.toFixed(4)} | Latency: {t.latency_ms != null ? `${t.latency_ms}ms` : "—"}
      </p>
      {t.spans?.length > 0 && (
        <>
          <h3 style={{ marginTop: 16, fontSize: 14 }}>Spans ({t.spans.length})</h3>
          <SpanTimeline spans={t.spans} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add TraceDetail route to App.tsx**

Add `import { TraceDetail } from "./pages/TraceDetail";` and add route:

```tsx
<Route path="/traces/:traceId" element={<TraceDetail />} />
```

- [ ] **Step 4: Build and verify**

Run: `cd packages/tracecast-dashboard && npm run build`

- [ ] **Step 5: Commit**

```bash
git add packages/tracecast-dashboard/src/
git commit -m "feat: implement Traces list, TraceDetail with span waterfall"
```

---

## Task 14: React Dashboard — Models, Sessions, Projects Pages

**Files:**
- Modify: `packages/tracecast-dashboard/src/pages/Models.tsx`
- Modify: `packages/tracecast-dashboard/src/pages/Sessions.tsx`
- Modify: `packages/tracecast-dashboard/src/pages/Projects.tsx`

- [ ] **Step 1: Implement Models page**

```tsx
// packages/tracecast-dashboard/src/pages/Models.tsx
import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export function Models() {
  const [period, setPeriod] = useState("7d");
  const { data: m, loading } = useApi<any>(`/metrics?period=${period}`, [period]);
  const { data: traces } = useApi<any>("/traces?page=1&page_size=200", []);

  if (loading || !m) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  const costData = Object.entries(m.cost_by_model || {}).map(([name, value]) => ({ name, cost: value as number }));

  const modelStats: Record<string, { count: number; tokens: number }> = {};
  for (const t of (traces?.traces ?? [])) {
    if (!t.model) continue;
    if (!modelStats[t.model]) modelStats[t.model] = { count: 0, tokens: 0 };
    modelStats[t.model].count++;
    modelStats[t.model].tokens += t.total_tokens ?? 0;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Models</h2>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}
          style={{ padding: "6px 12px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, fontSize: 13 }}>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 20, marginBottom: 24 }}>
        <h3 style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 16 }}>Cost per Model</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={costData}>
            <CartesianGrid stroke="var(--border)" />
            <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
            <Bar dataKey="cost" fill="#6366f1" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Model</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Traces</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Total Tokens</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(modelStats).sort(([, a], [, b]) => b.count - a.count).map(([model, stats]) => (
            <tr key={model}>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{model}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{stats.count}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{stats.tokens.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Implement Sessions page**

```tsx
// packages/tracecast-dashboard/src/pages/Sessions.tsx
import { useApi } from "../hooks/useApi";

interface SessionSummary {
  session_id: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  total_tokens_in: number;
  total_tokens_out: number;
  first_trace_at: string;
  last_trace_at: string;
}

export function Sessions() {
  const { data, loading } = useApi<{ sessions: SessionSummary[]; total: number }>("/sessions", []);

  if (loading || !data) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Sessions</h2>
      <span style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, display: "block" }}>{data.total} sessions</span>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Session ID</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Traces</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Cost</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Tokens</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>First Trace</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Last Trace</th>
          </tr>
        </thead>
        <tbody>
          {data.sessions.map((s) => (
            <tr key={s.session_id}>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}><code>{s.session_id}</code></td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{s.trace_count}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>${s.total_cost_usd.toFixed(4)}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{s.total_tokens.toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(s.first_trace_at).toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(s.last_trace_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Implement Projects page**

```tsx
// packages/tracecast-dashboard/src/pages/Projects.tsx
import { useApi } from "../hooks/useApi";

interface ProjectSummary {
  project_id: string;
  trace_count: number;
  total_cost_usd: number;
  total_tokens: number;
  total_tokens_in: number;
  total_tokens_out: number;
  first_trace_at: string;
  last_trace_at: string;
}

export function Projects() {
  const { data, loading } = useApi<{ projects: ProjectSummary[]; total: number }>("/projects", []);

  if (loading || !data) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Projects</h2>
      <span style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, display: "block" }}>{data.total} projects</span>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Project ID</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Traces</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Cost</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Tokens</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>First Trace</th>
            <th style={{ textAlign: "left", padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>Last Trace</th>
          </tr>
        </thead>
        <tbody>
          {data.projects.map((p) => (
            <tr key={p.project_id}>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}><code>{p.project_id}</code></td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{p.trace_count}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>${p.total_cost_usd.toFixed(4)}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{p.total_tokens.toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(p.first_trace_at).toLocaleString()}</td>
              <td style={{ padding: "10px 14px", fontSize: 13, borderBottom: "1px solid var(--border)" }}>{new Date(p.last_trace_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Build and verify**

Run: `cd packages/tracecast-dashboard && npm run build`

- [ ] **Step 5: Commit**

```bash
git add packages/tracecast-dashboard/src/
git commit -m "feat: implement Models, Sessions, and Projects dashboard pages"
```

---

## Task 15: Build Pipeline + Copy Static + Update pyproject.toml

**Files:**
- Create: `packages/tracecast-dashboard/scripts/copy-static.sh`
- Modify: `packages/tracecast-py/pyproject.toml`
- Modify: `packages/tracecast-ts/package.json`

- [ ] **Step 1: Create copy script**

```bash
#!/bin/bash
# packages/tracecast-dashboard/scripts/copy-static.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$(dirname "$SCRIPT_DIR")"
DIST="$DASHBOARD_DIR/dist"

PY_STATIC="$DASHBOARD_DIR/../tracecast-py/tracecast/dashboard/static"
TS_STATIC="$DASHBOARD_DIR/../tracecast-ts/src/dashboard/static"

rm -rf "$PY_STATIC"/* 2>/dev/null || true
rm -rf "$TS_STATIC"/* 2>/dev/null || true

cp -r "$DIST"/* "$PY_STATIC/"
cp -r "$DIST"/* "$TS_STATIC/"

echo "Copied dashboard build to Python and TypeScript static dirs"
```

- [ ] **Step 2: Build dashboard and copy**

```bash
cd packages/tracecast-dashboard && npm run build && bash scripts/copy-static.sh
```

- [ ] **Step 3: Add dashboard optional dep to pyproject.toml**

Add to `[project.optional-dependencies]` in `packages/tracecast-py/pyproject.toml`:

```toml
dashboard = ["fastapi>=0.100.0", "uvicorn>=0.20"]
all       = ["tracecast[mongo,postgres,langchain,dashboard]"]
```

- [ ] **Step 4: Add express peer dep to package.json**

Ensure `packages/tracecast-ts/package.json` has:

```json
"peerDependencies": {
  "express": ">=4.0.0",
  "mongodb": ">=5",
  "pg": ">=8"
},
"peerDependenciesMeta": {
  "express": { "optional": true },
  "mongodb": { "optional": true },
  "pg": { "optional": true }
}
```

- [ ] **Step 5: Run all tests (both Python and TS)**

```bash
cd packages/tracecast-py && python -m pytest tests/ -v
cd packages/tracecast-ts && npx jest --verbose
```

- [ ] **Step 6: Commit**

```bash
git add packages/tracecast-dashboard/scripts/ packages/tracecast-py/pyproject.toml packages/tracecast-ts/package.json packages/tracecast-py/tracecast/dashboard/static/ packages/tracecast-ts/src/dashboard/static/
git commit -m "feat: add build pipeline, copy scripts, and update package configs for v0.2.0"
```

---

## Task 16: Final Integration Test + Cleanup

**Files:**
- Verify all tests pass
- Remove old vanilla JS static files (replaced by React build)

- [ ] **Step 1: Run full Python test suite**

```bash
cd packages/tracecast-py && python -m pytest tests/ -v
```

- [ ] **Step 2: Run full TS test suite**

```bash
cd packages/tracecast-ts && npx jest --verbose
```

- [ ] **Step 3: Build TS package**

```bash
cd packages/tracecast-ts && npx tsc
```

- [ ] **Step 4: Verify dashboard build**

```bash
cd packages/tracecast-dashboard && npm run build
```

- [ ] **Step 5: Update version to 0.2.0**

In `packages/tracecast-py/pyproject.toml`: change `version = "0.1.2"` to `version = "0.2.0"`.
In `packages/tracecast-ts/package.json`: change `"version": "0.1.2"` to `"version": "0.2.0"`.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: bump version to v0.2.0 — auto-instrument + React dashboard"
```
