import threading

from tracecast.core.export_stats import ExportStats


def test_snapshot_keys():
    s = ExportStats()
    snap = s.snapshot()
    assert set(snap) >= {
        "exported_ok",
        "export_failed",
        "export_retried",
        "summary_fallback",
        "queue_dropped",
        "last_error",
        "last_error_at",
    }
    assert snap["exported_ok"] == 0
    assert snap["last_error"] is None


def test_incr_and_last_error():
    s = ExportStats()
    s.incr("exported_ok")
    s.incr("export_failed", 2)
    s.set_last_error("boom")
    snap = s.snapshot()
    assert snap["exported_ok"] == 1
    assert snap["export_failed"] == 2
    assert snap["last_error"] == "boom"
    assert snap["last_error_at"] is not None


def test_concurrent_incr():
    s = ExportStats()

    def work():
        for _ in range(100):
            s.incr("exported_ok")

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.snapshot()["exported_ok"] == 400
