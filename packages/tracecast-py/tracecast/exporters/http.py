"""HTTP exporter — push traces to a TraceCast ingest endpoint.

Designed for fire-and-forget clients: pair with ``background_export=True`` so the
request path only enqueues; this class does the short network hop on the worker.
Uses stdlib ``urllib`` only (no extra deps on bot hosts).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..models.trace import Trace
from .base import BaseExporter

_logger = logging.getLogger("tracecast")

DEFAULT_TIMEOUT = 2.0
DEFAULT_MAX_RETRIES = 0  # Tracer already retries; exporter stays simple


def _default_timeout() -> float:
    raw = os.environ.get("TRACECAST_HTTP_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_TIMEOUT
    try:
        return max(0.1, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT


class HttpExporter(BaseExporter):
    """POST traces to ``{base_url}/api/ingest`` or ``/api/ingest/batch``."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: Optional[float] = None,
        auth: Optional[tuple] = None,
        headers: Optional[Dict[str, str]] = None,
        path_prefix: str = "",
    ):
        url = (base_url or "").strip().rstrip("/")
        if not url:
            raise ValueError("HttpExporter base_url is required")
        # Allow either full prefix (…/tracecast) or host root.
        self.base_url = url
        self.timeout = timeout if timeout is not None else _default_timeout()
        self._auth = auth
        self._headers = dict(headers or {})
        if path_prefix:
            self._prefix = path_prefix.rstrip("/")
        else:
            self._prefix = ""

    def _endpoint(self, path: str) -> str:
        # path like /api/ingest/batch
        if self.base_url.endswith("/tracecast") or self.base_url.rstrip("/").endswith(
            self._prefix
        ) if self._prefix else False:
            return f"{self.base_url}{path}"
        if self._prefix:
            return f"{self.base_url}{self._prefix}{path}"
        return f"{self.base_url}{path}"

    def _post(self, path: str, body: Any) -> dict:
        url = self._endpoint(path)
        data = json.dumps(body, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._headers,
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        if self._auth:
            import base64

            token = base64.b64encode(
                f"{self._auth[0]}:{self._auth[1]}".encode("utf-8")
            ).decode("ascii")
            req.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {"status": resp.status}
                try:
                    return json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    return {"status": resp.status, "raw": raw.decode("utf-8", errors="replace")}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HttpExporter HTTP {e.code} {url}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"HttpExporter network error {url}: {e.reason}") from e
        except TimeoutError as e:
            raise RuntimeError(f"HttpExporter timeout {url} after {self.timeout}s") from e

    def export(self, trace: Trace) -> None:
        self.export_doc(trace.to_dict())

    def export_doc(self, doc: dict) -> None:
        result = self._post("/api/ingest", {"trace": doc})
        if isinstance(result, dict) and result.get("dropped", 0) > 0:
            raise RuntimeError(f"HttpExporter server dropped trace: {result}")

    def export_docs_batch(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        if len(docs) == 1:
            self.export_doc(docs[0])
            return
        result = self._post("/api/ingest/batch", {"traces": docs})
        if isinstance(result, dict) and result.get("dropped", 0) > 0:
            # Partial drop still raises so retry/summary can react.
            raise RuntimeError(f"HttpExporter server dropped {result.get('dropped')} traces: {result}")

    def export_summary(self, summary: dict) -> None:
        # Summaries use same ingest path (same store on server).
        self.export_doc(summary)
