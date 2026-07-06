from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from tracecast.dashboard.retention import run_maintenance_once


def _fake_exporter(oldest: date):
    exporter = MagicMock()
    exporter.oldest_trace_date.return_value = oldest
    return exporter


def test_snapshots_each_day_before_cutoff_then_purges():
    now = datetime.now(timezone.utc)
    cutoff_day = (now - timedelta(days=7)).date()
    oldest = cutoff_day - timedelta(days=3)
    exporter = _fake_exporter(oldest)

    run_maintenance_once(exporter, retention_days=7)

    snapshotted_days = [c.args[0] for c in exporter.compute_daily_snapshot.call_args_list]
    assert snapshotted_days == [
        oldest, oldest + timedelta(days=1), oldest + timedelta(days=2),
    ]
    assert cutoff_day not in snapshotted_days

    exporter.purge_traces_before.assert_called_once()
    purge_cutoff = exporter.purge_traces_before.call_args.args[0]
    assert purge_cutoff == datetime(cutoff_day.year, cutoff_day.month, cutoff_day.day, tzinfo=timezone.utc)


def test_no_op_when_no_traces_yet():
    exporter = _fake_exporter(None)

    run_maintenance_once(exporter, retention_days=7)

    exporter.compute_daily_snapshot.assert_not_called()
    exporter.purge_traces_before.assert_not_called()


def test_no_op_when_oldest_trace_already_within_retention():
    now = datetime.now(timezone.utc)
    exporter = _fake_exporter(now.date())

    run_maintenance_once(exporter, retention_days=7)

    exporter.compute_daily_snapshot.assert_not_called()
    exporter.purge_traces_before.assert_called_once()


def test_stops_snapshotting_on_failure_and_skips_purge():
    now = datetime.now(timezone.utc)
    cutoff_day = (now - timedelta(days=7)).date()
    oldest = cutoff_day - timedelta(days=2)
    exporter = _fake_exporter(oldest)
    exporter.compute_daily_snapshot.side_effect = RuntimeError("boom")

    run_maintenance_once(exporter, retention_days=7)

    exporter.compute_daily_snapshot.assert_called_once_with(oldest)
    exporter.purge_traces_before.assert_not_called()
