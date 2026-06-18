import pytest

from tracecast import Tracer
from tracecast.prompts import create_prompt, get_prompt, set_label, PromptVersion
from tracecast.exporters.dict_exporter import DictExporter


def test_create_increments_version():
    exp = DictExporter()
    v1 = create_prompt("greeting", "Hello {name}", exporters=[exp])
    v2 = create_prompt("greeting", "Hi {name}", exporters=[exp])
    assert v1.version == 1
    assert v2.version == 2


def test_get_prompt_defaults_to_highest_version():
    exp = DictExporter()
    create_prompt("p", "a", exporters=[exp])
    create_prompt("p", "b", exporters=[exp])
    assert get_prompt("p", label=None, exporters=[exp]).version == 2


def test_get_prompt_by_explicit_version():
    exp = DictExporter()
    create_prompt("p", "a", exporters=[exp])
    create_prompt("p", "b", exporters=[exp])
    assert get_prompt("p", version=1, exporters=[exp]).template == "a"


def test_label_resolution_and_move():
    exp = DictExporter()
    create_prompt("p", "v1", labels=["production"], exporters=[exp])
    create_prompt("p", "v2", exporters=[exp])
    assert get_prompt("p", label="production", exporters=[exp]).version == 1
    set_label("p", 2, "production", exporters=[exp])
    assert get_prompt("p", label="production", exporters=[exp]).version == 2


def test_unknown_label_raises_with_available():
    exp = DictExporter()
    create_prompt("p", "v1", labels=["staging"], exporters=[exp])
    with pytest.raises(ValueError) as ei:
        get_prompt("p", label="production", exporters=[exp])
    assert "staging" in str(ei.value)


def test_no_exporter_raises():
    with pytest.raises(RuntimeError):
        get_prompt("p", exporters=[])


def test_cache_avoids_repeat_query():
    class CountingExp(DictExporter):
        def __init__(self):
            super().__init__()
            self.query_count = 0

        def query_prompts(self, *, name=None):
            self.query_count += 1
            return super().query_prompts(name=name)

    exp = CountingExp()
    create_prompt("p", "v1", labels=["production"], exporters=[exp])
    before = exp.query_count
    get_prompt("p", label="production", exporters=[exp], cache_ttl=60)
    get_prompt("p", label="production", exporters=[exp], cache_ttl=60)
    assert exp.query_count == before + 1


def test_auto_link_to_active_trace():
    exp = DictExporter()
    create_prompt("p", "v1", labels=["production"], exporters=[exp])
    tracer = Tracer(exporters=[exp])
    with tracer.trace(name="t") as tr:
        get_prompt("p", label="production", exporters=[exp])
        assert tr.metadata.get("prompt_name") == "p"
        assert tr.metadata.get("prompt_version") == 1


def test_promptversion_roundtrip():
    pv = PromptVersion(name="p", version=1, template="t", labels=["production"])
    back = PromptVersion.from_dict(pv.to_dict())
    assert back.name == "p"
    assert back.labels == ["production"]
