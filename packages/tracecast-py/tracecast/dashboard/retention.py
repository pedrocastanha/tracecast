import asyncio
import logging
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger("tracecast")


def run_maintenance_once(exporter, retention_days: int) -> None:
    now = datetime.now(timezone.utc)
    cutoff_day = (now - timedelta(days=retention_days)).date()

    oldest = exporter.oldest_trace_date()
    if oldest is None:
        return

    day = oldest
    while day < cutoff_day:
        try:
            exporter.compute_daily_snapshot(day)
        except Exception:
            _logger.exception("tracecast retention: failed to snapshot %s", day)
            return
        day += timedelta(days=1)

    cutoff_dt = datetime(cutoff_day.year, cutoff_day.month, cutoff_day.day, tzinfo=timezone.utc)
    try:
        deleted = exporter.purge_traces_before(cutoff_dt)
        if deleted:
            _logger.info("tracecast retention: purged %d traces before %s", deleted, cutoff_day)
    except Exception:
        _logger.exception("tracecast retention: failed to purge before %s", cutoff_day)


async def retention_loop(exporter, retention_days: int, interval_seconds: float = 24 * 3600) -> None:
    while True:
        try:
            await asyncio.to_thread(run_maintenance_once, exporter, retention_days)
        except Exception:
            _logger.exception("tracecast retention: loop iteration failed")
        await asyncio.sleep(interval_seconds)
