from datetime import datetime, timedelta, timezone

from tracecast.dashboard.reader import TraceReader
from tracecast.models.trace import Trace


def _trace(trace_id, hours_ago, cost=1.0, tokens_in=10, tokens_out=5):
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=hours_ago)
    t = Trace(trace_id=trace_id, name="req", started_at=started)
    t.finished_at = started
    t._finalize()
    d = t.to_dict()
    d["started_at"] = started.isoformat()
    d["cost_usd"] = cost
    d["total_tokens_in"] = tokens_in
    d["total_tokens_out"] = tokens_out
    return d


class FakeSnapshotExporter:
    def __init__(self, raw_docs, snapshots):
        self._docs = raw_docs
        self._snaps = snapshots

    def _match(self, d, project_name, project_id, from_dt, to_dt):
        if from_dt and d["started_at"] < from_dt.isoformat():
            return False
        if to_dt and d["started_at"] > to_dt.isoformat():
            return False
        return True

    def query(self, *, project_name=None, project_id=None, user_id=None, session_id=None,
              from_dt=None, to_dt=None, limit=50, offset=0, sort_by="date", order="desc"):
        rows = [d for d in self._docs if self._match(d, project_name, project_id, from_dt, to_dt)]
        return rows[offset:offset + limit]

    def count(self, *, project_name=None, project_id=None, user_id=None, session_id=None, from_dt=None, to_dt=None):
        return len([d for d in self._docs if self._match(d, project_name, project_id, from_dt, to_dt)])

    def get(self, trace_id):
        return None

    def query_snapshots(self, *, from_date, to_date, project_id=None, project_name=None):
        return [s for s in self._snaps if from_date.isoformat() <= s["date"] <= to_date.isoformat()]


def test_merges_snapshot_and_raw_totals():
    now = datetime.now(timezone.utc)
    retention_days = 7

    raw = [_trace("recent", hours_ago=2, cost=2.0, tokens_in=100, tokens_out=50)]
    old_day = (now - timedelta(days=10)).date()
    snapshots = [{
        "date": old_day.isoformat(), "project_id": None, "project_name": None,
        "trace_count": 5, "total_tokens_in": 500, "total_tokens_out": 200,
        "total_tokens_in_cached": 0, "total_cost_usd": 10.0, "total_latency_ms": 5000,
    }]

    exporter = FakeSnapshotExporter(raw, snapshots)
    reader = TraceReader([exporter], retention_days=retention_days)

    totals = reader.get_metrics_totals(
        from_dt=now - timedelta(days=15), to_dt=now,
    )

    assert totals is not None
    assert totals["total_traces"] == 6
    assert totals["total_cost_usd"] == 12.0
    assert totals["total_tokens_in"] == 600
    assert totals["total_tokens_out"] == 250
    dates = [d["date"] for d in totals["traces_over_time"]]
    assert old_day.isoformat() in dates
    assert now.strftime("%Y-%m-%d") in dates


def test_returns_none_when_fully_within_raw_retention():
    now = datetime.now(timezone.utc)
    reader = TraceReader([FakeSnapshotExporter([], [])], retention_days=7)

    totals = reader.get_metrics_totals(from_dt=now - timedelta(hours=1), to_dt=now)

    assert totals is None


def test_returns_none_when_retention_not_configured():
    now = datetime.now(timezone.utc)
    reader = TraceReader([FakeSnapshotExporter([], [])], retention_days=None)

    totals = reader.get_metrics_totals(from_dt=now - timedelta(days=30), to_dt=now)

    assert totals is None
