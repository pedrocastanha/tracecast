"""Server-side ingest buffer: bounded queue + optional JSONL spool + batch write.

Keeps HTTP handlers fast (enqueue only). A single worker drains to the store
exporter so Mongo sees controlled bulk writes instead of N concurrent clients.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .export_queue import (
    ExportWorker,
    approx_trace_bytes,
    default_export_queue_size,
    default_flush_at,
    default_flush_interval,
    default_max_batch_bytes,
)
from .export_stats import ExportStats

_logger = logging.getLogger("tracecast")

DEFAULT_INGEST_QUEUE = 500
DEFAULT_MAX_BODY_BYTES = 8_000_000  # 8 MB request body soft limit at handler


def default_ingest_queue_size() -> int:
    raw = os.environ.get("TRACECAST_INGEST_QUEUE")
    if raw is None or raw == "":
        return DEFAULT_INGEST_QUEUE
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_INGEST_QUEUE


def default_ingest_spool_path() -> Optional[str]:
    raw = os.environ.get("TRACECAST_INGEST_SPOOL")
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip()


class IngestService:
    """Accept trace dicts, queue them, batch-write via ``store_export_fn``."""

    def __init__(
        self,
        store_export_fn: Callable[[List[dict]], None],
        *,
        queue_size: Optional[int] = None,
        flush_at: Optional[int] = None,
        flush_interval: Optional[float] = None,
        max_batch_bytes: Optional[int] = None,
        spool_path: Optional[str] = None,
        spool_poll: float = 2.0,
    ):
        self.stats = ExportStats()
        self._accepted = 0
        self._dropped = 0
        self._spool_written = 0
        self._spool_drained = 0
        self._lock = threading.Lock()
        self._spool_path = spool_path if spool_path is not None else default_ingest_spool_path()
        self._spool_poll = spool_poll
        self._store_export_fn = store_export_fn

        size = queue_size if queue_size is not None else default_ingest_queue_size()
        self._worker = ExportWorker(
            self._write_batch,
            maxsize=size,
            flush_at=flush_at if flush_at is not None else default_flush_at(),
            flush_interval=flush_interval if flush_interval is not None else default_flush_interval(),
            max_batch_bytes=max_batch_bytes if max_batch_bytes is not None else default_max_batch_bytes(),
            name="tracecast-ingest",
            on_drop=self._on_mem_drop,
        )
        self._spool_stop = threading.Event()
        self._spool_thread: Optional[threading.Thread] = None
        if self._spool_path:
            Path(self._spool_path).parent.mkdir(parents=True, exist_ok=True)
            self._spool_thread = threading.Thread(
                target=self._spool_loop,
                name="tracecast-spool",
                daemon=True,
            )
            self._spool_thread.start()

    def _on_mem_drop(self, _item: Any) -> None:
        # ExportWorker already dropped from memory; we may have recovered via spool in accept().
        pass

    def _write_batch(self, items: List[Any]) -> None:
        docs = [i if isinstance(i, dict) else i for i in items]
        docs = [d for d in docs if isinstance(d, dict)]
        if not docs:
            return
        try:
            self._store_export_fn(docs)
            with self._lock:
                self.stats.incr("exported_ok", len(docs))
        except Exception as exc:
            with self._lock:
                self.stats.incr("export_failed", len(docs))
                self.stats.set_last_error(str(exc)[:500])
            _logger.warning("TraceCast ingest: store write failed (%d docs): %s", len(docs), exc)
            # Best-effort: re-spool so we don't lose under transient Mongo blips.
            if self._spool_path:
                for d in docs:
                    self._append_spool(d)

    def _append_spool(self, doc: dict) -> bool:
        if not self._spool_path:
            return False
        try:
            line = json.dumps(doc, default=str, ensure_ascii=False)
            with open(self._spool_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            with self._lock:
                self._spool_written += 1
            return True
        except Exception as exc:
            _logger.warning("TraceCast ingest: spool write failed: %s", exc)
            return False

    def _spool_loop(self) -> None:
        while not self._spool_stop.wait(self._spool_poll):
            self._drain_spool_once()

    def _drain_spool_once(self) -> None:
        path = self._spool_path
        if not path or not os.path.exists(path):
            return
        try:
            size = os.path.getsize(path)
            if size == 0:
                return
        except OSError:
            return

        # Room in memory queue?
        free = self._worker.maxsize - self._worker.qsize()
        if free < 1:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as exc:
            _logger.warning("TraceCast ingest: spool read failed: %s", exc)
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
            if self._worker.enqueue(doc):
                moved += 1
                with self._lock:
                    self._spool_drained += 1
            else:
                kept.append(line if line.endswith("\n") else line + "\n")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(kept)
        except OSError as exc:
            _logger.warning("TraceCast ingest: spool rewrite failed: %s", exc)

    def accept(self, docs: List[dict]) -> Dict[str, int]:
        """Enqueue docs. Returns counters: accepted, dropped, spooled."""
        accepted = 0
        dropped = 0
        spooled = 0
        for doc in docs:
            if not isinstance(doc, dict):
                dropped += 1
                continue
            if not doc.get("trace_id"):
                dropped += 1
                continue
            if self._worker.enqueue(doc):
                accepted += 1
                continue
            # Memory full → spool or drop
            if self._append_spool(doc):
                accepted += 1
                spooled += 1
            else:
                dropped += 1
        with self._lock:
            self._accepted += accepted
            self._dropped += dropped
        return {"accepted": accepted, "dropped": dropped, "spooled": spooled}

    def accept_one(self, doc: dict) -> Dict[str, int]:
        return self.accept([doc])

    def flush(self, timeout: Optional[float] = None) -> bool:
        self._drain_spool_once()
        return self._worker.flush(timeout=timeout)

    def shutdown(self, timeout: float = 10.0) -> None:
        self._spool_stop.set()
        if self._spool_thread is not None:
            self._spool_thread.join(timeout=min(2.0, timeout))
        self._drain_spool_once()
        self._worker.shutdown(timeout=timeout)

    def health(self) -> dict:
        with self._lock:
            snap = {
                "enabled": True,
                "queue_size": self._worker.qsize(),
                "queue_max": self._worker.maxsize,
                "accepted": self._accepted,
                "dropped": self._dropped,
                "spool_written": self._spool_written,
                "spool_drained": self._spool_drained,
                "spool_path": self._spool_path,
                "last_error": self.stats.snapshot().get("last_error"),
                "last_error_at": self.stats.snapshot().get("last_error_at"),
                "exported_ok": self.stats.snapshot().get("exported_ok", 0),
                "export_failed": self.stats.snapshot().get("export_failed", 0),
            }
        if self._spool_path and os.path.exists(self._spool_path):
            try:
                snap["spool_bytes"] = os.path.getsize(self._spool_path)
            except OSError:
                snap["spool_bytes"] = None
        else:
            snap["spool_bytes"] = 0
        return snap


def normalize_ingest_body(body: Any) -> List[dict]:
    """Normalize POST body into a list of trace dicts."""
    if body is None:
        return []
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return []
    if "traces" in body and isinstance(body["traces"], list):
        return [x for x in body["traces"] if isinstance(x, dict)]
    if "trace" in body and isinstance(body["trace"], dict):
        return [body["trace"]]
    # bare trace dict
    if body.get("trace_id") or body.get("spans") is not None:
        return [body]
    return []
