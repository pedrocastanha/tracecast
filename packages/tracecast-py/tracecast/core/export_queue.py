from __future__ import annotations

import atexit
import logging
import os
import queue
import threading
import time
from typing import Any, Callable, List, Optional

_logger = logging.getLogger("tracecast")

DEFAULT_EXPORT_QUEUE_SIZE = 100
DEFAULT_FLUSH_AT = 10
DEFAULT_FLUSH_INTERVAL = 1.0
DEFAULT_MAX_BATCH_BYTES = 2_000_000

_SENTINEL = object()


def default_export_queue_size() -> int:
    raw = os.environ.get("TRACECAST_EXPORT_QUEUE")
    if raw is None or raw == "":
        return DEFAULT_EXPORT_QUEUE_SIZE
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_EXPORT_QUEUE_SIZE


def default_flush_at() -> int:
    raw = os.environ.get("TRACECAST_FLUSH_AT")
    if raw is None or raw == "":
        return DEFAULT_FLUSH_AT
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_FLUSH_AT


def default_flush_interval() -> float:
    raw = os.environ.get("TRACECAST_FLUSH_INTERVAL")
    if raw is None or raw == "":
        return DEFAULT_FLUSH_INTERVAL
    try:
        return max(0.05, float(raw))
    except ValueError:
        return DEFAULT_FLUSH_INTERVAL


def default_max_batch_bytes() -> int:
    raw = os.environ.get("TRACECAST_MAX_BATCH_BYTES")
    if raw is None or raw == "":
        return DEFAULT_MAX_BATCH_BYTES
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_BATCH_BYTES


def approx_trace_bytes(item: Any) -> int:
    if isinstance(item, dict):
        n = 512
        for span in item.get("spans") or []:
            if not isinstance(span, dict):
                n += 256
                continue
            n += 256
            inp = span.get("input")
            out = span.get("output")
            if isinstance(inp, str):
                n += len(inp)
            if isinstance(out, str):
                n += len(out)
        return n
    spans = getattr(item, "spans", None) or []
    n = 512
    for span in spans:
        n += 256
        inp = getattr(span, "input", None)
        out = getattr(span, "output", None)
        if isinstance(inp, str):
            n += len(inp)
        if isinstance(out, str):
            n += len(out)
    return n


class _FlushMarker:
    __slots__ = ("event",)

    def __init__(self) -> None:
        self.event = threading.Event()


class ExportWorker:
    def __init__(
        self,
        export_batch_fn: Callable[[List[Any]], None],
        maxsize: int = DEFAULT_EXPORT_QUEUE_SIZE,
        flush_at: int = DEFAULT_FLUSH_AT,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        max_batch_bytes: int = DEFAULT_MAX_BATCH_BYTES,
        name: str = "tracecast-export",
        on_drop: Optional[Callable[[Any], None]] = None,
    ):
        if maxsize < 1:
            raise ValueError("export queue maxsize must be >= 1")
        if flush_at < 1:
            raise ValueError("flush_at must be >= 1")
        self._export_batch_fn = export_batch_fn
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self._maxsize = maxsize
        self._flush_at = flush_at
        self._flush_interval = flush_interval
        self._max_batch_bytes = max_batch_bytes
        self._on_drop = on_drop
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._started = False
        self._start_lock = threading.Lock()
        self._dropped = 0
        self._last_drop_log = 0.0
        self._atexit_registered = False

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def dropped(self) -> int:
        return self._dropped

    def qsize(self) -> int:
        return self._q.qsize()

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._thread.start()
            self._started = True
            if not self._atexit_registered:
                atexit.register(self.shutdown)
                self._atexit_registered = True

    def enqueue(self, item: Any) -> bool:
        self.start()
        try:
            self._q.put_nowait(item)
            return True
        except queue.Full:
            self._dropped += 1
            self._log_drop(item)
            if self._on_drop is not None:
                try:
                    self._on_drop(item)
                except Exception:
                    pass
            return False

    def flush(self, timeout: Optional[float] = None) -> bool:
        if not self._started:
            return True
        marker = _FlushMarker()
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
            try:
                self._q.put(marker, timeout=remaining)
                break
            except queue.Full:
                if deadline is not None and time.monotonic() >= deadline:
                    return False
                time.sleep(0.01)
        wait_timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
        return marker.event.wait(timeout=wait_timeout)

    def shutdown(self, timeout: float = 10.0) -> None:
        if not self._started:
            return
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                self._q.put(_SENTINEL, timeout=min(0.5, remaining))
                break
            except queue.Full:
                time.sleep(0.01)
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _log_drop(self, item: Any) -> None:
        now = time.monotonic()
        if now - self._last_drop_log < 5.0:
            return
        self._last_drop_log = now
        if isinstance(item, dict):
            trace_id = item.get("trace_id", "?")
        else:
            trace_id = getattr(item, "trace_id", "?")
        _logger.warning(
            "TraceCast: export queue full (maxsize=%d); dropped trace %s "
            "(total_dropped=%d). Raise TRACECAST_EXPORT_QUEUE or reduce payload size.",
            self._maxsize,
            trace_id,
            self._dropped,
        )

    def _emit(self, batch: List[Any]) -> None:
        if not batch:
            return
        try:
            self._export_batch_fn(batch)
        except Exception:
            _logger.exception("TraceCast: unexpected error in export worker")

    def _run(self) -> None:
        while True:
            batch: List[Any] = []
            batch_bytes = 0
            flush_markers: List[_FlushMarker] = []
            stop = False

            try:
                first = self._q.get(block=True, timeout=self._flush_interval)
            except queue.Empty:
                continue

            items_taken = 1
            if first is _SENTINEL:
                stop = True
            elif isinstance(first, _FlushMarker):
                flush_markers.append(first)
            else:
                batch.append(first)
                batch_bytes += approx_trace_bytes(first)

            while (
                not stop
                and len(flush_markers) == 0
                and len(batch) < self._flush_at
                and (self._max_batch_bytes <= 0 or batch_bytes < self._max_batch_bytes)
            ):
                try:
                    item = self._q.get(block=True, timeout=0.05)
                except queue.Empty:
                    break
                items_taken += 1
                if item is _SENTINEL:
                    stop = True
                    break
                if isinstance(item, _FlushMarker):
                    flush_markers.append(item)
                    break
                batch.append(item)
                batch_bytes += approx_trace_bytes(item)

            try:
                self._emit(batch)
                for marker in flush_markers:
                    marker.event.set()
            finally:
                for _ in range(items_taken):
                    try:
                        self._q.task_done()
                    except ValueError:
                        break

            if stop:
                while True:
                    try:
                        leftover = self._q.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        if leftover is _SENTINEL:
                            continue
                        if isinstance(leftover, _FlushMarker):
                            leftover.event.set()
                            continue
                        self._emit([leftover])
                    finally:
                        try:
                            self._q.task_done()
                        except ValueError:
                            pass
                return
