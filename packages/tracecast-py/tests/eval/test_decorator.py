import asyncio

import pytest

from tracecast.eval.decorator import evaluator, get_target, list_targets, clear_registry


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def test_registers_and_is_transparent():
    @evaluator(dataset="d.json", name="bot", scorers=["contains"], threshold=0.6, project_id="p")
    def bot(x):
        return x.upper()

    assert bot("hi") == "HI"
    target = get_target("bot")
    assert target is not None
    assert target.datasets == ["d.json"]
    assert target.scorers == ["contains"]
    assert target.threshold == 0.6
    assert target.project_id == "p"
    assert target.is_async is False


def test_default_name_and_multi_dataset():
    @evaluator(dataset=["a.json", "b.json"])
    def agent(x):
        return x

    t = get_target("agent")
    assert t.datasets == ["a.json", "b.json"]
    assert "agent" in list_targets()


def test_async_target():
    @evaluator(dataset="d.json", name="abot")
    async def abot(x):
        return x

    assert asyncio.run(abot("z")) == "z"
    assert get_target("abot").is_async is True
