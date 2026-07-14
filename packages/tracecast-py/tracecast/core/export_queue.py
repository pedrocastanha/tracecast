from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
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


def default_export_spool_path() -> Optional[str]:
    raw = os.environ.get("TRACECAST_EXPORT_SPOOL")
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip()


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


def item_to_doc(item: Any) -> Any:
    """Normalize Trace → dict on the worker thread. Pass through other types."""
    if isinstance(item, dict):
        return item
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return item


class _FlushMarker:
    __slots__ = ("event",)

    def __init__(self) -> None:
        self.event = threading.Event()


def default_overflow_queue_size(main_maxsize: int) -> int:
    """Secondary buffer for disk-spool handoff — still bounded, never blocks request path."""
    raw = os.environ.get("TRACECAST_EXPORT_OVERFLOW")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    # At least as large as main queue (and ≥256) so brief export stalls
    # hand off to spool thread without dropping; hard cap for RAM.
    return max(1, min(5000, max(main_maxsize, 256)))


class ExportWorker:
    """Bounded export buffer with **hard latency guarantee on request path**.

    Request / ASGI path does **only** ``queue.put_nowait``:
      1) main export queue
      2) if full and spool enabled → overflow queue (still put_nowait)
      3) if overflow full → drop counter (never block the user message)

    Serialize, disk spool I/O, HTTP/Mongo all run on daemon worker threads.
    """

    def __init__(
        self,
        export_batch_fn: Callable[[List[Any]], None],
        maxsize: int = DEFAULT_EXPORT_QUEUE_SIZE,
        flush_at: int = DEFAULT_FLUSH_AT,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        max_batch_bytes: int = DEFAULT_MAX_BATCH_BYTES,
        name: str = "tracecast-export",
        on_drop: Optional[Callable[[Any], None]] = None,
        spool_path: Optional[str] = None,
        spool_poll: float = 1.0,
        overflow_maxsize: Optional[int] = None,
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
        self._spooled = 0
        self._spool_drained = 0
        self._last_drop_log = 0.0
        self._atexit_registered = False
        self._spool_path = spool_path if spool_path is not None else default_export_spool_path()
        self._spool_poll = max(0.2, float(spool_poll))
        self._spool_stop = threading.Event()
        self._spool_thread: Optional[threading.Thread] = None
        # Overflow: hold Trace refs briefly until spool thread writes JSONL.
        # Never serialize/disk on the calling (request) thread.
        osize = (
            overflow_maxsize
            if overflow_maxsize is not None
            else default_overflow_queue_size(maxsize)
        )
        self._overflow: Optional[queue.Queue] = (
            queue.Queue(maxsize=max(1, osize)) if self._spool_path else None
        )
        if self._spool_path:
            Path(self._spool_path).parent.mkdir(parents=True, exist_ok=True)

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def spooled(self) -> int:
        return self._spooled

    def qsize(self) -> int:
        return self._q.qsize()

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._thread.start()
            self._started = True
            if self._spool_path and self._spool_thread is None:
                self._spool_thread = threading.Thread(
                    target=self._spool_loop,
                    name=f"{self._thread.name}-spool",
                    daemon=True,
                )
                self._spool_thread.start()
            if not self._atexit_registered:
                atexit.register(self.shutdown)
                self._atexit_registered = True

    def enqueue(self, item: Any) -> bool:
        """Non-blocking. Never waits on disk, network, or locks held by exporters.

        Latency budget on caller: a few microseconds for put_nowait.
        """
        self.start()
        try:
            self._q.put_nowait(item)
            return True
        except queue.Full:
            pass
        # Main full → overflow handoff for async spool (still non-blocking).
        if self._overflow is not None:
            try:
                self._overflow.put_nowait(item)
                self._spooled += 1
                return True
            except queue.Full:
                pass
        self._dropped += 1
        self._log_drop(item)
        if self._on_drop is not None:
            try:
                self._on_drop(item)
            except Exception:
                pass
        return False

    def _append_spool(self, item: Any) -> bool:
        """Disk write — **worker thread only**, never request path."""
        if not self._spool_path:
            return False
        try:
            doc = item_to_doc(item)
            line = json.dumps(doc, default=str, ensure_ascii=False)
            with open(self._spool_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True
        except Exception as exc:
            _logger.warning("TraceCast: export spool write failed: %s", exc)
            return False

    def _flush_overflow_to_spool(self) -> None:
        if self._overflow is None:
            return
        while True:
            try:
                item = self._overflow.get_nowait()
            except queue.Empty:
                break
            if not self._append_spool(item):
                # Last resort: try main queue again; else count drop.
                try:
                    self._q.put_nowait(item)
                except queue.Full:
                    self._dropped += 1
                    self._log_drop(item)

    def _spool_loop(self) -> None:
        while not self._spool_stop.wait(self._spool_poll):
            self._flush_overflow_to_spool()
            self._drain_spool_once()

    def _drain_spool_once(self) -> None:
        path = self._spool_path
        if not path or not os.path.exists(path):
            return
        try:
            if os.path.getsize(path) == 0:
                return
        except OSError:
            return
        free = self._maxsize - self._q.qsize()
        if free < 1:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as exc:
            _logger.warning("TraceCast: export spool read failed: %s", exc)
            return
        kept: List[str] = []
        moved = 0
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            if moved >= free:
                kept.append(line if line.endswith("\n") else line + "\n")
                continue
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError:
                continue
            try:
                self._q.put_nowait(doc)
                moved += 1
                self._spool_drained += 1
            except queue.Full:
                kept.append(line if line.endswith("\n") else line + "\n")
                # leave remaining lines as-is after this one
                idx = lines.index(line)
                for ln in lines[idx + 1 :]:
                    if ln.strip():
                        kept.append(ln if ln.endswith("\n") else ln + "\n")
                break
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(kept)
        except OSError as exc:
            _logger.warning("TraceCast: export spool rewrite failed: %s", exc)

    def flush(self, timeout: Optional[float] = None) -> bool:
        if not self._started:
            return True
        self._flush_overflow_to_spool()
        self._drain_spool_once()
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
        self._spool_stop.set()
        if self._spool_thread is not None:
            self._spool_thread.join(timeout=min(2.0, timeout))
        self._flush_overflow_to_spool()
        self._drain_spool_once()
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
            "(total_dropped=%d). Set TRACECAST_EXPORT_SPOOL or raise TRACECAST_EXPORT_QUEUE.",
            self._maxsize,
            trace_id,
            self._dropped,
        )

    def _emit(self, batch: List[Any]) -> None:
        if not batch:
            return
        try:
            # Normalize Trace → dict on the worker thread (not request path).
            docs = [item_to_doc(x) for x in batch]
            self._export_batch_fn(docs)
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
