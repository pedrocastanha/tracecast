import pytest

from tracecast.core.export_retry import retry_call, default_export_retries, default_export_retry_base


def test_succeeds_on_second_attempt():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise IOError("temp")
        return "ok"

    sleeps = []
    assert retry_call(flaky, attempts=3, base_delay=0.1, sleep=sleeps.append) == "ok"
    assert calls["n"] == 2
    assert len(sleeps) == 1


def test_exhausted_raises_last():
    def always():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        retry_call(always, attempts=3, base_delay=0.0, sleep=lambda _: None)


def test_on_retry_called():
    seen = []

    def flaky():
        if len(seen) < 2:
            raise RuntimeError("x")
        return 1

    def on_retry(i, exc):
        seen.append((i, type(exc)))

    retry_call(flaky, attempts=3, base_delay=0.0, on_retry=on_retry, sleep=lambda _: None)
    assert len(seen) == 2


def test_defaults():
    assert default_export_retries() >= 1
    assert default_export_retry_base() >= 0
