from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ExportStats:
    __slots__ = (
        "_lock",
        "exported_ok",
        "export_failed",
        "export_retried",
        "summary_fallback",
        "queue_dropped",
        "last_error",
        "last_error_at",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.exported_ok = 0
        self.export_failed = 0
        self.export_retried = 0
        self.summary_fallback = 0
        self.queue_dropped = 0
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[str] = None

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            if not hasattr(self, name):
                raise AttributeError(f"unknown counter: {name}")
            setattr(self, name, getattr(self, name) + n)

    def set_last_error(self, msg: str) -> None:
        with self._lock:
            self.last_error = msg
            self.last_error_at = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "exported_ok": self.exported_ok,
                "export_failed": self.export_failed,
                "export_retried": self.export_retried,
                "summary_fallback": self.summary_fallback,
                "queue_dropped": self.queue_dropped,
                "last_error": self.last_error,
                "last_error_at": self.last_error_at,
            }
