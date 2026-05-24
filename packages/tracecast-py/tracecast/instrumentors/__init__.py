from .base import BaseInstrumentor
import importlib


def _register_all():
    """Register all built-in instrumentors into the global registry.

    Called lazily from auto_instrument() (in instrument.py) to avoid a circular
    import: instrument.py imports instrumentors.base (which triggers this __init__),
    and this module would otherwise try to import instrument._registry before
    instrument.py is fully initialized.
    """
    # Imported here (not at module level) to break the circular dependency.
    from ..instrument import _registry

    instrumentors = [
        ("openai", "openai_inst", "OpenAIInstrumentor"),
        ("anthropic", "anthropic_inst", "AnthropicInstrumentor"),
        ("gemini", "gemini_inst", "GeminiInstrumentor"),
        ("langchain", "langchain_inst", "LangChainInstrumentor"),
        ("llamaindex", "llamaindex_inst", "LlamaIndexInstrumentor"),
        ("crewai", "crewai_inst", "CrewAIInstrumentor"),
    ]
    for name, module_name, class_name in instrumentors:
        if name in _registry:
            continue  # already registered (e.g., from tests)
        try:
            mod = importlib.import_module(f".{module_name}", package=__name__)
            cls = getattr(mod, class_name)
            _registry[name] = cls()
        except ImportError:
            pass
        except Exception as exc:
            import warnings
            warnings.warn(
                f"TraceCast: failed to register instrumentor '{name}': {exc}",
                stacklevel=2,
            )


__all__ = ["BaseInstrumentor"]
